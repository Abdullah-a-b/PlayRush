"""
 نظام المساعدات في "البنك" (Play to Win)

المبدأ: تساعد التكتيك والمقامرة الذكية — لا تعطي الإجابة.
3 عادية تبدأ مع اللاعب ×1 | خانات: 3 + رابعة تُشترى (ليفل 10).
تعارض تجهيز: درع الرصيد × فرصة ثانية (حماية مزدوجة ممنوعة).
معرّفات بادئة b_ (المخزون جدول مشترك بين الألعاب).
"""

HELP_SLOTS = 3
FOURTH_SLOT_LEVEL = 10
FOURTH_SLOT_ITEM = "slot4_bank"

# أزواج لا يجوز تجهيزها معاً (حماية مزدوجة)
CONFLICTS = [
    ("b_shield", "b_second_chance"),
]

HELP_CATALOG = {
    # عادية — تبدأ مع اللاعب ×1، شراء من ليفل 0
    "b_skip": {
        "id": "b_skip", "name": "تخطّي السؤال",
        "desc": "يستبدل سؤالك الحالي بسؤال آخر من نفس الصعوبة — بلا عقوبة.",
        "rarity": "common", "icon": "⏭️", "enabled": True,
        "unlock_level": 0, "timing": "question", "params": {},
    },
    "b_first_letter": {
        "id": "b_first_letter", "name": "الحرف الأول",
        "desc": "يكشف أول حرف من إجابة سؤالك الحالي.",
        "rarity": "common", "icon": "🔤", "enabled": True,
        "unlock_level": 0, "timing": "question", "params": {},
    },
    "b_time_plus": {
        "id": "b_time_plus", "name": "وقت إضافي",
        "desc": "يضيف 10 ثوانٍ لوقت جولتك الحالية.",
        "rarity": "common", "icon": "⏱️", "enabled": True,
        "unlock_level": 0, "timing": "playing", "params": {"seconds": 10},
    },
    # نادرة
    "b_shield": {
        "id": "b_shield", "name": "درع الرصيد",
        "desc": "خطؤك القادم لا يمسح رصيدك المؤقت (يُستهلك عنده). لا يُجهَّز مع فرصة ثانية.",
        "rarity": "rare", "icon": "🛡️", "enabled": True,
        "unlock_level": 5, "timing": "playing", "params": {},
    },
    "b_double_next": {
        "id": "b_double_next", "name": "نقاط مضاعفة",
        "desc": "سؤالك القادم يمنح ×2 نقاطاً إن أصبت — والخطأ يمسح كالعادة. مقامرة!",
        "rarity": "rare", "icon": "💰", "enabled": True,
        "unlock_level": 8, "timing": "playing", "params": {},
    },
    # ملحمية
    "b_second_chance": {
        "id": "b_second_chance", "name": "فرصة ثانية",
        "desc": "عند خطئك القادم: تجاوب مرة أخرى على نفس السؤال (+5ث) قبل احتسابه. لا تُجهَّز مع درع الرصيد.",
        "rarity": "epic", "icon": "🔄", "enabled": True,
        "unlock_level": 12, "timing": "playing", "params": {},
    },
    "b_hard_boost": {
        "id": "b_hard_boost", "name": "قفزة للصعب",
        "desc": "سلّمك يقفز فوراً للصعب (3 نقاط لكل سؤال) — مخاطرة قصوى.",
        "rarity": "epic", "icon": "🚀", "enabled": True,
        "unlock_level": 14, "timing": "playing", "params": {},
    },
    "b_flash_bank": {
        "id": "b_flash_bank", "name": "بنك خاطف",
        "desc": "بنك فوري حتى أثناء عرض السؤال — ينقذ رصيدك في اللحظات الحرجة.",
        "rarity": "epic", "icon": "⚡", "enabled": True,
        "unlock_level": 16, "timing": "any", "params": {},
    },
}

DEFAULT_LOADOUT = ["b_skip", "b_first_letter", "b_time_plus"]

ENABLED_HELPS = [h for h in HELP_CATALOG.values() if h.get("enabled")]


def get_slots_for_player(level: int, owns_fourth: bool) -> int:
    return 4 if owns_fourth else HELP_SLOTS


def get_enabled_catalog():
    """قائمة (نفس شكل حروف — loadout.js يعتمد find/filter)."""
    return ENABLED_HELPS


def is_valid_help(help_id: str) -> bool:
    h = HELP_CATALOG.get(help_id)
    return bool(h and h.get("enabled"))


def get_help(help_id: str):
    return HELP_CATALOG.get(help_id)


def loadout_conflict(slots):
    """يرجع (id1, id2) لو التشكيلة تحوي زوجاً متعارضاً، وإلا None."""
    s = set(slots or [])
    for a, b in CONFLICTS:
        if a in s and b in s:
            return (a, b)
    return None
