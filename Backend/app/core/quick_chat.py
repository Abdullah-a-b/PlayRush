"""
 نظام الرسائل الجاهزة (Quick Chat) — بديل آمن للدردشة الحرة.

المبدأ: العميل لا يرسل نصاً حراً أبداً، بل يرسل *معرّف* (ID) عبارة جاهزة فقط.
الخادم هو المصدر الوحيد للنصوص — يستحيل حقن نص مسيء لأن لا نص يُكتب أصلاً.

هذا يلغي كل مخاطر المحتوى المسيء/التنمّر/التحرّش من جذرها (مهم لحماية القاصرين)،
مع إبقاء التفاعل الاجتماعي حيّاً عبر عبارات وإيموجي معتمدة مسبقاً.

الدردشة الحرة مؤجَّلة — ستُضاف لاحقاً مع نظام إشراف وبلاغات مكتمل.
"""

# كل عبارة لها معرّف ثابت (id) لا يتغيّر — العميل يرسل الـ id فقط.
# مقسّمة لفئات لعرضها مرتّبة في الواجهة.
QUICK_CHAT_LOBBY = {
    "تحية": [
        {"id": "g1", "text": "السلام عليكم 👋"},
        {"id": "g2", "text": "هلا والله 😄"},
        {"id": "g3", "text": "يا هلا بالشباب 🎉"},
        {"id": "g4", "text": "جاهز للعب؟ 🎮"},
    ],
    "تنسيق": [
        {"id": "l1", "text": "نلعب جولة؟ 🎯"},
        {"id": "l2", "text": "وش رايكم نبدأ 🚀"},
        {"id": "l3", "text": "دقيقة وأجي ⏳"},
        {"id": "l4", "text": "أنا جاهز ✅"},
    ],
    "روح رياضية": [
        {"id": "s5", "text": "شكراً على اللعب 🤝"},
        {"id": "s6", "text": "كانت ممتعة 😊"},
        {"id": "s4", "text": "نعيدها؟ 🔄"},
    ],
}

QUICK_CHAT_INGAME = {
    "أثناء اللعب": [
        {"id": "p1", "text": "لعبة حلوة 👏"},
        {"id": "p2", "text": "أحسنت! 🔥"},
        {"id": "p3", "text": "حركة ذكية 🤔"},
        {"id": "p4", "text": "يا سلام 😮"},
        {"id": "p5", "text": "قريب أفوز 😎"},
        {"id": "p6", "text": "صعبة هذي 😅"},
    ],
    "تحدّي": [
        {"id": "c1", "text": "ورني وش عندك 💪"},
        {"id": "c2", "text": "هذي سهلة 😏"},
        {"id": "c3", "text": "بسرعة! ⏱️"},
        {"id": "c4", "text": "حظ موفق 🍀"},
    ],
    "روح رياضية": [
        {"id": "s1", "text": "حظ أوفر 🍀"},
        {"id": "s2", "text": "مبروك الفوز 🏆"},
        {"id": "s3", "text": "تستاهل الفوز 💪"},
        {"id": "s5", "text": "شكراً على اللعب 🤝"},
    ],
}

# نجمع كل العبارات في فهرس واحد (id  text) ليعمل التحقق في أي سياق
QUICK_CHAT = {**QUICK_CHAT_LOBBY}  # توافق خلفي
_ALL_CATS = [QUICK_CHAT_LOBBY, QUICK_CHAT_INGAME]

# فهرس سريع id  text (للتحقق والبحث بزمن ثابت) — يغطّي الكتالوجين
_PHRASE_BY_ID = {
    item["id"]: item["text"]
    for cat_dict in _ALL_CATS
    for cat in cat_dict.values()
    for item in cat
}

_EMOJI_BY_ID = {
    item["id"]: item["emojiId"]
    for cat_dict in _ALL_CATS
    for cat in cat_dict.values()
    for item in cat
    if item.get("emojiId")
}


def resolve_emoji(phrase_id: str):
    """يُرجع معرّف ملف Lottie للإيموجي (أو None)."""
    if not isinstance(phrase_id, str):
        return None
    # معرّفات التفاعل الديناميكي: react_<emojiId>
    if phrase_id.startswith("react_"):
        emoji_id = phrase_id[len("react_"):]
        return emoji_id if emoji_id else None
    return _EMOJI_BY_ID.get(phrase_id)


