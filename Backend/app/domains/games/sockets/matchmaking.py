import secrets
import string
import json
import asyncio
import time
from app.domains.games.core_manager import (add_to_queue, remove_from_queue,
                                    check_queue_for_match, ranked_pairs, alternatives,
                                    create_match_room)
from app.domains.wallet.reward_service import get_clean_avatar
from app.sockets.auth_helper import verify_socket_token


# ============================================================
# المسار العنقودي (المرحلة ب-2): طابور مطابقة عالمي على Redis
# لاعبان على workers مختلفة يتطابقان. الغرفة تُنشأ على الـ worker
# الذي أجرى المطابقة (= مالكها)، وmatch_found يعبر للطرف الآخر
# عبر Redis manager. قفل قصير يمنع مطابقة مزدوجة متزامنة.
# بدون REDIS_URL: المسار المحلي القديم كما هو.
# ============================================================
_MMQ = 'pr:mmq:'
_MMQ_SID = 'pr:mmq_sid:'
_MMQ_UID = 'pr:mmq_uid:'
_MMQ_LOCK = 'pr:mmq_lock:'


async def _redis_mm():
    from app.infrastructure.redis_client import redis_enabled, redis_available, get_redis
    if not redis_enabled():
        return None
    if not await redis_available():
        return None
    return get_redis()


async def _cluster_try_match(sio, r, game_mode):
    """يحاول مطابقة زوج صالح من الطابور العالمي (تحت قفل قصير)."""
    from app.core import cluster
    lease = secrets.token_hex(16)
    got_lock = await r.set(_MMQ_LOCK + game_mode, lease, nx=True, ex=10)
    if not got_lock:
        return
    try:
        key = _MMQ + game_mode
        size = await r.llen(key)
        raw = await r.lrange(key, 0, 63)
        if size > 64:
            # Retain the oldest requests and rotate through the remainder.
            cursor = key + ":batch"
            page = (await r.incr(cursor) - 1) % ((size - 64 + 63) // 64)
            await r.expire(cursor, 120)
            start = 64 + page * 64
            raw.extend(await r.lrange(key, start, start + 63))
        entries = []
        for item in raw:
            try:
                e = json.loads(item)
            except Exception:
                await r.lrem(_MMQ + game_mode, 1, item)
                continue
            # مدخل ميت (اتصاله انتهى)؟ ننظفه
            if not await r.get('pr:conn:' + e.get('sid', '')):
                await r.lrem(_MMQ + game_mode, 1, item)
                await r.delete(_MMQ_SID + e.get('sid', ''))
                if e.get('user_id'):
                    await _release_uid(r,e)
                continue
            entries.append((item, e))

        choices = await asyncio.to_thread(ranked_pairs, [entry for _,entry in entries], game_mode)
        for i,j in choices:
            p1_item,p1 = entries[i]
            p2_item,p2 = entries[j]
            room_code = "".join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(6))
            active_keys = ["pr:mm_active:"+str(p["user_id"]) for p in (p1,p2)]
            reserved = await r.eval("""
                if redis.call('GET',KEYS[2]) ~= ARGV[1] then return 0 end
                if redis.call('GET',KEYS[3]) ~= ARGV[4] or redis.call('GET',KEYS[4]) ~= ARGV[5] then return 0 end
                if not redis.call('LPOS',KEYS[1],ARGV[2]) or not redis.call('LPOS',KEYS[1],ARGV[3]) then return 0 end
                if redis.call('EXISTS',KEYS[7],KEYS[8],KEYS[9])~=0 then return 0 end
                redis.call('SET',KEYS[7],ARGV[6],'EX',120);redis.call('SET',KEYS[8],ARGV[6],'EX',120)
                redis.call('SET',KEYS[9],ARGV[7],'EX',120)
                redis.call('LREM',KEYS[1],1,ARGV[2]);redis.call('LREM',KEYS[1],1,ARGV[3])
                redis.call('DEL',KEYS[3],KEYS[4],KEYS[5],KEYS[6])
                return 1
            """,9,_MMQ+game_mode,_MMQ_LOCK+game_mode,_MMQ_UID+str(p1['user_id']),_MMQ_UID+str(p2['user_id']),
                _MMQ_SID+p1['sid'],_MMQ_SID+p2['sid'],*active_keys,'pr:room_owner:'+room_code,lease,p1_item,p2_item,p1['sid'],p2['sid'],room_code,cluster.WORKER_ID)
            if not reserved:
                continue
            # الغرفة تُنشأ هنا — هذا الـ worker مالكها
            try:
                counts = alternatives(choices, i, j)
                p1["alternatives"], p2["alternatives"] = counts[i], counts[j]
                room_code, matched, rp_data = create_match_room(p1,p2,game_mode,room_code)
            except Exception:
                for key in active_keys:
                    await r.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) end",1,key,room_code)
                for player in (p1,p2):
                    await sio.emit('quick_play_error',{'msg':'تعذر إنشاء المباراة. أعد البحث.'},to=player['sid'])
                raise
            players_list = list(rp_data.values())
            for p in matched:
                role = 'host' if p['sid'] == matched[0]['sid'] else 'guest'
                await sio.emit('match_found',
                               {'room_code': room_code, 'role': role,
                                'players': players_list}, to=p['sid'])
            print(f" [matchmaking] تطابق عنقودي {room_code} "
                  f"(مالكها worker {cluster.WORKER_ID})")
            return
    finally:
        try:
            await r.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end return 0",1,_MMQ_LOCK+game_mode,lease)
        except Exception:
            pass


