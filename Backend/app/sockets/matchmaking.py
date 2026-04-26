import asyncio
from app.sockets.state import (
    join_matchmaking, leave_matchmaking, check_matchmaking, 
    create_active_room, get_connected_player
)

def register_matchmaking_events(sio):

    @sio.on('find_match')
    async def find_match(sid, data):
        game_mode = data.get('gameMode', 'huroof')
        
        # جلب بيانات اللاعب المؤكدة من Redis
        player = await get_connected_player(sid)
        if not player:
            return
            
        player_name = player.get('name', 'مجهول')
        player_avatar = player.get('avatar', '')
        
        print(f"🔍 [ماتش ميكنج] اللاعب {player_name} يبحث عن خصم في {game_mode}")
        
        player_data = {
            'sid': sid,
            'name': player_name,
            'avatar': player_avatar
        }

        # 1. إضافة اللاعب لطابور الانتظار
        await join_matchmaking(game_mode, player_data)

        # 2. إرسال تأكيد للاعب
        await sio.emit('matchmaking_started', {'message': 'جاري البحث عن خصم...'}, to=sid)

        # 3. محاولة سحب لاعبين من الطابور لبدء مباراة
        p1, p2 = await check_matchmaking(game_mode)
        
        if p1 and p2:
            # تم العثور على مباراة!
            print(f"⚔️ [ماتش ميكنج] مباراة جديدة! {p1['name']} ضد {p2['name']}")
            
            # إنشاء غرفة في Redis
            room_id, room_data = await create_active_room(game_mode, p1, p2)
            
            # إدخال اللاعبين في الغرفة الخاصة بالسوكيت
            await sio.enter_room(p1['sid'], room_id)
            await sio.enter_room(p2['sid'], room_id)
            
            match_payload = {
                'room_code': room_id,
                'players': [
                    {'name': p1['name'], 'avatar': p1['avatar'], 'color': 'green'},
                    {'name': p2['name'], 'avatar': p2['avatar'], 'color': 'orange'}
                ]
            }
            
            # إرسال match_found للاعبين لرؤية بعضهم — اللعبة تبدأ مباشرة بعد الانتقال
            await sio.emit('match_found', match_payload, room=room_id)

    @sio.on('cancel_matchmaking')
    async def cancel_matchmaking(sid, data):
        game_mode = data.get('gameMode', 'huroof')
        print(f"🛑 [ماتش ميكنج] لاعب ألغى البحث في {game_mode}")
        await leave_matchmaking(game_mode, sid)
        await sio.emit('matchmaking_cancelled', {'message': 'تم إلغاء البحث.'}, to=sid)