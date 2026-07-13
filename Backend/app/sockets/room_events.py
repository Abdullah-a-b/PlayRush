import secrets
import string
import asyncio
from app.sockets.state import connected_players, disconnect_timers
from app.games.core_manager import create_room, join_room, get_room_state
from app.services.reward_service import get_player_full_stats, get_clean_avatar
from app.sockets.auth_helper import verify_socket_token


def register_room_events(sio):

    @sio.on('create_room')
    async def handle_create_room(sid, data):
        token = data.get('token')

        # 🛡️ إنشاء غرفة خاصة يتطلب توكن صالح
        user, db = verify_socket_token(token)
        if not user:
            await sio.emit('error_message', 'يجب تسجيل الدخول لإنشاء غرفة خاصة', to=sid)
            return
        host_name = user.player_name or 'لاعب'
        avatar = get_clean_avatar(user.avatar, host_name)
        db.close()

        game_mode = data.get('game_mode')

        # 🛡️ room_code بـ secrets بدل random — يمنع تخمين كود الغرفة الخاصة
        alphabet = string.ascii_uppercase + string.digits
        room_code = ''.join(secrets.choice(alphabet) for _ in range(6))

        room = create_room(room_code, sid, host_name, 2, game_mode, "0.0.0.0", avatar, "private")
        # 🕸️ هذا الـ worker مالك الغرفة الخاصة
        from app.core import cluster
        await cluster.claim_room(room_code)
        await sio.emit('room_created', {'room_code': room_code, 'players': room['players']}, to=sid)

    @sio.on('join_room')
    async def handle_join_room(sid, data):
        room_code = data.get('room_code')
        token = data.get('token')

        # 🛡️ نجلب الاسم والأفاتار من DB إن وُجد التوكن — يمنع انتحال الهوية
        user, db = verify_socket_token(token)
        joining_user_id = None
        if user:
            player_name = user.player_name or 'مجهول'
            avatar = get_clean_avatar(user.avatar, player_name)
            joining_user_id = user.id
            db.close()
        else:
            player_name = str(data.get('player_name', 'مجهول'))[:30]
            avatar = get_clean_avatar(data.get('avatar', ''), player_name)

        success, msg = join_room(room_code, sid, player_name, avatar, user_id=joining_user_id)
        print(f"🔌 [join_room] sid={sid} uid={joining_user_id} name={player_name!r} room={room_code} → success={success} msg={msg!r}")
        if not success:
            await sio.emit('error_message', msg, to=sid)
            return

        # 🔧 نخزّن user_id مباشرة على اللاعب (مصدر حقيقة ثابت لا يتأثر بتغيّر sid)
        room_obj = get_room_state(room_code)
        if room_obj and joining_user_id:
            for p in room_obj['players']:
                if p['sid'] == sid:
                    p['user_id'] = joining_user_id

        # 🔧 مزامنة شاملة: نربط sids المحرك بلاعبي الغرفة الحاليين عبر
        # user_id (مصدر الحقيقة الثابت). يعالج جذر KeyError/فشل الدور:
        # حالة اللعبة تُنشأ بـsids الطابور، ثم اللاعبون ينضمون بـsids
        # مختلفة — بلا هذه المزامنة يبقى p1/p2/turn على sids قديمة.
        if room_obj and room_obj.get('game_state'):
            gs = room_obj['game_state']
            if hasattr(gs, 'remap_sid'):
                # نبني خريطة uid → sid الحالي من لاعبي الغرفة
                uid_to_sid = {p.get('user_id'): p.get('sid')
                              for p in room_obj['players'] if p.get('user_id')}
                # p1/p2 بالمحرك: نطابقهما بترتيب اللاعبين عبر user_id
                players = room_obj['players']
                for slot in ('p1', 'p2'):
                    cur = getattr(gs, slot, None)
                    if cur is None:
                        continue
                    # اللاعب صاحب هذا الـslot: نجده بالـsid القديم أو الترتيب
                    match_p = next((p for p in players if p.get('sid') == cur), None)
                    if match_p is None:
                        # الـsid تغيّر — نطابق بالترتيب (p1=players[0], p2=players[1])
                        idx = 0 if slot == 'p1' else 1
                        if idx < len(players):
                            new_sid = players[idx].get('sid')
                            if new_sid and new_sid != cur:
                                gs.remap_sid(cur, new_sid)

        # 🔧 (احتياط) reconnect صريح بـold_sid
        if msg == "reconnected":
            if room_obj and room_obj.get('game_state'):
                gs = room_obj['game_state']
                for p in room_obj['players']:
                    if p['sid'] == sid and p.get('old_sid') and p['old_sid'] != sid:
                        old = p['old_sid']
                        if hasattr(gs, 'remap_sid'):
                            gs.remap_sid(old, sid)
                        if getattr(gs, 'p1', None) == old: gs.p1 = sid
                        if getattr(gs, 'p2', None) == old: gs.p2 = sid
                        if getattr(gs, 'turn', None) == old: gs.turn = sid
                        if getattr(gs, 'buzzed_player', None) == old: gs.buzzed_player = sid

        await sio.enter_room(sid, room_code)

        room = get_room_state(room_code)

        # نضع علامة أن هذا اللاعب انضم فعلاً لغرفة socket.io
        for p in room['players']:
            if p.get('sid') == sid:
                p['_socket_joined'] = True
                break

        game_mode = room.get('game_mode', 'huroof')
        # 🤝 نميّز مباراة الصديق (الودية) في الحالة المعروضة
        _loc = f'playing_{game_mode}'
        if room.get('type') == 'friendly':
            _loc += '_friendly'
        # نحافظ على user_id الموجود (لا نفقده عند تحديث الحالة)
        _existing_uid = connected_players.get(sid, {}).get('user_id')
        connected_players[sid] = {
            'name': player_name,
            'avatar': avatar,
            'location': _loc,
            'token': token,
            'user_id': _existing_uid,
        }

        # 🔄 نبثّ delta صغيراً (ليظهر "يخوض معركة" لحظياً بلا تحديث الصفحة)
        try:
            from app.sockets.lobby import presence_delta
            await presence_delta(sio, sid, 'update')
        except Exception:
            pass

        safe_room = {k: v for k, v in room.items() if k != 'game_state'}
        fetch_tasks = []

        for p in safe_room['players']:
            if p.get('sid') == sid and token:
                p['token'] = token
            p_token = p.get('token') or (
                connected_players.get(p['sid'], {}).get('token') if p.get('sid') else None
            )
            fetch_tasks.append(get_player_full_stats(p_token, p['name'], p.get('avatar', '')))

        stats_results = await asyncio.gather(*fetch_tasks)
        for i, p in enumerate(safe_room['players']):
            p['stats'] = stats_results[i]
            if p['stats']:
                p['avatar'] = p['stats']['avatar']

        # 🔒 نزيل الحقول الداخلية قبل الإرسال للعميل (user_id, old_sid)
        safe_room['players'] = [
            {k: v for k, v in p.items() if k not in ('user_id', 'old_sid', 'token')}
            for p in safe_room['players']
        ]

        # 👥 نحسب علاقة هذا اللاعب بخصمه (لإظهار زر الصداقة/الحظر الصحيح)
        # نقرأ user_id من كائن اللاعب مباشرةً (أوثق من user_ids map الذي قد يتأخّر بناؤه)
        me_player  = next((p for p in room['players'] if p.get('sid') == sid), None)
        opp_player = next((p for p in room['players'] if p.get('sid') != sid), None)
        my_uid  = (me_player or {}).get('user_id') or (room.get('user_ids') or {}).get(sid)
        opp_uid = (opp_player or {}).get('user_id')
        relation = 'none'
        if my_uid and opp_uid:
            from app.services.friends import (are_friends, is_blocked_between,
                                              i_blocked_them, get_pending_requests)
            if is_blocked_between(my_uid, opp_uid):
                relation = 'i_blocked' if i_blocked_them(my_uid, opp_uid) else 'they_blocked'
            elif are_friends(my_uid, opp_uid):
                relation = 'friends'
            else:
                # هل يوجد طلب معلّق؟ ومن أرسله؟
                incoming = [r.get('id') for r in get_pending_requests(my_uid)]  # من أرسلوا لي
                if opp_uid in incoming:
                    relation = 'pending_incoming'   # الخصم أرسل لي → أقدر أقبل
                else:
                    outgoing = [r.get('id') for r in get_pending_requests(opp_uid)]  # من أرسلوا للخصم
                    if my_uid in outgoing:
                        relation = 'pending_outgoing'  # أنا أرسلت له → في انتظار الرد
        safe_room['opponent_relation'] = relation
        safe_room['opponent_user_id'] = opp_uid  # لقبول الطلب الوارد داخل المباراة
        # 🔑 sid هذا اللاعب صراحةً — الجذر الأمتن: الواجهة تعرف sid الخادم
        # الخاص بها يقيناً بدل تخمينه من socket.id أو مطابقة الاسم (كانت
        # تفشل لو اختلف الاسم بين DB والواجهة → المشكلة الأزلية).
        safe_room['your_sid'] = sid

        await sio.emit('room_joined', safe_room, to=sid)
        await sio.emit('update_players_stats', safe_room['players'], room=room_code)
        await sio.emit('player_joined', {'player': player_name}, room=room_code)

        # 🎮 بدء المباراة تلقائياً عند انضمام الطرفين فعلياً لغرفة socket.io
        gs_check = room.get('game_state')
        all_connected = all(p.get('_socket_joined') for p in room['players'])
        both_present = len(room['players']) >= 2 and all_connected
        print(f"🔎 [join_room] room={room_code} game_mode={room.get('game_mode')} "
              f"players={[{'sid': p.get('sid'), 'uid': p.get('user_id'), 'name': p.get('name'), 'joined': p.get('_socket_joined')} for p in room['players']]} "
              f"state={room['state']} both_present={both_present} has_gs={gs_check is not None}")
        if both_present and room['state'] == 'starting' and gs_check:
            room['state'] = 'playing'
            # 🔧 نضمن أن p1/p2/turn تشير للـ sids الحالية (لا القديمة من اللوبي)
            # نربط حسب اللون: green=host=p1, orange=guest=p2
            green_player = next((p for p in room['players'] if p.get('color') == 'green'), None)
            orange_player = next((p for p in room['players'] if p.get('color') == 'orange'), None)
            if green_player and orange_player:
                old_p1, old_p2 = gs_check.p1, gs_check.p2
                sids_changed = (old_p1 != green_player['sid'] or old_p2 != orange_player['sid'])

                # huroof يستخدم turn؛ ألعاب أخرى قد لا تملكه
                turn_was_green = getattr(gs_check, 'turn', old_p1) == old_p1
                gs_check.p1 = green_player['sid']
                gs_check.p2 = orange_player['sid']
                if hasattr(gs_check, 'turn'):
                    gs_check.turn = gs_check.p1 if turn_was_green else gs_check.p2

                # 🔧 نعيد بناء مفاتيح النقاط/السترايك فقط لو الـ sids تغيّرت (انتقال لوبي→لعبة)
                # لو لم تتغيّر (اتصال مباشر) نبقيها كما هي لتجنّب مسح بيانات جارية
                if sids_changed:
                    if hasattr(gs_check, 'scores'):
                        gs_check.scores = {gs_check.p1: 0, gs_check.p2: 0}
                    if hasattr(gs_check, 'strikes'):
                        gs_check.strikes = {gs_check.p1: 0, gs_check.p2: 0}
                    if hasattr(gs_check, 'helps_used'):
                        gs_check.helps_used = {gs_check.p1: set(), gs_check.p2: set()}
                    # 🔧 [knowledge] points + total_strikes مفهرسة بالsid —
                    # يجب إعادة بنائها كذلك وإلا KeyError يوقف close_round
                    if hasattr(gs_check, 'points'):
                        gs_check.points = {gs_check.p1: 0, gs_check.p2: 0}
                    if hasattr(gs_check, 'total_strikes'):
                        gs_check.total_strikes = {gs_check.p1: 0, gs_check.p2: 0}
                    # 🔧 نستدعي _sync_keys كشبكة أمان إضافية لو كانت اللعبة تملكها
                    if hasattr(gs_check, '_sync_keys'):
                        gs_check._sync_keys()

                # 🔧 نبني user_ids من user_id المخزّن على كل لاعب (ثابت)
                new_uids = {}
                for p in room['players']:
                    if p.get('user_id') is not None:
                        new_uids[p['sid']] = p['user_id']
                if new_uids:
                    room['user_ids'] = new_uids

            game_mode = room.get('game_mode', 'huroof')
            if game_mode == 'huroof':
                await sio.emit('huroof_board_init', {'board': gs_check.board}, room=room_code)
                await sio.emit('huroof_turn_changed', {
                    'turn_sid': gs_check.turn,
                    'turn_color': ('green' if gs_check.turn == gs_check.p1 else 'orange')
                }, room=room_code)
            elif game_mode == 'career':
                # ⚽ مسيرة لاعب: نُعلم الطرفين أن اللعبة جاهزة، ثم نبدأها
                # gs_check.stage == 'waiting' يضمن أننا لا نبدأ مرتين
                if gs_check.stage == 'waiting':
                    print(f"⚽ [career] بدء المباراة | room={room_code} | players={len(room['players'])}")
                    await sio.emit('career_ready', {'roomCode': room_code}, room=room_code)
                    try:
                        from app.games.career.events import trigger_career_start
                        await trigger_career_start(sio, room_code)
                        print(f"⚽ [career] trigger_career_start اكتمل | room={room_code}")
                    except Exception as _e:
                        print(f"❌ [career] خطأ بدء: {_e}")
                        import traceback; traceback.print_exc()
                else:
                    print(f"⚽ [career] تجاهل trigger مكرر | room={room_code} | stage={gs_check.stage}")

            elif game_mode == 'knowledge':
                # 🧠 ماذا تعرف: نُعلم الطرفين ثم نبدأ أول سؤال
                gs_check = room.get('game_state')
                if gs_check and getattr(gs_check, 'stage', '') == 'waiting':
                    await sio.emit('knowledge_ready', {'roomCode': room_code}, room=room_code)
                    try:
                        from app.games.knowledge.events import trigger_knowledge_start
                        await trigger_knowledge_start(sio, room_code)
                    except Exception as _e:
                        print(f"❌ [knowledge] خطأ بدء: {_e}")
                        import traceback; traceback.print_exc()

            elif game_mode == 'bank':
                # 🏦 البنك: نُعلم الطرفين ثم نبدأ أول دور
                if gs_check.stage == 'waiting':
                    print(f"🏦 [bank] بدء المباراة | room={room_code}")
                    await sio.emit('bank_ready', {'roomCode': room_code}, room=room_code)
                    try:
                        from app.games.bank.events import trigger_bank_start
                        await trigger_bank_start(sio, room_code)
                    except Exception as _e:
                        print(f"❌ [bank] خطأ بدء: {_e}")
                        import traceback; traceback.print_exc()

        if msg in ["reconnected", "reconnected_ready"]:
            if room_code in disconnect_timers:
                disconnect_timers[room_code].cancel()
                del disconnect_timers[room_code]
                await sio.emit('opponent_reconnected', {'msg': 'عاد الخصم للعب!'}, room=room_code)

            gs = room.get('game_state')
            reconnect_game_mode = room.get('game_mode', 'huroof')

            if reconnect_game_mode == 'huroof' and gs and hasattr(gs, 'board'):
                # 🔁 إعادة إرسال حالة حروف للاعب العائد
                await sio.emit('huroof_board_init', {'board': gs.board}, to=sid)
                if room['state'] == 'playing':
                    await sio.emit('huroof_turn_changed', {
                        'turn_sid': gs.turn,
                        'turn_color': ('green' if gs.turn == gs.p1 else 'orange')
                    }, room=room_code)
                    if gs.stage != 'selecting' and gs.current_question and gs.active_hex:
                        await sio.emit('huroof_hex_locked', {
                            'hexIndex': gs.active_hex['index'],
                            'letter': gs.active_hex['letter']
                        }, to=sid)
                        await sio.emit('huroof_new_question', {
                            'questionData': gs.current_question,
                            'round': 'r1',
                            'timer': 40
                        }, to=sid)

            elif reconnect_game_mode == 'career' and gs:
                # 🔁 إعادة إرسال حالة مسيرة لاعب للاعب العائد
                if room['state'] == 'playing' and gs.stage != 'waiting':
                    try:
                        from app.games.career.events import send_career_reconnect_state
                        await send_career_reconnect_state(sio, room_code, sid)
                    except Exception as _re:
                        print(f"⚠️ [career] خطأ reconnect state: {_re}")

            elif reconnect_game_mode == 'bank' and gs:
                # 🔁 إعادة إرسال حالة البنك للاعب العائد
                if room['state'] == 'playing' and gs.stage != 'waiting':
                    try:
                        # 🔁 لو عاد بـsid جديد: نعيد ربط حالته أولاً
                        room_sids = {p['sid'] for p in room['players']}
                        for old in (gs.p1, gs.p2):
                            if old not in room_sids:
                                gs.remap_sid(old, sid)
                                break
                        ps = gs.pstate.get(sid, {})
                        await sio.emit('bank_state', {
                            'safe': gs.safe, 'temp': {sid: ps.get('temp', 0)},
                            'round': gs.round, 'totalRounds': gs.TOTAL_ROUNDS,
                            'stage': gs.stage,
                        }, to=sid)
                        q = ps.get('question')
                        if q and gs.stage == 'playing' and not ps.get('done'):
                            await sio.emit('bank_question', {
                                'id': q['id'], 'text': q['q'],
                                'category': q.get('cat', ''),
                                'remaining': round(gs.remaining(sid), 1),
                            }, to=sid)
                    except Exception as _re:
                        print(f"⚠️ [bank] خطأ reconnect state: {_re}")

    @sio.on('start_game')
    async def handle_start_game(sid, data):
        room_code = data.get('room_code')
        room = get_room_state(room_code)
        if room and room.get('host') == sid:
            room['state'] = 'starting'
            await sio.emit('game_started', {'roomCode': room_code}, room=room_code)