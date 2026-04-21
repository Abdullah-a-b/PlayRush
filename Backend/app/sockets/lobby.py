import html
from app.sockets.state import connected_players, global_chat_history, game_lobby_players, game_chat_history
from app.services.reward_service import get_clean_avatar

async def return_players_to_lobby(sio, room):
    game_mode = room.get('game_mode', 'huroof')
    if game_mode not in game_lobby_players: game_lobby_players[game_mode] = {}
    for player in room.get('players', []):
        p_sid = player.get('sid')
        if not p_sid: continue
        p_name = player.get('name', 'لاعب')
        # 👈 تنظيف أفاتار الخصم قبل إرجاعه للوبي
        p_avatar = get_clean_avatar(player.get('avatar', ''), p_name)
        
        connected_players[p_sid] = {'name': p_name, 'avatar': p_avatar, 'location': game_mode}
        game_lobby_players[game_mode][p_sid] = {'name': p_name, 'avatar': p_avatar}
    
    players_list = list(game_lobby_players[game_mode].values())
    for p_sid in list(game_lobby_players[game_mode].keys()):
        await sio.emit('update_game_lobby_players', players_list, to=p_sid)
    await sio.emit('update_online_players', list(connected_players.values()))


def register_lobby_events(sio):
    
    @sio.on('join_global_lobby')
    async def join_global_lobby(sid, data):
        player_name = data.get('name', 'لاعب')
        avatar = get_clean_avatar(data.get('avatar', ''), player_name)
        connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': 'global'}
        await sio.emit('chat_history', global_chat_history, to=sid)
        await sio.emit('update_online_players', list(connected_players.values()))

    @sio.on('join_game_lobby')
    async def join_game_lobby(sid, data):
        game_mode, player_name, token = data.get('gameMode'), data.get('name', 'لاعب'), data.get('token', None)
        avatar = get_clean_avatar(data.get('avatar', ''), player_name)
        
        if game_mode not in game_lobby_players: game_lobby_players[game_mode] = {}
        if game_mode not in game_chat_history: game_chat_history[game_mode] = []
        
        game_lobby_players[game_mode][sid] = {'name': player_name, 'avatar': avatar}
        connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': game_mode, 'token': token}
        
        await sio.emit('update_online_players', list(connected_players.values()))
        await sio.emit('game_chat_history', game_chat_history[game_mode], to=sid)
        
        players_list = list(game_lobby_players[game_mode].values())
        for p_sid in list(game_lobby_players[game_mode].keys()):
            await sio.emit('update_game_lobby_players', players_list, to=p_sid)

    @sio.on('update_player_info')
    async def update_player_info(sid, data):
        if sid in connected_players:
            player_data = connected_players[sid]
            player_data['name'] = data.get('name', player_data['name'])
            player_data['avatar'] = get_clean_avatar(data.get('avatar', ''), player_data['name'])
            connected_players[sid] = player_data
            await sio.emit('update_online_players', list(connected_players.values()))

    # ==========================================
    # 💬 أحداث الدردشة (تم استرجاعها وتأمينها)
    # ==========================================

    @sio.on('send_chat_message')
    async def send_chat_message(sid, data):
        raw_text = str(data.get('text', ''))
        
        # 🛡️ الجدار الناري: منع أكواد XSS وقص النصوص الطويلة جداً (أقصى حد 200 حرف للرسالة)
        clean_text = html.escape(raw_text.strip())[:200] 
        
        # إذا كانت الرسالة فارغة بعد التنظيف نتجاهلها
        if not clean_text: return
        
        msg = {'sender': data.get('sender'), 'text': clean_text, 'isSystem': False}
        global_chat_history.append(msg)
        
        if len(global_chat_history) > 50: global_chat_history.pop(0)
        await sio.emit('new_chat_message', msg)

    @sio.on('send_game_chat_message')
    async def send_game_chat_message(sid, data):
        game_mode = data.get('gameMode')
        raw_text = str(data.get('text', ''))
        
        # 🛡️ الجدار الناري
        clean_text = html.escape(raw_text.strip())[:200] 
        if not clean_text: return
        
        msg = {'sender': data.get('sender'), 'text': clean_text, 'isSystem': False}
        
        if game_mode not in game_chat_history:
            game_chat_history[game_mode] = []
            
        game_chat_history[game_mode].append(msg)
        if len(game_chat_history[game_mode]) > 50: 
            game_chat_history[game_mode].pop(0)
            
        if game_mode in game_lobby_players:
            for p_sid in list(game_lobby_players[game_mode].keys()):
                await sio.emit('new_game_chat_message', msg, to=p_sid)