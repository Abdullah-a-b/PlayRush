import secrets
import string
from app.games.core_manager import add_to_queue, remove_from_queue, check_queue_for_match
from app.services.reward_service import get_clean_avatar
from app.sockets.auth_helper import verify_socket_token

def register_matchmaking_events(sio):

    @sio.on('quick_play_search')
    async def quick_play_search(sid, data):
        # 🛡️ التحقق من هوية اللاعب قبل إدخاله الطابور
        token = data.get('token')
        user, db = verify_socket_token(token)
        if not user:
            print(f"❌ [matchmaking] توكن غير صالح لـ sid={sid}")
            await sio.emit('quick_play_error', {'msg': 'يجب تسجيل الدخول أولاً'}, to=sid)
            return

        game_mode = data.get('game_mode')
        # ✅ نقرأ كل بيانات المستخدم قبل إغلاق الـ db
        player_name = user.player_name or 'لاعب'
        avatar = get_clean_avatar(user.avatar, player_name)
        user_id = user.id
        db.close()

        # 🛡️ نجلب الـ IP الخاص بالـ sid (لمنع اللعب ضد نفس المنطقة)
        from app.sockets.state import sid_ip_map
        client_ip = sid_ip_map.get(sid)

        # 🚪 فحص حظر الانسحاب المتكرر قبل دخول الطابور
        from app.services.leaver_penalty import get_leaver_ban
        leaver_ban = get_leaver_ban(user_id)
        if leaver_ban:
            print(f"🔎 [matchmaking] ⛔ uid={user_id} محظور (انسحاب متكرر): {leaver_ban['msg']}")
            await sio.emit('quick_play_error', {'msg': leaver_ban['msg']}, to=sid)
            return

        success, msg = add_to_queue(sid, player_name, avatar, game_mode,
                                     token=token, user_id=user_id, ip=client_ip)
        print(f"🔎 [matchmaking] uid={user_id} دخل الطابور؟ {success} | {msg}")
        if not success:
            print(f"❌ [matchmaking] رُفض الدخول: {msg}")
            await sio.emit('quick_play_error', {'msg': msg}, to=sid)
            return

        match_found, room_code, matched_players, rp_data = check_queue_for_match(game_mode)
        from app.games.core_manager import matchmaking_queue
        qsize = len(matchmaking_queue.get(game_mode, []))

        if match_found:
            players_list = list(rp_data.values())
            for p in matched_players:
                role = 'host' if p['sid'] == matched_players[0]['sid'] else 'guest'
                await sio.emit('match_found', {'room_code': room_code, 'role': role, 'players': players_list}, to=p['sid'])

    @sio.on('cancel_quick_play')
    async def cancel_quick_play(sid):
        if remove_from_queue(sid):
            await sio.emit('quick_play_cancelled', {}, to=sid)
