import random

ARABIC_LETTERS = list('أبتثجحخدذرزسشصضطظعغفقكلمنهوي')

def get_neighbors(row, col):
    """تحديد جيران الخلية السداسية بدقة"""
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
    """كلاس يدير حالة مباراة حروف بالكامل ويمنع الغش.

     جاهز لإطار BaseGame: يوفّر to_dict/from_dict + حقول أساسية مشتركة
    (room_code/players/winner) دون كسر الـ constructor القديم (p1_sid, p2_sid).
    """
    def __init__(self, p1_sid, p2_sid, room_code=None, players=None):
        self.p1 = p1_sid
        self.p2 = p2_sid
        # حقول أساسية مشتركة (BaseGame) — اختيارية للتوافق الخلفي
        self.room_code = room_code
        self.players = players or []
        self.winner = None  # sid الفائز عند الانتهاء

        self.green_wins = 0
        self.orange_wins = 0
        self.round_number = 1

        self.points = {'green': 0, 'orange': 0} 
        self.points_to_win_match = 2              
        
        self.used_questions = [] 
        self.used_answers = [] 
        
        # نظام المساعدات: نتتبّع ما استُخدم لكل لاعب (مرة واحدة في المباراة)
        # المفتاح = sid اللاعب، القيمة = set بمعرّفات المساعدات المستخدمة
        self.helps_used = {p1_sid: set(), p2_sid: set()}
        self.active_timer = None  # بيانات المؤقّت النشط (لمساعدة تمديد الوقت)
        
        self.reset_board()
        self.state_version = 0

    # ==========================================
    # Redis-ready serialization (BaseGame)
    # ==========================================
    def bump_version(self):
        self.state_version += 1
        return self.state_version

    def is_player_in_game(self, sid):
        return sid in (self.p1, self.p2)

    def to_dict(self):
        """يحوّل الحالة لـ dict قابل للتخزين (Redis-ready). الـ sets تتحوّل لقوائم."""
        return {
            'p1': self.p1, 'p2': self.p2,
            'room_code': self.room_code, 'players': self.players, 'winner': self.winner,
            'green_wins': self.green_wins, 'orange_wins': self.orange_wins,
            'round_number': self.round_number, 'points': self.points,
            'points_to_win_match': self.points_to_win_match,
            'used_questions': self.used_questions, 'used_answers': self.used_answers,
            'helps_used': {k: list(v) for k, v in self.helps_used.items()},
            'active_timer': self.active_timer,
            'board': self.board, 'turn': self.turn, 'active_hex': self.active_hex,
            'current_question': self.current_question, 'stage': self.stage,
            'buzzed_player': self.buzzed_player, 'failed_attempts': self.failed_attempts,
            'skip_votes': list(self.skip_votes), 'state_version': self.state_version,
            'preferred_category': getattr(self, 'preferred_category', {}),
        }

    @classmethod
    def from_dict(cls, data):
        """يعيد بناء الحالة من dict (من Redis). الـ sets تُعاد من القوائم."""
        obj = cls(data['p1'], data['p2'],
                  room_code=data.get('room_code'), players=data.get('players', []))
        obj.winner = data.get('winner')
        obj.green_wins = data.get('green_wins', 0)
        obj.orange_wins = data.get('orange_wins', 0)
        obj.round_number = data.get('round_number', 1)
        obj.points = data.get('points', {'green': 0, 'orange': 0})
        obj.points_to_win_match = data.get('points_to_win_match', 2)
        obj.used_questions = data.get('used_questions', [])
        obj.used_answers = data.get('used_answers', [])
        obj.helps_used = {k: set(v) for k, v in data.get('helps_used', {}).items()}
        obj.active_timer = data.get('active_timer')
        obj.board = data.get('board', obj.board)
        obj.turn = data.get('turn', obj.turn)
        obj.active_hex = data.get('active_hex')
        obj.current_question = data.get('current_question')
        obj.stage = data.get('stage', 'selecting')
        obj.buzzed_player = data.get('buzzed_player')
        obj.failed_attempts = data.get('failed_attempts', [])
        obj.skip_votes = set(data.get('skip_votes', []))
        obj.state_version = data.get('state_version', 0)
        obj.preferred_category = data.get('preferred_category', {})
        return obj

    def reset_board(self):
        letters = random.sample(ARABIC_LETTERS, 25)
        self.board = [{'index': i, 'letter': letters[i], 'color': None} for i in range(25)]
        self.turn = random.choice([self.p1, self.p2]) 
        self.active_hex = None 
        self.current_question = None
        self.stage = 'selecting' 
        self.buzzed_player = None
        self.failed_attempts = [] 
        self.skip_votes = set()   

    def reset_round_state(self, starting_turn=None):
        letters = random.sample(ARABIC_LETTERS, 25)
        self.board = [{'index': i, 'letter': letters[i], 'color': None} for i in range(25)]
        if starting_turn == 'green': self.turn = self.p1
        elif starting_turn == 'orange': self.turn = self.p2
        else: self.turn = random.choice([self.p1, self.p2])
        self.active_hex = None
        self.current_question = None
        self.stage = 'selecting'
        self.buzzed_player = None
        self.failed_attempts = []
        self.skip_votes = set()

    def check_win(self, color):
        start_nodes = []
        target_condition = None
        
        if color == 'green':
            start_nodes = [i for i, h in enumerate(self.board) if h['color'] == 'green' and i // 5 == 0]
            target_condition = lambda idx: idx // 5 == 4
        elif color == 'orange':
            start_nodes = [i for i, h in enumerate(self.board) if h['color'] == 'orange' and i % 5 == 0]
            target_condition = lambda idx: idx % 5 == 4
        else:
            return False
            
        for start in start_nodes:
            visited = set()
            queue = [start]
            while queue:
                curr = queue.pop(0)
                if curr in visited: continue
                visited.add(curr)
                if target_condition(curr): return True
                r, c = curr // 5, curr % 5
                for nr, nc in get_neighbors(r, c):
                    n_idx = nr * 5 + nc
                    if self.board[n_idx]['color'] == color and n_idx not in visited:
                        queue.append(n_idx)
        return False