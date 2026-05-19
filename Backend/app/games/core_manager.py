import secrets
import random
import time
import string
from app.games.huroof.engine import HuroofGameState

matchmaking_queue = {}
rooms = {}

# ⏱️ مدة انتظار الغرفة الخاصة قبل حذفها (30 دقيقة)
WAITING_ROOM_TTL = 30 * 60


def add_to_queue(sid, name, avatar, game_mode, token=None):
    if game_mode not in matchmaking_queue:
        matchmaking_queue[game_mode] = []
    for p in matchmaking_queue[game_mode]:
        if p['sid'] == sid:
            return False, "أنت بالفعل في طابور البحث!"
    matchmaking_queue[game_mode].append({
        'sid': sid,
        'name': name,
        'avatar': avatar,
        'token': token,
        'time': time.time()
    })
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

        # 🛡️ room_code بـ secrets بدل random
        alphabet = string.ascii_uppercase + string.digits
        room_code = ''.join(secrets.choice(alphabet) for _ in range(6))

        rooms[room_code] = {
            'code': room_code,
            'type': 'public',
            'game_mode': game_mode,
            'state': 'starting',
            'created_at': time.time(),
            'players': [
                {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'],
                 'token': p1.get('token'), 'role': 'host', 'color': 'green'},
                {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'],
                 'token': p2.get('token'), 'role': 'guest', 'color': 'orange'},
            ],
            'game_state': HuroofGameState(p1['sid'], p2['sid']) if game_mode == 'huroof' else None,
        }

        room_players_data = {
            'green':  {'name': p1['name'], 'avatar': p1['avatar'], 'sid': p1['sid']},
            'orange': {'name': p2['name'], 'avatar': p2['avatar'], 'sid': p2['sid']},
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
        'created_at': time.time(),   # ⏱️ لمتابعة عمر الغرفة
        'players': [{'sid': sid, 'name': host_name, 'avatar': avatar, 'role': 'host', 'color': 'green'}],
        'game_state': None,
    }
    return rooms[room_code]


def join_room(room_code, sid, player_name, avatar):
    room = rooms.get(room_code)
    if not room:
        return False, "الغرفة غير موجودة"

    if room['state'] in ['starting', 'playing']:
        for p in room['players']:
            if p['sid'] == sid:
                return True, "reconnected_ready"

        for p in room['players']:
            if p['name'] == player_name and p['sid'] is None:
                p['sid'] = sid
                p['avatar'] = avatar
                return True, "reconnected"
        return False, "اللعبة جارية بالفعل"

    if room['state'] == 'waiting':
        for p in room['players']:
            if p['sid'] == sid:
                return True, "already_in_room"
        if len(room['players']) >= room['max_players']:
            return False, "الغرفة ممتلئة"
        room['players'].append({
            'sid': sid, 'name': player_name, 'avatar': avatar, 'role': 'guest', 'color': 'orange'
        })
        return True, "joined"

    return False, "حالة الغرفة غير صالحة"


def leave_room(sid):
    for room_code, room in list(rooms.items()):
        for p in room['players']:
            if p.get('sid') == sid:
                if room['state'] == 'waiting':
                    room['players'] = [x for x in room['players'] if x.get('sid') != sid]
                    if not room['players']:
                        del rooms[room_code]
                    return room_code, None
                else:
                    old_sid = p['sid']
                    p['old_sid'] = old_sid
                    p['sid'] = None
                    return room_code, room
    return None, None


def get_room_state(room_code):
    return rooms.get(room_code)


def cleanup_stale_waiting_rooms():
    """
    يحذف غرف الـ waiting التي تجاوز عمرها WAITING_ROOM_TTL.
    يُستدعى من cron_jobs.
    """
    now = time.time()
    stale = [
        code for code, r in list(rooms.items())
        if r.get('state') == 'waiting' and (now - r.get('created_at', now)) > WAITING_ROOM_TTL
    ]
    for code in stale:
        del rooms[code]
        print(f"🧹 [cleanup] حُذفت غرفة waiting متروكة: {code}")
    return len(stale)