def get_quick_chat_catalog(context: str = "lobby") -> dict:
    """يُرجع قائمة العبارات حسب السياق:
    - 'game' أو 'room'  عبارات داخل المباراة (تنافسية/تفاعلية)
    - غير ذلك (lobby/categories)  عبارات اجتماعية عامة"""
    if context in ("game", "room", "ingame"):
        return QUICK_CHAT_INGAME
    return QUICK_CHAT_LOBBY


def get_catalog_for_user(context: str, owned_phrase_ids: list, game: str = None) -> dict:
    """يدمج العبارات الأساسية + العبارات المشتراة + الإيموجيات المملوكة.
    - في اللوبي/categories: عبارات عامة مشتراة + إيموجيات مملوكة (تفاعل سريع)
    - داخل المباراة: عبارات تلك اللعبة المشتراة"""
    import copy
    base = copy.deepcopy(get_quick_chat_catalog(context))
    is_ingame = context in ("game", "room", "ingame")

    # نجلب عناصر المتجر
    try:
        from app.domains.wallet.store_catalog import COSMETICS
    except Exception:
        return base

    owned = owned_phrase_ids or []

    # 1) العبارات المشتراة
    purchased = []
    for c in COSMETICS:
        if c.get("category") != "chat_phrase":
            continue
        if c["id"] not in owned:
            continue
        scope = c.get("scope", "general")
        if is_ingame:
            if scope == "game" and (not game or c.get("game") == game):
                purchased.append(c)
        else:
            if scope == "general":
                purchased.append(c)
    if purchased:
        base["عباراتي 💬"] = [{"id": c["id"], "text": c["name"]} for c in purchased]

    # 2) الإيموجيات المملوكة كـ "تفاعل سريع" (في اللوبي/categories فقط — اللعبة لها نظامها)
    if not is_ingame:
        # الأساسية المجانية + المشتراة
        base_emojis = ["emoji_laugh", "emoji_cry", "emoji_angry", "emoji_think"]
        owned_emojis = list(base_emojis)
        for c in COSMETICS:
            if c.get("category") == "emoji" and c["id"] in owned and c["id"] not in owned_emojis:
                owned_emojis.append(c["id"])
        # نبني صفّ التفاعل السريع من الإيموجيات المملوكة
        emoji_icon = {c["id"]: c.get("icon", "🙂") for c in COSMETICS if c.get("category") == "emoji"}
        # نضيف أيقونات الأساسية
        emoji_icon.setdefault("emoji_laugh", "😂")
        emoji_icon.setdefault("emoji_cry", "😭")
        emoji_icon.setdefault("emoji_angry", "😡")
        emoji_icon.setdefault("emoji_think", "🤔")
        react_row = []
        for eid in owned_emojis:
            react_row.append({"id": f"react_{eid}", "text": emoji_icon.get(eid, "🙂"), "emojiId": eid})
        if react_row:
            base["تفاعل سريع"] = react_row

    return base


# فهرس عبارات المتجر (للتحقق عند الإرسال)
def _store_phrase_text(phrase_id: str):
    try:
        from app.domains.wallet.store_catalog import COSMETICS
        for c in COSMETICS:
            if c.get("category") == "chat_phrase" and c["id"] == phrase_id:
                return c["name"]
    except Exception:
        pass
    return None


def resolve_phrase(phrase_id: str):
    """يحوّل معرّف العبارة لنصّها المعتمد. يُرجع None لو المعرّف غير صالح.
    يبحث في العبارات الأساسية ثم عبارات المتجر ثم تفاعلات الإيموجي."""
    if not isinstance(phrase_id, str):
        return None
    base = _PHRASE_BY_ID.get(phrase_id)
    if base is not None:
        return base
    # تفاعل إيموجي: react_<emojiId>  أيقونة الإيموجي
    if phrase_id.startswith("react_"):
        emoji_id = phrase_id[len("react_"):]
        try:
            from app.domains.wallet.store_catalog import COSMETICS
            for c in COSMETICS:
                if c.get("category") == "emoji" and c["id"] == emoji_id:
                    return c.get("icon", "🙂")
        except Exception:
            pass
        # الأساسية المجانية
        _base_icons = {"emoji_laugh": "😂", "emoji_cry": "😭", "emoji_angry": "😡", "emoji_think": "🤔"}
        return _base_icons.get(emoji_id)
    return _store_phrase_text(phrase_id)


def is_valid_phrase_id(phrase_id) -> bool:
    if not isinstance(phrase_id, str):
        return False
    if phrase_id in _PHRASE_BY_ID:
        return True
    if phrase_id.startswith("react_") and resolve_phrase(phrase_id) is not None:
        return True
    return _store_phrase_text(phrase_id) is not None
