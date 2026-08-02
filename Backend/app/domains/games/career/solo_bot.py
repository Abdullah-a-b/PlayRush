"""
الوضع الفردي — محرّك قرار البوت (خصم الكمبيوتر) للعبة مسيرة لاعب.
============================================================
ملف مستقل تماماً: لا يستورده أي مسار أونلاين، ولا يعدّل أي منطق قائم.
يُستخدم فقط حين تكون الغرفة من نوع فردي (is_solo=True).

قواعد اللعبة كما في engine.py:
  • نادٍ كل REVEAL_INTERVAL (5ث)، ونافذة آخر نادٍ FINAL_WINDOW (10ث)
  • ANSWER_WINDOW (10ث) للكتابة بعد الجرس — والكشف يتوقّف خلالها
  • صحيح قبل اكتمال المسيرة = نقطتان، بعد اكتمالها = نقطة
  • MAX_STRIKES = 2 لكل لاعب *لكل شخصية* (لا للمباراة كلها)
  • مسيرة من نادٍ واحد: 5ث بنقطتين ثم 10ث بنقطة
    (career_complete=True من البداية، و first_reveal_done يقلبها لنقطة)

فلسفة العدل:
  ⚠️ البوت **لا يعرف كم نادياً بقي** ولا متى آخر نادٍ — تماماً كاللاعب
     البشري. أي قرار مبني على "نسبة الأندية الظاهرة من الإجمالي" غش صريح
     يجعله يبزّ دائماً قبل النادي الأخير بنادٍ. لذلك تنمو ثقته من الأندية
     التي *رآها* فقط. الاستثناء الوحيد المشروع: مساعدة "عدّاد الأندية" —
     يدفع ثمنها كاللاعب، فيحقّ له ما تكشفه.
  • لا يبزّ في أول ناديين مهما بلغت ثقته (إلا مسيرة النادي الواحد).
  • لا يبزّ بزّاً تكتيكياً فارغاً لتجميد الكشف عن خصمه — سلوك مزعج،
    ممنوع حتى في "خبير".
  • يخطئ أحياناً بعد البزّ — لولا ذلك لصار بزّه إعلان فوز.

رياضيات عتبة البزّ:
  البزّ الآن = نقطتان باحتمال p. الانتظار = نقطة واحدة غير مضمونة (قد
  يسبقك الخصم). فالبزّ أفضل متى 2p > 1 أي p > 50%. ووجود سترايك ثانٍ
  يجعل الخطأ الأول غير مُقصٍ فتنخفض العتبة أكثر للمستويات العليا.

نتائج الوضع الفردي لا تمسّ التصنيف إطلاقاً (يُضمن في طبقة الربط).
"""
import random


# ============================================================
#  إعدادات الصعوبات الأربع
# ============================================================
# know_base:      احتمال أن يعرف البوت هذه الشخصية أصلاً
# growth:         كم ترتفع ثقته مع كل نادٍ جديد يراه (نموّ تراكمي)
# thresh_first:   عتبة الثقة للبزّ وهو بلا سترايكات
# thresh_second:  عتبة الثقة للبزّ وقد استهلك سترايكاً (أكثر حذراً)
# buzz_react:     تأخّر بشري بعد ظهور النادي قبل ضغط الجرس (ثوانٍ)
# type_min/max:   زمن الكتابة داخل نافذة الإجابة (ثوانٍ)
# accuracy:       دقّته بعد البزّ حين يكون "يعرف"
# blind_buzz:     احتمال بزّة يائسة وهو لا يعرف (سلوك بشري نادر)
DIFFICULTIES = {
    "beginner": {
        "label": "مبتدئ",
        "know_base": 0.45,
        "growth": 0.22,
        "thresh_first": 0.80,     # جبان: ينتظر آخر نادٍ فيجمع نقطة واحدة
        "thresh_second": 0.92,
        "buzz_react": (2.0, 4.0),
        "type_min": 6.0, "type_max": 8.5,
        "accuracy": 0.80,
        "blind_buzz": 0.03,
    },
    "medium": {
        "label": "متوسط",
        "know_base": 0.65,
        "growth": 0.30,
        "thresh_first": 0.58,
        "thresh_second": 0.78,
        "buzz_react": (1.5, 3.0),
        "type_min": 4.5, "type_max": 7.0,
        "accuracy": 0.88,
        "blind_buzz": 0.05,
    },
    "hard": {
        "label": "صعب",
        "know_base": 0.80,
        "growth": 0.40,
        "thresh_first": 0.45,
        "thresh_second": 0.70,
        "buzz_react": (1.0, 2.2),
        "type_min": 3.0, "type_max": 5.0,
        "accuracy": 0.93,
        "blind_buzz": 0.06,
    },
    "expert": {
        "label": "خبير",
        "know_base": 0.90,
        "growth": 0.50,
        "thresh_first": 0.36,     # مقامر محسوب: يخمّن مبكراً ويثق بفرصته الثانية
        "thresh_second": 0.62,
        "buzz_react": (0.8, 1.8),
        "type_min": 2.0, "type_max": 4.0,
        "accuracy": 0.96,
        "blind_buzz": 0.07,
    },
}

