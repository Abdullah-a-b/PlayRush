import random
import time
import json
from app.sockets.state import redis_db

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

class HuroofGameEngine:
    """كلاس يدير حالة مباراة حروف بالكامل ويدعم التوسع اللحظي (Scalability) عبر Redis"""
    def __init__(self, room_id, room_data):
        self.room_id = room_id
        self.room_data = room_data # 👈 العقل المركزي الآن هو هذا القاموس

        # تعريف اللاعبين من البيانات القادمة من Redis
        players = self.room_data.get('players', [])
        self.p1 = players[0].get('sid') if len(players) > 0 else None
        self.p2 = players[1].get('sid') if len(players) > 1 else None

    async def _save_state(self):
        """يحفظ أي تغييرات في العقل المركزي Redis فوراً"""
        await redis_db.hset("active_rooms", self.room_id, json.dumps(self.room_data))

    async def initialize_board(self):
        """تهيئة اللوحة والمباراة بالكامل لأول مرة فقط"""
        if 'board' not in self.room_data:
            self.room_data['green_wins'] = 0
            self.room_data['orange_wins'] = 0
            self.room_data['round_number'] = 1
            self.room_data['points'] = {'green': 0, 'orange': 0}
            self.room_data['used_questions'] = []
            self.room_data['used_answers'] = []
            self.room_data['state_version'] = 0
            
            self._reset_board_logic()
            await self._save_state()

    def _reset_board_logic(self, starting_turn=None):
        """إعادة بناء اللوحة للحالة المبدئية (أو عند بدء جولة جديدة)"""
        letters = random.sample(ARABIC_LETTERS, 25)
        self.room_data['board'] = [{'index': i, 'letter': letters[i], 'color': None} for i in range(25)]
        
        if starting_turn == 'green': 
            self.room_data['turn'] = self.p1
        elif starting_turn == 'orange': 
            self.room_data['turn'] = self.p2
        else: 
            self.room_data['turn'] = random.choice([self.p1, self.p2])
            
        self.room_data['active_hex'] = None
        self.room_data['current_question'] = None
        self.room_data['stage'] = 'selecting'
        self.room_data['buzzed_player'] = None
        self.room_data['failed_attempts'] = []
        
        # ⚠️ ملاحظة مهمة: في كودك القديم استخدمت set()، 
        # لكن Redis يتعامل مع JSON والذي لا يدعم الـ set، لذلك حولناها إلى قائمة (List)
        self.room_data['skip_votes'] = [] 
        
        self.room_data['answer_start_time'] = 0.0
        self.room_data['question_start_time'] = 0.0
        self.room_data['last_action_time'] = time.time()

    async def check_win(self, color):
        """خوارزمية البحث المتقدمة (BFS) للتحقق من اتصال المسار والفوز"""
        board = self.room_data.get('board', [])
        start_nodes = []
        target_condition = None
        
        if color == 'green':
            # الأخضر من الأعلى للأسفل
            start_nodes = [i for i, h in enumerate(board) if h['color'] == 'green' and i // 5 == 0]
            target_condition = lambda idx: idx // 5 == 4
        elif color == 'orange':
            # البرتقالي من اليسار لليمين
            start_nodes = [i for i, h in enumerate(board) if h['color'] == 'orange' and i % 5 == 0]
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
                    if board[n_idx]['color'] == color and n_idx not in visited:
                        queue.append(n_idx)
        return False

    async def claim_hex_and_check(self, hex_index, color):
        """أداة مساعدة: تسجيل الخلية باسم اللاعب والتحقق مما إذا كان قد فاز بالمباراة"""
        self.room_data['board'][hex_index]['color'] = color
        self.room_data['state_version'] += 1
        
        is_win = await self.check_win(color)
        if is_win:
            self.room_data[f'{color}_wins'] += 1
            if self.room_data[f'{color}_wins'] >= 2: # الفوز بمباراتين من أصل 3
                self.room_data['state'] = 'finished'
                self.room_data['match_winner'] = color
            else:
                self.room_data['round_number'] += 1
                loser = 'orange' if color == 'green' else 'green'
                self._reset_board_logic(starting_turn=loser)
        else:
            self.room_data['stage'] = 'selecting'
            self.room_data['active_hex'] = None
            self.room_data['turn'] = self.p2 if self.room_data['turn'] == self.p1 else self.p1
            
        await self._save_state()
        return is_win