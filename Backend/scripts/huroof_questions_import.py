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
وdedup بنص السؤال (append-only، لا يمس اليدوي).

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
]


def build_curated_questions():
    """حقائق الحروف النادرة — منسّقة يدوياً، الحرف يُشتق آلياً من الإجابة."""
    qs = []
    for f in CURATED_FACTS:
        letter = _answer_letter(f["a"])
        if not letter:
            continue
        qs.append({
            "question_text": f["q"],
            "correct_answer": f["a"],
            "category": f["cat"],
            "letter": letter,
            "accepted_answers": _variants(f["a"], None),
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
            if kind == "cap" and f["country_id"].rsplit("/", 1)[-1] == "Q801":
                text = "المدينة التي تعلنها إسرائيل عاصمة لها"
            qs.append({"question_text": text, "correct_answer": answer, "category": "ثقافة", "letter": letter, "accepted_answers": sorted(set(_variants(answer, g["en"]) + [original_answer])), "source_id": stable_id(kind, key)})
    return qs


EXTRA_QUERIES = {
    "language": """SELECT ?item ?itemAr ?answerAr ?answerEn WHERE {
      ?item wdt:P218 ?itemAr .
      ?item rdfs:label ?answerAr FILTER(LANG(?answerAr)='ar')
      OPTIONAL { ?item rdfs:label ?answerEn FILTER(LANG(?answerEn)='en') }
    } ORDER BY ?item""",
    "book": """SELECT ?item ?itemAr ?answerAr ?answerEn WHERE {
      { SELECT DISTINCT ?item WHERE { ?item wdt:P31 wd:Q571; wikibase:sitelinks ?n; wdt:P50 ?a . FILTER(?n>=20) ?item rdfs:label ?titleAr . FILTER(LANG(?titleAr)="ar") ?a rdfs:label ?authorAr . FILTER(LANG(?authorAr)="ar") } ORDER BY ?item LIMIT 250 }
      ?item wdt:P50 ?author; rdfs:label ?itemAr . FILTER(LANG(?itemAr)='ar')
      ?author rdfs:label ?answerAr FILTER(LANG(?answerAr)='ar')
      OPTIONAL { ?author rdfs:label ?answerEn FILTER(LANG(?answerEn)='en') }
    } ORDER BY ?item ?answerAr""",
}


def save_to_db(questions, complete_groups=()):
    """تحديث الآلي بهوية المصدر؛ لا نستبدل أي سجل يدوي."""
    from app.infrastructure.database import SessionLocal
    from app.domains.games.models import Question
    from app.core.import_support import canonical, stable_id
    db = SessionLocal()
    stats = {"added": 0, "updated": 0, "unchanged": 0, "manual_protected": 0, "deactivated": 0}
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
            if row and extra.get("_curation", {}).get("hold_import"):
                stats["manual_protected"] += 1
                continue
            if row and extra.get("source") not in ("auto_wikidata", "auto_curated"):
                stats["manual_protected"] += 1
                continue
            # تحديث النص لا يصطدم بسجل آخر حتى لو كان يدوياً.
            if row and by_text.get(key) not in (None, row):
                stats["manual_protected"] += 1
                continue
            data = {"letter": q["letter"], "accepted_answers": q["accepted_answers"], "source": "auto_wikidata" if q.get("source_id") else "auto_curated", "source_id": sid, "active": True}
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
            stale = bool(allowed and sid.startswith(allowed) and sid not in active_ids)
            if not sid and extra.get("source") == "auto_wikidata":
                text = old.question_text or ""
                legacy_group = "countries" if text.startswith(("دولة عاصمتها ", "عاصمة دولة ", "العملة الرسمية لدولة ")) else ("elements" if text.startswith(("عنصر كيميائي رمزه ", "العنصر الكيميائي ذو العدد الذري ")) else None)
                stale = legacy_group in complete_groups and canonical(text) not in active_texts
            if stale and extra.get("source") in ("auto_wikidata", "auto_curated") and extra.get("active", True):
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


def run_import():
    from app.core.paths import DATA_DIR
    from app.core.import_support import read_json, atomic_json
    # نتائج كل مصدر مستقلة؛ نجاح مصدر لا يمنع إعادة المصدر الذي فشل.
    cache_path = DATA_DIR / "huroof_source_snapshots.json"
    cache = read_json(cache_path, {})
    questions = build_quran_questions() + build_curated_questions()
    failed = []
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
            reused = isinstance(entry, dict) and entry.get("last_success", 0) > time.time() - 7 * 86400 and not entry.get("error")
            if reused:
                rows = entry["rows"]
            else:
                if name == "book":
                    query = query.replace("LIMIT 250 }", f"LIMIT 250 OFFSET {entry.get('offset', 0)} }}")
                rows = fetch_rows(query)
            if name != "book" and len(rows) < 50:
                raise RuntimeError("نتائج المصدر أقل من حد الأمان")
            if not rows and not (name == "book" and entry.get("offset", 0) > 0):
                raise RuntimeError("المصدر فارغ")
            next_offset = entry.get("offset", 0) if isinstance(entry, dict) else 0
            if name == "book" and not reused:
                seen_items = {_g(b, "item") for b in rows}
                previous = entry.get("rows", [])
                merged = [b for b in previous if _g(b, "item") not in seen_items] + rows
                next_offset = next_offset + 250 if len(seen_items) >= 250 else 0
                rows = merged
            cache[name] = {"rows": rows, "last_success": entry["last_success"] if reused else time.time(), "offset": next_offset}
            complete_groups.append(name)
        except Exception as exc:
            failed.append(name)
            print(f" [huroof-import] فشل المصدر {name}: {type(exc).__name__}")
            entry = cache.get(name, {})
            rows = entry.get("rows", []) if isinstance(entry, dict) else entry
            cache[name] = {**(entry if isinstance(entry, dict) else {}), "rows": rows, "last_success": entry.get("last_success", 0) if isinstance(entry, dict) else 0, "error": True}
        if name == "countries":
            questions += build_country_questions(rows)
        elif name == "elements":
            questions += build_element_questions(rows)
        else:
            questions += build_extra_questions(rows, name)
    if len(failed) == len(sources):
        raise RuntimeError("فشلت جميع مصادر حروف؛ لم نغير قاعدة الأسئلة")
    from app.core.import_support import unambiguous_questions
    questions = unambiguous_questions(questions, "question_text", "correct_answer")
    stats = save_to_db(questions, complete_groups)
    atomic_json(cache_path, cache)
    from collections import Counter
    stats.update(status="partial" if failed else "success", failed_sources=failed, generated=len(questions), coverage=dict(Counter(q["letter"] for q in questions)))
    print(f" [huroof-import] {stats}")
    return stats


if __name__ == "__main__":
    print(run_import())