DEFAULT_DIFFICULTY = "medium"

# معرّف اللاعب الوهمي داخل الغرفة (نفس اصطلاح حروف)
BOT_SID = "__BOT__"
BOT_NAME = "الكمبيوتر"

# لا يبزّ قبل رؤية هذا العدد من الأندية مهما بلغت ثقته
MIN_CLUBS_BEFORE_BUZZ = 2


def get_difficulty(name):
    """يُرجع إعدادات الصعوبة، ويسقط للمتوسط لو الاسم غير معروف."""
    return DIFFICULTIES.get(name, DIFFICULTIES[DEFAULT_DIFFICULTY])


# ============================================================
#  نموذج المعرفة والثقة
# ============================================================
# تأثير شهرة الشخصية الفعلية (عمود career_players.difficulty — محسوب وقت
# الاستيراد من عدد لغات ويكيبيديا المغطّية للاعب، مؤشر شهرة حقيقي) على
# فرصة "المعرفة" الأساسية — مستقل عن صعوبة البوت، يُطبَّق فوقها. بدون هذا
# كانت "المعرفة" رمية عملة ثابتة بصعوبة البوت فقط بغض النظر عن شهرة من
# يُعرض فعلياً — فيعرف بوت المبتدئ نجوماً وغير معروفين بنفس الاحتمال.
FAME_ADJUST = {
    "easy":   {"bonus": 0.35},    # مشهور جداً — كل مستويات البوت شبه متأكدة
    "medium": {"bonus": 0.0},     # افتراضي — نفس know_base الحالي بلا تغيير
    "hard":   {"factor": 0.35},   # مغمور — حتى الخبير نادراً ما يعرفه فعلياً
}


def bot_knows_player(difficulty_name, player_difficulty="medium"):
    """هل يعرف البوت هذه الشخصية أصلاً؟ يُستدعى مرة واحدة عند بدء كل شخصية.

    القرار يُتّخذ مسبقاً ويُخزَّن في حالة الغرفة، فلا يتغيّر أثناء الكشف —
    كاللاعب البشري: إما يعرف اللاعب أو لا. يمزج بين صعوبة البوت وشهرة
    الشخصية الفعلية (player_difficulty: easy/medium/hard).
    """
    cfg = get_difficulty(difficulty_name)
    adjust = FAME_ADJUST.get(player_difficulty, FAME_ADJUST["medium"])
    if "factor" in adjust:
        p = cfg["know_base"] * adjust["factor"]
    else:
        p = cfg["know_base"] + adjust.get("bonus", 0.0)
    return random.random() < max(0.02, min(0.97, p))


def confidence(difficulty_name, knows, revealed_count, seed_jitter=0.0,
               single_club=False):
    """ثقة البوت الحالية بعد رؤية عدد من الأندية.

    ⚠️ لا تستقبل عدد الأندية الكلي إطلاقاً — البوت يجهله كاللاعب.
    """
    cfg = get_difficulty(difficulty_name)
    n = max(0, revealed_count - 1)       # النادي الأول لا يبني ثقة تقريباً

    # مسيرة من نادٍ واحد: النادي الوحيد يحمل معلومة كثيفة (لاعب ارتبط اسمه
    # بناديه غالباً مشهور) فنمنحه وزن ناديين ونصف، وإلا بقيت ثقته صفراً
    # فلا يحاول إطلاقاً في هذه الحالة.
    if single_club:
        n = 2.5

    if knows:
        # نموّ تراكمي متناقص: 1 - (1-g)^n → يقترب من 1 ولا يبلغه
        conf = 1.0 - ((1.0 - cfg["growth"]) ** n)
    else:
        # لا يعرفه: سقف منخفض مهما رأى (قد يخمّن متأخراً فقط)
        conf = min(0.35, 0.06 * n)

    conf += seed_jitter                  # تذبذب ثابت لكل شخصية
    return max(0.0, min(0.99, conf))


