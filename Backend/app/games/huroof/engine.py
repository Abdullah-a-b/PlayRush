import random
import time

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
    """كلاس يدير حالة مباراة حروف بالكامل ويمنع الغش"""
    def __init__(self, p1_sid, p2_sid):
        self.p1 = p1_sid
        self.p2 = p2_sid
        self.green_wins = 0
        self.orange_wins = 0
        self.round_number = 1

        self.points = {'green': 0, 'orange': 0} 
        self.points_to_win_match = 2              
        
        self.used_questions = [] 
        self.used_answers = [] 
        
        self.reset_board()
        self.state_version = 0

        self.question_start_time = 0.0  # وقت بدء السؤال
        self.last_action_time = 0.0     # وقت آخر حركة للاعب

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
        self.answer_start_time = 0.0

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