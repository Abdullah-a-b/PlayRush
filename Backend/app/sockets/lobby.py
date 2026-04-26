import html
import json
from app.core.database import SessionLocal
from app.models.user import User
from app.services.reward_service import get_clean_avatar
from app.core.redis_client import redis_db
from app.sockets.state import (
    add_connected_player, get_connected_player, get_all_online_players,
    add_game_lobby_player, get_game_lobby_players,
    add_chat_message, get_chat_history
)

async def return_players_to_lobby(sio, room):
    game_mode = room.get('game_mode', 'huroof')
    db = SessionLocal()
    try:
        for player in room.get('players', []):
            p_sid = player.get('sid')
            if not p_sid: continue
            p_name = player.get('name', 'لاعب')

            # ✅ الإصلاح: جلب الأفاتار الحقيقي من قاعدة البيانات وليس من Redis
            user_in_db = db.query(User).filter(User.player_name == p_name).first()
            if user_in_db and user_in_db.avatar:
                p_avatar = get_clean_avatar(user_in_db.avatar, p_name)
            else:
                p_avatar = get_clean_avatar(player.get('avatar', ''), p_name)

            player_data = {'name': p_name, 'avatar': p_avatar, 'location': game_mode}
            await add_connected_player(p_sid, player_data)
            await add_game_lobby_player(game_mode, p_sid, {'name': p_name, 'avatar': p_avatar})
    finally:
        db.close()

    players_list = await get_game_lobby_players(game_mode)
    await sio.emit('update_game_lobby_players', players_list, room=game_mode)
    
    online_players = await get_all_online_players()
    await sio.emit('update_online_players', online_players)


def register_lobby_events(sio):
    
    @sio.on('join_global_lobby')
    async def join_global_lobby(sid, data):
        player_name = data.get('name', 'لاعب')
        if not player_name or player_name == 'لاعب':
            return  # ❌ رفض الانضمام بدون اسم حقيقي (يحدث قبل اكتمال fetch /auth/me)

        # 🧹 مسح أي SID قديم لنفس اللاعب (أشباح بعد انقطاع أو إعادة اتصال)
        all_connected = await redis_db.hgetall("global:connected_players")
        import json as _json
        for ghost_sid, ghost_str in all_connected.items():
            if ghost_sid == sid:
                continue
            ghost = _json.loads(ghost_str)
            if ghost.get('name') == player_name:
                await redis_db.hdel("global:connected_players", ghost_sid)
                try:
                    await sio.leave_room(ghost_sid, "global")
                except:
                    pass

        db = SessionLocal()
        user_in_db = db.query(User).filter(User.player_name == player_name).first()
        correct_avatar = user_in_db.avatar if user_in_db and user_in_db.avatar else "assets/avatars/avatar_1.svg"
        db.close()

        player_data = {'name': player_name, 'avatar': correct_avatar, 'location': 'global'}
        await add_connected_player(sid, player_data)
        
        chat_hist = await get_chat_history('global')
        await sio.emit('chat_history', chat_hist, to=sid)
        
        online_players = await get_all_online_players()
        await sio.emit('update_online_players', online_players)

    @sio.on('join_game_lobby')
    async def join_game_lobby(sid, data):
        player_name = data.get('name')
        game_mode = data.get('gameMode', 'huroof')
        
        # 🧹 [الحل الحاسم 3]: نظام "طرد الأشباح" (Ghost Sweeper)
        # مسح أي اتصال قديم معلق لنفس اللاعب في هذا اللوبي قبل إضافة اتصاله الجديد
        from app.sockets.state import redis_db, remove_connected_player
        import json
        
        all_ghosts = await redis_db.hgetall(f"lobby:{game_mode}")
        for ghost_sid, ghost_data_str in all_ghosts.items():
            ghost_data = json.loads(ghost_data_str)
            if ghost_data.get('name') == player_name:
                # تدمير أي نسخة قديمة للاعب من Redis
                await redis_db.hdel(f"lobby:{game_mode}", ghost_sid)
                await remove_connected_player(ghost_sid)
                try:
                    await sio.leave_room(ghost_sid, game_mode)
                except:
                    pass

        # === تكملة كود الانضمام الطبيعي ===
        db = SessionLocal()
        user_in_db = db.query(User).filter(User.player_name == player_name).first()
        if not user_in_db:
            db.close()
            return
        correct_avatar = user_in_db.avatar if user_in_db.avatar else "assets/avatars/avatar_1.svg"
        db.close()

        player_data = {'name': player_name, 'avatar': correct_avatar, 'location': game_mode}
        
        await add_connected_player(sid, player_data)
        await add_game_lobby_player(game_mode, sid, {'name': player_name, 'avatar': correct_avatar})
        
        # ضمان إدخال اللاعب للغرفة الخاصة باللوبي لاستلام رسائل الشات وقائمة اللاعبين
        await sio.enter_room(sid, game_mode) 
        
        # ✅ الإصلاح: نُرسل التحديثات بالترتيب الصحيح
        # أولاً قائمة اللاعبين في اللوبي لكل من في الغرفة
        players_list = await get_game_lobby_players(game_mode)
        await sio.emit('update_game_lobby_players', players_list, room=game_mode)
        
        # ثانياً القائمة العالمية للمتصلين لكل الغرف
        online_players = await get_all_online_players()
        await sio.emit('update_online_players', online_players)
        
        # ثالثاً سجل الشات للاعب الجديد فقط
        game_chat_hist = await get_chat_history(game_mode)
        await sio.emit('game_chat_history', game_chat_hist, to=sid)

    @sio.on('send_chat_message')
    async def send_chat_message(sid, data):
        raw_text = str(data.get('text', ''))
        clean_text = html.escape(raw_text.strip())[:200] 
        if not clean_text: return
        
        msg = {'sender': data.get('sender'), 'text': clean_text, 'isSystem': False}
        await add_chat_message('global', msg)
        await sio.emit('new_chat_message', msg)

    @sio.on('send_game_chat_message')
    async def send_game_chat_message(sid, data):
        game_mode = data.get('gameMode')
        raw_text = str(data.get('text', ''))
        clean_text = html.escape(raw_text.strip())[:200] 
        if not clean_text: return
        
        msg = {'sender': data.get('sender'), 'text': clean_text, 'isSystem': False}
        await add_chat_message(game_mode, msg)
        await sio.emit('new_game_chat_message', msg, room=game_mode)
        
    @sio.on('severe_security_breach')
    async def handle_security_breach(sid, data):
        player = await get_connected_player(sid)
        if player and 'name' in player:
            print(f"🚨 [أمان] محاولة اختراق من: {player['name']}")
            db = SessionLocal()
            db_user = db.query(User).filter(User.player_name == player['name']).first()
            if db_user:
                db_user.is_banned = True
                db.commit()
            db.close()
            await sio.emit('force_logout', {'message': 'تم حظر حسابك نهائياً.'}, to=sid)
            await sio.disconnect(sid)