async def _cluster_join_queue(sio, sid, entry, game_mode):
    """إدخال للطابور العالمي + محاولة مطابقة فورية."""
    r = await _redis_mm()
    if r is None:
        return False, "البحث غير متاح مؤقتاً"
    inserted = await r.eval("""
        if redis.call('EXISTS',KEYS[2],KEYS[3],KEYS[4])~=0 then return 0 end
        redis.call('SET',KEYS[2],ARGV[1],'EX',120)
        redis.call('SET',KEYS[3],ARGV[1],'EX',120)
        redis.call('RPUSH',KEYS[1],ARGV[2])
        return 1
    """,4,_MMQ+game_mode,_MMQ_SID+sid,_MMQ_UID+str(entry['user_id']),"pr:mm_active:"+str(entry["user_id"]),sid,json.dumps(entry,ensure_ascii=False))
    if not inserted:
        return False, "أنت بالفعل في البحث"
    await search_started(sio, sid, entry["time"])
    await _cluster_try_match(sio, r, game_mode)
    return True, "تم الانضمام لطابور البحث"


async def _release_uid(r,entry):
    await r.eval("if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0",
                 1,_MMQ_UID+str(entry['user_id']),entry['sid'])


async def _cluster_leave_queue(sid):
    r = await _redis_mm()
    if r is None:
        return False
    removed = False
    try:
        from app.domains.games.core_manager import _get_valid_modes
        for mode in _get_valid_modes():
            key = _MMQ+mode
            for item in await r.lrange(key, 0, -1):
                try:
                    e = json.loads(item)
                except Exception:
                    continue
                if e.get('sid') == sid:
                    await r.lrem(key, 1, item)
                    if e.get('user_id'):
                        await _release_uid(r,e)
                    removed = True
        await r.delete(_MMQ_SID + sid)
    except Exception as ex:
        print(f" [matchmaking] إلغاء عنقودي: {ex}")
    return removed


async def search_started(sio, sid, queued_at):
    await sio.emit("quick_play_started", {"expires_at": queued_at + 30, "server_time": time.time()}, to=sid)


