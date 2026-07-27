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


def _hex_neighbors(row, col):
    """جيران الخلية السداسية — نفس منطق المحرّك بالضبط."""
    if row % 2 == 0:
        moves = [(-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1)]
    else:
        moves = [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0)]
    out = []
    for dr, dc in moves:
        r, c = row + dr, col + dc
        if 0 <= r < 5 and 0 <= c < 5:
            out.append(r * 5 + c)
    return out


def _goal_distance(idx, color, board):
    """تقييم خلية لبناء جسر البوت.

    نكافئ (بترتيب الأهمية):
      1. الملاصقة السداسية الحقيقية لسلسلة البوت (تمدّها متّصلة)
      2. التقدّم نحو الحافة الأبعد التي لم يصلها بعد
      3. الوصول لحافة هدف مباشرة (صف 0/4 للأخضر، عمود 0/4 للبرتقالي)
    """
    row, col = idx // 5, idx % 5
    mine = _bot_cells(board, color)

    # 1) ملاصقة سداسية حقيقية لسلسلة البوت — يجب أن تطغى على كل شيء،
    #    وإلا قفز البوت بين حافتين متباعدتين بلا سلسلة متّصلة.
    neighbors = set(_hex_neighbors(row, col))
    touching = any(c in neighbors for c in mine)
    adjacency = 20 if touching else 0

    if color == 'green':
        # الأخضر يصل صف0↔صف4 (عمودي). نكافئ التقدّم عبر الصفوف
        # نحو الحافة الأبعد، ونعاقب البقاء في نفس صفوف السلسلة.
        rows = [c // 5 for c in mine]
        if not mine:
            progress = 2 - abs(row - 2)          # ابدأ من الوسط
        else:
            reached_top, reached_bot = min(rows), max(rows)
            # الحافة الأبعد التي لم نصلها
            if (4 - reached_bot) >= reached_top:
                progress = row - reached_bot       # نريد النزول أكثر
            else:
                progress = reached_top - row       # نريد الصعود أكثر
            progress = max(0, progress) * 3        # نكافئ التقدّم العمودي بقوة
        edge_bonus = 4 if (row in (0, 4) and touching) else 0
    else:  # orange
        # البرتقالي يصل عمود0↔عمود4 (أفقي).
        cols = [c % 5 for c in mine]
        if not mine:
            progress = 2 - abs(col - 2)
        else:
            reached_left, reached_right = min(cols), max(cols)
            if (4 - reached_right) >= reached_left:
                progress = col - reached_right
            else:
                progress = reached_left - col
            progress = max(0, progress) * 3
        edge_bonus = 4 if (col in (0, 4) and touching) else 0

    return adjacency + progress + edge_bonus


def _completes_win(board_colors, idx, color):
    """هل أخذ هذه الخلية يُكمل جسر البوت من حافة لحافة؟
    نحاكي التلوين ثم نفحص الاتصال بـ BFS (نفس منطق المحرّك)."""
    sim = list(board_colors)
    sim[idx] = color

    if color == 'green':
        starts = [i for i in range(25) if sim[i] == 'green' and i // 5 == 0]
        target = lambda x: x // 5 == 4
    else:
        starts = [i for i in range(25) if sim[i] == 'orange' and i % 5 == 0]
        target = lambda x: x % 5 == 4

    for start in starts:
        visited, queue = set(), [start]
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            if target(cur):
                return True
            r, c = cur // 5, cur % 5
            for n in _hex_neighbors(r, c):
                if sim[n] == color and n not in visited:
                    queue.append(n)
    return False


def choose_hex(board, bot_color, difficulty_name):
    """يختار البوت خلية في دوره.

    مبتدئ: عشوائي بحت.
    مستويات أعلى: (1) لو خلية تُكمل الفوز يأخذها فوراً،
                  (2) لو خلية تمنع فوز الخصم الوشيك يأخذها،
                  (3) وإلا يبني جسره متّصلاً نحو حافته.
    """
    empties = _empty_cells(board)
    if not empties:
        return None

    cfg = get_difficulty(difficulty_name)
    strat = cfg["strategy"]

    if strat <= 0.0 or random.random() > strat:
        return random.choice(empties)

    opp_color = "orange" if bot_color == "green" else "green"
    colors = [h.get('color') for h in board]

    # (1) خلية تُكمل فوز البوت → أولوية قصوى مطلقة
    for idx in empties:
        if _completes_win(colors, idx, bot_color):
            return idx

    # (2) خلية تمنع فوز الخصم الوشيك (لو كان الخصم سيفوز بها) → نأخذها
    #     (المستويات الأعلى فقط تعي الدفاع)
    if strat >= 0.6:
        for idx in empties:
            if _completes_win(colors, idx, opp_color):
                return idx

    # (3) بناء الجسر العادي
    scored = []
    for idx in empties:
        mine = _goal_distance(idx, bot_color, board)
        block = _goal_distance(idx, opp_color, board) * 0.5
        scored.append((mine + block, idx))

    scored.sort(reverse=True)

    # كلما ارتفع المستوى قلّ العشوائية:
    #   خبير: من أفضل خيار (شبه حتمي) — لا خلايا غريبة
    #   صعب:  من أفضل خيارين
    #   متوسط: من أفضل ثلاثة
    if strat >= 0.9:
        pool = scored[:1] if len(scored) >= 1 else scored
        # نادراً (10%) يوسّع لأفضل خيارين ليبقى بشرياً غير متوقّع تماماً
        if len(scored) >= 2 and random.random() < 0.10:
            pool = scored[:2]
    elif strat >= 0.6:
        pool = scored[:min(2, len(scored))]
    else:
        pool = scored[:min(3, len(scored))]

    # كسر التعادل بين المتساويين فعلياً فقط
    best_score = pool[0][0]
    tied = [p for p in pool if abs(p[0] - best_score) < 0.5] or pool
    return random.choice(tied)[1]


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