def new_player_jitter():
    """تذبذب صغير يُولَّد مرة لكل شخصية ويُخزَّن، كي لا تتغيّر ثقته كل ثانية."""
    return random.uniform(-0.08, 0.08)


# ============================================================
#  قرار البزّ
# ============================================================
def decide_on_reveal(difficulty_name, knows, revealed_count,
                     strikes_used, jitter=0.0, opponent_locked=False,
                     is_final=False, single_club=False,
                     conf_bonus=0.0, has_shield_now=False):
    """هل يبزّ البوت الآن بعد كشف نادٍ جديد؟

    is_final:         هل صارت الإجابة تساوي نقطة واحدة؟ أي مطابقة لـ
                      (gs.career_complete and gs.first_reveal_done) في
                      المحرّك — وتشمل اكتمال المسيرة الطويلة، ومسيرة
                      النادي الواحد بعد أول 5 ثوانٍ. حينها الانتظار لا
                      يفيد (الشخصية ستُستبدل) فتنخفض العتبة كثيراً.
    strikes_used:     كم سترايك استهلكه البوت على هذه الشخصية (0 أو 1)
    opponent_locked:  هل استُبعد الخصم؟ حينها لا سباق فيرفع عتبته.
    conf_bonus:       دفعة ثقة من المساعدات المستخدمة
    has_shield_now:   هل درع السترايك مفعّل؟ (أول خطأ لا يُحسب)

    يُرجع dict: {'will_buzz', 'delay', 'confident'}
    """
    cfg = get_difficulty(difficulty_name)

    # لا يبزّ مبكراً جداً مهما عرف — البزّ عند أول نادٍ يكشف أنه يغشّ.
    # الاستثناء الوحيد: مسيرة من نادٍ واحد، فلا "نادٍ ثانٍ" ينتظره.
    if not single_club and revealed_count < MIN_CLUBS_BEFORE_BUZZ:
        return {"will_buzz": False, "delay": None, "confident": 0.0}

    # استهلك سترايكيه على هذه الشخصية → لا يستطيع المحاولة أصلاً
    if strikes_used >= 2:
        return {"will_buzz": False, "delay": None, "confident": 0.0}

    conf = min(0.99, confidence(difficulty_name, knows, revealed_count,
                                jitter, single_club) + conf_bonus)
    thresh = cfg["thresh_second"] if strikes_used >= 1 else cfg["thresh_first"]

    # درع السترايك: أول خطأ لا يُحسب، فالمخاطرة أرخص → يبزّ بثقة أقل
    if has_shield_now:
        thresh *= 0.75

    # لا منافس على الجرس → لا داعي للمخاطرة، ينتظر ثقة أعلى
    if opponent_locked and not is_final:
        thresh = min(0.95, thresh + 0.20)

    # اكتملت المسيرة: إما الآن أو تضيع الشخصية → يحاول بما لديه
    # ⚠️ فقط لو "يعرف" فعلاً — لولا شرط knows، فإن سقف الثقة حين "لا يعرف"
    # (min(0.35, 0.06*n) + jitter) يتجاوز هذا الحدّ المخفّض بسهولة حتى في
    # مبتدئ (0.80×0.45=0.36)، فيبزّ ويجيب صح أحياناً على شخصية لا يعرفها
    # إطلاقاً — يناقض تماماً فلسفة "لا يعرف = لا يحاول" أعلى الملف. البزّة
    # اليائسة الحقيقية (لا يعرف) لها مسارها المستقل الوحيد: blind_buzz أدناه.
    if is_final and knows:
        thresh *= 0.45

    will = conf >= thresh

    # بزّة يائسة نادرة وهو لا يعرف (بشرية) — من نافذة متأخرة فقط
    if not will and not knows and revealed_count >= 4:
        if random.random() < cfg["blind_buzz"]:
            will = True

    if not will:
        return {"will_buzz": False, "delay": None, "confident": conf}

    lo, hi = cfg["buzz_react"]
    return {
        "will_buzz": True,
        "delay": round(random.uniform(lo, hi), 2),
        "confident": conf,
    }


# ============================================================
#  الإجابة بعد البزّ
# ============================================================
def bot_answer_delay(difficulty_name, answer_window):
    """كم يستغرق البوت في "الكتابة" داخل نافذة الإجابة."""
    cfg = get_difficulty(difficulty_name)
    lo = min(cfg["type_min"], answer_window * 0.25)
    hi = min(cfg["type_max"], answer_window * 0.85)
    if hi <= lo:
        hi = lo + 0.5
    return round(random.uniform(lo, hi), 2)


