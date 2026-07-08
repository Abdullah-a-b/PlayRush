"""
🛒 كتالوج المتجر (Store Catalog) — قيم افتراضية مبدئية

المتجر يعرض:
  - في لوبي كل لعبة: مساعدات تلك اللعبة + كل التجميليات
  - في categories: كل المساعدات (كل الألعاب) + كل التجميليات

كل عنصر له:
  - unlock_level: المستوى الذي يُفتح فيه (0 = متاح للجميع)
  - price + currency: السعر (coins/gems)
  - category: نوع العنصر (help/avatar/theme/emoji/chat_phrase)
  - game: للمساعدات فقط (huroof/bank/...) أو None للتجميليات

⚠️ القيم الافتراضية مبدئية — عدّلها بعد تحديد الأسعار النهائية.
"""

# ===== مساعدات حسب اللعبة =====
# (نستورد التعريفات من helps.py للعبة حروف)
from app.games.huroof.helps import HELP_CATALOG as HUROOF_HELPS
from app.games.career.helps import HELP_CATALOG as CAREER_HELPS
from app.games.bank.helps import HELP_CATALOG as BANK_HELPS

# نبني عناصر متجر للمساعدات (كوينز فقط — لا جواهر، Play to Win)
_RARITY_DEFAULTS = {
    "common": {"price": 150, "currency": "coins", "unlock_level": 0},
    "rare":   {"price": 400, "currency": "coins", "unlock_level": 5},
    "epic":   {"price": 900, "currency": "coins", "unlock_level": 12},
    "legendary": {"price": 1500, "currency": "coins", "unlock_level": 20},
}


def _build_help_items(help_catalog: dict, game: str) -> list:
    items = []
    for hid, h in help_catalog.items():
        if not h.get("enabled"):
            continue  # المعطّلة لا تظهر في المتجر بعد
        rd = _RARITY_DEFAULTS.get(h["rarity"], _RARITY_DEFAULTS["common"])
        items.append({
            "id": f"help_{game}_{hid}",
            "ref_id": hid,            # المعرّف الأصلي للمساعدة
            "category": "help",
            "game": game,
            "name": h["name"],
            "desc": h["desc"],
            "icon": h["icon"],
            "rarity": h["rarity"],
            "price": rd["price"],
            "currency": rd["currency"],
            # نستخدم مستوى الفتح المحدد لكل مساعدة (أو الافتراضي حسب الندرة)
            "unlock_level": h.get("unlock_level", rd["unlock_level"]),
        })
    # نرتّبها حسب مستوى الفتح (الأسهل أولاً)
    items.sort(key=lambda x: x["unlock_level"])
    return items


# مساعدات كل لعبة (حالياً حروف فقط مفعّلة، البقية placeholders)
HELPS_BY_GAME = {
    "huroof": _build_help_items(HUROOF_HELPS, "huroof"),
    "career": _build_help_items(CAREER_HELPS, "career"),
    "bank": _build_help_items(BANK_HELPS, "bank"),     # لعبة البنك — مساعداتها لاحقاً
    "game3": [],
    "game4": [],
    "game5": [],
}

