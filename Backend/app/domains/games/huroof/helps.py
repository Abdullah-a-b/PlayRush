"""
 نظام المساعدات في لعبة حروف (Phase 0 — 3 مساعدات بداية)

المبدأ: المساعدة تساعدك، لا تعاقب خصمك (Play to Win لا Pay to Win).
كل مساعدة تُستخدم مرة واحدة فقط في المباراة، و3 خانات للاعب.

المساعدات المُفعّلة الآن (الفئة العادية):
  - extend_time   : تمديد وقت الإجابة (+ثوانٍ، لك فقط)
  - change_question: سؤال جديد لنفس الحرف
  - count_letters : كشف عدد حروف الإجابة

الكتالوج الكامل (للمتجر لاحقاً) معرّف في HELP_CATALOG مع حالة enabled.
"""

# الكتالوج الكامل — كل مساعدات حروف مُفعّلة، بمستويات فتح متدرّجة
HELP_CATALOG = {
    # عادية (Common) — الثلاث الأساسية كلها مُتاحة من ليفل 0
    # timing: "pre" (قبل اختيار الحرف) | "post" (بعد اختيار الحرف وظهور السؤال) | "any" (مرن)
    "extend_time": {
        "id": "extend_time",
        "name": "تمديد الوقت",
        "desc": "يضيف 10 ثوانٍ إضافية لمؤقّت إجابتك. يُستخدم بعد اختيار الحرف.",
        "rarity": "common",
        "icon": "⏱️",
        "enabled": True,
        "unlock_level": 0,
        "timing": "post",
        "params": {"seconds": 10},
    },
    "count_letters": {
        "id": "count_letters",
        "name": "كاشف عدد الحروف",
        "desc": "يكشف عدد حروف الإجابة المطلوبة، مما يضيّق نطاق التفكير.",
        "rarity": "common",
        "icon": "🔢",
        "enabled": True,
        "unlock_level": 0,
        "timing": "post",
        "params": {},
    },
    "change_question": {
        "id": "change_question",
        "name": "تغيير السؤال",
        "desc": "يحذف السؤال الحالي ويجلب سؤالاً جديداً لنفس الحرف.",
        "rarity": "common",
        "icon": "🔄",
        "enabled": True,
        "unlock_level": 0,
        "timing": "post",
        "params": {},
    },
    "skip_letter": {
        "id": "skip_letter", "name": "تخطّي الحرف",
        "desc": "تتجاهل الحرف الحالي وتعود لاختيار حرف آخر بلا عقوبة.",
        "rarity": "common", "icon": "⏭️", "enabled": True,
        "unlock_level": 3, "timing": "post", "params": {},
    },
    # نادرة (Rare) — منتصف الطريق
    "reveal_second_letter": {
        "id": "reveal_second_letter", "name": "كاشف الحرف الثاني",
        "desc": "يكشف الحرف الذي يلي الحرف المختار في الإجابة.",
        "rarity": "rare", "icon": "🔍", "enabled": True,
        "unlock_level": 5, "timing": "post", "params": {},
    },
    "reveal_last_letter": {
        "id": "reveal_last_letter", "name": "كاشف آخر حرف",
        "desc": "يكشف الحرف الأخير من الإجابة المطلوبة.",
        "rarity": "rare", "icon": "🎯", "enabled": True,
        "unlock_level": 7, "timing": "post", "params": {},
    },
    "hint_category": {
        "id": "hint_category", "name": "تلميح التصنيف",
        "desc": "يُظهر مجال السؤال (رياضة، علوم، تاريخ...).",
        "rarity": "rare", "icon": "🏷️", "enabled": True,
        "unlock_level": 9, "timing": "post", "params": {},
    },
    # ملحمية (Epic) — متقدّمة (كوينز فقط — لا جواهر، Play to Win)
    "second_chance": {
        "id": "second_chance", "name": "فرصة ثانية",
        "desc": "إذا أخطأت، تحصل على محاولة إضافية فورية لنفس السؤال.",
        "rarity": "epic", "icon": "🔁", "enabled": False,
        "unlock_level": 12, "timing": "post", "params": {},
    },
    "freeze_timer": {
        "id": "freeze_timer", "name": "تجميد المؤقّت",
        "desc": "يوقف عدّاد وقتك 5 ثوانٍ كاملة. يُستخدم بعد اختيار الحرف.",
        "rarity": "epic", "icon": "❄️", "enabled": True,
        "unlock_level": 12, "timing": "post", "params": {"seconds": 5},
    },
    "reveal_middle_letter": {
        "id": "reveal_middle_letter", "name": "كاشف حرف وسطي",
        "desc": "يكشف حرفاً واحداً من وسط الإجابة — تلميح خفيف لا يعطي الكلمة.",
        "rarity": "epic", "icon": "🎲", "enabled": True,
        "unlock_level": 15, "timing": "post", "params": {},
    },
    "choose_category": {
        "id": "choose_category", "name": "اختيار التصنيف",
        "desc": "تحدد مجال سؤالك القادم مسبقاً (قبل اختيار الحرف).",
        "rarity": "epic", "icon": "📚", "enabled": True,
        "unlock_level": 18, "timing": "pre", "params": {},
    },
}

# المساعدات المُفعّلة فقط (للبداية)
ENABLED_HELPS = [h for h in HELP_CATALOG.values() if h.get("enabled")]
ENABLED_HELP_IDS = [h["id"] for h in ENABLED_HELPS]

# عدد الخانات الأساسية + الخانة الرابعة المتقدّمة
HELP_SLOTS = 3
FOURTH_SLOT_LEVEL = 10
FOURTH_SLOT_ITEM = "slot4_huroof"


def get_slots_for_level(level: int) -> int:
    return HELP_SLOTS


def get_slots_for_player(level: int, owns_fourth: bool) -> int:
    return 4 if owns_fourth else HELP_SLOTS

# المساعدات الافتراضية في الخانات الثلاث (للبداية — كلها مُفعّلة)
DEFAULT_LOADOUT = ["extend_time", "change_question", "count_letters"]


def get_enabled_catalog():
    """يُرجع المساعدات المُفعّلة فقط (للعرض في اللعبة)."""
    return ENABLED_HELPS


def is_valid_help(help_id: str) -> bool:
    """هل المساعدة موجودة ومُفعّلة؟"""
    h = HELP_CATALOG.get(help_id)
    return bool(h and h.get("enabled"))


def get_help(help_id: str):
    return HELP_CATALOG.get(help_id)
