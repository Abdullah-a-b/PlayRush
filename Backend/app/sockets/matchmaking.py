import secrets
import string
import json
import asyncio
import time
from app.games.core_manager import (add_to_queue, remove_from_queue,
                                    check_queue_for_match, pair_is_valid,
                                    create_match_room)
from app.services.reward_service import get_clean_avatar
from app.sockets.auth_helper import verify_socket_token


# ============================================================
# 🕸️ المسار العنقودي (المرحلة ب-2): طابور مطابقة عالمي على Redis
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
    from app.core.redis_client import redis_enabled, redis_available, get_redis
    if not redis_enabled():
        return None
    if not await redis_available():
        return None
    return get_redis()


async def _cluster_try_match(sio, r, game_mode):
    """يحاول مطابقة زوج صالح من الطابور العالمي (تحت قفل قصير)."""
    from app.core import cluster
    got_lock = await r.set(_MMQ_LOCK + game_mode, cluster.WORKER_ID, nx=True, ex=3)
    if not got_lock:
        return
    try:
        raw = await r.lrange(_MMQ + game_mode, 0, -1)
        entries = []
        for item in raw:
            try:
                e = json.loads(item)
            except Exception:
                await r.lrem(_MMQ + game_mode, 1, item)
                continue
            # 🧹 مدخل ميت (اتصاله انتهى)؟ ننظفه
            if not await r.get('pr:conn:' + e.get('sid', '')):
                await r.lrem(_MMQ + game_mode, 1, item)
                await r.delete(_MMQ_SID + e.get('sid', ''))
                if e.get('user_id'):
                    await r.delete(_MMQ_UID + str(e['user_id']))
                continue
            entries.append((item, e))

        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                p1_item, p1 = entries[i]
                p2_item, p2 = entries[j]
                # فحوصات الصلاحية نفسها (نفس المستخدم/IP/تقابل حديث/حظر/صداقة)
                if not await asyncio.to_thread(pair_is_valid, p1, p2):
                    continue
                # ✂️ نخرجهما ذرّياً — لو أحدهما أُخرج قبلنا نتراجع
                if await r.lrem(_MMQ + game_mode, 1, p1_item) == 0:
                    break  # p1 اختفى — أعد من طابور محدث بالدورة القادمة
                if await r.lrem(_MMQ + game_mode, 1, p2_item) == 0:
                    await r.rpush(_MMQ + game_mode, p1_item)  # نرجع p1
                    continue
                for e in (p1, p2):
                    await r.delete(_MMQ_SID + e['sid'])
                    if e.get('user_id'):
                        await r.delete(_MMQ_UID + str(e['user_id']))

                # 🏠 الغرفة تُنشأ هنا — هذا الـ worker مالكها
                room_code, matched, rp_data = await asyncio.to_thread(
                    create_match_room, p1, p2, game_mode)
                await cluster.claim_room(room_code)
                players_list = list(rp_data.values())
                for p in matched:
                    role = 'host' if p['sid'] == matched[0]['sid'] else 'guest'
                    await sio.emit('match_found',
                                   {'room_code': room_code, 'role': role,
                                    'players': players_list}, to=p['sid'])
                print(f"🕸️ [matchmaking] تطابق عنقودي {room_code} "
                      f"(مالكها worker {cluster.WORKER_ID})")
                return
    finally:
        try:
            await r.delete(_MMQ_LOCK + game_mode)
        except Exception:
            pass


async def _cluster_join_queue(sio, sid, entry, game_mode):
    """إدخال للطابور العالمي + محاولة مطابقة فورية."""
    r = await _redis_mm()
    # ⛔ حمايات التكرار (عبر كل الـ workers)
    if not await r.set(_MMQ_SID + sid, '1', nx=True, ex=120):
        # نفس الـsid يبحث مرتين بسرعة — نسمح (تحديث) بدل الرفض القاسي
        await r.set(_MMQ_SID + sid, '1', ex=120)
    if entry.get('user_id'):
        uid_key = _MMQ_UID + str(entry['user_id'])
        if not await r.set(uid_key, sid, nx=True, ex=120):
            # القفل محجوز — نتحقق: هل صاحبه (sid قديم) ما زال حياً؟
            holder = await r.get(uid_key)
            holder = holder.decode() if isinstance(holder, bytes) else holder
            holder_alive = holder and await r.get('pr:conn:' + holder)
            if holder_alive and holder != sid:
                # جلسة حيّة فعلاً من جهاز/تبويب آخر → نرفض
                await r.delete(_MMQ_SID + sid)
                return False, "أنت بالفعل في البحث من جهاز آخر!"
            # القفل عالق من جلسة ميتة → نحرّره ونأخذه (تنظيف ذاتي)
            await r.set(uid_key, sid, ex=120)
    await r.rpush(_MMQ + game_mode, json.dumps(entry, ensure_ascii=False))
    await _cluster_try_match(sio, r, game_mode)
    # لو القفل كان محجوزاً لحظتها — محاولة مؤجلة قصيرة تضمن عدم التعليق
    async def _retry():
        await asyncio.sleep(0.7)
        rr = await _redis_mm()
        if rr is not None:
            await _cluster_try_match(sio, rr, game_mode)
    asyncio.get_event_loop().create_task(_retry())
    return True, "تم الانضمام لطابور البحث"


