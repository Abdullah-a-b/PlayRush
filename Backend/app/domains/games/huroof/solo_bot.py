"""
الوضع الفردي — محرّك قرار البوت (خصم الكمبيوتر) للعبة حروف.
============================================================
ملف مستقل تماماً: لا يستورده أي مسار أونلاين، ولا يعدّل أي منطق قائم.
يُستخدم فقط حين تكون الغرفة من نوع فردي (is_solo=True).

فلسفة العدل (مبنية على قراءة دورة اللعبة الفعلية):
  • البوت لا "يسرق" السؤال بسرعة آلية — يبزّ بزمن تفكير بشري عشوائي
    على نافذة الـ40ث (أو 30ث في المحاولة الثانية).
  • لا يعرف كل شيء: احتمال معرفته يعتمد على مستواه × صعوبة السؤال.
  • لو لا يعرف الإجابة → لا يبزّ إطلاقاً (لا يخاطر بما يجهل).
  • أحياناً يتردّد ثم يتراجع (سلوك بشري).
  • لو بزّ اللاعب أولاً، البوت يتوقّف.
  • اختيار الخلية: عشوائي للمبتدئ، استراتيجي (بناء الجسر + قطع الخصم)
    للمستويات العليا — الأخضر يصل أعلى↔أسفل، البرتقالي يمين↔يسار.

نتائج الوضع الفردي لا تمسّ التصنيف إطلاقاً (يُضمن في طبقة الربط).
"""
import random


# ============================================================
#  إعدادات الصعوبات الأربع
# ============================================================
# know_base:     احتمال أساسي أن يعرف البوت الإجابة (يُعدّل بصعوبة السؤال)
# buzz_min/max:  نطاق زمن التفكير قبل البزّ (ثوانٍ) — عشوائي، بشري
# hesitate:      احتمال أن "يتردّد" فيتراجع رغم معرفته (واقعية)
# strategy:      وزن الذكاء في اختيار الخلية (0=عشوائي, 1=مثالي)
# retry_boost:   زيادة المعرفة في المحاولة الثانية (رأى محاولة خاطئة قبله)
DIFFICULTIES = {
    "beginner": {
        "label": "مبتدئ",
        "know_base": 0.40,
        "buzz_min": 8.0, "buzz_max": 16.0,
        "hesitate": 0.20,
        "strategy": 0.0,
        "retry_boost": 0.05,
    },
    "medium": {
        "label": "متوسط",
        "know_base": 0.65,
        "buzz_min": 6.0, "buzz_max": 12.0,
        "hesitate": 0.12,
        "strategy": 0.35,
        "retry_boost": 0.10,
    },
    "hard": {
        "label": "صعب",
        "know_base": 0.82,
        "buzz_min": 4.0, "buzz_max": 9.0,
        "hesitate": 0.06,
        "strategy": 0.70,
        "retry_boost": 0.12,
    },
    "expert": {
        "label": "خبير",
        "know_base": 0.93,
        "buzz_min": 3.0, "buzz_max": 7.0,
        "hesitate": 0.03,
        "strategy": 1.0,
        "retry_boost": 0.15,
    },
}

DEFAULT_DIFFICULTY = "medium"

# معرّف اللاعب الوهمي داخل الغرفة (لا يتعارض مع أي sid حقيقي)
BOT_SID = "__BOT__"
BOT_NAME = "الكمبيوتر"

# كم يقتطع البوت من نافذة البزّ كحدّ أقصى (حتى لا يتأخّر للنهاية دائماً)
_WINDOW_SAFETY = 0.85


def get_difficulty(name):
    """يُرجع إعدادات الصعوبة، ويسقط للمتوسط لو الاسم غير معروف."""
    return DIFFICULTIES.get(name, DIFFICULTIES[DEFAULT_DIFFICULTY])


def _difficulty_factor(question_difficulty):
    """يحوّل صعوبة السؤال إلى معامل يضرب احتمال المعرفة.
    سؤال سهل → البوت يعرفه أكثر؛ صعب → أقل."""
    return {
        "easy": 1.15,
        "medium": 1.0,
        "hard": 0.75,
    }.get((question_difficulty or "medium"), 1.0)


def bot_knows_answer(difficulty_name, question_difficulty, attempt=1):
    """هل يعرف البوت إجابة هذا السؤال؟ قرار احتمالي.

    يجمع: احتمال المستوى الأساسي × معامل صعوبة السؤال (+ تعزيز المحاولة 2).
    """
    cfg = get_difficulty(difficulty_name)
    p = cfg["know_base"] * _difficulty_factor(question_difficulty)
    if attempt >= 2:
        p += cfg["retry_boost"]        # رأى محاولة خاطئة، فرصته أعلى
    p = max(0.0, min(0.98, p))         # لا يعرف 100% أبداً — يبقى لك مجال
    return random.random() < p


def bot_will_buzz(difficulty_name, knows):
    """قرار البزّ: يبزّ فقط لو يعرف، وأحياناً يتردّد فيتراجع."""
    if not knows:
        return False                   # لا يخاطر بما يجهل
    cfg = get_difficulty(difficulty_name)
    if random.random() < cfg["hesitate"]:
        return False                   # تردّد بشري: عرفها لكن لم يثق
    return True


def bot_buzz_delay(difficulty_name, window_seconds):
    """زمن التفكير قبل البزّ — عشوائي ضمن نطاق المستوى، مقيّد بالنافذة.

    window_seconds: 40 للمحاولة الأولى، 30 للثانية.
    يُضغط النطاق تناسبياً لو كانت النافذة أقصر من المعتاد.
    """
    cfg = get_difficulty(difficulty_name)
    lo, hi = cfg["buzz_min"], cfg["buzz_max"]

    # لا نتجاوز نسبة آمنة من النافذة (حتى لا يبزّ في الثانية الأخيرة)
    cap = window_seconds * _WINDOW_SAFETY
    lo = min(lo, cap * 0.5)
    hi = min(hi, cap)
    if hi <= lo:
        hi = lo + 0.5
    return round(random.uniform(lo, hi), 2)


