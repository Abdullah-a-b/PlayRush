"""
🧠 لعبة "ماذا تعرف" — أدوار على أسئلة قوائم (على إطار BaseGame)

الآلية (تصميم المطوّر):
- سؤال قائمة موحّد للطرفين (مثل: "اذكر عواصم دول عربية") — بمئات
  الإجابات الصالحة، منفصل تماماً عن بنك أسئلة "البنك".
- أدوار: البادئ يُحدَّد عشوائياً بأول جولة ثم يتناوب البادئون.
  إجابة صحيحة → الدور ينتقل للخصم، وهكذا.
- السترايك (لكل لاعب داخل الجولة) بحالتين: خطأ مباشر (ميونخ ليست
  عاصمة ألمانيا) أو انتهاء عدّاد الكتابة (10 ثوانٍ ثابتة للطرفين).
  الإجابة المكررة داخل الجولة = خطأ مباشر أيضاً.
  بعد الخطأ/المهلة ينتقل الدور للخصم (لا يحترق لاعب وحده).
- الجولة تنتهي ببلوغ أحدهما 3 سترايكات (يخسر السؤال = 0 نقاط)،
  والناجي: خرج بصفر سترايك = نقطتان، بسترايك أو اثنين = نقطة.
- 5 أسئلة للمباراة، الأعلى نقاطاً يفوز. تعادل → جولة حاسمة إضافية
  (حتى 2)، ثم الأقل سترايكات إجمالاً، ثم البادئ الثاني (عِوض الدور).
- حافة نادرة: نفدت إجابات القائمة والاثنان أحياء → كلٌّ يُنقّط
  بقاعدة سترايكاته (0→2، وإلا 1) — لا خاسر.
"""
import time

from app.games.base import BaseGameState


