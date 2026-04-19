import random
import time
import string

# ==========================================
# 📊 قواعد البيانات المؤقتة في الذاكرة
# ==========================================
matchmaking_queue = {}  # {game_mode: [{'sid': sid, 'name': name, 'avatar': avatar, 'time': float}]}
rooms = {}              # {room_code: room_data}

ARABIC_LETTERS = list('أبتثجحخدذرزسشصضطظعغفقكلمنهوي')

# ==========================================
# 🧠 محرك اللعبة (Game Engine) - خوارزميات حروف
# ==========================================
def get_neighbors(row, col):
    """تحديد جيران الخلية السداسية بدقة بناءً على الصف الزوجي/الفردي"""
    neighbors = []
    if row % 2 == 0:
        moves = [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1)]
    else:
        moves = [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0)]
        
    for dr, dc in moves:
        r, c = row + dr, col + dc
        if 0 <= r < 5 and 0 <= c < 5:
            neighbors.append((r, c))
    return neighbors

class HuroofGameState:
    """كلاس يدير حالة مباراة حروف بالكامل ويمنع الغش"""
    def __init__(self, p1_sid, p2_sid):
        self.p1 = p1_sid
        self.p2 = p2_sid
        self.green_wins = 0
        self.orange_wins = 0
        self.round_number = 1

        # 🏆 نظام الجولات (Best of 3)
        self.points = {'green': 0, 'orange': 0}  # نقاط الجولات المكتسبة
        self.points_to_win_match = 2              # يفوز من يحقق جولتين أولاً
        
        self.used_questions = [] 
        self.used_answers = [] # 🚀 الذاكرة الحديدية لمنع الذكاء الاصطناعي من التكرار
        
        self.reset_board()
        self.state_version = 0

    def reset_board(self):
        """إعادة ضبط اللوحة لجولة جديدة"""
        letters = random.sample(ARABIC_LETTERS, 25)
        self.board = [{'index': i, 'letter': letters[i], 'color': None} for i in range(25)]
        
        # اختيار عشوائي لمن يبدأ
        self.turn = random.choice([self.p1, self.p2]) 
        self.active_hex = None # السداسي الأصفر الحالي
        self.current_question = None
        
        # المراحل: 'selecting', 'r1_buzz', 'r1_answer', 'r2_buzz', 'r2_answer'
        self.stage = 'selecting' 
        
        self.buzzed_player = None
        self.failed_attempts = [] # SIDs لمن جاوبوا خطأ في هذه المرحلة
        self.skip_votes = set()   # SIDs لمن طلبوا تغيير السؤال


    def reset_round_state(self, starting_turn=None):
        """إعادة ضبط اللوحة لجولة جديدة مع تحديد اللاعب الذي يبدأ (الخاسر يبدأ)"""
        letters = random.sample(ARABIC_LETTERS, 25)
        self.board = [{'index': i, 'letter': letters[i], 'color': None} for i in range(25)]

        # الخاسر يبدأ الجولة الجديدة، أو عشوائي إذا لم يُحدَّد
        if starting_turn == 'green':
            self.turn = self.p1
        elif starting_turn == 'orange':
            self.turn = self.p2
        else:
            self.turn = random.choice([self.p1, self.p2])

        self.active_hex = None
        self.current_question = None
        self.stage = 'selecting'
        self.buzzed_player = None
        self.failed_attempts = []
        self.skip_votes = set()

    def check_win(self, color):
        """خوارزمية البحث (Pathfinding) للتحقق من الفوز في السيرفر لمنع غش الفرونت إند"""
        start_nodes = []
        target_condition = None
        
        if color == 'green':
            # الأخضر يبدأ من الصف 0 (أول 5 خلايا) ويصل للصف 4
            start_nodes = [i for i, h in enumerate(self.board) if h['color'] == 'green' and i // 5 == 0]
            target_condition = lambda idx: idx // 5 == 4
        elif color == 'orange':
            # البرتقالي يبدأ من العمود 0 ويصل للعمود 4
            start_nodes = [i for i, h in enumerate(self.board) if h['color'] == 'orange' and i % 5 == 0]
            target_condition = lambda idx: idx % 5 == 4
        else:
            return False
            
        # خوارزمية البحث بالعمق/العرض (BFS)
        for start in start_nodes:
            visited = set()
            queue = [start]
            
            while queue:
                curr = queue.pop(0)
                if curr in visited: continue
                visited.add(curr)
                
                # هل وصلنا للضفة الأخرى؟
                if target_condition(curr):
                    return True
                    
                # إضافة الجيران المطابقين للون
                r, c = curr // 5, curr % 5
                for nr, nc in get_neighbors(r, c):
                    n_idx = nr * 5 + nc
                    if self.board[n_idx]['color'] == color and n_idx not in visited:
                        queue.append(n_idx)
                        
        return False

# ==========================================
# 🌐 إدارة طوابير البحث (Matchmaking)
# ==========================================
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
        random.shuffle(players) # 🎲 خلط اللاعبين لتوزيع الألوان عشوائياً!
        p1, p2 = players[0], players[1]
        
        room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # إنشاء الغرفة في حالة 'starting'
        rooms[room_code] = {
            'code': room_code,
            'type': 'public',
            'game_mode': game_mode,
            'state': 'starting',
            'players': [
                {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'], 'role': 'host', 'color': 'green'},
                {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'], 'role': 'guest', 'color': 'orange'}
            ],
            # 🚀 توليد اللوحة فوراً قبل انتقالهم للصفحة!
            'game_state': HuroofGameState(p1['sid'], p2['sid']) if game_mode == 'huroof' else None
        }
        
        room_players_data = {
            'green': {'name': p1['name'], 'avatar': p1['avatar'], 'sid': p1['sid']},
            'orange': {'name': p2['name'], 'avatar': p2['avatar'], 'sid': p2['sid']}
        }
        return True, room_code, [p1, p2], room_players_data
    return False, None, None, None

# ==========================================
# 🚪 إدارة الغرف الخاصة
# ==========================================
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
        # 🛡️ تحسين: إذا كان اللاعب متصلاً بالفعل بهذا الـ SID، اعتبره انضماماً ناجحاً
        for p in room['players']:
            if p['sid'] == sid:
                return True, "reconnected_ready"
        
        # محاولة المطابقة بالاسم
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

    # الانضمام الطبيعي للغرف الخاصة
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
                    # 🛡️ الغرفة بدأت أو تنتقل، لا تحذفها! احفظ الـ SID القديم وصفر الحالي
                    p['old_sid'] = p['sid']
                    p['sid'] = None
                return code, room
    return None, None