# ===== التجميليات (مشتركة عبر كل المنصة) =====
COSMETICS = [
    # 🎨 أفاتارات (1-15 مجانية في الإعدادات، 16-60 للشراء)
    {"id": "avatar_16", "category": "avatar", "game": None,
     "name": "أفاتار 16", "icon": "🎭", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 0,
     "asset": "assets/avatars/avatar_16.svg"},
    {"id": "avatar_17", "category": "avatar", "game": None,
     "name": "أفاتار 17", "icon": "🎭", "rarity": "common",
     "price": 170, "currency": "coins", "unlock_level": 0,
     "asset": "assets/avatars/avatar_17.svg"},
    {"id": "avatar_18", "category": "avatar", "game": None,
     "name": "أفاتار 18", "icon": "🎭", "rarity": "common",
     "price": 190, "currency": "coins", "unlock_level": 0,
     "asset": "assets/avatars/avatar_18.svg"},
    {"id": "avatar_19", "category": "avatar", "game": None,
     "name": "أفاتار 19", "icon": "🎭", "rarity": "common",
     "price": 210, "currency": "coins", "unlock_level": 0,
     "asset": "assets/avatars/avatar_19.svg"},
    {"id": "avatar_20", "category": "avatar", "game": None,
     "name": "أفاتار 20", "icon": "🎭", "rarity": "common",
     "price": 230, "currency": "coins", "unlock_level": 1,
     "asset": "assets/avatars/avatar_20.svg"},
    {"id": "avatar_21", "category": "avatar", "game": None,
     "name": "أفاتار 21", "icon": "🎭", "rarity": "common",
     "price": 250, "currency": "coins", "unlock_level": 1,
     "asset": "assets/avatars/avatar_21.svg"},
    {"id": "avatar_22", "category": "avatar", "game": None,
     "name": "أفاتار 22", "icon": "🎭", "rarity": "common",
     "price": 270, "currency": "coins", "unlock_level": 1,
     "asset": "assets/avatars/avatar_22.svg"},
    {"id": "avatar_23", "category": "avatar", "game": None,
     "name": "أفاتار 23", "icon": "🎭", "rarity": "common",
     "price": 290, "currency": "coins", "unlock_level": 1,
     "asset": "assets/avatars/avatar_23.svg"},
    {"id": "avatar_24", "category": "avatar", "game": None,
     "name": "أفاتار 24", "icon": "🎭", "rarity": "common",
     "price": 310, "currency": "coins", "unlock_level": 2,
     "asset": "assets/avatars/avatar_24.svg"},
    {"id": "avatar_25", "category": "avatar", "game": None,
     "name": "أفاتار 25", "icon": "🎭", "rarity": "common",
     "price": 330, "currency": "coins", "unlock_level": 2,
     "asset": "assets/avatars/avatar_25.svg"},
    {"id": "avatar_26", "category": "avatar", "game": None,
     "name": "أفاتار 26", "icon": "🎭", "rarity": "common",
     "price": 350, "currency": "coins", "unlock_level": 2,
     "asset": "assets/avatars/avatar_26.svg"},
    {"id": "avatar_27", "category": "avatar", "game": None,
     "name": "أفاتار 27", "icon": "🎭", "rarity": "common",
     "price": 370, "currency": "coins", "unlock_level": 2,
     "asset": "assets/avatars/avatar_27.svg"},
    {"id": "avatar_28", "category": "avatar", "game": None,
     "name": "أفاتار 28", "icon": "🎭", "rarity": "common",
     "price": 390, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_28.svg"},
    {"id": "avatar_29", "category": "avatar", "game": None,
     "name": "أفاتار 29", "icon": "🎭", "rarity": "common",
     "price": 410, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_29.svg"},
    {"id": "avatar_30", "category": "avatar", "game": None,
     "name": "أفاتار 30", "icon": "🎭", "rarity": "common",
     "price": 430, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_30.svg"},
    {"id": "avatar_31", "category": "avatar", "game": None,
     "name": "أفاتار 31", "icon": "🎭", "rarity": "common",
     "price": 450, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_31.svg"},
    {"id": "avatar_32", "category": "avatar", "game": None,
     "name": "أفاتار 32", "icon": "🎭", "rarity": "common",
     "price": 470, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_32.svg"},
    {"id": "avatar_33", "category": "avatar", "game": None,
     "name": "أفاتار 33", "icon": "🎭", "rarity": "common",
     "price": 490, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_33.svg"},
    {"id": "avatar_34", "category": "avatar", "game": None,
     "name": "أفاتار 34", "icon": "🎭", "rarity": "common",
     "price": 510, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_34.svg"},
    {"id": "avatar_35", "category": "avatar", "game": None,
     "name": "أفاتار 35", "icon": "🎭", "rarity": "common",
     "price": 530, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_35.svg"},
    {"id": "avatar_36", "category": "avatar", "game": None,
     "name": "أفاتار نادر 36", "icon": "⭐", "rarity": "rare",
     "price": 600, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_36.svg"},
    {"id": "avatar_37", "category": "avatar", "game": None,
     "name": "أفاتار نادر 37", "icon": "⭐", "rarity": "rare",
     "price": 660, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_37.svg"},
    {"id": "avatar_38", "category": "avatar", "game": None,
     "name": "أفاتار نادر 38", "icon": "⭐", "rarity": "rare",
     "price": 720, "currency": "coins", "unlock_level": 3,
     "asset": "assets/avatars/avatar_38.svg"},
    {"id": "avatar_39", "category": "avatar", "game": None,
     "name": "أفاتار نادر 39", "icon": "⭐", "rarity": "rare",
     "price": 780, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_39.svg"},
    {"id": "avatar_40", "category": "avatar", "game": None,
     "name": "أفاتار نادر 40", "icon": "⭐", "rarity": "rare",
     "price": 840, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_40.svg"},
    {"id": "avatar_41", "category": "avatar", "game": None,
     "name": "أفاتار نادر 41", "icon": "⭐", "rarity": "rare",
     "price": 900, "currency": "coins", "unlock_level": 4,
     "asset": "assets/avatars/avatar_41.svg"},
    {"id": "avatar_42", "category": "avatar", "game": None,
     "name": "أفاتار نادر 42", "icon": "⭐", "rarity": "rare",
     "price": 960, "currency": "coins", "unlock_level": 5,
     "asset": "assets/avatars/avatar_42.svg"},
    {"id": "avatar_43", "category": "avatar", "game": None,
     "name": "أفاتار نادر 43", "icon": "⭐", "rarity": "rare",
     "price": 1020, "currency": "coins", "unlock_level": 5,
     "asset": "assets/avatars/avatar_43.svg"},
    {"id": "avatar_44", "category": "avatar", "game": None,
     "name": "أفاتار نادر 44", "icon": "⭐", "rarity": "rare",
     "price": 1080, "currency": "coins", "unlock_level": 5,
     "asset": "assets/avatars/avatar_44.svg"},
    {"id": "avatar_45", "category": "avatar", "game": None,
     "name": "أفاتار نادر 45", "icon": "⭐", "rarity": "rare",
     "price": 1140, "currency": "coins", "unlock_level": 6,
     "asset": "assets/avatars/avatar_45.svg"},
    {"id": "avatar_46", "category": "avatar", "game": None,
     "name": "أفاتار نادر 46", "icon": "⭐", "rarity": "rare",
     "price": 1200, "currency": "coins", "unlock_level": 6,
     "asset": "assets/avatars/avatar_46.svg"},
    {"id": "avatar_47", "category": "avatar", "game": None,
     "name": "أفاتار نادر 47", "icon": "⭐", "rarity": "rare",
     "price": 1260, "currency": "coins", "unlock_level": 6,
     "asset": "assets/avatars/avatar_47.svg"},
    {"id": "avatar_48", "category": "avatar", "game": None,
     "name": "أفاتار نادر 48", "icon": "⭐", "rarity": "rare",
     "price": 1320, "currency": "coins", "unlock_level": 7,
     "asset": "assets/avatars/avatar_48.svg"},
    {"id": "avatar_49", "category": "avatar", "game": None,
     "name": "أفاتار نادر 49", "icon": "⭐", "rarity": "rare",
     "price": 1380, "currency": "coins", "unlock_level": 7,
     "asset": "assets/avatars/avatar_49.svg"},
    {"id": "avatar_50", "category": "avatar", "game": None,
     "name": "أفاتار نادر 50", "icon": "⭐", "rarity": "rare",
     "price": 1440, "currency": "coins", "unlock_level": 7,
     "asset": "assets/avatars/avatar_50.svg"},
    {"id": "avatar_51", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 51", "icon": "👑", "rarity": "epic",
     "price": 25, "currency": "gems", "unlock_level": 8,
     "asset": "assets/avatars/avatar_51.svg"},
    {"id": "avatar_52", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 52", "icon": "👑", "rarity": "epic",
     "price": 33, "currency": "gems", "unlock_level": 9,
     "asset": "assets/avatars/avatar_52.svg"},
    {"id": "avatar_53", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 53", "icon": "👑", "rarity": "epic",
     "price": 41, "currency": "gems", "unlock_level": 10,
     "asset": "assets/avatars/avatar_53.svg"},
    {"id": "avatar_54", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 54", "icon": "👑", "rarity": "epic",
     "price": 49, "currency": "gems", "unlock_level": 11,
     "asset": "assets/avatars/avatar_54.svg"},
    {"id": "avatar_55", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 55", "icon": "👑", "rarity": "epic",
     "price": 57, "currency": "gems", "unlock_level": 12,
     "asset": "assets/avatars/avatar_55.svg"},
    {"id": "avatar_56", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 56", "icon": "👑", "rarity": "epic",
     "price": 65, "currency": "gems", "unlock_level": 13,
     "asset": "assets/avatars/avatar_56.svg"},
    {"id": "avatar_57", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 57", "icon": "👑", "rarity": "epic",
     "price": 73, "currency": "gems", "unlock_level": 14,
     "asset": "assets/avatars/avatar_57.svg"},
    {"id": "avatar_58", "category": "avatar", "game": None,
     "name": "أفاتار ملكي 58", "icon": "👑", "rarity": "epic",
     "price": 81, "currency": "gems", "unlock_level": 15,
     "asset": "assets/avatars/avatar_58.svg"},
    {"id": "avatar_59", "category": "avatar", "game": None,
     "name": "أفاتار أسطوري 59", "icon": "🔥", "rarity": "legendary",
     "price": 100, "currency": "gems", "unlock_level": 18,
     "asset": "assets/avatars/avatar_59.svg"},
    {"id": "avatar_60", "category": "avatar", "game": None,
     "name": "أفاتار أسطوري 60", "icon": "🔥", "rarity": "legendary",
     "price": 150, "currency": "gems", "unlock_level": 20,
     "asset": "assets/avatars/avatar_60.svg"},

    # 🎭 ثيمات (تصاميم متكاملة)
    {"id": "theme_ocean", "category": "theme", "game": None,
     "name": "ثيم المحيط", "icon": "🌊", "rarity": "common",
     "price": 300, "currency": "coins", "unlock_level": 1},
    {"id": "theme_forest", "category": "theme", "game": None,
     "name": "ثيم الغابة", "icon": "🌲", "rarity": "common",
     "price": 350, "currency": "coins", "unlock_level": 2},
    {"id": "theme_cherry", "category": "theme", "game": None,
     "name": "ثيم الكرز", "icon": "🌸", "rarity": "common",
     "price": 400, "currency": "coins", "unlock_level": 3},
    {"id": "theme_sunset", "category": "theme", "game": None,
     "name": "ثيم الغروب", "icon": "🌅", "rarity": "rare",
     "price": 700, "currency": "coins", "unlock_level": 5},
    {"id": "theme_cyber", "category": "theme", "game": None,
     "name": "ثيم سايبر", "icon": "🤖", "rarity": "rare",
     "price": 900, "currency": "coins", "unlock_level": 7},
    {"id": "theme_lava", "category": "theme", "game": None,
     "name": "ثيم الحمم", "icon": "🌋", "rarity": "rare",
     "price": 1100, "currency": "coins", "unlock_level": 9},
    {"id": "theme_galaxy", "category": "theme", "game": None,
     "name": "ثيم المجرّة", "icon": "🌌", "rarity": "epic",
     "price": 60, "currency": "gems", "unlock_level": 12},
    {"id": "theme_aurora", "category": "theme", "game": None,
     "name": "ثيم الشفق", "icon": "❄️", "rarity": "epic",
     "price": 90, "currency": "gems", "unlock_level": 16},
    {"id": "theme_gold", "category": "theme", "game": None,
     "name": "ثيم ذهبي", "icon": "✨", "rarity": "legendary",
     "price": 150, "currency": "gems", "unlock_level": 25},
    {"id": "theme_diamond", "category": "theme", "game": None,
     "name": "ثيم الماس", "icon": "💎", "rarity": "legendary",
     "price": 220, "currency": "gems", "unlock_level": 30},

    # 😄 إيموجيات متحركة (Lottie)
    {"id": "emoji_laugh", "category": "emoji", "game": None,
     "name": "ضحكة", "icon": "😂", "rarity": "common",
     "price": 100, "currency": "coins", "unlock_level": 0},
    {"id": "emoji_cry", "category": "emoji", "game": None,
     "name": "بكاء", "icon": "😭", "rarity": "common",
     "price": 100, "currency": "coins", "unlock_level": 0},
    {"id": "emoji_angry", "category": "emoji", "game": None,
     "name": "غضب", "icon": "😡", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 1},
    {"id": "emoji_think", "category": "emoji", "game": None,
     "name": "تفكير", "icon": "🤔", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "emoji_cool", "category": "emoji", "game": None,
     "name": "متباهٍ", "icon": "😎", "rarity": "rare",
     "price": 400, "currency": "coins", "unlock_level": 4},
    {"id": "emoji_fire", "category": "emoji", "game": None,
     "name": "نار", "icon": "🔥", "rarity": "rare",
     "price": 500, "currency": "coins", "unlock_level": 6},
    {"id": "emoji_clap", "category": "emoji", "game": None,
     "name": "تصفيق", "icon": "👏", "rarity": "rare",
     "price": 550, "currency": "coins", "unlock_level": 8},
    {"id": "emoji_crown", "category": "emoji", "game": None,
     "name": "ملك", "icon": "👑", "rarity": "epic",
     "price": 35, "currency": "gems", "unlock_level": 14},
    {"id": "emoji_goat", "category": "emoji", "game": None,
     "name": "الأعظم", "icon": "🐐", "rarity": "legendary",
     "price": 100, "currency": "gems", "unlock_level": 22},
    # ✨ إيموجيات إضافية (تتطلب ملفات Lottie في assets/emojis/)
    {"id": "emoji_shock", "category": "emoji", "game": None,
     "name": "صدمة", "icon": "😱", "rarity": "common",
     "price": 200, "currency": "coins", "unlock_level": 2},
    {"id": "emoji_mindblown", "category": "emoji", "game": None,
     "name": "انفجار العقل", "icon": "🤯", "rarity": "rare",
     "price": 450, "currency": "coins", "unlock_level": 5},
    {"id": "emoji_target", "category": "emoji", "game": None,
     "name": "إصابة دقيقة", "icon": "🎯", "rarity": "rare",
     "price": 600, "currency": "coins", "unlock_level": 8},
    {"id": "emoji_heart", "category": "emoji", "game": None,
     "name": "حب", "icon": "❤️", "rarity": "rare",
     "price": 650, "currency": "coins", "unlock_level": 9},
    {"id": "emoji_devil", "category": "emoji", "game": None,
     "name": "شيطنة", "icon": "😈", "rarity": "epic",
     "price": 30, "currency": "gems", "unlock_level": 12},
    {"id": "emoji_bolt", "category": "emoji", "game": None,
     "name": "سرعة", "icon": "⚡", "rarity": "epic",
     "price": 45, "currency": "gems", "unlock_level": 15},
    {"id": "emoji_trophy", "category": "emoji", "game": None,
     "name": "بطل", "icon": "🏆", "rarity": "legendary",
     "price": 110, "currency": "gems", "unlock_level": 24},

    # 💬 عبارات دردشة عامة (للوبيات + categories)
    # 💬 عبارات عامة (للوبيات + categories) — تحيّة/روح رياضية/تفاعل
    {"id": "chat_gg", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "لعبة رائعة! 👏", "icon": "💬", "rarity": "common",
     "price": 100, "currency": "coins", "unlock_level": 0},
    {"id": "chat_hello", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "أهلاً بالجميع! 👋", "icon": "💬", "rarity": "common",
     "price": 100, "currency": "coins", "unlock_level": 0},
    {"id": "chat_lucky", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "حظ موفّق! 🍀", "icon": "💬", "rarity": "common",
     "price": 120, "currency": "coins", "unlock_level": 1},
    {"id": "chat_ready", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "جاهز للتحدّي! 🔥", "icon": "💬", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_wp", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "أحسنت اللعب! 💪", "icon": "💬", "rarity": "common",
     "price": 180, "currency": "coins", "unlock_level": 3},
    {"id": "chat_gh", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "حظاً أوفر المرة القادمة 🤝", "icon": "💬", "rarity": "rare",
     "price": 300, "currency": "coins", "unlock_level": 4},
    {"id": "chat_respect", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "احترامي! 🫡", "icon": "💬", "rarity": "rare",
     "price": 400, "currency": "coins", "unlock_level": 6},
    {"id": "chat_legend", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "أسطورة! 🐐", "icon": "💬", "rarity": "epic",
     "price": 800, "currency": "coins", "unlock_level": 10},
    {"id": "chat_unstoppable", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "لا يُوقَف! ⚡", "icon": "💬", "rarity": "epic",
     "price": 40, "currency": "gems", "unlock_level": 14},
    {"id": "chat_goat", "category": "chat_phrase", "game": None, "scope": "general",
     "name": "الأعظم على الإطلاق 👑", "icon": "💬", "rarity": "legendary",
     "price": 90, "currency": "gems", "unlock_level": 20},

    # 💬 عبارات خاصة بلعبة حروف (داخل المباراة)
    {"id": "chat_huroof_close", "category": "chat_phrase", "game": "huroof", "scope": "game",
     "name": "كانت قريبة! 😅", "icon": "🔤", "rarity": "common",
     "price": 120, "currency": "coins", "unlock_level": 1},
    {"id": "chat_huroof_easy", "category": "chat_phrase", "game": "huroof", "scope": "game",
     "name": "هذي سهلة 😎", "icon": "🔤", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_huroof_think", "category": "chat_phrase", "game": "huroof", "scope": "game",
     "name": "خلّني أفكّر... 🤔", "icon": "🔤", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_huroof_fast", "category": "chat_phrase", "game": "huroof", "scope": "game",
     "name": "بسرعة! ⏳", "icon": "🔤", "rarity": "rare",
     "price": 300, "currency": "coins", "unlock_level": 4},
    {"id": "chat_huroof_rematch", "category": "chat_phrase", "game": "huroof", "scope": "game",
     "name": "نعيدها؟ 🔄", "icon": "🔤", "rarity": "rare",
     "price": 350, "currency": "coins", "unlock_level": 5},
    {"id": "chat_huroof_master", "category": "chat_phrase", "game": "huroof", "scope": "game",
     "name": "سيّد الحروف 🏆", "icon": "🔤", "rarity": "epic",
     "price": 700, "currency": "coins", "unlock_level": 9},

    # ⚽ عبارات "مسيرة لاعب" (خاصة باللعبة)
    {"id": "chat_career_easy", "category": "chat_phrase", "game": "career", "scope": "game",
     "name": "لاعب سهل! ⚽", "icon": "⚽", "rarity": "common",
     "price": 120, "currency": "coins", "unlock_level": 1},
    {"id": "chat_career_who", "category": "chat_phrase", "game": "career", "scope": "game",
     "name": "مين هذا؟ 🤔", "icon": "⚽", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_career_early", "category": "chat_phrase", "game": "career", "scope": "game",
     "name": "عرفته من أول نادي! 🔥", "icon": "⚽", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_career_bell", "category": "chat_phrase", "game": "career", "scope": "game",
     "name": "الجرس أسرع مني 😅", "icon": "🔔", "rarity": "rare",
     "price": 300, "currency": "coins", "unlock_level": 4},
    {"id": "chat_career_legend", "category": "chat_phrase", "game": "career", "scope": "game",
     "name": "أسطورة! 👑", "icon": "⚽", "rarity": "rare",
     "price": 350, "currency": "coins", "unlock_level": 5},
    {"id": "chat_career_scout", "category": "chat_phrase", "game": "career", "scope": "game",
     "name": "كشّاف محترف 🎯", "icon": "⚽", "rarity": "epic",
     "price": 700, "currency": "coins", "unlock_level": 9},

    # 🏦 عبارات "البنك" (خاصة باللعبة)
    {"id": "chat_bank_bankit", "category": "chat_phrase", "game": "bank", "scope": "game",
     "name": "بنّكها! 🏦", "icon": "🏦", "rarity": "common",
     "price": 120, "currency": "coins", "unlock_level": 1},
    {"id": "chat_bank_gamble", "category": "chat_phrase", "game": "bank", "scope": "game",
     "name": "غامر شوي 😏", "icon": "🏦", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_bank_gone", "category": "chat_phrase", "game": "bank", "scope": "game",
     "name": "راحت عليك 💸", "icon": "🏦", "rarity": "common",
     "price": 150, "currency": "coins", "unlock_level": 2},
    {"id": "chat_bank_protected", "category": "chat_phrase", "game": "bank", "scope": "game",
     "name": "رصيدي محمي 🔒", "icon": "🏦", "rarity": "rare",
     "price": 300, "currency": "coins", "unlock_level": 4},
    {"id": "chat_bank_riskking", "category": "chat_phrase", "game": "bank", "scope": "game",
     "name": "ملك المخاطرة 👑", "icon": "🏦", "rarity": "rare",
     "price": 350, "currency": "coins", "unlock_level": 5},
    {"id": "chat_bank_mybank", "category": "chat_phrase", "game": "bank", "scope": "game",
     "name": "البنك بنكي 💰", "icon": "🏦", "rarity": "epic",
     "price": 700, "currency": "coins", "unlock_level": 9},
]


def _cosmetics_for_context(game: str = None):
    """التجميليات حسب السياق:
    - في لوبي لعبة (game محدّد): العامة + عبارات تلك اللعبة فقط.
    - في categories (game=None): كل شيء — العامة + عبارات كل الألعاب
      (مع تمييز النطاق واللعبة في الواجهة)."""
    result = []
    for c in COSMETICS:
        if c.get("category") == "chat_phrase":
            scope = c.get("scope", "general")
            if scope == "general":
                result.append(c)
            elif scope == "game":
                if game is None:
                    result.append(c)  # categories: أظهر عبارات كل الألعاب
                elif c.get("game") == game:
                    result.append(c)  # لوبي: عبارات هذه اللعبة فقط
        else:
            result.append(c)
    return result


def get_store_for_lobby(game: str) -> dict:
    """متجر لوبي لعبة: مساعدات تلك اللعبة + ترقيات + تجميليات (عامة + عبارات اللعبة)."""
    return {
        "context": game,
        "helps": HELPS_BY_GAME.get(game, []),
        "upgrades": UPGRADES_BY_GAME.get(game, []),
        "cosmetics": _cosmetics_for_context(game),
    }


def get_store_for_categories() -> dict:
    """متجر categories: كل المساعدات + الترقيات + تجميليات عامة (بلا عبارات لعبة)."""
    all_helps = []
    all_upgrades = []
    for game_helps in HELPS_BY_GAME.values():
        all_helps.extend(game_helps)
    for game_ups in UPGRADES_BY_GAME.values():
        all_upgrades.extend(game_ups)
    return {
        "context": "categories",
        "helps": all_helps,
        "upgrades": all_upgrades,
        "cosmetics": _cosmetics_for_context(None),
    }


def find_item(item_id: str):
    """يبحث عن عنصر بالـ id عبر كل الكتالوج (للشراء)."""
    for game_helps in HELPS_BY_GAME.values():
        for it in game_helps:
            if it["id"] == item_id:
                return it
    for game_ups in UPGRADES_BY_GAME.values():
        for it in game_ups:
            if it["id"] == item_id:
                return it
    for it in COSMETICS:
        if it["id"] == item_id:
            return it
    return None


# 🔓 ترقيات (الخانة الرابعة)
UPGRADES_BY_GAME = {
    "huroof": [
        {
            "id": "slot4_huroof", "ref_id": "slot4_huroof",
            "category": "upgrade", "game": "huroof",
            "name": "الخانة الرابعة", "icon": "🎯",
            "desc": "تفتح خانة مساعدة رابعة في لعبة خلية الحروف.",
            "rarity": "epic", "price": 2000, "currency": "coins",
            "unlock_level": 10,
        },
    ],
    "career": [
        {
            "id": "slot4_career", "ref_id": "slot4_career",
            "category": "upgrade", "game": "career",
            "name": "الخانة الرابعة", "icon": "🎯",
            "desc": "تفتح خانة مساعدة رابعة في مسيرة لاعب.",
            "rarity": "epic", "price": 2000, "currency": "coins",
            "unlock_level": 10,
        },
    ],
    "bank": [
        {
            "id": "slot4_bank", "ref_id": "slot4_bank",
            "category": "upgrade", "game": "bank",
            "name": "الخانة الرابعة", "icon": "🎯",
            "desc": "تفتح خانة مساعدة رابعة في لعبة البنك.",
            "rarity": "epic", "price": 2000, "currency": "coins",
            "unlock_level": 10,
        },
    ],
    "game3": [], "game4": [], "game5": [],
}


# التجميليات الأساسية المملوكة للجميع مجاناً
BASE_OWNED_COSMETICS = [
    "emoji_laugh", "emoji_cry", "emoji_angry", "emoji_think",
]


def get_base_owned_cosmetics() -> list:
    return list(BASE_OWNED_COSMETICS)

