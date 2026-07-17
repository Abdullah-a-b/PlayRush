"""
 لعبة البنك — النمط المتزامن (على إطار BaseGame)

الآلية الجديدة:
- اللاعبان يلعبان **بالتزامن** (لا انتظار): لكل لاعب أسئلته ومؤقّته المستقلان.
- كل جولة: 60 ثانية لكل لاعب (تجري معاً). 4 جولات.
- تدرّج صعوبة لكل لاعب (سلّم): سهل (1نقطة)  متوسط (2)  صعب (3) كل 20 ثانية.
- "بنك" يحفظ المؤقّت في الآمن + يعيد السلّم للسهل.
- الخطأ يمسح المؤقّت + يعيد السلّم للسهل.
- الوقت **لا يتجمّد** أثناء الكتابة (منع ثغرة "8 ثوانٍ تفكير مجانية").
- تنتهي الجولة بانتهاء وقت الاثنين  بنك تلقائي  الجولة التالية.
- بعد 4 جولات: الأعلى رصيداً آمناً يفوز.
"""
import time

from app.domains.games.base import BaseGameState


class BankGameState(BaseGameState):
    """حالة مباراة 'البنك' المتزامنة."""

    TURN_SECONDS = 60          # مدة الجولة لكل لاعب (متزامنة)
    ANSWER_WINDOW = 8          # مهلة الكتابة بعد ضغط "إجابة" (الوقت يستمر!)
    TOTAL_ROUNDS = 4           # عدد الجولات
    LADDER_STEP = 20           # كل 20ث يصعد السلّم درجة (سهلمتوسطصعب)
    POINTS = {"easy": 1, "medium": 2, "hard": 3}

    def __init__(self, p1_sid, p2_sid, room_code=None, players=None):
        super().__init__(room_code=room_code or '', players=players or [])
        self.p1 = p1_sid
        self.p2 = p2_sid
        self.safe = {p1_sid: 0, p2_sid: 0}
        self.round = 1
        self.stage = 'waiting'   # waiting|playing|between|finished
        self.used_question_ids = []          # مشترك (منع تكرار بالمباراة)
        # حالة مستقلة لكل لاعب داخل الجولة
        self.pstate = {
            p1_sid: self._fresh_pstate(),
            p2_sid: self._fresh_pstate(),
        }

    @staticmethod
    def _fresh_pstate():
        return {
            'temp': 0,               # الرصيد المؤقت
            'started_at': None,      # بداية جولة اللاعب
            'ladder_base': 0,        # أساس سلّم الصعوبة
            'question': None,        # السؤال الحالي
            'question_diff': None,   # الصعوبة المعروضة (النقاط منها)
            'answering': False,      # يكتب الآن (الوقت مجمّد)
            'frozen_at': None,       # لحظة التجميد (كتابة/تحكيم AI)
            'done': False,           # انتهى وقته في هذه الجولة
        }

    def freeze(self, sid):
        """تجميد مؤقّت اللاعب (كتابة/تحكيم AI) — عدل: الكتابة لا تأكل وقتك."""
        ps = self.pstate[sid]
        if ps['frozen_at'] is None:
            ps['frozen_at'] = time.time()
            self.bump_version()

    def unfreeze(self, sid):
        """استئناف: نمدّ started_at بمدة التجميد (الوقت المتبقي كما كان)."""
        ps = self.pstate[sid]
        if ps['frozen_at'] is not None:
            frozen_for = time.time() - ps['frozen_at']
            if ps['started_at'] is not None:
                ps['started_at'] += frozen_for
            ps['frozen_at'] = None
            self.bump_version()

    # ---- إدارة الجولة ----
    def start_round(self):
        """يبدأ جولة متزامنة للاعبَين."""
        now = time.time()
        for sid in (self.p1, self.p2):
            ps = self._fresh_pstate()
            ps['started_at'] = now
            self.pstate[sid] = ps
        self.stage = 'playing'
        self.bump_version()

    def elapsed(self, sid):
        ps = self.pstate[sid]
        st = ps['started_at']
        if st is None:
            return 0
        now = ps['frozen_at'] if ps['frozen_at'] is not None else time.time()
        return now - st

    def remaining(self, sid):
        return max(0, self.TURN_SECONDS - self.elapsed(sid))

    def difficulty_now(self, sid):
        e = self.elapsed(sid) - self.pstate[sid]['ladder_base']
        if e < self.LADDER_STEP:
            return "easy"
        if e < self.LADDER_STEP * 2:
            return "medium"
        return "hard"

    def points_for(self, difficulty):
        return self.POINTS.get(difficulty, 1)

    # ---- الأفعال (لكل لاعب) ----
    def add_temp(self, sid, points):
        self.pstate[sid]['temp'] += points
        self.bump_version()

    def wipe_temp(self, sid):
        """خطأ: يمسح المؤقّت ويعيد السلّم للسهل (فكرة اللعبة)."""
        lost = self.pstate[sid]['temp']
        self.pstate[sid]['temp'] = 0
        self.pstate[sid]['ladder_base'] = self.elapsed(sid)
        self.bump_version()
        return lost

    def bank(self, sid):
        """يحفظ المؤقّت في الآمن + يعيد السلّم للسهل."""
        amount = self.pstate[sid]['temp']
        self.safe[sid] = self.safe.get(sid, 0) + amount
        self.pstate[sid]['temp'] = 0
        self.pstate[sid]['ladder_base'] = self.elapsed(sid)
        self.bump_version()
        return amount

    def mark_done(self, sid):
        self.pstate[sid]['done'] = True
        self.bump_version()

    def both_done(self):
        return self.pstate[self.p1]['done'] and self.pstate[self.p2]['done']

    def advance_round(self):
        """يرجع 'next' أو 'finished'."""
        self.round += 1
        if self.round > self.TOTAL_ROUNDS:
            return 'finished'
        self.stage = 'between'
        self.bump_version()
        return 'next'

    def temp_of(self, sid):
        return self.pstate[sid]['temp']

    def temps(self):
        return {self.p1: self.pstate[self.p1]['temp'],
                self.p2: self.pstate[self.p2]['temp']}

    def remap_sid(self, old_sid, new_sid):
        """إعادة ربط لاعب عائد (sid جديد) بحالته — يمنع نتائج 0-0 الوهمية."""
        if old_sid == new_sid or old_sid not in (self.p1, self.p2):
            return
        if self.p1 == old_sid:
            self.p1 = new_sid
        else:
            self.p2 = new_sid
        for d in (self.safe, self.pstate):
            if old_sid in d:
                d[new_sid] = d.pop(old_sid)
        if self.winner == old_sid:
            self.winner = new_sid
        self.bump_version()

    def opponent(self, sid):
        return self.p2 if sid == self.p1 else self.p1

    def is_player_in_game(self, sid):
        return sid in (self.p1, self.p2)

    def leader(self):
        if self.safe.get(self.p1, 0) == self.safe.get(self.p2, 0):
            return None
        return self.p1 if self.safe.get(self.p1, 0) > self.safe.get(self.p2, 0) else self.p2

    def to_dict(self):
        return {
            'p1': self.p1, 'p2': self.p2,
            'room_code': self.room_code, 'players': self.players,
            'winner': self.winner, 'stage': self.stage,
            'created_at': self.created_at, 'state_version': self.state_version,
            'safe': self.safe, 'round': self.round,
            'used_question_ids': self.used_question_ids,
            'pstate': self.pstate,
        }

    @classmethod
    def from_dict(cls, data):
        obj = cls(data['p1'], data['p2'],
                  room_code=data.get('room_code'), players=data.get('players', []))
        obj.winner = data.get('winner')
        obj.stage = data.get('stage', 'waiting')
        obj.created_at = data.get('created_at', time.time())
        obj.state_version = data.get('state_version', 0)
        obj.safe = data.get('safe', {})
        obj.round = data.get('round', 1)
        obj.used_question_ids = data.get('used_question_ids', [])
        obj.pstate = data.get('pstate', {})
        return obj
