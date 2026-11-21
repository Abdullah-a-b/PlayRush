"""
 مولّد أسئلة "حروف" من Wikidata — حقائق ثابتة محصّنة من الهلوسة.

المبادئ الصارمة (شروط المطوّر — النسخة المنقّحة):
1. دون اختلاق لغوي: قوالب نصية ثابتة + قيم verbatim من مصادر موثوقة.
   لا توليد لغوي إطلاقاً — نفس مبدأ مولّدي البنك والمسيرة.
2. الحرف يُشتق من الإجابة الحقيقية (بنفس normalize_letter حق المحرك)،
   لا العكس. الحروف النادرة (كـ ظ) تحصل على أسئلة فقط إن وُجد كيان
   حقيقي يبدأ بها — اختراع إجابة مستحيل بنيوياً. تقرير التغطية بعد
   كل تشغيل يُظهر الحروف الناقصة لتغطيتها يدوياً.
3. الديني مسموح — بلا هلوسة إطلاقاً وبلا هزار: مصدره قائمة منسّقة
   ثابتة داخل الكود (ترتيب سور المصحف — حقيقة ثابتة منذ 14 قرناً)
   بقالب رصين ثابت. لا يُشتق أي محتوى ديني من Wikidata (labels
   خارجية فوضوية = مخاطرة غير مقبولة هنا)، والحارس الديني يمنع
   تسرب أي نص ديني عابر من القوالب الخارجية لهذا السبب تحديداً.

قواعد التحكيم العادل:
- تُقبل فقط العلاقات الأحادية (دولةعاصمة، عنصررمز/عدد ذري).
  قالب متعدد الإجابات الصحيحة ("لاعب لعب لنادي X") يظلم من أجاب
  إجابة صحيحة أخرى — مرفوض.
- عاصمة تظهر لدولتين  تُستبعد الدولتان (غموض).
- دولة بأكثر من عملة رسمية  سؤال عملتها يُتخطّى.

الإخراج: جدول questions مباشرة (game_mode='huroof') لأن حروف يقرأ
من DB — مع extra_data={'letter','accepted_answers','source':'auto_wikidata'}
ومنع التكرار بهوية المصدر ونص السؤال، مع حماية المراجعات والمحتوى اليدوي.

التشغيل اليدوي:  python scripts/huroof_questions_import.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "PlayRushHuroofQuestions/1.0 (educational game)",
           "Accept": "application/sparql-results+json"}

# ===== قالب 1-3: الدول (نفس استعلام البنك — علاقات موثوقة) =====
QUERY_COUNTRIES = """
SELECT ?c ?cap ?cur ?cLabelAr ?cLabelEn ?capAr ?capEn ?curAr ?curEn WHERE {
  ?c wdt:P31 wd:Q3624078 .
  FILTER NOT EXISTS { ?c wdt:P31 wd:Q3024240 }
  FILTER NOT EXISTS { ?c wdt:P576 ?dissolved }
  OPTIONAL { ?c p:P36 ?capClaim . ?capClaim ps:P36 ?cap . FILTER NOT EXISTS { ?capClaim pq:P582 ?endedCap } FILTER NOT EXISTS { ?capClaim wikibase:rank wikibase:DeprecatedRank } }
  OPTIONAL { ?c p:P38 ?curClaim . ?curClaim ps:P38 ?cur . FILTER NOT EXISTS { ?curClaim pq:P582 ?endedCur } FILTER NOT EXISTS { ?curClaim wikibase:rank wikibase:DeprecatedRank } }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?c rdfs:label ?cLabelAr . ?cap rdfs:label ?capAr . ?cur rdfs:label ?curAr . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?c rdfs:label ?cLabelEn . ?cap rdfs:label ?capEn . ?cur rdfs:label ?curEn . }
}
"""

# ===== قالب 4-5: العناصر الكيميائية (أحادية تُتحقق شروطها) =====
QUERY_ELEMENTS = """
SELECT ?e ?eLabelAr ?eLabelEn ?symbol ?z WHERE {
  ?e wdt:P31 wd:Q11344 .
  ?e wdt:P246 ?symbol .
  ?e wdt:P1086 ?z .
  FILTER(?z >= 1 && ?z <= 118)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?e rdfs:label ?eLabelAr . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?e rdfs:label ?eLabelEn . }
}
"""

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")

# الحارس الديني (دوره الجديد): يمنع تسرب أي نص ديني من القوالب
# *الخارجية* (Wikidata) — لأن labels الخارجية فوضوية والهلوسة ممنوعة
# في الديني قطعاً. المحتوى الديني يأتي حصراً من القائمة المنسّقة أدناه.
_RELIGIOUS_GUARD = ("الله", "نبي", "النبي", "رسول", "قرآن", "سورة", "آية",
                    "حديث", "صحاب", "إنجيل", "توراة", "كنيسة", "مسجد",
                    "معبد", "دير ", "قديس", "بابا ")

# ==========================================================
# القائمة المنسّقة: سور المصحف بترتيبها (حقيقة ثابتة — مصدرها
# المصحف نفسه لا Wikidata). أي تعديل عليها يمر بمراجعة يدوية.
# ==========================================================
SURAHS = [
    "الفاتحة", "البقرة", "آل عمران", "النساء", "المائدة", "الأنعام",
    "الأعراف", "الأنفال", "التوبة", "يونس", "هود", "يوسف", "الرعد",
    "إبراهيم", "الحجر", "النحل", "الإسراء", "الكهف", "مريم", "طه",
    "الأنبياء", "الحج", "المؤمنون", "النور", "الفرقان", "الشعراء",
    "النمل", "القصص", "العنكبوت", "الروم", "لقمان", "السجدة",
    "الأحزاب", "سبأ", "فاطر", "يس", "الصافات", "ص", "الزمر", "غافر",
    "فصلت", "الشورى", "الزخرف", "الدخان", "الجاثية", "الأحقاف",
    "محمد", "الفتح", "الحجرات", "ق", "الذاريات", "الطور", "النجم",
    "القمر", "الرحمن", "الواقعة", "الحديد", "المجادلة", "الحشر",
    "الممتحنة", "الصف", "الجمعة", "المنافقون", "التغابن", "الطلاق",
    "التحريم", "الملك", "القلم", "الحاقة", "المعارج", "نوح", "الجن",
    "المزمل", "المدثر", "القيامة", "الإنسان", "المرسلات", "النبأ",
    "النازعات", "عبس", "التكوير", "الانفطار", "المطففين", "الانشقاق",
    "البروج", "الطارق", "الأعلى", "الغاشية", "الفجر", "البلد",
    "الشمس", "الليل", "الضحى", "الشرح", "التين", "العلق", "القدر",
    "البينة", "الزلزلة", "العاديات", "القارعة", "التكاثر", "العصر",
    "الهمزة", "الفيل", "قريش", "الماعون", "الكوثر", "الكافرون",
    "النصر", "المسد", "الإخلاص", "الفلق", "الناس",
]
assert len(SURAHS) == 114 and len(set(SURAHS)) == 114, "قائمة السور يجب أن تكون 114 فريدة"

# ==========================================================
# حقائق منسّقة للحروف النادرة (نفس آلية SURAHS الموثوقة)
# بعض الحروف (كـ ظ) لا يغطيها أي مصدر خارجي بكيان حقيقي —
# والاختراع ممنوع. الحل: حقائق صلبة مدقّقة يدوياً هنا، والحرف
# يبقى مشتقاً من الإجابة بالكود (لا يُكتب يدوياً فلا مجال لخطأ).
# التوسعة: أضف حقيقة أحادية العلاقة (إجابة واحدة صحيحة فقط)
# وسيلتقطها المولد تلقائياً في الدورة القادمة.
# ==========================================================
CURATED_FACTS = [
    {"q": "ظاهرة جوية من قطرات ماء قرب سطح الأرض تقل معها الرؤية الأفقية عن كيلومتر",
     "a": "ضباب", "cat": "علوم"},
    {"q": "محافظة عُمانية مركزها مدينة صلالة",
     "a": "ظفار", "cat": "جغرافيا"},
    {"q": "مدينة سعودية تقع فيها جامعة الملك فهد للبترول والمعادن",
     "a": "الظهران", "cat": "جغرافيا"},
    {"q": "مدينة سعودية يقع فيها المقر الرئيسي لشركة أرامكو",
     "a": "الظهران", "cat": "جغرافيا"},
    {"q": "محافظة عُمانية مركزها مدينة عبري",
     "a": "الظاهرة", "cat": "جغرافيا"},
    {"q": "حيوان سُمّيت مدينة أبوظبي نسبةً إليه",
     "a": "ظبي", "cat": "عام"},
    {"q": "شاعر مصري لُقّب بأمير الشعراء", "a": "أحمد شوقي", "cat": "أدب"},
    {"q": "أداة تستخدم إبرة مغناطيسية لتحديد الاتجاهات", "a": "بوصلة", "cat": "علوم عامة"},
    {"q": "آلة وترية تُعزف بقوس، تُسند إلى الأرض بدبوس ويضعها العازف بين ركبتيه", "a": "تشيلو", "cat": "موسيقى"},
    {"q": "ماذا يسمى تسجيل لاعب كرة قدم ثلاثة أهداف في مباراة واحدة؟", "a": "ثلاثية", "cat": "رياضة"},
    {"q": "لوحة فنية تُرسم على سطح جدار", "a": "جدارية", "cat": "فنون"},
    {"q": "شاعر مصري لُقّب بشاعر النيل", "a": "حافظ إبراهيم", "cat": "أدب"},
    {"q": "ثديي يطير طيرانًا فعليًا وله أجنحة جلدية", "a": "خفاش", "cat": "حيوانات"},
    {"q": "ما اسم الحرف الذي يشبه الدال وتعلوه نقطة؟", "a": "ذال", "cat": "لغة عربية"},
    {"q": "ما وصف المضلع الذي يتكون من أربعة أضلاع؟", "a": "رباعي", "cat": "رياضيات"},
    {"q": "ما اسم الرياضة المائية التي تشمل سباقات الفراشة والصدر والظهر؟", "a": "سباحة", "cat": "رياضة"},
    {"q": "ما اسم القرد الإفريقي الذي ينتمي إلى جنس البونوبو نفسه ويُعرف بالنوع الشائع منه؟", "a": "شمبانزي", "cat": "حيوانات"},
    {"q": "آلة إيقاعية تتألف عادة من قرصين معدنيين يُضرب أحدهما بالآخر", "a": "صنج", "cat": "موسيقى"},
    {"q": "برمائي تُعرف يرقته المائية باسم الشرغوف", "a": "ضفدع", "cat": "حيوانات"},
    {"q": "طائر يستعرض ذكره ريشًا ذا بقع تشبه العيون", "a": "طاووس", "cat": "حيوانات"},
    {"q": "ما الذي يتكوّن خلف جسم معتم يحجب الضوء؟", "a": "ظل", "cat": "علوم عامة"},
    {"q": "آلة وترية شرقية لها صندوق كمثري وعنق قصير بلا دساتين", "a": "عود", "cat": "موسيقى"},
    {"q": "أكبر القردة العليا الحية حجمًا", "a": "غوريلا", "cat": "حيوانات"},
    {"q": "فن تكوين صورة بترتيب قطع صغيرة ملونة من الزجاج أو الحجر", "a": "فسيفساء", "cat": "فنون"},
    {"q": "حيوان ثديي صغير مغطى بالأشواك يلتف على هيئة كرة عند الخطر", "a": "قنفذ", "cat": "حيوانات"},
    {"q": "رياضة يستخدم فيها الضارب مضربًا مسطحًا ويحمي الويكيت", "a": "كريكيت", "cat": "رياضة"},
    {"q": "ما اسم الضربة التي يوجهها الملاكم بقبضته؟", "a": "لكمة", "cat": "رياضة"},
    {"q": "أداة بصرية تُستخدم لتكبير الأجسام الدقيقة مثل الخلايا", "a": "مِجهر", "cat": "علوم عامة"},
    {"q": "ما اسم القطعة المستقيمة التي تصل مركز الدائرة بنقطة على محيطها؟", "a": "نصف القطر", "cat": "رياضيات"},
    {"q": "رياضة جماعية تُلعب على حلبة جليدية بالعصي وقرص مطاطي", "a": "هوكي الجليد", "cat": "رياضة"},
    {"q": "ثديي ضخم له قرن أو قرنان فوق الأنف", "a": "وحيد القرن", "cat": "حيوانات"},
    {"q": "ما اسم الطور الذي يلي البيضة ويسبق العذراء في دورة حياة الفراشة؟", "a": "يرقة", "cat": "علوم عامة"},
    {"q": "آلة إيقاعية مستديرة لها إطار مغطى بجلد يُضرب باليد", "a": "دف", "cat": "موسيقى"},
    {"q": "أي زر طويل في لوحة المفاتيح يضيف فراغًا بين الكلمات؟", "a": "زر المسافة", "cat": "تقنية"},
]


def build_curated_questions():
    """حقائق الحروف النادرة — منسّقة يدوياً، الحرف يُشتق آلياً من الإجابة."""
    qs = []
    from pathlib import Path
    starter = json.loads((Path(__file__).resolve().parents[1] / 'data/huroof_starter_questions.json').read_text(encoding='utf-8'))
    from scripts.sports_facts import SPORTS_FACTS
    sports = [{"q": q, "a": a, "cat": "رياضة", "accepted_answers": aliases}
              for _, q, a, aliases in SPORTS_FACTS]
    for f in CURATED_FACTS + starter['questions'] + sports:
        letter = _answer_letter(f["a"])
        if not letter:
            continue
        qs.append({
            "question_text": f["q"],
            "correct_answer": f["a"],
            "category": f["cat"],
            "letter": letter,
            "accepted_answers": sorted(set(_variants(f["a"], None) + f.get('accepted_answers', []))),
            "difficulty": f.get('difficulty', 'medium'),
        })
    return qs


def _is_arabic(s):
    return bool(s) and any(ch in _ARABIC_CHARS for ch in s)


def _religious(*texts):
    joined = " ".join(t or "" for t in texts)
    return any(w in joined for w in _RELIGIOUS_GUARD)


def _answer_letter(ans):
    """يشتق حرف اللوحة من الإجابة الحقيقية — بنفس منطق المحرك حرفياً:
    إسقاط 'ال' ثم تطبيع الحرف الأول. يرجع None لو خارج حروف اللوحة."""
    t = (ans or "").strip()
    if t.startswith("ال") and len(t) > 3:
        t = t[2:]
    if not t:
        return None
    mapping = {'ا': 'أ', 'إ': 'أ', 'آ': 'أ', 'ٱ': 'أ', 'ة': 'ه', 'ى': 'ي', 'ؤ': 'و'}
    letter = mapping.get(t[0], t[0])
    return letter if letter in 'أبتثجحخدذرزسشصضطظعغفقكلمنهوي' else None


def _variants(ar, en):
    """تنويعات الإملاء الحتمية (جغ، حذف ألف المد...) — محرك مشترك."""
    from scripts.answer_variants import spelling_variants
    return spelling_variants(ar, en)


def _valid_answer(ans):
    """إجابة عربية سليمة: ليست QID خاماً، طول معقول، ≤ 4 كلمات."""
    return (_is_arabic(ans) and not ans.startswith("Q")
            and 2 <= len(ans) <= 40 and len(ans.split()) <= 4)


def fetch_rows(query):
    from app.core.import_support import sparql_rows
    return sparql_rows(query, HEADERS)


def _g(b, k):
    return (b.get(k) or {}).get("value", "").strip()


def build_country_questions(rows):
    from scripts.wikidata_facts import country_facts
    from app.core.import_support import stable_id
    qs = []
    for f in country_facts(rows):
        country, answer, kind = f["country"], f["answer"], f["kind"]
        if _religious(country, answer):
            continue
        if kind == "cap" and f["inverse_unique"] and _valid_answer(country) and f["country_id"].rsplit("/", 1)[-1] != "Q801":
            qs.append({"question_text": f"دولة عاصمتها {answer}", "correct_answer": country, "category": "جغرافيا", "letter": _answer_letter(country), "accepted_answers": _variants(country, f["country_en"]), "source_id": stable_id("country_by_cap", f["country_id"])})
        if _valid_answer(answer) and kind in ("cap", "cur"):
            text = f"عاصمة دولة {country}" if kind == "cap" else f"العملة الرسمية لدولة {country}"
            if kind == "cap" and f["country_id"].rsplit("/", 1)[-1] == "Q801":
                text = "المدينة التي تعلنها إسرائيل عاصمة لها"
            qs.append({"question_text": text, "correct_answer": answer, "category": "جغرافيا", "letter": _answer_letter(answer), "accepted_answers": _variants(answer, f["english"]), "source_id": f["id"]})
    return [q for q in qs if q["letter"]]


def build_element_questions(rows):
    """قوالب العناصر — علاقة أحادية مضمونة (رمز/عدد ذري  عنصر واحد)."""
    from app.core.import_support import stable_id
    qs, seen = [], set()
    for b in rows:
        name, en = _g(b, "eLabelAr"), _g(b, "eLabelEn")
        sym, z = _g(b, "symbol"), _g(b, "z")
        if not _valid_answer(name) or name in seen or _religious(name):
            continue
        if not sym or not z or not z.isdigit() or not (1 <= int(z) <= 118):
            continue
        seen.add(name)
        letter = _answer_letter(name)
        if not letter:
            continue
        acc = _variants(name, en)
        qs.append({"question_text": f"عنصر كيميائي رمزه ({sym})",
                   "correct_answer": name, "category": "علوم",
                   "letter": letter, "accepted_answers": acc, "source_id": stable_id("element_symbol", _g(b, "e") or name)})
        qs.append({"question_text": f"العنصر الكيميائي ذو العدد الذري ({int(z)})",
                   "correct_answer": name, "category": "علوم",
                   "letter": letter, "accepted_answers": acc, "source_id": stable_id("element_number", _g(b, "e") or name)})
    return qs


def build_quran_questions():
    """ القالب الديني — من القائمة المنسّقة حصراً (لا Wikidata).
    علاقة أحادية مطلقة: رقم الترتيب  سورة واحدة. قالب رصين ثابت —
    لا مجال لهزار ولا لهلوسة لأن لا شيء يُولَّد أصلاً."""
    qs = []
    for i, name in enumerate(SURAHS, start=1):
        letter = _answer_letter(name)
        if not letter:
            continue  # (لا ينطبق عملياً — كل الأسماء عربية سليمة)
        accepted = sorted({name, f"سورة {name}",
                           *( [name[2:]] if name.startswith("ال") and len(name) > 4 else [] )})
        qs.append({
            "question_text": f"السورة رقم ({i}) في ترتيب المصحف",
            "correct_answer": name,
            "category": "دين",
            "letter": letter,
            "accepted_answers": accepted,
        })
    return qs


def build_extra_questions(rows, kind):
    from app.core.import_support import stable_id
    groups = {}
    for b in rows:
        key = _g(b, "item")
        label, answer = _g(b, "itemAr"), _g(b, "answerAr")
        import re
        valid_label = _is_arabic(label) if kind == "book" else bool(re.fullmatch(r"[a-z]{2}", label))
        if not key or not _valid_answer(answer) or not valid_label or _religious(label, answer):
            continue
        group = groups.setdefault(key, {"label": label, "answers": set(), "en": _g(b, "answerEn")})
        group["answers"].add(answer)
    qs = []
    for key, g in groups.items():
        if len(g["answers"]) != 1:
            continue
        answer = next(iter(g["answers"]))
        original_answer = answer
        if kind == "language":
            import re
            answer = re.sub(r"^(?:اللغة|لغة)\s+", "", answer).strip()
        text = f"من مؤلف كتاب «{g['label']}»؟" if kind == "book" else f"لغة رمزها الدولي ({g['label']})"
        letter = _answer_letter(answer)
        if letter:
            qs.append({"question_text": text, "correct_answer": answer, "category": "أدب" if kind == "book" else "لغات", "letter": letter, "accepted_answers": sorted(set(_variants(answer, g["en"]) + [original_answer])), "source_id": stable_id(kind, key)})
    return qs


EXTRA_QUERIES = {
    "book": """SELECT ?item ?itemAr ?answerAr ?answerEn WHERE {
      { SELECT DISTINCT ?item WHERE { ?item wdt:P31 wd:Q571; wikibase:sitelinks ?n; wdt:P50 ?a . FILTER(?n>=20) ?item rdfs:label ?titleAr . FILTER(LANG(?titleAr)="ar") ?a rdfs:label ?authorAr . FILTER(LANG(?authorAr)="ar") } ORDER BY ?item LIMIT 250 }
      ?item wdt:P50 ?author; rdfs:label ?itemAr . FILTER(LANG(?itemAr)='ar')
      ?author rdfs:label ?answerAr FILTER(LANG(?answerAr)='ar')
      OPTIONAL { ?author rdfs:label ?answerEn FILTER(LANG(?answerEn)='en') }
    } ORDER BY ?item ?answerAr""",
}


def prepare_questions(questions, rules=None):
    """رفض المدخلات المعيبة والتعارضات قبل لمس قاعدة البيانات."""
    from app.core.huroof_answers import answer_letter, is_language_code_question
    from app.core.import_support import canonical, stable_id, unambiguous_questions
    prepared = []
    for original in questions:
        if not isinstance(original, dict):
            continue
        sid = original.get('source_id') or stable_id('curated', original.get('question_text', ''))
        rule = (rules or {}).get(sid, {})
        if rule.get('active') is False:
            continue
        q = {**original, **{k: v for k, v in rule.items() if k != 'active'}}
        if not all(isinstance(q.get(k), str) and q[k].strip()
                   for k in ('question_text', 'correct_answer', 'category')):
            continue
        for key in ('question_text', 'correct_answer', 'category'):
            q[key] = q[key].strip()
        answer = q['correct_answer']
        letter = answer_letter(answer)
        if (letter not in 'أبتثجحخدذرزسشصضطظعغفقكلمنهوي' or not letter
                or len(answer) > 80 or len(q['question_text']) > 500
                or not _is_arabic(q['question_text'])
                or is_language_code_question(q['question_text'], q)):
            continue
        aliases = q.get('accepted_answers', [])
        if not isinstance(aliases, list):
            aliases = []
        q['accepted_answers'] = sorted({answer} | {
            a.strip() for a in aliases if isinstance(a, str) and 0 < len(a.strip()) <= 80
        })
        q['letter'] = letter
        prepared.append(q)
    # هوية مصدر واحدة لا تقبل حقيقتين، حتى لو اختلف نص السؤال.
    by_source = {}
    for q in prepared:
        sid = q.get('source_id') or stable_id('curated', q['question_text'])
        by_source.setdefault(sid, []).append(q)
    clean = []
    for sid, group in sorted(by_source.items()):
        if len({(canonical(q['question_text']), canonical(q['correct_answer'])) for q in group}) == 1:
            chosen = dict(sorted(group, key=lambda q: json.dumps(q, ensure_ascii=False, sort_keys=True))[0])
            chosen['accepted_answers'] = sorted({a for q in group for a in q['accepted_answers']})
            clean.append(chosen)
    return unambiguous_questions(clean, 'question_text', 'correct_answer')


def save_to_db(questions, complete_groups=()):
    """تحديث الآلي بهوية المصدر؛ لا نستبدل أي سجل يدوي."""
    from app.infrastructure.database import SessionLocal
    from app.domains.games.models import Question
    from app.core.import_support import canonical, stable_id
    # مراجعة الهوية تسبق الحفظ حتى لا تعيد المصادر أخطاءً عُزلت سابقاً.
    from pathlib import Path
    from app.core.huroof_answers import answer_letter, is_language_code_question
    rules = json.loads((Path(__file__).resolve().parents[1] / 'data/huroof_review_rules.json').read_text(encoding='utf-8'))['rules']
    count_before = len(questions)
    questions = prepare_questions(questions, rules)
    db = SessionLocal()
    stats = {"added": 0, "updated": 0, "unchanged": 0, "manual_protected": 0, "deactivated": 0,
             "rejected": count_before - len(questions), "identity_conflicts": 0}
    try:
        existing = db.query(Question).filter(Question.game_mode == "huroof").all()
        from app.core.import_support import content_backup
        content_backup("huroof", [{"id": r.id, "game_mode": r.game_mode, "question_text": r.question_text, "correct_answer": r.correct_answer, "category": r.category, "extra_data": r.extra_data} for r in existing])
        by_text, by_source = {}, {}
        for row in existing:
            try:
                extra = json.loads(row.extra_data or '{}')
                if not isinstance(extra, dict): extra = {}
            except (ValueError, TypeError):
                extra = {}
            by_text.setdefault(canonical(row.question_text), row)
            if extra.get("source_id"):
                by_source[extra["source_id"]] = row
        for q in questions:
            sid = q.get("source_id") or stable_id("curated", q["question_text"])
            key = canonical(q["question_text"])
            row = by_source.get(sid) or by_text.get(key)
            try:
                extra = json.loads(row.extra_data or '{}') if row and row.extra_data else {}
                if not isinstance(extra, dict): extra = {}
            except (ValueError, TypeError):
                extra = {}
            curation = extra.get('_curation') if isinstance(extra.get('_curation'), dict) else {}
            if row and curation.get("hold_import"):
                stats["manual_protected"] += 1
                continue
            if row and extra.get("source") not in ("auto_wikidata", "auto_curated"):
                stats["manual_protected"] += 1
                continue
            if row and extra.get('source_id') not in (None, '', sid):
                # تطابق النص لا ينقل سجلّاً معروف الهوية إلى مصدر آخر.
                stats['identity_conflicts'] += 1
                continue
            # تحديث النص لا يصطدم بسجل آخر حتى لو كان يدوياً.
            if row and by_text.get(key) not in (None, row):
                stats["manual_protected"] += 1
                continue
            aliases = set(q['accepted_answers'])
            if row and canonical(row.correct_answer) == canonical(q['correct_answer']):
                previous_aliases = extra.get('accepted_answers', [])
                if isinstance(previous_aliases, list):
                    aliases.update(a for a in previous_aliases if isinstance(a, str) and a.strip())
            # نحفظ المراجعات السابقة؛ تبديل المصدر لا يمحو صعوبة أو كتابة اسم معتمدة.
            data = {**extra, "letter": q["letter"], "accepted_answers": sorted(aliases), "source": "auto_wikidata" if q.get("source_id") else "auto_curated", "source_id": sid, "active": True}
            if q.get('difficulty') in ('easy', 'medium', 'hard', 'rare'):
                data['difficulty'] = q['difficulty']
            elif data.get('difficulty') not in ('easy', 'medium', 'hard', 'rare'):
                from app.domains.games.huroof.solo_bot import question_difficulty
                data['difficulty'] = question_difficulty(q['question_text'], data)
            for provenance_key in ('source_url', 'source_property', 'source_answer_id', 'source_revision'):
                if q.get(provenance_key):
                    data[provenance_key] = q[provenance_key]
            encoded = json.dumps(data, ensure_ascii=False, sort_keys=True)
            if row is None:
                row = Question(game_mode="huroof", question_text=q["question_text"], correct_answer=q["correct_answer"], category=q["category"], extra_data=encoded)
                db.add(row); by_text[key] = row; by_source[sid] = row; stats["added"] += 1
            elif (row.question_text, row.correct_answer, row.category, row.extra_data) != (q["question_text"], q["correct_answer"], q["category"], encoded):
                by_text.pop(canonical(row.question_text), None)
                row.question_text, row.correct_answer, row.category, row.extra_data = q["question_text"], q["correct_answer"], q["category"], encoded
                by_text[key] = row; by_source[sid] = row; stats["updated"] += 1
            else:
                stats["unchanged"] += 1
        # العلاقة التي لم تعد مؤهلة تُعزل عن اللعب، لا تُحذف؛ اليدوي والقديم بلا هوية يراجعان لاحقاً.
        prefixes = {"countries": ("wd_cap_", "wd_cur_", "wd_country_by_cap_"), "elements": ("wd_element_symbol_", "wd_element_number_"), "language": ("wd_language_",), "curated": ("wd_curated_",)}
        active_ids = {q.get("source_id") or stable_id("curated", q["question_text"]) for q in questions}
        active_texts = {canonical(q["question_text"]) for q in questions}
        allowed = tuple(prefix for group in complete_groups for prefix in prefixes.get(group, ()))
        for old in existing:
            try: extra = json.loads(old.extra_data or '{}')
            except (ValueError, TypeError): continue
            if not isinstance(extra, dict): continue
            sid = extra.get("source_id") or ""
            curation = extra.get('_curation') if isinstance(extra.get('_curation'), dict) else {}
            if curation.get('hold_import'):
                continue
            stale = bool(allowed and sid.startswith(allowed) and sid not in active_ids)
            if not sid and extra.get("source") == "auto_wikidata":
                text = old.question_text or ""
                legacy_group = "countries" if text.startswith(("دولة عاصمتها ", "عاصمة دولة ", "العملة الرسمية لدولة ")) else ("elements" if text.startswith(("عنصر كيميائي رمزه ", "العنصر الكيميائي ذو العدد الذري ")) else None)
                stale = legacy_group in complete_groups and canonical(text) not in active_texts
            retired = (is_language_code_question(old.question_text, extra)
                       or (rules.get(sid, {}).get('active') is False
                           and extra.get('source') in ('auto_wikidata', 'auto_curated')))
            if (retired or (stale and extra.get("source") in ("auto_wikidata", "auto_curated"))) and extra.get("active", True):
                extra["active"] = False
                old.extra_data = json.dumps(extra, ensure_ascii=False, sort_keys=True)
                stats["deactivated"] += 1
        db.commit()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _source_questions(name, rows):
    if name == 'countries':
        return prepare_questions(build_country_questions(rows))
    if name == 'elements':
        return prepare_questions(build_element_questions(rows))
    return prepare_questions(build_extra_questions(rows, name))


def _validate_source(name, rows, generated, previous):
    """عدد الصفوف الخام لا يثبت اكتمال المصدر؛ نقيس حقائق مختلفة صالحة."""
    minimum = {'countries': 200, 'elements': 180}.get(name, 1)
    if len(generated) < minimum:
        raise ValueError('عدد الحقائق الصالحة أقل من حد الأمان')
    old_count = len(_source_questions(name, previous)) if previous else 0
    if old_count and len(generated) < old_count * .70:
        raise ValueError('انخفاض غير متوقع في تغطية المصدر')


def run_import(*, dry_run=False, force_refresh=False):
    from app.core.paths import DATA_DIR
    from app.core.import_support import read_json, atomic_json
    # نتائج كل مصدر مستقلة؛ نجاح مصدر لا يمنع إعادة المصدر الذي فشل.
    cache_path = DATA_DIR / "huroof_source_snapshots.json"
    cache = read_json(cache_path, {})
    questions = build_quran_questions() + build_curated_questions()
    failed = []
    source_report = {}
    complete_groups = ["curated"]
    sources = {"countries": QUERY_COUNTRIES, "elements": QUERY_ELEMENTS, **EXTRA_QUERIES}
    # استعلام الكتب تجريبي وثقيل على Wikidata؛ لا يُفعّل في الإنتاج افتراضياً.
    if os.getenv("HUROOF_BOOK_IMPORT", "0") != "1":
        sources.pop("book", None)
    for name, query in sources.items():
        try:
            import time
            entry = cache.get(name, {})
            if not isinstance(entry, dict): entry = {"rows": entry}
            reused = not force_refresh and entry.get("last_success", 0) > time.time() - 7 * 86400 and not entry.get("error")
            if reused:
                rows = entry["rows"]
            else:
                if name == "book":
                    query = query.replace("LIMIT 250 }", f"LIMIT 250 OFFSET {entry.get('offset', 0)} }}")
                rows = fetch_rows(query)
            if not isinstance(rows, list) or any(not isinstance(b, dict) for b in rows):
                raise ValueError('صيغة مصدر غير صالحة')
            if not rows and not (name == "book" and entry.get("offset", 0) > 0):
                raise RuntimeError("المصدر فارغ")
            next_offset = entry.get("offset", 0) if isinstance(entry, dict) else 0
            if name == "book" and not reused:
                seen_items = {_g(b, "item") for b in rows}
                previous = entry.get("rows", [])
                merged = [b for b in previous if _g(b, "item") not in seen_items] + rows
                next_offset = next_offset + 250 if len(seen_items) >= 250 else 0
                rows = merged
            generated = _source_questions(name, rows)
            _validate_source(name, rows, generated, entry.get('rows', []))
            cache[name] = {"rows": rows, "last_success": entry["last_success"] if reused else time.time(), "offset": next_offset}
            complete_groups.append(name)
            questions += generated
            source_report[name] = {'status': 'cached' if reused else 'fetched',
                                   'valid_questions': len(generated)}
        except Exception as exc:
            failed.append(name)
            print(f" [huroof-import] فشل المصدر {name}: {type(exc).__name__}")
            entry = cache.get(name, {})
            rows = entry.get("rows", []) if isinstance(entry, dict) else entry
            cache[name] = {**(entry if isinstance(entry, dict) else {}), "rows": rows, "last_success": entry.get("last_success", 0) if isinstance(entry, dict) else 0, "error": True}
            source_report[name] = {'status': 'failed', 'error': type(exc).__name__}
            # لا نعيد تطبيق حقيقة من نسخة قديمة عند انقطاع المصدر؛ نترك المخزون الحالي.
    if os.getenv('HUROOF_DIVERSE_IMPORT', '1') != '0':
        # قائمة مواضيع مألوفة؛ مصدرها علاقات محددة، وليست أسماء عشوائية من وصف حر.
        import time
        from scripts.huroof_diverse_facts import fetch_questions, SOURCE_VERSION
        name = 'familiar'
        entry = cache.get(name, {})
        if not isinstance(entry, dict):
            entry = {}
        try:
            reused = (not force_refresh and entry.get('version') == SOURCE_VERSION
                      and entry.get('last_success', 0) > time.time() - 7 * 86400
                      and not entry.get('error'))
            candidates = entry.get('questions', []) if reused else fetch_questions()
            generated = prepare_questions(candidates)
            if not generated or len(generated) != len(candidates):
                raise ValueError('حقائق مألوفة ناقصة أو متعارضة')
            questions += generated
            cache[name] = {'questions': generated, 'version': SOURCE_VERSION,
                           'last_success': entry['last_success'] if reused else time.time()}
            source_report[name] = {'status': 'cached' if reused else 'fetched',
                                   'valid_questions': len(generated)}
        except Exception as exc:
            failed.append(name)
            cache[name] = {**entry, 'error': True}
            source_report[name] = {'status': 'failed', 'error': type(exc).__name__}
            print(f' [huroof-import] فشل المصدر {name}: {type(exc).__name__}')
    # الأسئلة المحلية المراجعة لا تعتمد على توافر Wikidata. المصادر التي فشلت
    # ليست complete_groups، لذلك لا نعطّل أسئلتها عند حفظ التوسعة المحلية.
    questions = prepare_questions(questions)
    stats = {'dry_run': True} if dry_run else save_to_db(questions, complete_groups)
    if not dry_run:
        atomic_json(cache_path, cache)
    from collections import Counter
    stats.update(status="partial" if failed else "success", failed_sources=failed,
                 sources=source_report, generated=len(questions),
                 coverage=dict(Counter(q["letter"] for q in questions)),
                 categories=dict(Counter(q["category"] for q in questions)))
    print(f" [huroof-import] {stats}")
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='استيراد محتوى حروف بعد التحقق')
    parser.add_argument('--dry-run', action='store_true', help='فحص المصدر دون تعديل القاعدة أو حالة الاستيراد')
    parser.add_argument('--force-refresh', action='store_true', help='فحص المصادر مباشرة دون الكاش')
    options = parser.parse_args()
    run_import(dry_run=options.dry_run, force_refresh=options.force_refresh)
