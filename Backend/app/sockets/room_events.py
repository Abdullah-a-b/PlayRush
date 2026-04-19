import asyncio
from app.sockets.state import connected_players, disconnect_timers
from app.games.core_manager import create_room, join_room, get_room_state
from app.services.reward_service import get_player_full_stats
from app.core.database import SessionLocal
from app.core.security import get_user_from_token

def register_room_events(sio):
    
    # 👈 استخدام @sio.on يطابق الحدث مع الجافاسكريبت بدون تغيير اسم الدالة
    @sio.on('create_room')
    async def handle_create_room(sid, data):
        host_name = data.get('host_name')
        game_mode = data.get('game_mode')
        avatar = data.get('avatar', '')
        
        import string
        import random
        room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        room = create_room(room_code, sid, host_name, 2, game_mode, "0.0.0.0", avatar, "private")
        
        await sio.emit('room_created', {'room_code': room_code, 'players': room['players']}, to=sid)

    @sio.on('join_room')
    async def handle_join_room(sid, data):
        room_code = data.get('room_code')
        token = data.get('token')
        
        db = SessionLocal()
        user = get_user_from_token(db, token) if token else None
        db.close()

        player_name = user.player_name if user else data.get('player_name', 'مجهول')
        avatar = user.avatar if user else data.get('avatar', '')
            
        success, msg = join_room(room_code, sid, player_name, avatar)
        if success:
            await sio.enter_room(sid, room_code)
            room = get_room_state(room_code)
            game_mode = room.get('game_mode', 'huroof')
            connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': f'playing_{game_mode}', 'token': token}

            safe_room = {k: v for k, v in room.items() if k != 'game_state'}
            fetch_tasks = []
            
            for p in safe_room['players']:
                if p.get('sid') == sid and token: p['token'] = token
                p_token = p.get('token') or (connected_players.get(p['sid'], {}).get('token') if p.get('sid') else None)
                fetch_tasks.append(get_player_full_stats(p_token, p['name'], p.get('avatar', '')))

            stats_results = await asyncio.gather(*fetch_tasks)
            for i, p in enumerate(safe_room['players']):
                p['stats'] = stats_results[i]
                if p['stats']: p['avatar'] = p['stats']['avatar']

            await sio.emit('room_joined', safe_room, to=sid)
            await sio.emit('update_players_stats', safe_room['players'], room=room_code)
            await sio.emit('player_joined', {'player': player_name}, room=room_code)
            
            if msg in ["reconnected", "reconnected_ready"]:
                if room_code in disconnect_timers:
                    disconnect_timers[room_code].cancel()
                    del disconnect_timers[room_code]
                    await sio.emit('opponent_reconnected', {'msg': 'عاد الخصم للعب!'}, room=room_code)

                gs = room.get('game_state')
                if gs and hasattr(gs, 'board'):
                    await sio.emit('huroof_board_init', {'board': gs.board}, to=sid)
                    if room['state'] == 'playing':
                        await sio.emit('huroof_turn_changed', {'turn_sid': gs.turn}, room=room_code)
                        if gs.stage != 'selecting' and gs.current_question and gs.active_hex:
                            await sio.emit('huroof_hex_locked', {'hexIndex': gs.active_hex['index'], 'letter': gs.active_hex['letter']}, to=sid)
                            await sio.emit('huroof_new_question', {'questionData': gs.current_question, 'round': 'r1', 'timer': 40}, to=sid)
        else:
            await sio.emit('error_message', msg, to=sid)

    @sio.on('start_game')
    async def handle_start_game(sid, data):
        room_code = data.get('room_code')
        room = get_room_state(room_code)
        if room and room.get('host') == sid:
            room['state'] = 'starting'
            await sio.emit('game_started', {'roomCode': room_code}, room=room_code)