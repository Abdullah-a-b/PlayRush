import random
import time
import string
# تم الاستبدال بالكلاس الجديد المتوافق مع Redis
from app.games.huroof.engine import HuroofGameEngine

matchmaking_queue = {}  
rooms = {}              

def add_to_queue(sid, name, avatar, game_mode):
    if game_mode not in matchmaking_queue:
        matchmaking_queue[game_mode] = []
    for p in matchmaking_queue[game_mode]:
        if p['sid'] == sid:
            return False, "أنت بالفعل في طابور البحث!"
    matchmaking_queue[game_mode].append({'sid': sid, 'name': name, 'avatar': avatar, 'time': time.time()})
    return True, "تم الانضمام لطابور البحث"

def remove_from_queue(sid):
    for mode, queue in matchmaking_queue.items():
        for i, p in enumerate(queue):
            if p['sid'] == sid:
                queue.pop(i)
                return True
    return False

def check_queue_for_match(game_mode):
    queue = matchmaking_queue.get(game_mode, [])
    if len(queue) >= 2:
        players = [queue.pop(0), queue.pop(0)]
        random.shuffle(players) 
        p1, p2 = players[0], players[1]
        
        room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        rooms[room_code] = {
            'code': room_code,
            'type': 'public',
            'game_mode': game_mode,
            'state': 'starting',
            'players': [
                {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'], 'role': 'host', 'color': 'green'},
                {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'], 'role': 'guest', 'color': 'orange'}
            ],
            # هنا نقوم بتشغيل محرك اللعبة بناءً على نوع اللعبة
            'game_state': HuroofGameEngine(p1['sid'], p2['sid']) if game_mode == 'huroof' else None
        }
        
        room_players_data = {
            'green': {'name': p1['name'], 'avatar': p1['avatar'], 'sid': p1['sid']},
            'orange': {'name': p2['name'], 'avatar': p2['avatar'], 'sid': p2['sid']}
        }
        return True, room_code, [p1, p2], room_players_data
    return False, None, None, None

def create_room(room_code, sid, host_name, max_players, game_mode, ip_address, avatar, room_type="private"):
    rooms[room_code] = {
        'code': room_code,
        'host': sid,
        'max_players': max_players,
        'game_mode': game_mode,
        'ip': ip_address,
        'state': 'waiting',
        'type': room_type,
        'players': [{'sid': sid, 'name': host_name, 'avatar': avatar, 'role': 'host', 'color': 'green'}],
        'game_state': None
    }
    return rooms[room_code]

def join_room(room_code, sid, player_name, avatar):
    room = rooms.get(room_code)
    if not room: return False, "الغرفة غير موجودة"
    
    if room['state'] in ['starting', 'playing']:
        assigned_player = None
        for p in room['players']:
            if p['sid'] == sid: return True, "reconnected_ready"
        
        for p in room['players']:
            if p['name'] == player_name and p['sid'] is None:
                assigned_player = p
                break
        
        if not assigned_player:
            for p in room['players']:
                if p['sid'] is None:
                    assigned_player = p
                    p['name'] = player_name
                    break
                    
        if assigned_player:
            old_sid = assigned_player.get('old_sid')
            assigned_player['old_sid'] = old_sid
            assigned_player['sid'] = sid
            
            gs = room.get('game_state')
            if gs:
                if assigned_player['color'] == 'green': gs.p1 = sid
                elif assigned_player['color'] == 'orange': gs.p2 = sid
                if gs.turn == old_sid: gs.turn = sid
                if gs.buzzed_player == old_sid: gs.buzzed_player = sid
                
            if all(player['sid'] is not None for player in room['players']):
                room['state'] = 'playing'
                
            return True, "reconnected_ready"
            
        return False, "الغرفة ممتلئة"

    if room['state'] != 'waiting': return False, "المباراة بدأت بالفعل"
    if len(room['players']) >= room['max_players']: return False, "الغرفة ممتلئة"
    for p in room['players']:
        if p['sid'] == sid: return False, "أنت متصل بالفعل"
        
    color = 'orange' if len(room['players']) == 1 else 'spectator'
    room['players'].append({'sid': sid, 'name': player_name, 'avatar': avatar, 'role': 'guest', 'color': color})
    
    return True, "تم الانضمام بنجاح"

def get_room_state(room_code):
    return rooms.get(room_code)

def leave_room(sid):
    for code, room in list(rooms.items()):
        for i, p in enumerate(room['players']):
            if p['sid'] == sid:
                if room['state'] == 'waiting':
                    room['players'].pop(i)
                    if len(room['players']) == 0:
                        del rooms[code]
                else:
                    p['old_sid'] = p['sid']
                    p['sid'] = None
                return code, room
    return None, None