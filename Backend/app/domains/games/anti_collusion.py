"""
 نظام مكافحة التواطؤ (Anti-Collusion)

المشكلة: لاعبان يتفقان يلعبان ضد بعض بشكل متكرر لجمع نقاط/جوائز.

الحل (طبقتان، لا يعتمد على IP/الموقع):
  الطبقة 1 — منع المطابقة المتكررة:
    لو لاعبان تقابلا، ما يُطابَقان ثانية لمدة REMATCH_COOLDOWN.
  الطبقة 2 — تقليل الجائزة التدريجي:
    كلما تكررت المواجهة بين نفس الزوج في نافذة زمنية، قلّت الجائزة.

 in-memory الآن. Redis-ready: البنية بسيطة (dict) تنتقل لـ Redis بسهولة لاحقاً.
"""
import time
import os

# ==========================================
# إعدادات قابلة للضبط
# ==========================================
# مدة منع تكرار نفس الزوج (بالدقائق) — تُضبط بمتغيّر البيئة REMATCH_COOLDOWN_MIN.
# في الفترة التجريبية بعدد لاعبين قليل، القيمة العالية تُقفل الجميع بسرعة
# فيظنون المنصة معطّلة؛ لذلك اجعلها صغيرة (مثلاً 3) أثناء البيتا،
# وارفعها تدريجياً كلما زاد عدد اللاعبين.
try:
    _COOLDOWN_MIN = float(os.environ.get("REMATCH_COOLDOWN_MIN", "5"))
except (TypeError, ValueError):
    _COOLDOWN_MIN = 5.0
REMATCH_COOLDOWN = int(_COOLDOWN_MIN * 60)
COLLUSION_WINDOW = 6 * 60 * 60    # 6 ساعات: نافذة عدّ المواجهات المتكررة
# جدول تقليل الجائزة حسب عدد المواجهات في النافذة
# مرة 1-2 = كامل، 3 = نصف، 4 = ربع، 5+ = صفر
REWARD_MULTIPLIERS = {1: 1.0, 2: 1.0, 3: 0.5, 4: 0.25}
REWARD_MULTIPLIER_MIN = 0.0       # 5+ مواجهات = صفر

# ==========================================
# الحالة (in-memory)
# matchup_history[pair_key] = [timestamp1, timestamp2, ...]
# ==========================================
matchup_history = {}

# منع تكرار الزوج — منفصل لكل لعبة:
# last_match_by_game[(pair_key, game_mode)] = timestamp
# هكذا من لعب "حروف" مع فلان يظل قادراً على مواجهته في "البنك" فوراً،
# بينما يبقى عدّ التواطؤ (matchup_history) عاماً عبر كل الألعاب.
last_match_by_game = {}


def _pair_key(user_id_a, user_id_b) -> str:
    """مفتاح ثابت للزوج بغض النظر عن الترتيب (1,2) == (2,1)."""
    a, b = sorted([str(user_id_a), str(user_id_b)])
    return f"{a}|{b}"


def _clean_old(timestamps: list, window: int) -> list:
    """يحذف الطوابع الأقدم من النافذة."""
    cutoff = time.time() - window
    return [t for t in timestamps if t >= cutoff]


def were_recently_matched(user_id_a, user_id_b, game_mode=None) -> bool:
    """
    الطبقة 1: هل تقابل هذان اللاعبان مؤخراً في *نفس اللعبة*؟
    الحظر منفصل لكل لعبة — لا يمنع مواجهتهما في لعبة أخرى.
    """
    if user_id_a is None or user_id_b is None:
        return False
    key = _pair_key(user_id_a, user_id_b)
    last_match = last_match_by_game.get((key, game_mode))
    if last_match is None:
        return False
    return (time.time() - last_match) < REMATCH_COOLDOWN


def record_matchup(user_id_a, user_id_b, game_mode=None) -> None:
    """
    يسجّل مواجهة بين لاعبين (يُستدعى عند بدء المباراة).
    • matchup_history: عام عبر كل الألعاب (يُستخدم لتقليل الجائزة عند التواطؤ)
    • last_match_by_game: منفصل لكل لعبة (يُستخدم لمنع التكرار الفوري)
    """
    if user_id_a is None or user_id_b is None:
        return
    key = _pair_key(user_id_a, user_id_b)
    history = _clean_old(matchup_history.get(key, []), COLLUSION_WINDOW)
    history.append(time.time())
    matchup_history[key] = history
    last_match_by_game[(key, game_mode)] = time.time()


def get_reward_multiplier(user_id_a, user_id_b) -> float:
    """
    الطبقة 2: معامل تقليل الجائزة حسب تكرار المواجهة في النافذة.
    يُستدعى عند حساب المكافآت.

    1-2 مواجهات  1.0 (كامل)
    3  0.5، 4  0.25، 5+  0.0
    """
    if user_id_a is None or user_id_b is None:
        return 1.0
    key = _pair_key(user_id_a, user_id_b)
    history = _clean_old(matchup_history.get(key, []), COLLUSION_WINDOW)
    count = len(history)
    if count == 0:
        return 1.0
    return REWARD_MULTIPLIERS.get(count, REWARD_MULTIPLIER_MIN)


def cleanup_old_matchups() -> int:
    """
    تنظيف دوري للأزواج القديمة (يُستدعى من cron).
    يرجع عدد المفاتيح المحذوفة.
    """
    removed = 0
    for key in list(matchup_history.keys()):
        cleaned = _clean_old(matchup_history[key], COLLUSION_WINDOW)
        if cleaned:
            matchup_history[key] = cleaned
        else:
            del matchup_history[key]
            removed += 1
    return removed
