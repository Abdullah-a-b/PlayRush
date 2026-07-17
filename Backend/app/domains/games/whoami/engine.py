"""
محرك «من أنا» — Who Am I

شخصية مخفية تُكشف معلومات تلمّح لها واحدة كل 10 ثوانٍ (5 معلومات، من
الأغمض إلى الأوضح). الإجابة بالجرس: من يضغط أولاً يكتب اسمه خلال 10
ثوانٍ. النقاط تنازلية حسب عدد المعلومات المكشوفة عند الجرس:
المعلومة 1 = 4 نقاط، 2 = 3، 3 = 2، 4 = 1، 5 = 1.
خطأ أو انتهاء المهلة = سترايك، وسترايكان في الشخصية نفسها يقصيانك منها.
لو لم يعرفها أحد بعد آخر معلومة (نافذة أخيرة 10 ثوانٍ) تُكشف الإجابة
وتنتقل اللعبة للشخصية التالية. 5 شخصيات — الأعلى نقاطاً يفوز،
والتعادل يُحسم بشخصيات إضافية.
"""
import time


class WhoamiGameState:
    TOTAL_CHARACTERS = 5
    HINTS_PER_CHARACTER = 5
    HINT_INTERVAL = 10      # ثوانٍ بين المعلومة والأخرى
    ANSWER_WINDOW = 10      # نافذة الكتابة بعد الجرس
    FINAL_WINDOW = 10       # نافذة أخيرة بعد آخر معلومة قبل كشف الإجابة
    MAX_STRIKES = 2
    # نقاط الإجابة حسب رقم المعلومة المكشوفة (1..5)
    POINTS_BY_HINT = [4, 3, 2, 1, 1]

    def __init__(self, p1_sid, p2_sid, room_code=None, players=None):
        self.room_code = room_code
        self.p1 = p1_sid
        self.p2 = p2_sid
        self.p1_uid = None
        self.p2_uid = None
        if players:
            for p in players:
                if p.get('sid') == p1_sid:
                    self.p1_uid = p.get('user_id')
                elif p.get('sid') == p2_sid:
                    self.p2_uid = p.get('user_id')
        self.scores = {p1_sid: 0, p2_sid: 0}
        self.char_index = 0
        self.tiebreaker = False
        self.current = None            # الشخصية الحالية {id,name,accepted_answers,category,hints}
        self.revealed_count = 0        # كم معلومة كُشفت
        self.hints_done = False        # آخر معلومة كُشفت (النافذة الأخيرة جارية)
        self.stage = 'waiting'         # waiting | revealing | buzzed | finished
        self.buzzed_player = None
        self.strikes = {p1_sid: 0, p2_sid: 0}
        self.used_char_ids = []
        # ===== نظام المساعدات (نمط بقية الألعاب) =====
        # كل مساعدة مرة واحدة بالمباراة
        self.helps_used = {p1_sid: set(), p2_sid: set()}
        # «درع السترايك»: يمتص أول خطأ في الشخصية الحالية (يُصفَّر كل شخصية)
        self.shield_active = {p1_sid: False, p2_sid: False}
        # «قفل النقاط»: قيمة مثبّتة للشخصية الحالية (None = بلا قفل)
        self.locked_points = {p1_sid: None, p2_sid: None}
        # ثوانٍ أُضيفت لنافذة الإجابة الحالية عبر «تمديد الجرس»
        self.buzz_extra = 0
        self.reveal_remaining = None
        self.reveal_started_at = None
        self.reveal_wait = None
        self.state_version = 0
        self.winner = None

    # ---------- أساسيات ----------
    def bump_version(self):
        self.state_version += 1
        return self.state_version

    def opponent(self, sid):
        return self.p2 if sid == self.p1 else self.p1

    def is_player_in_game(self, sid):
        return sid in (self.p1, self.p2)

    def remap_sid(self, old_sid, new_sid):
        """إعادة ربط اللاعب بعد reconnect (sid جديد)."""
        if old_sid == new_sid:
            return
        for dct in (self.scores, self.strikes, self.helps_used,
                    self.shield_active, self.locked_points):
            if old_sid in dct:
                dct[new_sid] = dct.pop(old_sid)
        if self.p1 == old_sid:
            self.p1 = new_sid
        elif self.p2 == old_sid:
            self.p2 = new_sid
        if self.buzzed_player == old_sid:
            self.buzzed_player = new_sid

    # ---------- دورة الشخصية ----------
    def start_new_character(self, char_data, advance_index=True):
        if advance_index:
            self.char_index += 1
        self.current = char_data
        self.revealed_count = 1        # المعلومة الأولى تُعرض فوراً
        self.hints_done = False
        self.stage = 'revealing'
        self.buzzed_player = None
        self.strikes = {self.p1: 0, self.p2: 0}
        self.shield_active = {self.p1: False, self.p2: False}
        self.locked_points = {self.p1: None, self.p2: None}
        self.buzz_extra = 0
        self.reveal_remaining = None
        if char_data.get('id') is not None:
            self.used_char_ids.append(char_data['id'])
        self.bump_version()

    def reveal_next_hint(self):
        """يكشف المعلومة التالية. يرجع False لو كانت الأخيرة مكشوفة أصلاً."""
        hints = (self.current or {}).get('hints', [])
        if self.revealed_count >= len(hints):
            self.hints_done = True
            return False
        self.revealed_count += 1
        if self.revealed_count >= len(hints):
            self.hints_done = True
        self.bump_version()
        return True

    def revealed_hints(self):
        return ((self.current or {}).get('hints', []))[: self.revealed_count]

    # ---------- الجرس والسترايكات ----------
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

    # ---------- النقاط ----------
    def score_for_current(self, sid=None):
        """نقاط الإجابة الصحيحة الآن — حسب رقم المعلومة المكشوفة.
        لو فعّل اللاعب «قفل النقاط» تُرجَع القيمة المثبّتة."""
        if sid is not None and self.locked_points.get(sid) is not None:
            return self.locked_points[sid]
        idx = max(1, min(self.revealed_count, len(self.POINTS_BY_HINT)))
        return self.POINTS_BY_HINT[idx - 1]

    # ---------- المساعدات ----------
    def help_used(self, sid, help_id):
        return help_id in self.helps_used.get(sid, set())

    def mark_help_used(self, sid, help_id):
        self.helps_used.setdefault(sid, set()).add(help_id)
        self.bump_version()

    def in_tiebreak(self):
        return self.tiebreaker

    def current_points_value(self):
        """القيمة الحالية غير المقفولة (لتثبيتها في قفل النقاط)."""
        idx = max(1, min(self.revealed_count, len(self.POINTS_BY_HINT)))
        return self.POINTS_BY_HINT[idx - 1]

    def lock_points_for(self, sid):
        self.locked_points[sid] = self.current_points_value()
        self.bump_version()

    def consume_shield_if_active(self, sid):
        """يمتص السترايك إن كان الدرع مفعّلاً (خارج كسر التعادل).
        يرجع True لو امتص."""
        if self.in_tiebreak():
            return False
        if self.shield_active.get(sid, False):
            self.shield_active[sid] = False
            self.bump_version()
            return True
        return False

    def award(self, sid, points):
        self.scores[sid] = self.scores.get(sid, 0) + points

    def all_characters_done(self):
        return self.char_index >= self.TOTAL_CHARACTERS and not self.tiebreaker or \
               (self.tiebreaker and self.char_index > self.TOTAL_CHARACTERS and not self.is_tie())

    def is_tie(self):
        return self.scores.get(self.p1, 0) == self.scores.get(self.p2, 0)

    def leader(self):
        if self.is_tie():
            return None
        return self.p1 if self.scores.get(self.p1, 0) > self.scores.get(self.p2, 0) else self.p2

    # ---------- التسلسل (Redis / العناقيد) ----------
    def to_dict(self):
        return {
            'room_code': self.room_code, 'p1': self.p1, 'p2': self.p2,
            'p1_uid': self.p1_uid, 'p2_uid': self.p2_uid,
            'scores': self.scores, 'char_index': self.char_index,
            'tiebreaker': self.tiebreaker, 'current': self.current,
            'revealed_count': self.revealed_count, 'hints_done': self.hints_done,
            'stage': self.stage, 'buzzed_player': self.buzzed_player,
            'strikes': self.strikes, 'used_char_ids': self.used_char_ids,
            'state_version': self.state_version, 'winner': self.winner,
            'helps_used': {k: list(v) for k, v in self.helps_used.items()},
            'shield_active': self.shield_active,
            'locked_points': self.locked_points,
        }

    @classmethod
    def from_dict(cls, d, players=None):
        gs = cls(d.get('p1'), d.get('p2'), room_code=d.get('room_code'), players=players)
        for k in ('p1_uid', 'p2_uid', 'scores', 'char_index', 'tiebreaker',
                  'current', 'revealed_count', 'hints_done', 'stage',
                  'buzzed_player', 'strikes', 'used_char_ids',
                  'state_version', 'winner', 'shield_active', 'locked_points'):
            if k in d:
                setattr(gs, k, d[k])
        if 'helps_used' in d:
            gs.helps_used = {k: set(v) for k, v in (d['helps_used'] or {}).items()}
        return gs
