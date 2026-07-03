import re
import time
from app.sockets.state import connected_players, global_chat_history, game_lobby_players, game_chat_history
from app.services.reward_service import get_clean_avatar
from app.sockets.auth_helper import verify_socket_token


def _public_players():
    """قائمة المتصلين بدون حقول داخلية (user_id/token) — للبث العلني."""
    return [
        {k: v for k, v in p.items() if k not in ('user_id', 'token')}
        for p in connected_players.values()
    ]


async def return_players_to_lobby(sio, room):
    """
    يُستدعى بعد انتهاء معركة. مهمته:
    - تنظيف بيانات الـ avatar للاعبين (لو فيها قيم خبيثة)
    - لا يُحدّث location مسبقاً — اللاعب يحدّث location بنفسه عبر join_game_lobby
      عندما يصل فعلاً للوبي.
    """
    game_mode = room.get('game_mode', 'huroof')
    if game_mode not in game_lobby_players:
        game_lobby_players[game_mode] = {}

    for player in room.get('players', []):
        p_sid = player.get('sid')
        if not p_sid:
            continue
        p_name = player.get('name', 'لاعب')
        p_avatar = get_clean_avatar(player.get('avatar', ''), p_name)

        if p_sid in connected_players:
            connected_players[p_sid]['avatar'] = p_avatar

    await sio.emit('update_online_players', _public_players())


def _sanitize_chat_text(raw: str) -> str:
    """فلتر نص الشات: يقص ويمنع الرسائل الفارغة."""
    return str(raw).strip()[:200]


