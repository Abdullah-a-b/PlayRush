"""
نظام المساعدات في «ماذا تعرف» (Play to Win)

المبدأ نفسه في كل الألعاب: المساعدة تكتيك وقرار توقيت — لا تعطي الإجابة.
3 خانات + رابعة تُشترى (ليفل 10). كل مساعدة مرة واحدة في المباراة.
تعارض تجهيز: مراوغة × محاولة ثانية (حماية مزدوجة ممنوعة — نمط البنك).
معرّفات بادئة k_ (المخزون جدول مشترك بين الألعاب).

قواعد «مراوغة» الخاصة:
- تتاح فقط في دورك وعندك سترايكان بالضبط: تنقل الدور لخصمك بلا سترايك.
- لو الطرفان على سترايكين ومن يراوغ أولاً تُقفل مراوغة خصمه لبقية
  المباراة — تمنع المراوغة المتبادلة اللانهائية في حالة 2-2.
"""

HELP_SLOTS = 3
FOURTH_SLOT_LEVEL = 10
FOURTH_SLOT_ITEM = "slot4_knowledge"

# أزواج لا يجوز تجهيزها معاً (حماية مزدوجة)
CONFLICTS = [
    ("k_dodge", "k_retry"),
]

HELP_CATALOG = {
    # ===== عادية — تبدأ مع اللاعب ×1، شراء من ليفل 0 =====
    "k_time_plus": {
        "id": "k_time_plus", "name": "وقت إضافي",
        "desc": "يضيف 5 ثوانٍ لدورك الحالي — نصف عمر الدور فرصةً إضافية للتذكر.",
        "rarity": "common", "icon": "⏱️", "enabled": True,
        "unlock_level": 0, "timing": "turn", "params": {"seconds": 5},
    },
    "k_first_letter": {
        "id": "k_first_letter", "name": "الحرف الأول",
        "desc": "يكشف لك أول حرف من إجابة عشوائية لم تُذكر بعد من القائمة.",
        "rarity": "common", "icon": "🔤", "enabled": True,
        "unlock_level": 0, "timing": "turn", "params": {},
    },
    "k_dodge": {
        "id": "k_dodge", "name": "مراوغة",
        "desc": "عند سترايكين بالضبط وفي دورك: راوغ لتنقل الدور لخصمك بلا "
                "سترايك. في حالة 2-2 من يراوغ أولاً يُقفل مراوغة خصمه. "
                "مرة واحدة بالمباراة.",
        "rarity": "common", "icon": "🌀", "enabled": True,
        "unlock_level": 0, "timing": "turn", "params": {},
    },
    # ===== نادرة =====
    "k_last_letter": {
        "id": "k_last_letter", "name": "الحرف الأخير",
        "desc": "يكشف لك آخر حرف من إجابة عشوائية لم تُذكر بعد من القائمة.",
        "rarity": "rare", "icon": "🔚", "enabled": True,
        "unlock_level": 5, "timing": "turn", "params": {},
    },
    "k_letter_count": {
        "id": "k_letter_count", "name": "عدّاد الحروف",
        "desc": "يكشف لك عدد حروف إجابة عشوائية لم تُذكر بعد من القائمة — "
                "ضيّق تفكيرك على الطول الصحيح.",
        "rarity": "rare", "icon": "🔢", "enabled": True,
        "unlock_level": 5, "timing": "turn", "params": {},
    },
    "k_retry": {
        "id": "k_retry", "name": "محاولة ثانية",
        "desc": "فعّلها في دورك: إجابتك المكتوبة الخاطئة القادمة لا تُحسب "
                "سترايكاً وتُفتح لك 5 ثوانٍ لمحاولة أخرى. لا تعمل في جولات "
                "الحسم، ولا تُجهَّز مع «مراوغة».",
        "rarity": "rare", "icon": "🔄", "enabled": True,
        "unlock_level": 5, "timing": "turn", "params": {"seconds": 5},
    },
    # ===== ملحمية =====
    "k_double_round": {
        "id": "k_double_round", "name": "مضاعفة الجولة",
        "desc": "فعّلها في دورك: إن نجوت في هذه الجولة تُضاعَف نقاطها "
                "(2←4 أو 1←2). إن خسرت الجولة ذهبت سدى — مقامرة! "
                "لا تعمل في جولات الحسم.",
        "rarity": "epic", "icon": "💎", "enabled": True,
        "unlock_level": 10, "timing": "turn", "params": {},
    },
    "k_hawk_eye": {
        "id": "k_hawk_eye", "name": "عين الصقر",
        "desc": "يكشف لك أول وآخر حرف من الإجابة نفسها (لم تُذكر بعد) — "
                "أقوى تلميح في اللعبة، والوسط عليك.",
        "rarity": "epic", "icon": "🦅", "enabled": True,
        "unlock_level": 15, "timing": "turn", "params": {},
    },
}

DEFAULT_LOADOUT = ["k_dodge", "k_time_plus", "k_first_letter"]

ENABLED_HELPS = [h for h in HELP_CATALOG.values() if h.get("enabled")]


def get_slots_for_player(level: int, owns_fourth: bool) -> int:
    return 4 if owns_fourth else HELP_SLOTS


def get_enabled_catalog():
    """قائمة (نفس شكل بقية الألعاب — loadout.js يعتمد find/filter)."""
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