def register_matchmaking_events(sio):

    tasks = {}
    async def service(mode, clustered):
        from app.domains.games.core_manager import matchmaking_queue
        try:
            while True:
                if clustered:
                    r = await _redis_mm()
                    if r is None:
                        return
                    items = await r.lrange(_MMQ+mode,0,-1)
                    if not items:
                        return
                    for raw in items:
                        entry = json.loads(raw)
                        if time.time()-entry['time'] >= 30 and await r.lrem(_MMQ+mode,1,raw):
                            await r.eval("if redis.call('get',KEYS[1])==ARGV[1] then redis.call('del',KEYS[1],KEYS[2]) end",2,_MMQ_UID+str(entry['user_id']),_MMQ_SID+entry['sid'],entry['sid'])
                            await sio.emit('quick_play_error',{'code':'expired','msg':'انتهى البحث. يمكنك المحاولة مجدداً.'},to=entry['sid'])
                    await _cluster_try_match(sio,r,mode)
                else:
                    queue = matchmaking_queue.get(mode,[])
                    for entry in list(queue):
                        if time.time()-entry['time'] >= 30:
                            remove_from_queue(entry['sid'])
                            await sio.emit('quick_play_error',{'code':'expired','msg':'انتهى البحث. يمكنك المحاولة مجدداً.'},to=entry['sid'])
                    if not queue:
                        return
                    await local_match(mode)
                await asyncio.sleep(1)
        finally:
            tasks.pop(mode,None)

    def schedule(mode, clustered):
        if mode not in tasks:
            tasks[mode] = asyncio.create_task(service(mode,clustered))

    @sio.on('quick_play_search')
    async def quick_play_search(sid, data):
        # التحقق من هوية اللاعب قبل إدخاله الطابور
        token = data.get('token')
        user, db = verify_socket_token(token)
        if not user:
            print(f" [matchmaking] توكن غير صالح لـ sid={sid}")
            await sio.emit('quick_play_error', {'msg': 'يجب تسجيل الدخول أولاً'}, to=sid)
            return

        game_mode = data.get('game_mode')
        # نقرأ كل بيانات المستخدم قبل إغلاق الـ db
        player_name = user.player_name or 'لاعب'
        avatar = get_clean_avatar(user.avatar, player_name)
        user_id = user.id
        db.close()

        # نجلب الـ IP الخاص بالـ sid (لمنع اللعب ضد نفس المنطقة)
        from app.sockets.state import sid_ip_map
        client_ip = sid_ip_map.get(sid)

        # فحص حظر الانسحاب المتكرر قبل دخول الطابور
        from app.domains.games.leaver_penalty import get_leaver_ban
        leaver_ban = get_leaver_ban(user_id)
        if leaver_ban:
            print(f" [matchmaking]  uid={user_id} محظور (انسحاب متكرر): {leaver_ban['msg']}")
            await sio.emit('quick_play_error', {'msg': leaver_ban['msg']}, to=sid)
            return

        success, msg = add_to_queue(sid, player_name, avatar, game_mode,
                                     token=token, user_id=user_id, ip=client_ip)
        print(f" [matchmaking] uid={user_id} دخل الطابور؟ {success} | {msg}")

        # المسار العنقودي: مع Redis نستخدم الطابور العالمي بدل المحلي
        r = await _redis_mm()
        from app.infrastructure.redis_client import redis_enabled
        if r is None and redis_enabled():
            if success: remove_from_queue(sid)
            await sio.emit('quick_play_error',{'msg':'البحث غير متاح مؤقتاً'},to=sid)
            return
        if r is not None:
            # add_to_queue أعلاه تحقق من صحة الوضع؛ نُخرجه من المحلي
            if success:
                remove_from_queue(sid)
            else:
                await sio.emit('quick_play_error', {'msg': msg}, to=sid)
                return
            entry = {'sid': sid, 'name': player_name, 'avatar': avatar,
                     'token': token, 'user_id': user_id, 'ip': client_ip,
                     'time': time.time()}
            ok, cmsg = await _cluster_join_queue(sio, sid, entry, game_mode)
            if ok:
                schedule(game_mode,True)
            if not ok:
                await sio.emit('quick_play_error', {'msg': cmsg}, to=sid)
            return

        if not success:
            print(f" [matchmaking] رُفض الدخول: {msg}")
            await sio.emit('quick_play_error', {'msg': msg}, to=sid)
            return

        from app.domains.games.core_manager import matchmaking_queue
        entry = next((p for p in matchmaking_queue.get(game_mode, []) if p["sid"] == sid), None)
        if entry:
            await search_started(sio, sid, entry["time"])
        schedule(game_mode,False)
        await local_match(game_mode)

    async def local_match(game_mode):
        match_found, room_code, matched_players, rp_data = await check_queue_for_match(game_mode)

        if match_found:
            # هذا الـ worker أنشأ الغرفة — نسجّله مالكاً (no-op بلا Redis)
            from app.core import cluster
            await cluster.claim_room(room_code)
            players_list = list(rp_data.values())
            for p in matched_players:
                role = 'host' if p['sid'] == matched_players[0]['sid'] else 'guest'
                await sio.emit('match_found', {'room_code': room_code, 'role': role, 'players': players_list}, to=p['sid'])

    @sio.on('cancel_quick_play')
    async def cancel_quick_play(sid):
        removed = remove_from_queue(sid)
        if await _redis_mm() is not None:
            removed = (await _cluster_leave_queue(sid)) or removed
        if removed:
            await sio.emit('quick_play_cancelled', {}, to=sid)
