import asyncio
from app.sockets.state import connected_players, game_lobby_players, disconnect_timers
from app.games.core_manager import leave_room, get_room_state, rooms
from app.services.reward_service import record_match_result
from app.sockets.lobby import return_players_to_lobby, presence_delta # نستوردها من ملف اللوبي

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
                    from app.services.anti_collusion import get_reward_multiplier
                    uids = list((room.get('user_ids') or {}).values())
                    mult = get_reward_multiplier(uids[0], uids[1]) if len(uids) == 2 else 1.0
                    await asyncio.to_thread(
                        record_match_result, winner_player, missing_player, room.get('game_mode', 'huroof'),
                        extra={'reason': 'surrender', 'collusion_multiplier': mult,
                               'friendly': room.get('type') == 'friendly'})
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


        # 🛡️ نخزّن الـ IP مؤقتاً للاستخدام في منع اللعب ضد النفس/نفس المنطقة
        from app.sockets.state import sid_ip_map
        sid_ip_map[sid] = client_ip
        # 🕸️ عنقود: نسجّل أي worker يملك هذا الاتصال (no-op بلا Redis)
        from app.core import cluster
        await cluster.register_conn(sid)

    @sio.event
    async def disconnect(sid):
        # 🛡️ تنظيف خريطة الـ IP
        from app.sockets.state import sid_ip_map
        sid_ip_map.pop(sid, None)
        # 🕸️ عنقود: إلغاء تسجيل الاتصال (no-op بلا Redis)
        from app.core import cluster
        await cluster.unregister_conn(sid)

        if sid in connected_players:
            del connected_players[sid]
            # 📡 delta صغير (pid فقط) بدل بث القائمة الكاملة للجميع
            await presence_delta(sio, sid, 'leave')

        # تنظيف قوائم لوبيات الألعاب (بدون بث — الواجهة تشتق القوائم من نظام الحضور)
        for game_mode, players in game_lobby_players.items():
            players.pop(sid, None)
                    
        # 🔍 تنظيف طابور البحث: لو انقطع اللاعب وهو يبحث، نزيل قفله
        # فوراً — وإلا يبقى عالقاً في Redis حتى 120ث ويمنعه من البحث
        # ثانيةً برسالة "أنت بالفعل في البحث من جهاز آخر".
        try:
            from app.sockets.matchmaking import _cluster_leave_queue
            await _cluster_leave_queue(sid)
        except Exception as _e:
            print(f"⚠️ [disconnect] تنظيف طابور البحث: {_e}")

        # 🕸️ مسار انقطاع الغرفة — مشترك بين الانقطاع المحلي وإشعار
        # sid_gone القادم من worker آخر (الغرفة قد تعيش عند مالك آخر)
        await _room_disconnect(sid)
        from app.core import cluster as _cl
        await _cl.broadcast_sid_gone(sid)

    async def _room_disconnect(sid):
        room_code, room = leave_room(sid)
        if room_code and room and room.get('state') == 'playing':
            await sio.emit('opponent_disconnected', {'msg': 'انقطع اتصال الخصم، ننتظر عودته...'}, room=room_code)
            if room.get('game_state'): room['game_state'].state_version += 1

            # ✅ إصلاح task leak: نلغي أي timer قديم لنفس الغرفة قبل إنشاء جديد
            old_timer = disconnect_timers.get(room_code)
            if old_timer and not old_timer.done():
                old_timer.cancel()

            disconnect_timers[room_code] = asyncio.create_task(handle_disconnection_timeout(room_code, sid))

    # 🕸️ نسجّل المسار كمعالج لإشعارات الانقطاع القادمة من workers أخرى
    from app.core import cluster as _cluster_reg
    _cluster_reg.on_remote_sid_gone = _room_disconnect