async def _cluster_leave_queue(sid):
    r = await _redis_mm()
    if r is None:
        return False
    removed = False
    try:
        for key in await r.keys(_MMQ + '*'):
            for item in await r.lrange(key, 0, -1):
                try:
                    e = json.loads(item)
                except Exception:
                    continue
                if e.get('sid') == sid:
                    await r.lrem(key, 1, item)
                    if e.get('user_id'):
                        await r.delete(_MMQ_UID + str(e['user_id']))
                    removed = True
        await r.delete(_MMQ_SID + sid)
    except Exception as ex:
        print(f"⚠️ [matchmaking] إلغاء عنقودي: {ex}")
    return removed


def register_matchmaking_events(sio):

    @sio.on('quick_play_search')
    async def quick_play_search(sid, data):
        # 🛡️ التحقق من هوية اللاعب قبل إدخاله الطابور
        token = data.get('token')
        user, db = verify_socket_token(token)
        if not user:
            print(f"❌ [matchmaking] توكن غير صالح لـ sid={sid}")
            await sio.emit('quick_play_error', {'msg': 'يجب تسجيل الدخول أولاً'}, to=sid)
            return

        game_mode = data.get('game_mode')
        # ✅ نقرأ كل بيانات المستخدم قبل إغلاق الـ db
        player_name = user.player_name or 'لاعب'
        avatar = get_clean_avatar(user.avatar, player_name)
        user_id = user.id
        db.close()

        # 🛡️ نجلب الـ IP الخاص بالـ sid (لمنع اللعب ضد نفس المنطقة)
        from app.sockets.state import sid_ip_map
        client_ip = sid_ip_map.get(sid)

        # 🚪 فحص حظر الانسحاب المتكرر قبل دخول الطابور
        from app.services.leaver_penalty import get_leaver_ban
        leaver_ban = get_leaver_ban(user_id)
        if leaver_ban:
            print(f"🔎 [matchmaking] ⛔ uid={user_id} محظور (انسحاب متكرر): {leaver_ban['msg']}")
            await sio.emit('quick_play_error', {'msg': leaver_ban['msg']}, to=sid)
            return

        success, msg = add_to_queue(sid, player_name, avatar, game_mode,
                                     token=token, user_id=user_id, ip=client_ip)
        print(f"🔎 [matchmaking] uid={user_id} دخل الطابور؟ {success} | {msg}")

        # 🕸️ المسار العنقودي: مع Redis نستخدم الطابور العالمي بدل المحلي
        r = await _redis_mm()
        if r is not None:
            # add_to_queue أعلاه تحقق من صحة الوضع؛ نُخرجه من المحلي
            if success:
                remove_from_queue(sid)
            elif "غير مدعوم" in (msg or ""):
                await sio.emit('quick_play_error', {'msg': msg}, to=sid)
                return
            entry = {'sid': sid, 'name': player_name, 'avatar': avatar,
                     'token': token, 'user_id': user_id, 'ip': client_ip,
                     'time': time.time()}
            ok, cmsg = await _cluster_join_queue(sio, sid, entry, game_mode)
            if not ok:
                await sio.emit('quick_play_error', {'msg': cmsg}, to=sid)
            return

        if not success:
            print(f"❌ [matchmaking] رُفض الدخول: {msg}")
            await sio.emit('quick_play_error', {'msg': msg}, to=sid)
            return

        match_found, room_code, matched_players, rp_data = check_queue_for_match(game_mode)
        from app.games.core_manager import matchmaking_queue
        qsize = len(matchmaking_queue.get(game_mode, []))

        if match_found:
            # 🏠 هذا الـ worker أنشأ الغرفة — نسجّله مالكاً (no-op بلا Redis)
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
