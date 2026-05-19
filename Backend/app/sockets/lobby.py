import re
from app.sockets.state import connected_players, global_chat_history, game_lobby_players, game_chat_history
from app.services.reward_service import get_clean_avatar
from app.sockets.auth_helper import verify_socket_token


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

    await sio.emit('update_online_players', list(connected_players.values()))


def _sanitize_chat_text(raw: str) -> str:
    """فلتر نص الشات: يقص ويمنع الرسائل الفارغة."""
    return str(raw).strip()[:200]


def register_lobby_events(sio):

    @sio.on('join_global_lobby')
    async def join_global_lobby(sid, data):
        # 🛡️ نحاول التحقق من التوكن إن وُجد — إن لم يكن موجوداً نقبل بالاسم كـ guest
        token = data.get('token')
        user, db = verify_socket_token(token)
        if user:
            player_name = user.player_name or 'لاعب'
            avatar = get_clean_avatar(user.avatar, player_name)
            db.close()
        else:
            player_name = str(data.get('name', 'لاعب'))[:30]
            avatar = get_clean_avatar(data.get('avatar', ''), player_name)

        connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': 'global'}
        await sio.emit('chat_history', global_chat_history, to=sid)
        await sio.emit('update_online_players', list(connected_players.values()))

    @sio.on('join_game_lobby')
    async def join_game_lobby(sid, data):
        token = data.get('token')
        game_mode = data.get('gameMode')

        # 🛡️ اللوبي يتطلب توكن صالح
        user, db = verify_socket_token(token)
        if user:
            player_name = user.player_name or 'لاعب'
            avatar = get_clean_avatar(user.avatar, player_name)
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
            'token': token  # نحتفظ بالتوكن للاستخدام الداخلي فقط (لا يُبث للعلن)
        }

        await sio.emit('update_online_players', list(connected_players.values()))
        await sio.emit('game_chat_history', game_chat_history[game_mode], to=sid)

        players_list = list(game_lobby_players[game_mode].values())
        for p_sid in list(game_lobby_players[game_mode].keys()):
            await sio.emit('update_game_lobby_players', players_list, to=p_sid)

    # ==========================================
    # 💬 رسائل الشات
    # ==========================================
    @sio.on('send_chat_message')
    async def send_chat_message(sid, data):
        # 🛡️ Anti-Cheat
        from app.core.anticheat import (
            check_action_rate, check_payload_safety,
            report_violation, is_temp_banned, Severity
        )

        if is_temp_banned(sid):
            return

        # payload safety
        payload_issue = check_payload_safety(data, max_string_len=500)
        if payload_issue:
            await report_violation(sid, sio, f"chat:{payload_issue}", severity=Severity.HIGH)
            return

        # rate limit (max 1 message/sec = 60/min — معقول لإنسان)
        rate_issue = check_action_rate(sid, 'chat_message', max_per_second=2)
        if rate_issue:
            await report_violation(sid, sio, f"chat_spam:{rate_issue}", severity=Severity.MEDIUM)
            return

        # 🛡️ نتحقق من أن المرسل مسجّل فعلاً في الـ lobby
        if sid not in connected_players:
            return

        raw_text = _sanitize_chat_text(data.get('text', ''))
        if not raw_text:
            return

        # نأخذ الاسم من server state لا من الـ data — يمنع انتحال الهوية في الشات
        sender_name = connected_players[sid].get('name', 'لاعب')
        msg = {'sender': sender_name, 'text': raw_text, 'isSystem': False}
        global_chat_history.append(msg)
        if len(global_chat_history) > 50:
            global_chat_history.pop(0)
        await sio.emit('new_chat_message', msg)

    @sio.on('send_game_chat_message')
    async def send_game_chat_message(sid, data):
        # 🛡️ Anti-Cheat
        from app.core.anticheat import (
            check_action_rate, check_payload_safety,
            report_violation, is_temp_banned, Severity
        )

        if is_temp_banned(sid):
            return

        payload_issue = check_payload_safety(data, max_string_len=500)
        if payload_issue:
            await report_violation(sid, sio, f"game_chat:{payload_issue}", severity=Severity.HIGH)
            return

        rate_issue = check_action_rate(sid, 'game_chat_message', max_per_second=2)
        if rate_issue:
            await report_violation(sid, sio, f"game_chat_spam:{rate_issue}", severity=Severity.MEDIUM)
            return

        if sid not in connected_players:
            return

        game_mode = data.get('gameMode')
        if not game_mode:
            return

        raw_text = _sanitize_chat_text(data.get('text', ''))
        if not raw_text:
            return

        # 🛡️ نتحقق أن اللاعب فعلاً في لوبي هذا الـ game_mode
        if game_mode not in game_lobby_players or sid not in game_lobby_players[game_mode]:
            return

        sender_name = connected_players[sid].get('name', 'لاعب')
        msg = {'sender': sender_name, 'text': raw_text, 'isSystem': False}

        if game_mode not in game_chat_history:
            game_chat_history[game_mode] = []
        game_chat_history[game_mode].append(msg)
        if len(game_chat_history[game_mode]) > 50:
            game_chat_history[game_mode].pop(0)

        for p_sid in list(game_lobby_players[game_mode].keys()):
            await sio.emit('new_game_chat_message', msg, to=p_sid)

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

        await sio.emit('update_online_players', list(connected_players.values()))

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