def bot_answers_correctly(difficulty_name, knows, confident, accuracy_bonus=0.0):
    """هل تكون إجابته صحيحة؟"""
    cfg = get_difficulty(difficulty_name)
    if knows:
        return random.random() < min(0.99, cfg["accuracy"] + accuracy_bonus)
    # بزّة يائسة: فرصة صغيرة أن يصادف الصواب
    return random.random() < min(0.18, confident * 0.4)


def decide_full(difficulty_name, knows, revealed_count, strikes_used,
                answer_window, jitter=0.0, opponent_locked=False,
                is_final=False, single_club=False,
                conf_bonus=0.0, has_shield_now=False, accuracy_bonus=0.0):
    """قرار كامل عند كشف نادٍ — تستدعيه طبقة الربط.

    يُرجع dict:
      will_buzz:    هل سيبزّ الآن؟
      buzz_delay:   بعد كم ثانية يضغط الجرس
      answer_delay: بعد كم ثانية (من البزّ) يُرسل إجابته
      correct:      هل ستكون إجابته صحيحة
    """
    d = decide_on_reveal(difficulty_name, knows, revealed_count,
                         strikes_used, jitter, opponent_locked, is_final,
                         single_club, conf_bonus, has_shield_now)
    if not d["will_buzz"]:
        return {"will_buzz": False, "buzz_delay": None,
                "answer_delay": None, "correct": False}

    return {
        "will_buzz": True,
        "buzz_delay": d["delay"],
        "answer_delay": bot_answer_delay(difficulty_name, answer_window),
        "correct": bot_answers_correctly(difficulty_name, knows,
                                         d["confident"], accuracy_bonus),
    }


# ============================================================
#  المساعدات — كيف يستخدمها البوت
# ============================================================
# ⚠️ مبدأ التصميم: مساعدات هذه اللعبة *معلوماتية* (جنسية، مركز، جيل، حرف
# أول)، والبوت لا "يقرأ" معلومات — معرفته محاكاة احتمالية. لذلك تُترجم كل
# مساعدة إلى **أثر على ثقته** بقدر ما تضيّق الاحتمالات على البشري:
#   الحرف الأول أقوى معلومة (يُقصي معظم الأسماء) → أكبر دفعة
#   الجيل والجنسية والمركز تضيّق أقل → دفعات أصغر
#
# واستثناء مهم: "عدّاد الأندية" هو الطريق الشرعي الوحيد ليعرف البوت طول
# المسيرة. منعناه من ذلك مجاناً لأنه غش، لكنه هنا **يدفع مساعدة** مقابله
# تماماً كاللاعب البشري — فيحقّ له أن يعرف أن آخر نادٍ قادم.
#
# ملاحظة: في الوضع الفردي لا تُخصم مساعدات اللاعب من مخزونه (تُعالَج في
# events.py)، وكذلك البوت يبدأ كل مباراة بعتاد كامل.
HELP_EFFECTS = {
    "c_first_letter":  {"conf": 0.30},
    "c_era":           {"conf": 0.15},
    "c_nationality":   {"conf": 0.12},
    "c_position":      {"conf": 0.10},
    "c_club_count":    {"knows_total": True},
    "c_strike_shield": {"shield": True},
    "c_extend_write":  {"answer_bonus": 5.0, "accuracy": 0.04},
    "c_double_lock":   {"double_on_final": True},
}

# عتاد البوت لكل مستوى — 3 خانات (الخانة الرابعة ميزة يشتريها اللاعب
# البشري عند المستوى 10؛ لا نمنحها للبوت كي يبقى العتاد في صالح اللاعب).
BOT_LOADOUTS = {
    "beginner": ["c_nationality", "c_extend_write", "c_club_count"],
    "medium":   ["c_nationality", "c_first_letter", "c_extend_write"],
    "hard":     ["c_first_letter", "c_era", "c_strike_shield"],
    "expert":   ["c_first_letter", "c_strike_shield", "c_club_count"],
}

