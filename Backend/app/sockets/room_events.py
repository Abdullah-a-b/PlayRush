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
        await sio.emit('room_created', {'room_code': room_code, 'players': room['players']}, to=sid)

    @sio.on('join_room')
    async def handle_join_room(sid, data):
        room_code = data.get('room_code')
        token = data.get('token')

        # 🛡️ نجلب الاسم والأفاتار من DB إن وُجد التوكن — يمنع انتحال الهوية
        user, db = verify_socket_token(token)
        if user:
            player_name = user.player_name or 'مجهول'
            avatar = get_clean_avatar(user.avatar, player_name)
            db.close()
        else:
            player_name = str(data.get('player_name', 'مجهول'))[:30]
            avatar = get_clean_avatar(data.get('avatar', ''), player_name)

        success, msg = join_room(room_code, sid, player_name, avatar)
        if not success:
            await sio.emit('error_message', msg, to=sid)
            return

        await sio.enter_room(sid, room_code)
        room = get_room_state(room_code)
        game_mode = room.get('game_mode', 'huroof')
        connected_players[sid] = {
            'name': player_name,
            'avatar': avatar,
            'location': f'playing_{game_mode}',
            'token': token
        }

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
                        await sio.emit('huroof_hex_locked', {
                            'hexIndex': gs.active_hex['index'],
                            'letter': gs.active_hex['letter']
                        }, to=sid)
                        await sio.emit('huroof_new_question', {
                            'questionData': gs.current_question,
                            'round': 'r1',
                            'timer': 40
                        }, to=sid)

    @sio.on('start_game')
    async def handle_start_game(sid, data):
        room_code = data.get('room_code')
        room = get_room_state(room_code)
        if room and room.get('host') == sid:
            room['state'] = 'starting'
            await sio.emit('game_started', {'roomCode': room_code}, room=room_code)
