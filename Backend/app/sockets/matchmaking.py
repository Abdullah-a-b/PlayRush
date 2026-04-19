from app.games.core_manager import add_to_queue, remove_from_queue, check_queue_for_match
from app.services.reward_service import get_clean_avatar

def register_matchmaking_events(sio):
    @sio.on('quick_play_search')
    async def quick_play_search(sid, data):
        game_mode = data.get('game_mode')
        player_name = data.get('player_name', 'لاعب')
        
        # 👈 تنظيف الصورة قبل دخول طابور البحث
        avatar = get_clean_avatar(data.get('avatar', ''), player_name)
        
        add_to_queue(sid, player_name, avatar, game_mode)
        match_found, room_code, matched_players, rp_data = check_queue_for_match(game_mode)
        
        if match_found:
            players_list = list(rp_data.values())
            for p in matched_players:
                role = 'host' if p['sid'] == matched_players[0]['sid'] else 'guest'
                await sio.emit('match_found', {'room_code': room_code, 'role': role, 'players': players_list}, to=p['sid'])

    @sio.on('cancel_quick_play')
    async def cancel_quick_play(sid):
        if remove_from_queue(sid):
            await sio.emit('quick_play_cancelled', {}, to=sid)