def register_lobby_events(sio):

    @sio.on('join_global_lobby')
    async def join_global_lobby(sid, data):
        # 🛡️ نحاول التحقق من التوكن إن وُجد — إن لم يكن موجوداً نقبل بالاسم كـ guest
        token = data.get('token')
        user, db = verify_socket_token(token)
        _uid = None
        if user:
            player_name = user.player_name or 'لاعب'
            avatar = get_clean_avatar(user.avatar, player_name)
            _uid = user.id
            db.close()
        else:
            player_name = str(data.get('name', 'لاعب'))[:30]
            avatar = get_clean_avatar(data.get('avatar', ''), player_name)

        # 🔧 نخزّن user_id + token (للإشعارات الحية + الكتم) — كان مفقوداً هنا
        connected_players[sid] = {
            'name': player_name, 'avatar': avatar, 'location': 'global',
            'user_id': _uid, 'token': token
        }
        await sio.emit('chat_history', global_chat_history, to=sid)
        await sio.emit('update_online_players', _public_players())

    @sio.on('join_game_lobby')
    async def join_game_lobby(sid, data):
        token = data.get('token')
        game_mode = data.get('gameMode')

        # 🛡️ اللوبي يتطلب توكن صالح
        user, db = verify_socket_token(token)
        _uid = None
        if user:
            player_name = user.player_name or 'لاعب'
            avatar = get_clean_avatar(user.avatar, player_name)
            _uid = user.id   # نحفظ user_id للكتم والبلاغات
            db.close()
        else:
            # نقبل guest بدون توكن لكن بدون وصول للطابور
            player_name = str(data.get('name', 'لاعب'))[:30]
            avatar = get_clean_avatar(data.get('avatar', ''), player_name)

        if game_mode not in game_lobby_players:
            game_lobby_players[game_mode] = {}
        if game_mode not in game_chat_history:
            game_chat_history[game_mode] = []

        game_lobby_players[game_mode][sid] = {'name': player_name, 'avatar': avatar}
        connected_players[sid] = {
            'name': player_name,
            'avatar': avatar,
            'location': game_mode,
            'token': token,  # نحتفظ بالتوكن للاستخدام الداخلي فقط (لا يُبث للعلن)
            'user_id': _uid
        }

        await sio.emit('update_online_players', _public_players())
        await sio.emit('game_chat_history', game_chat_history[game_mode], to=sid)

        players_list = list(game_lobby_players[game_mode].values())
        for p_sid in list(game_lobby_players[game_mode].keys()):
            await sio.emit('update_game_lobby_players', players_list, to=p_sid)

    # ==========================================
    # 💬 رسائل الشات
    # ==========================================
    @sio.on('get_player_profile')
    async def get_player_profile(sid, data):
        """يجلب بروفايل لاعب + إحصائياته + علاقتي به (لفتحه من الإشعارات).
        data: { token, target_id, game_mode? }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        my_id = user.id
        db.close()

        target_id = (data or {}).get('target_id')
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            target_id = None
        if not target_id:
            await sio.emit('player_profile_result', {'ok': False, 'msg': 'معرّف غير صالح'}, to=sid)
            return

        game_mode = (data or {}).get('game_mode') or None

        from app.services.reward_service import fetch_stats_by_user_id
        import asyncio as _asyncio
        stats = await _asyncio.to_thread(fetch_stats_by_user_id, target_id, game_mode)

        # العلاقة الحالية (لإظهار زر الصداقة/الحظر الصحيح)
        relation = 'none'
        if target_id == my_id:
            relation = 'self'
        else:
            from app.services.friends import (are_friends, is_blocked_between,
                                              i_blocked_them, get_pending_requests)
            if is_blocked_between(my_id, target_id):
                relation = 'i_blocked' if i_blocked_them(my_id, target_id) else 'they_blocked'
            elif are_friends(my_id, target_id):
                relation = 'friends'
            else:
                incoming = [r.get('id') for r in get_pending_requests(my_id)]
                if target_id in incoming:
                    relation = 'pending_incoming'
                else:
                    outgoing = [r.get('id') for r in get_pending_requests(target_id)]
                    if my_id in outgoing:
                        relation = 'pending_outgoing'

        await sio.emit('player_profile_result', {
            'ok': True, 'target_id': target_id,
            'stats': stats, 'relation': relation
        }, to=sid)

    @sio.on('get_quick_chat_catalog')
    async def get_quick_chat_catalog_handler(sid, data=None):
        """يُرسل قائمة العبارات الجاهزة للعميل (الأساسية + المشتراة)."""
        from app.core.quick_chat import get_catalog_for_user
        context = (data or {}).get('context', 'lobby') if isinstance(data, dict) else 'lobby'
        game = (data or {}).get('game') if isinstance(data, dict) else None
        # نجلب العبارات المشتراة للاعب (إن وُجد)
        owned_phrases = []
        try:
            uid = connected_players.get(sid, {}).get('user_id')
            if uid:
                from app.services.cosmetics import get_owned_cosmetics
                owned_phrases = get_owned_cosmetics(uid)
        except Exception:
            owned_phrases = []
        catalog = get_catalog_for_user(context, owned_phrases, game)
        await sio.emit('quick_chat_catalog', catalog, to=sid)

    @sio.on('send_chat_message')
    async def send_chat_message(sid, data):
        """💬 رسالة جاهزة عامة (Quick Chat). العميل يرسل معرّف عبارة فقط —
        لا نص حر. الخادم يحوّل المعرّف لنصّه المعتمد. (الدردشة الحرة مؤجّلة)."""
        from app.core.anticheat import (
            check_action_rate, check_payload_safety,
            report_violation, is_temp_banned, Severity
        )

        if is_temp_banned(sid):
            return

        payload_issue = check_payload_safety(data, max_string_len=50)
        if payload_issue:
            await report_violation(sid, sio, f"chat:{payload_issue}", severity=Severity.HIGH)
            return

        # حد المعدّل (ضد السبام بالعبارات)
        rate_issue = check_action_rate(sid, 'chat_message', max_per_second=2)
        if rate_issue:
            await report_violation(sid, sio, f"chat_spam:{rate_issue}", severity=Severity.MEDIUM)
            return

        if sid not in connected_players:
            return

        # 🛡️ فحص الكتم (من نظام البلاغات) — يبقى ساري حتى مع العبارات الجاهزة
        _uid = connected_players[sid].get('user_id')
        if _uid:
            from app.services.player_reports import is_chat_muted
            if is_chat_muted(_uid):
                await sio.emit('chat_error', {'msg': 'أنت مكتوم من الشات بسبب بلاغات'}, to=sid)
                return

        # 🔒 نقطة الأمان: نقبل معرّف عبارة فقط، ونحوّله لنصّه المعتمد من الخادم.
        from app.core.quick_chat import resolve_phrase, resolve_emoji
        phrase_id = data.get('phraseId') if isinstance(data, dict) else None
        text = resolve_phrase(phrase_id)
        if text is None:
            # معرّف غير صالح — محاولة تلاعب محتملة
            await report_violation(sid, sio, "chat:invalid_phrase_id", severity=Severity.MEDIUM)
            return
        emoji_id = resolve_emoji(phrase_id)

        # الاسم من server state لا من الـ data — يمنع انتحال الهوية
        sender_name = connected_players[sid].get('name', 'لاعب')
        sender_uid = connected_players[sid].get('user_id')
        msg = {'sender': sender_name, 'text': text, 'isSystem': False, 'id': f"{sid}-{int(time.time()*1000)}", 'sender_id': sender_uid, 'emojiId': emoji_id}
        global_chat_history.append(msg)
        if len(global_chat_history) > 50:
            global_chat_history.pop(0)
        await sio.emit('new_chat_message', msg)
        return

    @sio.on('send_game_chat_message')
    async def send_game_chat_message(sid, data):
        """💬 رسالة جاهزة داخل لوبي اللعبة. معرّف عبارة فقط — لا نص حر."""
        from app.core.anticheat import (
            check_action_rate, check_payload_safety,
            report_violation, is_temp_banned, Severity
        )

        if is_temp_banned(sid):
            return

        payload_issue = check_payload_safety(data, max_string_len=50)
        if payload_issue:
            await report_violation(sid, sio, f"game_chat:{payload_issue}", severity=Severity.HIGH)
            return

        rate_issue = check_action_rate(sid, 'game_chat_message', max_per_second=2)
        if rate_issue:
            await report_violation(sid, sio, f"game_chat_spam:{rate_issue}", severity=Severity.MEDIUM)
            return

        if sid not in connected_players:
            return

        game_mode = data.get('gameMode') if isinstance(data, dict) else None
        if not game_mode:
            return

        # 🛡️ فحص الكتم
        _uid = connected_players[sid].get('user_id')
        if _uid:
            from app.services.player_reports import is_chat_muted
            if is_chat_muted(_uid):
                await sio.emit('chat_error', {'msg': 'أنت مكتوم من الشات بسبب بلاغات'}, to=sid)
                return

        # 🛡️ نتحقق أن اللاعب فعلاً في لوبي هذا الـ game_mode
        if game_mode not in game_lobby_players or sid not in game_lobby_players[game_mode]:
            return

        # 🔒 معرّف عبارة فقط → نص معتمد من الخادم
        from app.core.quick_chat import resolve_phrase, resolve_emoji
        phrase_id = data.get('phraseId')
        text = resolve_phrase(phrase_id)
        if text is None:
            await report_violation(sid, sio, "game_chat:invalid_phrase_id", severity=Severity.MEDIUM)
            return
        emoji_id = resolve_emoji(phrase_id)

        sender_name = connected_players[sid].get('name', 'لاعب')
        sender_uid = connected_players[sid].get('user_id')
        msg = {'sender': sender_name, 'text': text, 'isSystem': False, 'sender_id': sender_uid, 'emojiId': emoji_id}

        if game_mode not in game_chat_history:
            game_chat_history[game_mode] = []
        game_chat_history[game_mode].append(msg)
        if len(game_chat_history[game_mode]) > 50:
            game_chat_history[game_mode].pop(0)

        for p_sid in list(game_lobby_players[game_mode].keys()):
            await sio.emit('new_game_chat_message', msg, to=p_sid)

    @sio.on('send_room_chat_message')
    async def send_room_chat_message(sid, data):
        """💬 رسالة جاهزة داخل غرفة مباراة (Quick Chat). معرّف عبارة فقط — لا نص حر.
        تُبثّ لكل من في الغرفة عبر Socket.IO room."""
        from app.core.anticheat import (
            check_action_rate, check_payload_safety,
            report_violation, is_temp_banned, Severity
        )

        if is_temp_banned(sid):
            return

        payload_issue = check_payload_safety(data, max_string_len=50)
        if payload_issue:
            await report_violation(sid, sio, f"room_chat:{payload_issue}", severity=Severity.HIGH)
            return

        rate_issue = check_action_rate(sid, 'room_chat_message', max_per_second=2)
        if rate_issue:
            await report_violation(sid, sio, f"room_chat_spam:{rate_issue}", severity=Severity.MEDIUM)
            return

        if sid not in connected_players:
            return

        room_code = data.get('roomCode') if isinstance(data, dict) else None
        if not room_code:
            return

        # 🛡️ فحص الكتم (من نظام البلاغات)
        _uid = connected_players[sid].get('user_id')
        if _uid:
            from app.services.player_reports import is_chat_muted
            if is_chat_muted(_uid):
                await sio.emit('chat_error', {'msg': 'أنت مكتوم من الشات بسبب بلاغات'}, to=sid)
                return

        # 🛡️ نتحقق أن اللاعب فعلاً عضو في هذه الغرفة
        from app.games.core_manager import rooms
        room = rooms.get(room_code)
        if not room or not any(p.get('sid') == sid for p in room.get('players', [])):
            return

        # 🔒 معرّف عبارة فقط → نص معتمد من الخادم
        from app.core.quick_chat import resolve_phrase
        text = resolve_phrase(data.get('phraseId'))
        if text is None:
            await report_violation(sid, sio, "room_chat:invalid_phrase_id", severity=Severity.MEDIUM)
            return

        sender_name = connected_players[sid].get('name', 'لاعب')
        msg = {'sender': sender_name, 'text': text, 'senderSid': sid, 'isSystem': False}
        await sio.emit('new_room_chat_message', msg, room=room_code)

    @sio.on('update_player_info')
    async def update_player_info(sid, data):
        if sid not in connected_players:
            return

        # 🛡️ نحاول التحقق من التوكن — إن صالح نجلب الاسم من DB
        token = connected_players[sid].get('token')
        user, db = verify_socket_token(token)
        if user:
            player_data = connected_players[sid]
            player_data['name'] = user.player_name or player_data['name']
            player_data['avatar'] = get_clean_avatar(user.avatar, player_data['name'])
            connected_players[sid] = player_data
            db.close()
        else:
            # guest: نقبل التحديث لكن بعد تنظيف
            player_data = connected_players[sid]
            player_data['avatar'] = get_clean_avatar(data.get('avatar', ''), player_data['name'])
            connected_players[sid] = player_data

        await sio.emit('update_online_players', _public_players())

    # ==========================================
    # 🛡️ Anti-Cheat: حظر فوري عبر السوكيت
    # ==========================================
    @sio.on('severe_security_breach')
    async def handle_security_breach(sid, data):
        from app.core.database import SessionLocal
        from app.models.user import User

        # 🛡️ نتحقق من التوكن بدل الاسم — يمنع حظر لاعب آخر بمعرفة اسمه فقط
        token = connected_players.get(sid, {}).get('token')
        if not token:
            return

        user, db = verify_socket_token(token)
        if not user:
            return

        reason = (data or {}).get('reason', 'unknown')
        print(f"🚨 [security] breach by {user.player_name} | sid={sid} | reason={reason}")

        try:
            if not getattr(user, 'is_banned', False):
                user.is_banned = True
                db.commit()
                print(f"🚫 [security] تم حظر {user.player_name} في قاعدة البيانات")
        finally:
            db.close()

        try:
            await sio.emit('force_logout', {'message': 'تم حظر حسابك نهائياً.'}, to=sid)
            await sio.disconnect(sid)
        except Exception:
            pass

    # ==========================================
    # 🔔 أحداث الإشعارات (صندوق الإشعارات في اللوبي/Categories)
    # ==========================================
    @sio.on('fetch_notifications')
    async def fetch_notifications(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()

        from app.services.notifications import get_notifications, get_unread_count
        notifs = get_notifications(uid)
        unread = get_unread_count(uid)
        await sio.emit('notifications_list', {'items': notifs, 'unread': unread}, to=sid)

    @sio.on('mark_notifications_read')
    async def mark_notifications_read(sid, data):
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()

        from app.services.notifications import mark_all_read
        mark_all_read(uid)
        await sio.emit('notifications_marked_read', {}, to=sid)

    # ==========================================
    # 👥 أحداث قسم الأصدقاء (اللوبي + categories)
    # ==========================================
    @sio.on('fetch_friends_data')
    async def fetch_friends_data(sid, data):
        """يجلب: قائمة الأصدقاء + الطلبات الواردة المعلّقة."""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()

        from app.services.friends import get_friends, get_pending_requests
        friends = get_friends(uid)
        pending = get_pending_requests(uid)
        await sio.emit('friends_data', {
            'friends': friends,
            'pending': pending,
            'pending_count': len(pending),
        }, to=sid)

    @sio.on('respond_friend_request')
    async def respond_friend_request_event(sid, data):
        """قبول/رفض طلب صداقة. data: { token, requester_id, accept }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        responder_name = user.player_name
        db.close()

        requester_id = (data or {}).get('requester_id')
        try:
            requester_id = int(requester_id)
        except (TypeError, ValueError):
            requester_id = None
        accept = bool((data or {}).get('accept'))
        if not requester_id:
            return

        from app.services.friends import respond_friend_request
        result = respond_friend_request(uid, requester_id, accept)
        await sio.emit('friend_response_result', result, to=sid)

        # لو قُبل، نُشعر صاحب الطلب (لو متصل)
        if result.get('ok') and accept:
            from app.services.notifications import add_notification, find_online_sid
            notif = add_notification(requester_id, 'friend_accepted',
                                     f'قبل {responder_name} طلب صداقتك', sender_id=uid)
            online_sid = find_online_sid(requester_id)
            if online_sid and notif:
                await sio.emit('new_notification', notif, to=online_sid)
                # 🆕 تحديث زر الطالب داخل المباراة (لو كان يلعب ضد هذا الخصم)
                await sio.emit('opponent_accepted_friend', {}, to=online_sid)

    @sio.on('remove_friend')
    async def remove_friend_event(sid, data):
        """حذف صديق. data: { token, friend_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()

        friend_id = (data or {}).get('friend_id')
        if not friend_id:
            return
        from app.services.friends import unblock_user  # نعيد استخدام الحذف
        # حذف الصداقة (نحذف العلاقة المقبولة)
        from app.core.database import engine
        from sqlalchemy import text
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    DELETE FROM friendships
                    WHERE status = 'accepted'
                      AND ((user_id = :a AND friend_id = :b) OR (user_id = :b AND friend_id = :a))
                """), {"a": uid, "b": friend_id})
                conn.commit()
        except Exception:
            pass
        await sio.emit('friend_removed', {'friend_id': friend_id}, to=sid)

    # ----------------------------------------
    # 🔎 البحث عن لاعب بالمعرّف (ID) لإضافته صديقاً
    # ----------------------------------------
    @sio.on('search_player_by_id')
    async def search_player_by_id(sid, data):
        """يبحث عن لاعب بـ player_id (مثل PR-12345). data: { token, player_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        try:
            me_id = user.id
            query_pid = ((data or {}).get('player_id') or '').strip().upper()
            if not query_pid:
                await sio.emit('search_player_result', {'ok': False, 'msg': 'أدخل معرّفاً صحيحاً'}, to=sid)
                return

            from app.core.database import User
            target = db.query(User).filter(User.player_id == query_pid).first()
            if not target:
                await sio.emit('search_player_result', {'ok': False, 'msg': 'لم يُعثر على لاعب بهذا المعرّف'}, to=sid)
                return

            # نحدّد العلاقة الحالية
            if target.id == me_id:
                relation = 'self'
            else:
                from app.services.friends import (are_friends, get_pending_requests,
                                                   is_blocked_between, i_blocked_them)
                if is_blocked_between(me_id, target.id):
                    # محظور: نفرّق بين "أنا حظرته" (أقدر أرفع) و"هو حظرني" (لا أقدر)
                    relation = 'i_blocked' if i_blocked_them(me_id, target.id) else 'they_blocked'
                elif are_friends(me_id, target.id):
                    relation = 'friends'
                else:
                    # هل يوجد طلب معلّق بأي اتجاه؟
                    pending_ids = [r.get('id') for r in get_pending_requests(me_id)]
                    pending_ids += [r.get('id') for r in get_pending_requests(target.id)]
                    relation = 'pending' if target.id in pending_ids or me_id in pending_ids else 'none'

            await sio.emit('search_player_result', {'ok': True, 'player': {
                'id': target.id, 'player_id': target.player_id,
                'name': target.player_name, 'avatar': target.avatar,
                'relation': relation,
            }}, to=sid)
        finally:
            db.close()

    @sio.on('send_friend_request_by_id')
    async def send_friend_request_by_id(sid, data):
        """يرسل طلب صداقة للاعب وُجد عبر البحث. data: { token, friend_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        uname = user.player_name
        db.close()

        friend_id = (data or {}).get('friend_id')
        try:
            friend_id = int(friend_id)
        except (TypeError, ValueError):
            friend_id = None
        print(f"🔎 [add-by-id] uid={uid} friend_id={friend_id} (type={type(friend_id).__name__})")
        if not friend_id:
            print("🔎 [add-by-id] ❌ friend_id فارغ")
            return

        from app.services.friends import send_friend_request, is_blocked_between
        if is_blocked_between(uid, friend_id):
            print("🔎 [add-by-id] ❌ يوجد حظر")
            await sio.emit('friend_result', {'ok': False, 'msg': 'تعذّر إرسال الطلب'}, to=sid)
            return
        result = send_friend_request(uid, friend_id)
        print(f"🔎 [add-by-id] نتيجة send_friend_request: {result}")
        await sio.emit('friend_result', result, to=sid)
        # نُشعر الطرف الآخر لو متصل
        if result.get('ok'):
            from app.services.notifications import add_notification, find_online_sid
            notif = add_notification(friend_id, 'friend_request', f'أرسل لك {uname} طلب صداقة', sender_id=uid)
            online_sid = find_online_sid(friend_id)
            print(f"🔎 [add-by-id] إشعار={bool(notif)} | online_sid للطرف الآخر={online_sid}")
            if online_sid and notif:
                await sio.emit('new_notification', notif, to=online_sid)
                print("🔎 [add-by-id] ✅ أُرسل الإشعار الحي للطرف الآخر")

    @sio.on('unblock_player_by_id')
    async def unblock_player_by_id(sid, data):
        """يرفع الحظر عن لاعب (أنا من حظرته). data: { token, target_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()

        target_id = (data or {}).get('target_id')
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            target_id = None
        if not target_id:
            return

        from app.services.friends import unblock_user
        result = unblock_user(uid, target_id)
        await sio.emit('unblock_result', result, to=sid)

    @sio.on('remove_friend_by_id')
    async def remove_friend_by_id(sid, data):
        """حذف صديق عبر معرّفه (من بروفايل الإشعارات). data: { token, friend_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()
        friend_id = (data or {}).get('friend_id')
        try:
            friend_id = int(friend_id)
        except (TypeError, ValueError):
            return
        from app.core.database import engine
        from sqlalchemy import text
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    DELETE FROM friendships
                    WHERE status = 'accepted'
                      AND ((user_id = :a AND friend_id = :b) OR (user_id = :b AND friend_id = :a))
                """), {"a": uid, "b": friend_id})
                conn.commit()
            await sio.emit('friend_result', {'ok': True, 'msg': 'تم حذف الصديق'}, to=sid)
            await sio.emit('friend_removed', {'friend_id': friend_id}, to=sid)
        except Exception:
            await sio.emit('friend_result', {'ok': False, 'msg': 'تعذّر الحذف'}, to=sid)

    @sio.on('block_player_by_id')
    async def block_player_by_id(sid, data):
        """حظر لاعب عبر معرّفه. data: { token, target_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        db.close()
        target_id = (data or {}).get('target_id')
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        from app.services.friends import block_user
        result = block_user(uid, target_id)
        await sio.emit('block_result', result, to=sid)
        if result.get('ok'):
            await sio.emit('friend_removed', {'friend_id': target_id}, to=sid)

    @sio.on('report_player_by_id')
    async def report_player_by_id(sid, data):
        """بلاغ عن لاعب عبر معرّفه. data: { token, target_id }"""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        reporter_id = user.id
        db.close()
        target_id = (data or {}).get('target_id')
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return
        try:
            from app.services.player_reports import submit_report
            submit_report(reporter_id, target_id, reason='toxic_chat', game_mode=None)
        except Exception:
            pass
        await sio.emit('report_result', {'ok': True, 'msg': 'تم إرسال البلاغ'}, to=sid)

    @sio.on('invite_friend_to_play')
    async def invite_friend_to_play(sid, data):
        """يدعو صديقاً متصلاً للعب. data: { token, friend_id, gameMode }
        لا نص حر — مجرد دعوة بمعرّفات. الخادم يتحقق من الصداقة والاتصال."""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        inviter_name = user.player_name
        db.close()

        friend_id = (data or {}).get('friend_id')
        game_mode = (data or {}).get('gameMode')
        if not friend_id or not game_mode:
            return

        # 🛡️ نتأكد أنهما صديقان فعلاً (لا دعوات لغرباء)
        from app.services.friends import get_friends, is_blocked_between
        friend_ids = [f.get('id') for f in get_friends(uid)]
        if friend_id not in friend_ids:
            await sio.emit('play_invite_result', {'ok': False, 'msg': 'ليس في قائمة أصدقائك'}, to=sid)
            return
        if is_blocked_between(uid, friend_id):
            return

        # 🛡️ نتأكد أن الصديق متصل
        from app.services.notifications import find_online_sid
        friend_sid = find_online_sid(friend_id)
        if not friend_sid:
            await sio.emit('play_invite_result', {'ok': False, 'msg': 'صديقك غير متصل الآن'}, to=sid)
            return

        # نرسل الدعوة للصديق (معرّفات فقط — لا نص حر)
        await sio.emit('play_invite_received', {
            'inviterId': uid,
            'inviterName': inviter_name,
            'inviterSid': sid,
            'gameMode': game_mode,
        }, to=friend_sid)
        await sio.emit('play_invite_result', {'ok': True, 'msg': 'أُرسلت الدعوة'}, to=sid)

    @sio.on('respond_play_invite')
    async def respond_play_invite(sid, data):
        """قبول/رفض دعوة لعب. data: { token, inviterId, gameMode, accept }
        عند القبول: ننشئ غرفة خاصة ونرسل الكود للطرفين."""
        token = (data or {}).get('token')
        user, db = verify_socket_token(token)
        if not user:
            return
        uid = user.id
        responder_name = user.player_name
        db.close()

        inviter_id = (data or {}).get('inviterId')
        game_mode = (data or {}).get('gameMode')
        accept = bool((data or {}).get('accept'))
        if not inviter_id or not game_mode:
            return

        from app.services.notifications import find_online_sid
        inviter_sid = find_online_sid(inviter_id)

        # رفض → نُعلم الداعي فقط
        if not accept:
            if inviter_sid:
                await sio.emit('play_invite_declined', {'byName': responder_name}, to=inviter_sid)
            return

        # 🛡️ تأكد أنهما صديقان (قد تتغيّر الحالة بين الدعوة والرد)
        from app.services.friends import get_friends
        if inviter_id not in [f.get('id') for f in get_friends(uid)]:
            return
        if not inviter_sid:
            await sio.emit('play_invite_result', {'ok': False, 'msg': 'الداعي لم يعد متصلاً'}, to=sid)
            return

        # ننشئ غرفة ودية بكود آمن، ونهيّئها بالكامل (مثل اللعب السريع)
        import secrets, string
        from app.games.core_manager import rooms
        from app.games.core_manager import _create_game_state
        import time as _time
        alphabet = string.ascii_uppercase + string.digits
        room_code = ''.join(secrets.choice(alphabet) for _ in range(6))
        inviter_name = connected_players.get(inviter_sid, {}).get('name', 'صديق')
        inviter_avatar = connected_players.get(inviter_sid, {}).get('avatar', '')
        inviter_token = connected_players.get(inviter_sid, {}).get('token')
        guest_name = connected_players.get(sid, {}).get('name', responder_name)
        guest_avatar = connected_players.get(sid, {}).get('avatar', '')
        guest_token = connected_players.get(sid, {}).get('token')

        # 🤝 غرفة ودية مُهيّأة كاملة: state=starting + game_state + user_ids
        # (هذا ما كان ناقصاً: بدونه لا يبدأ البورد، ويُعامل كأنه غير جاهز)
        rooms[room_code] = {
            'code': room_code,
            'type': 'friendly',          # 🛡️ يضمن صفر تصنيف/مكافآت
            'game_mode': game_mode,
            'state': 'starting',
            'created_at': _time.time(),
            'players': [
                {'sid': inviter_sid, 'name': inviter_name, 'avatar': inviter_avatar,
                 'token': inviter_token, 'user_id': inviter_id, 'role': 'host', 'color': 'green'},
                {'sid': sid, 'name': guest_name, 'avatar': guest_avatar,
                 'token': guest_token, 'user_id': uid, 'role': 'guest', 'color': 'orange'},
            ],
            'game_state': _create_game_state(
                game_mode, room_code,
                {'sid': inviter_sid, 'name': inviter_name, 'avatar': inviter_avatar,
                 'token': inviter_token, 'user_id': inviter_id},
                {'sid': sid, 'name': guest_name, 'avatar': guest_avatar,
                 'token': guest_token, 'user_id': uid},
            ),
            'user_ids': {inviter_sid: inviter_id, sid: uid},
        }
        # ملاحظة: لا نستدعي record_matchup للمباريات الودية (لا تدخل مكافحة التواطؤ)

        # نُدخل الـ socket للطرفين في غرفة Socket.IO
        await sio.enter_room(inviter_sid, room_code)
        await sio.enter_room(sid, room_code)

        # نبثّ match_found للطرفين (نفس تدفّق اللعب السريع → شاشة العد 3-2-1)
        players_list = [
            {'name': inviter_name, 'avatar': inviter_avatar, 'color': 'green', 'role': 'host'},
            {'name': guest_name,   'avatar': guest_avatar,   'color': 'orange', 'role': 'guest'},
        ]
        await sio.emit('match_found', {
            'room_code': room_code, 'role': 'host',
            'players': players_list, 'friendly': True, 'gameMode': game_mode
        }, to=inviter_sid)
        await sio.emit('match_found', {
            'room_code': room_code, 'role': 'guest',
            'players': players_list, 'friendly': True, 'gameMode': game_mode
        }, to=sid)