# ============================================================
#  اختيار الخلية (استراتيجية بناء الجسر)
# ============================================================
# اللوح 5×5 (فهرس 0..24). الأخضر يصل الصف 0 بالصف 4 (عمودي).
# البرتقالي يصل العمود 0 بالعمود 4 (أفقي).

def _empty_cells(board):
    """فهارس الخلايا التي لم تُلوَّن بعد."""
    out = []
    for i, h in enumerate(board):
        c = h.get("color")
        if c not in ("green", "orange"):
            out.append(i)
    return out


def _progress_score(idx, color):
    """كم تُقرّب هذه الخلية اللونَ من هدفه؟
    الأخضر يريد تغطية الصفوف (تقدّم رأسي)؛ البرتقالي الأعمدة (أفقي).
    قيمة أعلى = أفضل لبناء الجسر."""
    row, col = idx // 5, idx % 5
    if color == "green":
        # نكافئ الخلايا التي تمدّ السلسلة عمودياً (وسط الأعمدة أثمن للربط)
        center_bonus = 2 - abs(col - 2)       # العمود الأوسط أفضل للاتصال
        return row + center_bonus
    else:  # orange
        center_bonus = 2 - abs(row - 2)
        return col + center_bonus


def _bot_cells(board, color):
    """فهارس خلايا البوت الحالية."""
    return [i for i, h in enumerate(board) if h.get('color') == color]


def _goal_distance(idx, color, board):
    """كم تُقرّب هذه الخلية البوتَ من إكمال جسره؟

    الأخضر يصل الصف 0 بالصف 4؛ البرتقالي العمود 0 بالعمود 4.
    نكافئ: (أ) الخلايا الملاصقة لسلسلة البوت الحالية (تمدّها)،
           (ب) التقدّم نحو الحافة الأبعد التي لم يصلها بعد.
    """
    row, col = idx // 5, idx % 5
    mine = _bot_cells(board, color)

    # أقصى امتداد وصل له البوت نحو كل حافة
    if color == 'green':
        rows = [c // 5 for c in mine]
        reached_top = min(rows) if rows else 2
        reached_bot = max(rows) if rows else 2
        # نريد التوسّع نحو الحافة الأبعد
        if not mine:
            edge_pull = 2 - abs(row - 2)         # ابدأ من الوسط عمودياً
        elif (4 - reached_bot) >= reached_top:
            edge_pull = row                       # امتدّ للأسفل
        else:
            edge_pull = 4 - row                   # امتدّ للأعلى
        axis = col                                # نفضّل الاستمرار بنفس العمود
        same_axis_bonus = 3 if any(c % 5 == col for c in mine) else 0
    else:  # orange
        cols = [c % 5 for c in mine]
        reached_left = min(cols) if cols else 2
        reached_right = max(cols) if cols else 2
        if not mine:
            edge_pull = 2 - abs(col - 2)
        elif (4 - reached_right) >= reached_left:
            edge_pull = col
        else:
            edge_pull = 4 - col
        axis = row
        same_axis_bonus = 3 if any(c // 5 == row for c in mine) else 0

    # مكافأة الملاصقة لخلية للبوت (تمديد متّصل لا قفز عشوائي)
    adjacency = 0
    for c in mine:
        cr, cc = c // 5, c % 5
        if abs(cr - row) <= 1 and abs(cc - col) <= 1:
            adjacency = 4
            break

    return edge_pull * 1.5 + adjacency + same_axis_bonus


def choose_hex(board, bot_color, difficulty_name):
    """يختار البوت خلية في دوره.

    مبتدئ: عشوائي بحت.
    مستويات أعلى: يبني جسره من سلسلته الحالية نحو حافته الهدف،
    ويوازن مع قطع جسر الخصم.
    """
    empties = _empty_cells(board)
    if not empties:
        return None

    cfg = get_difficulty(difficulty_name)
    strat = cfg["strategy"]

    if strat <= 0.0 or random.random() > strat:
        return random.choice(empties)

    opp_color = "orange" if bot_color == "green" else "green"

    scored = []
    for idx in empties:
        mine = _goal_distance(idx, bot_color, board)     # بناء جسري
        block = _goal_distance(idx, opp_color, board) * 0.5  # قطع الخصم
        jitter = random.uniform(0, 1.5)                  # لمسة بشرية خفيفة
        scored.append((mine + block + jitter, idx))

    scored.sort(reverse=True)
    top_k = scored[:min(3, len(scored))]
    return random.choice(top_k)[1]


# ============================================================
#  ملخّص قرار كامل لسؤال واحد (تستدعيه طبقة الربط)
# ============================================================
def decide_on_question(difficulty_name, question_difficulty,
                       window_seconds, attempt=1):
    """القرار الكامل للبوت عند ظهور سؤال.

    يُرجع dict:
      will_buzz: هل سيبزّ؟
      delay:     بعد كم ثانية يبزّ (لو will_buzz)
      knows:     هل يعرف الإجابة (يحدّد صحّة إجابته لو بزّ)
    """
    knows = bot_knows_answer(difficulty_name, question_difficulty, attempt)
    will = bot_will_buzz(difficulty_name, knows)
    delay = bot_buzz_delay(difficulty_name, window_seconds) if will else None
    return {"will_buzz": will, "delay": delay, "knows": knows}
