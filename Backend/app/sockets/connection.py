import asyncio
from app.sockets.state import (
    get_connected_player, remove_connected_player, 
    remove_game_lobby_player, get_game_lobby_players, get_all_online_players,
    disconnect_timers
)

def register_connection_events(sio):
    @sio.event
    async def connect(sid, environ, auth=None):
        print(f"✅ [سوكيت] لاعب اتصل بالسيرفر: {sid}")

    @sio.event
    async def disconnect(sid):
        print(f"❌ [سوكيت] لاعب انقطع اتصاله: {sid}")
        
        player = await get_connected_player(sid)
        
        if player:
            loc = player.get('location', '')
            
            # ✅ الإصلاح الرئيسي: إذا كان اللاعب داخل مباراة، لا نمسحه من القائمة العالمية
            # لأنه سيتصل بـ SID جديد من صفحة اللعبة ويُضيف نفسه تلقائياً
            if loc and loc.startswith('playing_'):
                print(f"🎮 [disconnect] {player.get('name')} انتقل لصفحة اللعبة — لن نمسحه من القوائم")
                # نمسح الـ SID القديم فقط (سيُستبدل بـ SID جديد من huroof_player_ready)
                await remove_connected_player(sid)
            else:
                # لاعب خرج من اللوبي فعلاً
                await remove_connected_player(sid)
                
                if loc and loc != 'global':
                    await remove_game_lobby_player(loc, sid)
                    players_list = await get_game_lobby_players(loc)
                    await sio.emit('update_game_lobby_players', players_list, room=loc)
                
                online_players = await get_all_online_players()
                await sio.emit('update_online_players', online_players)
                print(f"🧹 [disconnect] تمت إزالة {player.get('name')} من الذاكرة المركزية")

        if sid in disconnect_timers:
            disconnect_timers[sid].cancel()
            del disconnect_timers[sid]
