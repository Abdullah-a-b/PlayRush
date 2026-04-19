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
        # 👈 تنظيف أفاتار الخصم قبل إرجاعه للوبي لحل المشكلة الثالثة
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

    # 👈 إضافة الحدث المفقود: الآن عند تغيير الأفاتار سيتحدث فوراً للجميع بدون تحديث الصفحة
    # في ملف app/sockets/lobby.py

    @sio.on('update_player_info')
    async def update_player_info(sid, data):
        if sid in connected_players:
            # 1. جلب البيانات القديمة (التي تحتوي على الـ location والـ token)
            player_data = connected_players[sid]
            
            # 2. تحديث الاسم والأفاتار فقط
            player_data['name'] = data.get('name', player_data['name'])
            player_data['avatar'] = get_clean_avatar(data.get('avatar', ''), player_data['name'])
            
            # 3. حفظ الكائن كاملاً لضمان عدم فقدان الـ location
            connected_players[sid] = player_data
            
            # 4. بث القائمة المحدثة للجميع
            await sio.emit('update_online_players', list(connected_players.values()))