"""
economy_config.py — مصدر الحقيقة الوحيد لكل ثوابت الاقتصاد والتصنيف.

الفلسفة (من وثيقة السياق):
- عملتان فقط: كوينز (لعب) + جواهر (نادرة، لعب فقط حالياً). فصل تام.
- Win-to-Play لا Win-to-Pay: لا شيء يُشترى بفلوس يقرر الفوز.
- الجواهر نادرة ومحمية: لا تأتي من المباريات، بل من الليفل والرتب
  والمهام الأسبوعية/الموسمية والـPass فقط.
- الرتبة (Elo) منفصلة تماماً عن الـPass ومنفصلة عن XP الليفل.

كل رقم هنا نظري ويُضبط بالاختبار على بيانات اللاعبين الفعلية.
"""

# ============================================================
#  1) الجواهر — المصادر النادرة
# ============================================================
# مصدر أساسي: جوهرة واحدة لكل ترقية مستوى (level up)
GEMS_PER_LEVEL = 2   # حسب الوثيقة: +2💎 لكل مستوى

# ترقية مجموعة الرتب (عبور حاجز: برونزي→فضي، فضي→ذهبي...)
# تُمنح مرة واحدة عند أول بلوغ لكل مجموعة أعلى (لا تتكرر بالهبوط والصعود)
GEMS_PER_TIER_PROMOTION = {
    "silver": 5,
    "gold": 8,
    "platinum": 12,
    "elite": 20,
}

# ============================================================
#  2) نظام التصنيف (Elo) — منفصل لكل لعبة
# ============================================================
ELO_STARTING = 1000          # نقطة البداية القياسية
ELO_K_FACTOR = 32            # معامل التغير الأساسي
ELO_MARGIN_MULT = {          # هامش الفوز (حروف: جولتان/ثلاث)
    "dominant": 1.1,         # فوز 2-0
    "close": 0.9,            # فوز 2-1
    "default": 1.0,          # بقية الألعاب (فوز/خسارة بسيط)
}
# حماية الأرضية: لا يهبط اللاعب تحت أرضية مجموعته (checkpoint ناعم)
ELO_FLOOR_PROTECTION = True

# soft reset موسمي: الرتبة تُعاد ضبطها كل موسم مع الـPass (قرار موسمي).
# new = 1000 + (old - 1000) * FACTOR — يحفظ نصف الفارق (منصة جديدة:
# يبقي فروق المهارة واضحة للمطابقة + تسلّق متسارع للعودة + شعور موسمي).
# ⚔️ قسوة الخسارة المتصاعدة بالرتبة (نموذج Brawl Stars):
# البرونزي صعوده محمي (خسارته رحيمة)، والنخبة كل مباراة تحسب.
LOSS_SEVERITY_BY_TIER = {
    "bronze": 0.5, "silver": 0.75, "gold": 1.0,
    "platinum": 1.15, "elite": 1.3,
}
# سقف تغيّر الـElo بالمباراة الواحدة: ±50% من K الأساسي
ELO_DELTA_CAP_FACTOR = 1.5
# 🛡️ حماية الأرضية بالرتب العليا: لا تهبط تحت أرضية رتبتك العليا المسجّلة
# بأول N مباريات بعد بلوغها (درع هبوط مؤقت لا يقتل التنافس)
DEMOTION_SHIELD_TIERS = ("platinum", "elite")
DEMOTION_SHIELD_MATCHES = 3
# 🚀 Rank Boost بعد الـreset الموسمي: مكاسب مضاعفة لأول N مباريات
# (تسلّق متسارع لاستعادة رتبتك — نموذج Brawl Stars)
RANK_BOOST_MATCHES = 10
RANK_BOOST_MULT = 1.5

SEASON_SOFT_RESET_FACTOR = 0.5
SEASON_RESET_BASELINE = 1000

# مجموعات الرتب المرئية — كل مجموعة 3 درجات (III → II → I)
# threshold = حد Elo الأدنى لدخول المجموعة
RANK_TIERS = [
    {"key": "bronze",   "name": "برونزي", "color": "#cd7f32", "min_elo": 850},
    {"key": "silver",   "name": "فضي",    "color": "#c0c0c0", "min_elo": 1100},
    {"key": "gold",     "name": "ذهبي",   "color": "#facc15", "min_elo": 1300},
    {"key": "platinum", "name": "بلاتيني", "color": "#22d3ee", "min_elo": 1500},
    {"key": "elite",    "name": "نخبة",   "color": "#f43f5e", "min_elo": 1750},
]
# داخل كل مجموعة: 3 درجات موزعة على مدى الـElo حتى المجموعة التالية
RANK_DIVISIONS = 3

# ============================================================
#  3) نظام الموسم والـPass (نموذج Brawl Stars — منفصل عن الرتبة)
# ============================================================
# الموسم شهري: يبدأ الخميس الثالث من كل شهر (كما بالوثيقة)
SEASON_LENGTH_DAYS = 30

