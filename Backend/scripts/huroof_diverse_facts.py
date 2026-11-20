"""حقائق مألوفة محدودة؛ نتحقق من العلاقة قبل إضافة السؤال ولا نخمن من الوصف.

القائمة مراجعة تحريرياً، وليست بحثاً مفتوحاً في آلاف الشخصيات المجهولة.
يتطلب توسيعها اختيار موضوع مألوف وتحديد السؤال والإجابة والبدائل أولاً.
علاقة مفقودة أو متعددة أو متغيرة في المصدر تمنع نشر السؤال تلقائياً.
"""
import re

from app.core.huroof_answers import answer_letter
from app.core.import_support import stable_id
from scripts.answer_variants import spelling_variants

API_URL = "https://www.wikidata.org/w/api.php"
SOURCE_VERSION = 1

# الموضوع، الخاصية، الإجابة المتوقعة، السؤال، الإجابة العربية، التصنيف، الصعوبة، البدائل.
FACTS = (
    ("Q1426", "P641", "Q847", "ما الرياضة التي اشتهر بها روجر فيدرير؟", "تنس", "رياضة", "easy", ("التنس", "كرة المضرب")),
    ("Q10132", "P641", "Q847", "ما الرياضة التي اشتهر بها رافاييل نادال؟", "تنس", "رياضة", "easy", ("التنس", "كرة المضرب")),
    ("Q39562", "P641", "Q31920", "ما الرياضة التي حقق فيها مايكل فيلبس ميدالياته الأولمبية؟", "سباحة", "رياضة", "easy", ("السباحة",)),
    ("Q28614", "P641", "Q718", "ما اللعبة التي اشتهر بها غاري كاسباروف؟", "شطرنج", "رياضة", "medium", ("الشطرنج",)),
    ("Q36107", "P641", "Q32112", "ما الرياضة التي اشتهر بها محمد علي كلاي؟", "ملاكمة", "رياضة", "easy", ("الملاكمة",)),
    ("Q79031", "P641", "Q32112", "ما الرياضة التي اشتهر بها مايك تايسون؟", "ملاكمة", "رياضة", "easy", ("الملاكمة",)),
    ("Q36159", "P641", "Q5372", "ما الرياضة التي اشتهر بها ليبرون جيمس؟", "كرة السلة", "رياضة", "easy", ("السلة",)),
    ("Q25369", "P641", "Q5372", "ما الرياضة التي اشتهر بها كوبي براينت؟", "كرة السلة", "رياضة", "medium", ("السلة",)),
    ("Q7520267", "P641", "Q326827", "ما الرياضة التي اشتهرت بها سيمون بايلز في الألعاب الأولمبية؟", "جمباز فني", "رياضة", "medium", ("جمباز", "الجمباز", "الجمباز الفني")),
    ("Q12418", "P170", "Q762", "من رسم لوحة الموناليزا؟", "ليوناردو دافنشي", "فنون", "easy", ("دافنشي", "دا فينشي", "ليوناردو دا فينشي", "ليوناردو دا فنشي")),
    ("Q45585", "P170", "Q5582", "من رسم لوحة ليلة النجوم؟", "فان غوخ", "فنون", "medium", ("فنسنت فان غوخ", "فينسنت فان غوخ", "فان جوخ", "فان غوغ")),
    ("Q175036", "P170", "Q5593", "من رسم لوحة غيرنيكا؟", "بيكاسو", "فنون", "medium", ("بابلو بيكاسو",)),
    ("Q180736", "P50", "Q535", "من مؤلف رواية البؤساء؟", "فيكتور هوغو", "أدب", "medium", ("فيكتور هوجو", "فكتور هوغو", "هوغو", "هوجو")),
    ("Q41567", "P50", "Q692", "من كتب مسرحية هاملت؟", "شكسبير", "أدب", "medium", ("ويليام شكسبير", "وليم شكسبير")),
    ("Q83186", "P50", "Q692", "من كتب مسرحية روميو وجولييت؟", "شكسبير", "أدب", "easy", ("ويليام شكسبير", "وليم شكسبير")),
    ("Q26505", "P50", "Q23434", "من كتب رواية الشيخ والبحر؟", "إرنست همنغواي", "أدب", "medium", ("أرنست همنغواي", "إرنست همنجواي", "أرنست همنجواي", "همنغواي", "همنجواي")),
    ("Q5017794", "P50", "Q7176", "من كتب ثلاثية القاهرة: بين القصرين وقصر الشوق والسكرية؟", "نجيب محفوظ", "أدب", "medium", ()),
    ("Q3149381", "P50", "Q7176", "من كتب رواية بين القصرين؟", "نجيب محفوظ", "أدب", "medium", ()),
    ("Q921128", "P50", "Q561434", "من كتب رواية موسم الهجرة إلى الشمال؟", "الطيب صالح", "أدب", "medium", ("طيب صالح",)),
    ("Q405", "P397", "Q2", "حول أي كوكب يدور القمر الذي نراه في سمائنا؟", "الأرض", "فضاء", "easy", ("أرض", "كوكب الأرض")),
)


