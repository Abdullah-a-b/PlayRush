"""
 مسيرة لاعب — حالة المباراة (على إطار BaseGame)

الآلية:
- يُعرض لاعب كرة عبر أنديته تدريجياً (نادٍ كل 7 ثوانٍ).
- من يضغط الجرس يأخذ 7 ثوانٍ للكتابة. صح قبل اكتمال المسيرة = نقطتان، بعدها = نقطة.
- الخطأ أو انتهاء الوقت = سترايك  (لكل لاعب محاولتان xx). يقدر يجيب ثانيةً.
  العدّاد الأصلي (بين الأندية) يكمل من حيث توقّف بعد الخطأ.
- تُعرض 5 شخصيات محدّدة. لو اكتملت مسيرة شخصية بلا إجابة، أو الاثنان xx 
  تُستبدل الشخصية بأخرى (تأخذ نفس الرقم — لا يؤثر على عدد الـ5).
- بعد الـ5: الأعلى نقاطاً يفوز. عند التعادل تُضاف شخصية إضافية حتى يفوز أحدهم.
"""
import time

from app.domains.games.base import BaseGameState


class CareerGameState(BaseGameState):
    """حالة مباراة 'مسيرة لاعب'."""

    TOTAL_PLAYERS = 5
    REVEAL_INTERVAL = 5     # ثوانٍ بين كشف نادٍ والذي يليه
    FINAL_WINDOW = 10       # نافذة آخر نادٍ (فرصة الإجابة بنقطة)
    ANSWER_WINDOW = 10      # نافذة الكتابة بعد الجرس
    MAX_STRIKES = 2

    def __init__(self, p1_sid, p2_sid, room_code=None, players=None):
        super().__init__(room_code=room_code or '', players=players or [])
        self.p1 = p1_sid
        self.p2 = p2_sid
        self.scores = {p1_sid: 0, p2_sid: 0}
        self.player_index = 0
        self.tiebreaker = False
        self.current_player = None
        self.revealed_count = 0
        self.career_complete = False
        self.stage = 'waiting'          # waiting | revealing | buzzed | finished
        self.buzzed_player = None
        self.strikes = {p1_sid: 0, p2_sid: 0}
        self.used_player_ids = []
        self.reveal_remaining = None
        self.helps_used = {p1_sid: set(), p2_sid: set()}
        self.state_version = 0

    def start_new_player(self, player_data, advance_index=True):
        if advance_index:
            self.player_index += 1
        self.current_player = player_data
        self.revealed_count = 1
        self.career_complete = (len(player_data.get('clubs', [])) <= 1)
        # للاعب نادي واحد: الفترة الأولى (10 ثوانٍ) = نقطتان، بعدها = نقطة
        self.first_reveal_done = False
        self.stage = 'revealing'
        self.buzzed_player = None
        self.strikes = {self.p1: 0, self.p2: 0}
        self.reveal_remaining = None
        if player_data.get('id') is not None:
            self.used_player_ids.append(player_data['id'])
        self.bump_version()

    def reveal_next_club(self):
        clubs = (self.current_player or {}).get('clubs', [])
        # أي كشف تالٍ يعني الفترة الأولى انتهت
        self.first_reveal_done = True
        if self.revealed_count >= len(clubs):
            self.career_complete = True
            return False
        self.revealed_count += 1
        if self.revealed_count >= len(clubs):
            self.career_complete = True
        self.bump_version()
        return True

    def can_buzz(self, sid):
        if sid not in (self.p1, self.p2):
            return False
        if self.stage != 'revealing':
            return False
        if self.buzzed_player is not None:
            return False
        if self.strikes.get(sid, 0) >= self.MAX_STRIKES:
            return False
        return True

    def register_buzz(self, sid):
        self.buzzed_player = sid
        self.stage = 'buzzed'
        self.bump_version()

    def add_strike(self, sid):
        self.strikes[sid] = self.strikes.get(sid, 0) + 1
        self.bump_version()
        return self.strikes[sid]

    def both_struck_out(self):
        return (self.strikes.get(self.p1, 0) >= self.MAX_STRIKES and
                self.strikes.get(self.p2, 0) >= self.MAX_STRIKES)

    def score_for_current(self):
        """نقطتان قبل انتهاء المسيرة، نقطة بعدها.
        لاعب نادي واحد: الفترة الأولى (10 ثوانٍ) = 2، بعدها = 1."""
        if self.career_complete:
            return 1 if getattr(self, 'first_reveal_done', False) else 2
        return 2

    def award(self, sid, points):
        self.scores[sid] = self.scores.get(sid, 0) + points
        self.bump_version()

    def opponent(self, sid):
        return self.p2 if sid == self.p1 else self.p1

    def revealed_clubs(self):
        clubs = (self.current_player or {}).get('clubs', [])
        return clubs[: self.revealed_count]

    def all_players_done(self):
        return self.player_index >= self.TOTAL_PLAYERS

    def is_tie(self):
        return self.scores.get(self.p1, 0) == self.scores.get(self.p2, 0)

    def leader(self):
        if self.is_tie():
            return None
        return self.p1 if self.scores.get(self.p1, 0) > self.scores.get(self.p2, 0) else self.p2

    def check_winner(self):
        if not self.all_players_done():
            return None
        return self.leader()

    def to_dict(self):
        return {
            'p1': self.p1, 'p2': self.p2,
            'room_code': self.room_code, 'players': self.players,
            'winner': self.winner, 'stage': self.stage,
            'created_at': self.created_at, 'state_version': self.state_version,
            'scores': self.scores, 'player_index': self.player_index,
            'tiebreaker': self.tiebreaker, 'current_player': self.current_player,
            'revealed_count': self.revealed_count, 'career_complete': self.career_complete,
            'first_reveal_done': getattr(self, 'first_reveal_done', False),
            'buzzed_player': self.buzzed_player, 'strikes': self.strikes,
            'used_player_ids': self.used_player_ids, 'reveal_remaining': self.reveal_remaining,
            'helps_used': {k: list(v) for k, v in self.helps_used.items()},
        }

    @classmethod
    def from_dict(cls, data):
        obj = cls(data['p1'], data['p2'],
                  room_code=data.get('room_code'), players=data.get('players', []))
        obj.winner = data.get('winner')
        obj.stage = data.get('stage', 'waiting')
        obj.created_at = data.get('created_at', time.time())
        obj.state_version = data.get('state_version', 0)
        obj.scores = data.get('scores', {})
        obj.player_index = data.get('player_index', 0)
        obj.tiebreaker = data.get('tiebreaker', False)
        obj.current_player = data.get('current_player')
        obj.revealed_count = data.get('revealed_count', 0)
        obj.career_complete = data.get('career_complete', False)
        obj.first_reveal_done = data.get('first_reveal_done', False)
        obj.buzzed_player = data.get('buzzed_player')
        obj.strikes = data.get('strikes', {})
        obj.used_player_ids = data.get('used_player_ids', [])
        obj.reveal_remaining = data.get('reveal_remaining')
        obj.helps_used = {k: set(v) for k, v in data.get('helps_used', {}).items()}
        return obj

    def is_player_in_game(self, sid):
        return sid in (self.p1, self.p2)