class KnowledgeGameState(BaseGameState):
    """حالة مباراة 'ماذا تعرف' — أدوار وقوائم وسترايكات."""

    TOTAL_ROUNDS = 5
    MAX_STRIKES = 3
    TURN_SECONDS = 10
    GRACE_BUFFER = 0.7   # ⏱️ ثوانٍ إضافية يتحملها الـ backend فوق عدّاد اللاعب
                          # تعوّض تأخر الشبكة (RTT) بين الـ server والـ client
                          # اللاعب يرى 10ث، الـ backend ينتظر 10.7ث فعلياً
    BETWEEN_SECONDS = 3.5
    MAX_TIEBREAK = 2

    def __init__(self, p1_sid, p2_sid, room_code=None, players=None):
        super().__init__(room_code=room_code or '', players=players or [])
        self.p1 = p1_sid
        self.p2 = p2_sid
        # 🔑 نحفظ user_id لكل slot (مرساة ثابتة لا تتغيّر — لمطابقة
        # sid موثوقة عند تغيّره بالطابور/reconnect)
        self.p1_uid = None
        self.p2_uid = None
        if players and len(players) >= 2:
            self.p1_uid = players[0].get('user_id')
            self.p2_uid = players[1].get('user_id')
        self.points = {p1_sid: 0, p2_sid: 0}
        self.total_strikes = {p1_sid: 0, p2_sid: 0}  # إجمالي المباراة (لكسر التعادل)
        self.round_index = 0
        self.tiebreak = 0
        self.stage = 'waiting'      # waiting|starting|turn|reveal|finished
        # حالة الجولة الحالية
        self.current_q = None        # {'id','q','cat'}
        self.answers_pool = []       # [{'norm': set(نصوص مطبّعة), 'display': str}]
        self.used_answer_idx = set()
        self.strikes = {p1_sid: 0, p2_sid: 0}
        self.turn = None
        self.turn_started_at = None
        self.first_turn_round = None  # بادئ هذه الجولة (للتناوب)
        self.used_question_ids = []
        self.judging = False          # ⚖️ تحكيم AI جارٍ (يمنع سباق المهلة)

    def opponent(self, sid):
        return self.p2 if sid == self.p1 else self.p1

    def remap_sid(self, old_sid, new_sid):
        """🔄 عند reconnect يتغيّر sid اللاعب. نعيد ربط كل الحقول
        والقواميس المفهرسة بالsid — وإلا KeyError يقلّش الجولة.
        (المحرك يحمل حالة مفهرسة بالsid أكثر من بقية الألعاب.)"""
        if old_sid == new_sid or not old_sid:
            return
        # الحقول المفردة
        for attr in ('p1', 'p2', 'turn', 'first_turn_round', 'winner'):
            if getattr(self, attr, None) == old_sid:
                setattr(self, attr, new_sid)
        # القواميس المفهرسة بالsid
        for dct in (self.points, self.total_strikes, self.strikes):
            if isinstance(dct, dict) and old_sid in dct:
                dct[new_sid] = dct.pop(old_sid)
        # 🔑 قائمة اللاعبين (is_player_in_game/can_submit تعتمد عليها)
        for p in (self.players or []):
            if p.get('sid') == old_sid:
                p['sid'] = new_sid
        self.bump_version()

    # ---------- الجولات ----------
    def begin_round(self, q, pool, starter):
        """q={'id','q','cat'} — pool=[{'norm':set,'display':str}]"""
        self.round_index += 1
        self.current_q = q
        self.answers_pool = pool
        self.used_answer_idx = set()
        self.strikes = {self.p1: 0, self.p2: 0}
        self.first_turn_round = starter
        self.turn = starter
        self.stage = 'turn'
        if q.get('id') is not None:
            self.used_question_ids.append(q['id'])
        return self.bump_version()

    def begin_turn(self, sid):
        self.turn = sid
        self.turn_started_at = time.time()
        self.judging = False
        return self.bump_version()

    def can_submit(self, sid):
        return (self.stage == 'turn' and self.turn == sid
                and self.is_player_in_game(sid) and not self.judging)

    def match_answer(self, norm_text):
        """يبحث النص المطبّع في القائمة. يرجع:
        ('correct', idx) | ('repeat', idx) | ('none', None)"""
        for i, item in enumerate(self.answers_pool):
            if norm_text in item['norm']:
                return ('repeat', i) if i in self.used_answer_idx else ('correct', i)
        return ('none', None)

    def consume_answer(self, idx):
        self.used_answer_idx.add(idx)

    def pool_exhausted(self):
        return len(self.used_answer_idx) >= len(self.answers_pool)

    def _sync_keys(self):
        """🛡️ يضمن أن كل القواميس المفهرسة بالsid تحوي p1/p2 الحاليين.
        جذر إصلاح KeyError: بعد أي تغيّر sid (reconnect/matchmaking)، قد
        تحمل القواميس sids قديمة. نستدعيها قبل أي وصول حسّاس فلا تنفجر
        أبداً — ونرحّل قيمة الـsid القديم للجديد إن أمكن (لا نفقد نقاطاً)."""
        for dct, default in ((self.points, 0), (self.total_strikes, 0),
                             (self.strikes, 0)):
            # لو فيه sid واحد فقط قديم + مفتاح حالي غائب → رحّل القيمة
            for cur in (self.p1, self.p2):
                if cur not in dct:
                    # نبحث عن قيمة يتيمة (sid غير p1/p2) لترحيلها
                    orphans = [k for k in dct if k not in (self.p1, self.p2)]
                    if len(orphans) == 1:
                        dct[cur] = dct.pop(orphans[0])
                    else:
                        dct[cur] = default
            # ننظّف أي sids قديمة متبقية (بعد ضمان p1/p2)
            for k in [k for k in dct if k not in (self.p1, self.p2)]:
                dct.pop(k, None)

    def add_strike(self, sid):
        self._sync_keys()
        if sid not in self.strikes:      # sid غريب تماماً (نادر جداً)
            self.strikes[sid] = 0
            self.total_strikes[sid] = 0
        self.strikes[sid] += 1
        self.total_strikes[sid] += 1
        self.bump_version()
        return self.strikes[sid]

    def round_points_for(self, sid):
        """نقاط الناجي حسب سترايكاته: 0→2، 1-2→1."""
        return 2 if self.strikes.get(sid, 0) == 0 else 1

    def close_round(self, loser_sid=None):
        """يوزّع نقاط الجولة. loser=None يعني نفدت القائمة (لا خاسر)."""
        self._sync_keys()
        self.stage = 'reveal'
        gains = {self.p1: 0, self.p2: 0}
        if loser_sid is not None:
            survivor = self.opponent(loser_sid)
            gains[survivor] = self.round_points_for(survivor)
        else:
            for s in (self.p1, self.p2):
                gains[s] = self.round_points_for(s)
        for s, g in gains.items():
            self.points[s] = self.points.get(s, 0) + g
        self.bump_version()
        return gains

    # ---------- النهاية ----------
    def is_over(self):
        if self.round_index < self.TOTAL_ROUNDS:
            return False
        if self.points.get(self.p1, 0) != self.points.get(self.p2, 0):
            return True
        return self.tiebreak >= self.MAX_TIEBREAK

    def decide_winner(self):
        self._sync_keys()
        s1, s2 = self.points.get(self.p1, 0), self.points.get(self.p2, 0)
        if s1 != s2:
            self.winner = self.p1 if s1 > s2 else self.p2
        else:
            t1 = self.total_strikes.get(self.p1, 0)
            t2 = self.total_strikes.get(self.p2, 0)
            if t1 != t2:
                self.winner = self.p1 if t1 < t2 else self.p2
            else:
                # عِوض من لم يبدأ الجولة الأولى
                self.winner = self.opponent(self.first_turn_round) \
                    if self.first_turn_round else self.p1
        self.stage = 'finished'
        self.bump_version()
        return self.winner

    # ---------- Redis-ready ----------
    def to_dict(self):
        return {
            'room_code': self.room_code, 'p1': self.p1, 'p2': self.p2,
            'points': self.points, 'round_index': self.round_index,
            'stage': self.stage, 'strikes': self.strikes,
            'turn': self.turn, 'tiebreak': self.tiebreak,
            'used_question_ids': self.used_question_ids,
            'state_version': self.state_version, 'winner': self.winner,
        }

    @classmethod
    def from_dict(cls, d, players=None):
        gs = cls(d['p1'], d['p2'], room_code=d.get('room_code'), players=players or [])
        for k in ('points', 'round_index', 'stage', 'strikes', 'turn',
                  'tiebreak', 'used_question_ids', 'state_version', 'winner'):
            if k in d:
                setattr(gs, k, d[k])
        return gs