# سياسة الاستخدام لكل مستوى
#   waste:          احتمال استخدامها في توقيت خاطئ (بلا حاجة) — سلوك مبتدئ
#   gap:            يستخدمها حين تكون ثقته أقل من العتبة بهذا الفارق أو أقل
#                   (أي أنها ستنقله فوق العتبة فعلاً — لا يهدرها بلا أثر)
#   min_reveal:     لا يستخدمها قبل هذا الكشف
#   max_per_player: سقف الاستخدام للشخصية الواحدة (كي لا يحرق عتاده أول شخصية)
HELP_POLICY = {
    "beginner": {"waste": 0.35, "gap": 0.10, "min_reveal": 1, "max_per_player": 1},
    "medium":   {"waste": 0.12, "gap": 0.18, "min_reveal": 2, "max_per_player": 1},
    "hard":     {"waste": 0.04, "gap": 0.22, "min_reveal": 2, "max_per_player": 1},
    "expert":   {"waste": 0.00, "gap": 0.26, "min_reveal": 2, "max_per_player": 2},
}


def bot_loadout(difficulty_name):
    """عتاد البوت — تستدعيه طبقة الربط مرة عند بدء المباراة.

    كل مساعدة تُستخدم مرة واحدة في المباراة (كاللاعب)، وتتجدّد في
    المباراة الفردية التالية لأنها لا تُخصم من مخزون أحد.
    """
    return list(BOT_LOADOUTS.get(difficulty_name,
                                 BOT_LOADOUTS[DEFAULT_DIFFICULTY]))


def help_conf_bonus(used_help_ids):
    """مجموع دفعات الثقة من المساعدات المستخدمة على الشخصية الحالية."""
    total = 0.0
    for hid in used_help_ids or []:
        total += HELP_EFFECTS.get(hid, {}).get("conf", 0.0)
    return min(0.45, total)       # سقف: المساعدات تساعد ولا تُغني عن المعرفة


def help_accuracy_bonus(used_help_ids):
    """دفعة الدقّة (تمديد الكتابة يمنحه وقتاً أطول للتأكّد)."""
    total = 0.0
    for hid in used_help_ids or []:
        total += HELP_EFFECTS.get(hid, {}).get("accuracy", 0.0)
    return min(0.06, total)


def has_shield(used_help_ids):
    return any(HELP_EFFECTS.get(h, {}).get("shield")
               for h in (used_help_ids or []))


def knows_total_clubs(used_help_ids):
    """هل دفع البوت ثمن معرفة طول المسيرة؟ (عدّاد الأندية)"""
    return any(HELP_EFFECTS.get(h, {}).get("knows_total")
               for h in (used_help_ids or []))


def decide_help(difficulty_name, knows, revealed_count, strikes_used,
                available_helps, used_this_player, jitter=0.0,
                single_club=False, is_final=False):
    """هل يستخدم البوت مساعدة الآن؟ يُرجع معرّف المساعدة أو None.

    available_helps:   ما تبقّى من عتاده في هذه المباراة
    used_this_player:  ما استخدمه على الشخصية الحالية
    """
    if not available_helps:
        return None

    pol = HELP_POLICY.get(difficulty_name, HELP_POLICY[DEFAULT_DIFFICULTY])
    if len(used_this_player) >= pol["max_per_player"]:
        return None
    if revealed_count < pol["min_reveal"]:
        return None

    # مبتدئ يهدر مساعداته في توقيت خاطئ — جزء من ضعفه لا تغبية مصطنعة
    if random.random() < pol["waste"]:
        return random.choice(available_helps)

    cfg = get_difficulty(difficulty_name)
    conf = confidence(difficulty_name, knows, revealed_count, jitter, single_club)
    conf += help_conf_bonus(used_this_player)
    thresh = cfg["thresh_second"] if strikes_used >= 1 else cfg["thresh_first"]
    if is_final:
        thresh *= 0.45

    gap = thresh - conf

    # فوق العتبة أصلاً → سيبزّ بلا مساعدة، فلا داعي لإهدارها
    if gap <= 0:
        return None

    # الفجوة أكبر من أن تسدّها مساعدة → لا فائدة من حرقها
    if gap > pol["gap"]:
        # إلا الدرع: قيمته في تأمين مخاطرة لا في رفع الثقة
        shields = [h for h in available_helps
                   if HELP_EFFECTS.get(h, {}).get("shield")]
        if shields and strikes_used == 0 and gap <= pol["gap"] * 1.8:
            return shields[0]
        return None

    # نختار المساعدة التي تسدّ الفجوة بأقلّ إسراف (أصغر دفعة كافية)
    boosters = [(HELP_EFFECTS.get(h, {}).get("conf", 0.0), h)
                for h in available_helps
                if HELP_EFFECTS.get(h, {}).get("conf", 0.0) > 0]
    enough = sorted([b for b in boosters if b[0] >= gap])
    if enough:
        return enough[0][1]
    if boosters:
        return sorted(boosters, reverse=True)[0][1]
    return None