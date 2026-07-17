"""
 نظام المساعدات في "مسيرة لاعب" (Play to Win)

المبدأ الذهبي: المساعدة تساعدك تفكّر أسرع أو تناور تكتيكياً — لا تعطيك الإجابة.
3 عادية تبدأ مع اللاعب ×1 | خانات: 3 + رابعة تُشترى (ليفل 10).
درع السترايك وقفل النقطتين لا يعملان في جولة كسر التعادل (حماية التنافس).
معرّفات بادئة c_ لتجنّب التصادم مع مخزون حروف (جدول مشترك).
"""

HELP_SLOTS = 3
FOURTH_SLOT_LEVEL = 10
FOURTH_SLOT_ITEM = "slot4_career"

HELP_CATALOG = {
    # عادية — تبدأ مع اللاعب ×1، شراء من ليفل 0
    "c_extend_write": {
        "id": "c_extend_write", "name": "تمديد الكتابة",
        "desc": "يضيف 5 ثوانٍ لنافذة كتابتك بعد ضغط الجرس (10→15).",
        "rarity": "common", "icon": "⏱️", "enabled": True,
        "unlock_level": 0, "timing": "buzzed", "params": {"seconds": 5},
    },
    "c_nationality": {
        "id": "c_nationality", "name": "كاشف الجنسية",
        "desc": "يكشف لك جنسية اللاعب المعروض — معلومة تضييق ذكية.",
        "rarity": "common", "icon": "🌍", "enabled": True,
        "unlock_level": 0, "timing": "revealing", "params": {},
    },
    "c_club_count": {
        "id": "c_club_count", "name": "عدّاد الأندية",
        "desc": "يكشف كم نادياً إجمالاً في مسيرة اللاعب — قرّر توقيت جرسك بذكاء.",
        "rarity": "common", "icon": "📊", "enabled": True,
        "unlock_level": 0, "timing": "revealing", "params": {},
    },
    # نادرة
    "c_first_letter": {
        "id": "c_first_letter", "name": "الحرف الأول",
        "desc": "يكشف أول حرف من اسم اللاعب.",
        "rarity": "rare", "icon": "🔤", "enabled": True,
        "unlock_level": 5, "timing": "revealing", "params": {},
    },
    "c_strike_shield": {
        "id": "c_strike_shield", "name": "درع السترايك",
        "desc": "أول خطأ لك في الشخصية الحالية لا يُحسب سترايكاً. لا يعمل في كسر التعادل.",
        "rarity": "rare", "icon": "🛡️", "enabled": True,
        "unlock_level": 8, "timing": "revealing", "params": {},
    },
    # ملحمية
    "c_era": {
        "id": "c_era", "name": "كاشف الجيل",
        "desc": "يكشف الفترة الزمنية لمسيرة اللاعب (مثل: 1995-2010).",
        "rarity": "epic", "icon": "🎂", "enabled": True,
        "unlock_level": 12, "timing": "revealing", "params": {},
    },
    "c_position": {
        "id": "c_position", "name": "كاشف المركز",
        "desc": "يكشف مركز اللاعب (مهاجم/وسط/مدافع/حارس).",
        "rarity": "epic", "icon": "🎯", "enabled": True,
        "unlock_level": 14, "timing": "revealing", "params": {},
    },
    "c_double_lock": {
        "id": "c_double_lock", "name": "قفل النقطتين",
        "desc": "فعّلها مبكراً: إجابتك الصحيحة بعد اكتمال المسيرة تمنحك نقطتين بدل نقطة. لا يعمل في كسر التعادل.",
        "rarity": "epic", "icon": "🔒", "enabled": True,
        "unlock_level": 16, "timing": "revealing", "params": {},
    },
}

DEFAULT_LOADOUT = ["c_extend_write", "c_nationality", "c_club_count"]


def get_slots_for_player(level: int, owns_fourth: bool) -> int:
    return 4 if owns_fourth else HELP_SLOTS


ENABLED_HELPS = [h for h in HELP_CATALOG.values() if h.get("enabled")]


def get_enabled_catalog():
    """قائمة (نفس شكل حروف — loadout.js يعتمد find/filter)."""
    return ENABLED_HELPS


def is_valid_help(help_id: str) -> bool:
    h = HELP_CATALOG.get(help_id)
    return bool(h and h.get("enabled"))


def get_help(help_id: str):
    return HELP_CATALOG.get(help_id)
