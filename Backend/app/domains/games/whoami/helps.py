"""
نظام المساعدات في «من أنا» (Play to Win)

المبدأ نفسه في كل الألعاب: المساعدة تضيّق أو تنجّي — لا تعطي الإجابة،
ولا تمنح أفضلية على الخصم في السؤال المشترك. 3 خانات + رابعة تُشترى
(ليفل 10). كل مساعدة مرة واحدة في المباراة. معرّفات بادئة w_.

ملاحظة تصميم: لا مساعدة تكشف «المعلومة التالية مبكراً» عمداً — فذلك
يشتري تقدّماً على الخصم في نفس السؤال (Pay-to-Win) لا تضييقاً شخصياً.
"""

HELP_SLOTS = 3
FOURTH_SLOT_LEVEL = 10
FOURTH_SLOT_ITEM = "slot4_whoami"

# لا أزواج متعارضة في هذه اللعبة (كل المساعدات مستقلة)
CONFLICTS = []

HELP_CATALOG = {
    # ===== عادية — تبدأ مع اللاعب ×1 (هدية البداية) =====
    "w_extend_buzz": {
        "id": "w_extend_buzz", "name": "تمديد الجرس",
        "desc": "بعد ضغطك الجرس: يضيف 5 ثوانٍ لنافذة إجابتك (10←15) — "
                "متنفّس للتذكّر تحت الضغط.",
        "rarity": "common", "icon": "⏱️", "enabled": True,
        "unlock_level": 0, "timing": "buzzed", "params": {"seconds": 5},
    },
    "w_reveal_category": {
        "id": "w_reveal_category", "name": "كاشف المجال",
        "desc": "يكشف لك مجال الشخصية (عالم/أديب/رياضي/مخترع...) — "
                "تلميح تضييق ذكي دون كشف الاسم.",
        "rarity": "common", "icon": "🏷️", "enabled": True,
        "unlock_level": 0, "timing": "revealing", "params": {},
    },
    "w_first_letter": {
        "id": "w_first_letter", "name": "أول حرف",
        "desc": "يكشف لك أول حرف من اسم الشخصية.",
        "rarity": "common", "icon": "🔤", "enabled": True,
        "unlock_level": 0, "timing": "revealing", "params": {},
    },
    # ===== نادرة =====
    "w_strike_shield": {
        "id": "w_strike_shield", "name": "درع السترايك",
        "desc": "فعّلها في دورك: أول خطأ لك في الشخصية الحالية لا يُحسب "
                "سترايكاً. لا يعمل في جولات كسر التعادل.",
        "rarity": "rare", "icon": "🛡️", "enabled": True,
        "unlock_level": 5, "timing": "revealing", "params": {},
    },
    "w_reveal_era": {
        "id": "w_reveal_era", "name": "كاشف الحقبة",
        "desc": "يكشف لك الحقبة الزمنية للشخصية (مثل: القرن العشرين / "
                "العصر العباسي) — تضييق زمني يقرّبك من الإجابة.",
        "rarity": "rare", "icon": "🎂", "enabled": True,
        "unlock_level": 5, "timing": "revealing", "params": {},
    },
    # ===== ملحمية =====
    "w_half_name": {
        "id": "w_half_name", "name": "نصف الاسم",
        "desc": "يكشف لك أول وآخر حرف من اسم الشخصية معاً — أقوى تلميح "
                "في اللعبة، والوسط عليك.",
        "rarity": "epic", "icon": "🎯", "enabled": True,
        "unlock_level": 10, "timing": "revealing", "params": {},
    },
    "w_lock_points": {
        "id": "w_lock_points", "name": "قفل النقاط",
        "desc": "فعّلها مبكراً: تثبّت قيمة نقاط الشخصية الحالية عند مستواها "
                "الآن، فلا تنقص مع كشف المعلومات التالية. مقامرة توقيت! "
                "لا يعمل في جولات كسر التعادل.",
        "rarity": "epic", "icon": "🔒", "enabled": True,
        "unlock_level": 15, "timing": "revealing", "params": {},
    },
}

DEFAULT_LOADOUT = ["w_extend_buzz", "w_reveal_category", "w_first_letter"]

ENABLED_HELPS = [h for h in HELP_CATALOG.values() if h.get("enabled")]


def get_slots_for_player(level: int, owns_fourth: bool) -> int:
    return 4 if owns_fourth else HELP_SLOTS


def get_enabled_catalog():
    return ENABLED_HELPS


def is_valid_help(help_id: str) -> bool:
    h = HELP_CATALOG.get(help_id)
    return bool(h and h.get("enabled"))


def get_help(help_id: str):
    return HELP_CATALOG.get(help_id)


def loadout_conflict(slots):
    s = set(slots or [])
    for a, b in CONFLICTS:
        if a in s and b in s:
            return (a, b)
    return None