# Pass XP منفصل تماماً عن XP الليفل وElo. مصادره: اللعب + المهام.
PASS_XP_PER_MATCH = 10           # لكل مباراة مكتملة (فوز أو خسارة)
PASS_XP_WIN_BONUS = 5            # إضافي للفائز
PASS_TIERS = 30                  # عدد محطات الـPass في الموسم
PASS_XP_PER_TIER = 100           # Pass XP للانتقال بين محطتين

# سعر الترقية إلى Premium Pass بالجواهر (مشتق حسابياً — انظر التقرير)
PREMIUM_PASS_PRICE_GEMS = 90
# مجموع الجواهر التي يردّها مسار Premium عبر محطاته (يموّل نفسه: +30 صافٍ)
PREMIUM_PASS_GEM_PAYBACK = 120

# ============================================================
#  4) مكافآت المهام
# ============================================================
# اليومية: كوينز + XP فقط (لا جواهر — تحمي ندرتها)
# الأسبوعية والموسمية: تمنح جواهر
# 📆 تتابع الدخول اليومي: مكافأة تصاعدية 5→50🪙 (تُصفّر بانقطاع يوم)
LOGIN_STREAK_COINS = [5, 10, 15, 20, 30, 40, 50]  # اليوم 7+ = 50

DAILY_QUEST_SLOTS = 3            # 3 مهام يومية نشطة
WEEKLY_QUEST_SLOTS = 3          # 3 مهام أسبوعية
SEASONAL_QUEST_SLOTS = 4        # 4 مهام موسمية كبرى

# ============================================================
#  5) مكافآت المباريات (كوينز + XP فقط — لا جواهر)
#     مطابقة لجداول وثيقة الاقتصاد
# ============================================================
# حروف: (xp, coins) حسب حالة الجولات
HUROOF_REWARDS = {
    "win_2_0":   {"xp": 40, "coins": 60},
    "win_2_1":   {"xp": 30, "coins": 50},
    "loss_2_1":  {"xp": 25, "coins": 40},
    "loss_2_0":  {"xp": 15, "coins": 20},
}
# باقي الألعاب: فوز/خسارة بسيط
OTHER_REWARDS = {
    "win":  {"xp": 35, "coins": 50},
    "loss": {"xp": 15, "coins": 20},
}

# مكافآت ثابتة إضافية
FIRST_WIN_OF_DAY_COINS = 100
LEVEL_UP_COINS = 200

# ============================================================
#  دوال مساعدة على الثوابت أعلاه
# ============================================================
def tier_for_elo(elo: int) -> dict:
    """يرجع مجموعة الرتبة الحالية حسب Elo."""
    current = RANK_TIERS[0]
    for tier in RANK_TIERS:
        if elo >= tier["min_elo"]:
            current = tier
        else:
            break
    return current


def division_for_elo(elo: int) -> int:
    """الدرجة داخل المجموعة (3 = الأدنى III، 1 = الأعلى I)."""
    tier = tier_for_elo(elo)
    idx = RANK_TIERS.index(tier)
    tier_min = tier["min_elo"]
    tier_max = RANK_TIERS[idx + 1]["min_elo"] if idx + 1 < len(RANK_TIERS) else tier_min + 300
    span = max(1, tier_max - tier_min)
    progress = min(0.999, max(0.0, (elo - tier_min) / span))
    # progress 0 → درجة III (الأدنى)، 0.99 → درجة I (الأعلى)
    return RANK_DIVISIONS - int(progress * RANK_DIVISIONS)


def rank_label(elo: int) -> str:
    """تسمية مقروءة: «ذهبي II»."""
    tier = tier_for_elo(elo)
    div = division_for_elo(elo)
    roman = {1: "I", 2: "II", 3: "III"}[div]
    return f"{tier['name']} {roman}"


def division_progress(elo: int) -> int:
    """📊 التقدم داخل الدرجة الحالية (0-100):
    0 = بداية الدرجة (مثل 1000 لبرونزي I)، 100 = بلوغ الدرجة التالية."""
    tier = tier_for_elo(elo)
    idx = RANK_TIERS.index(tier)
    tier_min = tier["min_elo"]
    tier_max = RANK_TIERS[idx + 1]["min_elo"] if idx + 1 < len(RANK_TIERS) else tier_min + 300
    div_span = max(1, (tier_max - tier_min) / RANK_DIVISIONS)
    within = (elo - tier_min) % div_span
    return int(min(99, max(0, within / div_span * 100)))


def rank_snapshot(elo: int) -> dict:
    """لقطة رتبة كاملة للواجهة (بروفايل/leaderboard)."""
    tier = tier_for_elo(elo)
    return {
        "elo": elo,
        "tier": tier["key"],
        "tier_name": tier["name"],
        "color": tier["color"],
        "division": division_for_elo(elo),
        "division_progress": division_progress(elo),
        "label": rank_label(elo),
    }