def _single_target(entity, prop):
    """لا نخفي التعارض باختيار الرتبة المفضلة؛ القيم المجهولة أيضاً تمنع النشر."""
    claims = entity.get("claims", {})
    if not isinstance(claims, dict) or not isinstance(claims.get(prop, []), list):
        return None
    targets = set()
    for claim in claims.get(prop, []):
        if not isinstance(claim, dict):
            return None
        if claim.get("rank") == "deprecated":
            continue
        # القالب غير المقيد لا يصح لعلاقة لا تنطبق إلا في فترة أو حالة خاصة.
        if claim.get("qualifiers"):
            return None
        snak = claim.get("mainsnak", {})
        if not isinstance(snak, dict) or snak.get("snaktype") != "value":
            return None
        value = snak.get("datavalue", {})
        value = value.get("value", {}) if isinstance(value, dict) else {}
        target = value.get("id") if isinstance(value, dict) else None
        if not isinstance(target, str) or not re.fullmatch(r"Q[1-9][0-9]*", target):
            return None
        targets.add(target)
    return next(iter(targets)) if len(targets) == 1 else None


def build_questions(entity_map):
    """بناء حتمي بلا شبكة؛ لا تدخل أسماء أو بدائل غير مراجعة من المصدر."""
    questions = []
    for item, prop, expected, text, answer, category, difficulty, aliases in FACTS:
        entity = entity_map.get(item, {})
        if not isinstance(entity, dict) or "missing" in entity:
            continue
        if entity.get("id") != item or _single_target(entity, prop) != expected:
            continue
        letter = answer_letter(answer)
        if not letter:
            continue
        questions.append({
            "question_text": text,
            "correct_answer": answer,
            "category": category,
            "letter": letter,
            "difficulty": difficulty,
            "accepted_answers": sorted(set(spelling_variants(answer, None) + list(aliases))),
            "source_id": stable_id("familiar", item, prop),
            "source_url": f"https://www.wikidata.org/wiki/{item}",
            "source_revision": entity.get("lastrevid"),
        })
    return questions


def fetch_entities():
    """طلب واحد محدود؛ يتولى المستدعي التخزين المؤقت وإعادة المحاولة لاحقاً."""
    import requests
    ids = sorted({fact[0] for fact in FACTS})
    if len(ids) > 50:
        raise ValueError("توسعة المصدر تتطلب تقسيم الطلبات ومراجعة حدها أولاً")
    response = requests.get(
        API_URL,
        params={"action": "wbgetentities", "ids": "|".join(ids),
                "props": "info|claims", "format": "json"},
        headers={"User-Agent": "PlayRushHuroofImporter/1.0 (educational game)"},
        timeout=(5, 20),
    )
    response.raise_for_status()
    data = response.json()
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, dict) or set(ids) - entities.keys():
        raise ValueError("استجابة مصدر الحقائق المألوفة ناقصة")
    for item in ids:
        entity = entities[item]
        if not isinstance(entity, dict) or ("missing" not in entity and entity.get("id") != item):
            raise ValueError("هوية غير متوقعة في مصدر الحقائق المألوفة")
    return entities


def fetch_questions():
    """لا نعلن اكتمال المصدر إذا تغيّرت علاقة؛ يحتفظ المستدعي بآخر نسخة سليمة."""
    questions = build_questions(fetch_entities())
    if len(questions) != len(FACTS):
        raise ValueError("بعض علاقات الحقائق المألوفة مفقودة أو تحتاج مراجعة")
    return questions
