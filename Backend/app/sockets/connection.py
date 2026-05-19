import asyncio
from app.sockets.state import connected_players, game_lobby_players, disconnect_timers
from app.games.core_manager import leave_room, get_room_state, rooms
from app.services.reward_service import record_match_result
from app.sockets.lobby import return_players_to_lobby # نستوردها من ملف اللوبي

def register_connection_events(sio):
    async def handle_disconnection_timeout(room_code, old_sid):
        try:
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
        except asyncio.CancelledError:
            # ✅ طبيعي لو لاعب رجع وألغينا الـ timer
            pass
        except Exception as e:
            print(f"⚠️ [Timeout handler] {type(e).__name__}: {e}")
        finally:
            # ✅ تنظيف الـ entry لمنع تراكم disconnect_timers
            disconnect_timers.pop(room_code, None)

    @sio.event
    async def connect(sid, environ):
        # ✅ Connect event: نفحص banned IP/users قبل قبول الاتصال
        # 🛡️ Anti-Cheat: rate limit على connections من نفس IP
        client_ip = "unknown"
        try:
            # استخراج IP الحقيقي (يدعم proxy headers)
            forwarded = environ.get("HTTP_X_FORWARDED_FOR", "")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
            else:
                client_ip = environ.get("REMOTE_ADDR", "unknown")
        except Exception:
            pass

        from app.core.anticheat import check_action_rate, report_violation, Severity
        # حد أقصى 10 connections/ثانية من نفس IP
        rate_issue = check_action_rate(f"ip:{client_ip}", 'socket_connect', max_per_second=10)
        if rate_issue:
            print(f"🚫 [connect] rejected ip={client_ip} reason={rate_issue}")
            return False  # يرفض الاتصال

        print(f"[+] اتصال جديد: {sid} from {client_ip}")

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

            # ✅ إصلاح task leak: نلغي أي timer قديم لنفس الغرفة قبل إنشاء جديد
            old_timer = disconnect_timers.get(room_code)
            if old_timer and not old_timer.done():
                old_timer.cancel()

            disconnect_timers[room_code] = asyncio.create_task(handle_disconnection_timeout(room_code, sid))