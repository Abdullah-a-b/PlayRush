import asyncio
from app.sockets.state import connected_players, game_lobby_players, disconnect_timers
from app.games.core_manager import leave_room, get_room_state, rooms
from app.services.reward_service import record_match_result
from app.sockets.lobby import return_players_to_lobby # نستوردها من ملف اللوبي

def register_connection_events(sio):
    async def handle_disconnection_timeout(room_code, old_sid):
        await asyncio.sleep(30)
        room = get_room_state(room_code)
        if room and room.get('state') == 'playing':
            missing_player = next((p for p in room['players'] if p.get('old_sid') == old_sid and p.get('sid') is None), None)
            if missing_player:
                print(f"⏰ [Timeout] إعلان فوز الخصم في الغرفة {room_code}.")
                winner_player = next((p for p in room['players'] if p.get('old_sid') != old_sid), None)
                winner_color = winner_player['color'] if winner_player else 'green'
                record_match_result(winner_player, missing_player, room.get('game_mode', 'huroof'), extra={'reason': 'surrender'})
                await sio.emit('show_winner', {'color': winner_color, 'reason': 'surrender'}, room=room_code)
                room['state'] = 'finished'
                if room.get('game_state'): room['game_state'].state_version += 9999 
                await return_players_to_lobby(sio, room)
                if room_code in rooms: del rooms[room_code]

    @sio.event
    async def connect(sid, environ):
        print(f"[+] اتصال جديد: {sid}")

    @sio.event
    async def disconnect(sid):
        if sid in connected_players:
            print(f"[-] غادر {connected_players[sid]['name']} النظام")
            del connected_players[sid]
            await sio.emit('update_online_players', list(connected_players.values()))
        
        for game_mode, players in game_lobby_players.items():
            if sid in players:
                del players[sid]
                players_list = list(players.values())
                for p_sid in list(players.keys()):
                    await sio.emit('update_game_lobby_players', players_list, to=p_sid)
                    
        room_code, room = leave_room(sid)
        if room_code and room and room.get('state') == 'playing':
            await sio.emit('opponent_disconnected', {'msg': 'انقطع اتصال الخصم، ننتظر عودته...'}, room=room_code)
            if room.get('game_state'): room['game_state'].state_version += 1 
            disconnect_timers[room_code] = asyncio.create_task(handle_disconnection_timeout(room_code, sid))