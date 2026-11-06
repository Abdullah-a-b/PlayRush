"""
 التجديد التلقائي لأسئلة "ماذا تعرف" — خلفية المنصة

يوسّع قوائم الإجابات من Wikidata بحقائق ثابتة موثوقة (لا هلوسة):
  - عواصم/دول عربية وأوروبية، عناصر كيميائية… إلخ.
  - يدمج الجديد مع القوائم المنسّقة يدوياً (لا يحذف، يُضيف فقط).
  - أول تشغيل بعد 5 دقائق من الإقلاع، ثم دورياً.
  - في thread منفصل + يصفّر كاش الأسئلة بعد النجاح (تحديث حيّ).

الضبط عبر البيئة (.env):
  KNOWLEDGE_AUTO_IMPORT=1              (افتراضي مفعّل — 0 للتعطيل)
  KNOWLEDGE_IMPORT_INTERVAL_DAYS=7
"""
import os
import json
import time
import asyncio

from app.core.paths import DATA_DIR
from app.core.import_support import atomic_json, read_json, import_lock, canonical, positive_days, due, record_result, sparql_rows

_DATA_FILE = str(DATA_DIR / "knowledge_questions.json")
STATE_FILE = str(DATA_DIR / "knowledge_import_state.json")

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "PlayRushKnowledge/1.0 (educational game)",
           "Accept": "application/sparql-results+json"}

# استعلامات حتمية موثوقة (نفس علاقات البنك/الحروف)
QUERIES = {
    # عواصم الدول العربية (أعضاء جامعة الدول العربية Q7172)
    "kq_arab_capitals": """
SELECT DISTINCT ?capAr WHERE {
  ?c wdt:P463 wd:Q7172 . ?c wdt:P36 ?cap .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cap rdfs:label ?capAr . }
}""",
    # الدول العربية نفسها
    "kq_arab_countries": """
SELECT DISTINCT ?cAr WHERE {
  ?c wdt:P463 wd:Q7172 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?c rdfs:label ?cAr . }
}""",
    # عواصم الدول الأوروبية
    "kq_euro_capitals": """
SELECT DISTINCT ?capAr WHERE {
  ?c wdt:P30 wd:Q46 . ?c wdt:P31 wd:Q3624078 . ?c wdt:P36 ?cap .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cap rdfs:label ?capAr . }
}""",
    # الدول الأوروبية
    "kq_euro_countries": """
SELECT DISTINCT ?cAr WHERE {
  ?c wdt:P30 wd:Q46 . ?c wdt:P31 wd:Q3624078 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?c rdfs:label ?cAr . }
}""",
    # العناصر الكيميائية
    "kq_elements": """
SELECT DISTINCT ?eAr WHERE {
  ?e wdt:P31 wd:Q11344 ; wdt:P1086 ?atomicNumber .
  FILTER(?atomicNumber >= 1 && ?atomicNumber <= 118)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?e rdfs:label ?eAr . }
}""",
}

# 🆕 قوالب أسئلة قوائم جديدة تُنشأ كاملة إن لم تكن موجودة
# (سؤال جاهز + استعلامه) — حقائق ثابتة لا تتقادم
NEW_QUESTION_TEMPLATES = {
    "kq_african_countries": {
        "q": "اذكر دول قارة أفريقيا", "cat": "جغرافيا",
        "sparql": """
SELECT DISTINCT ?cAr WHERE {
  ?c wdt:P30 wd:Q15 . ?c wdt:P31 wd:Q3624078 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?c rdfs:label ?cAr . }
}"""},
    "kq_asian_countries": {
        "q": "اذكر دول قارة آسيا", "cat": "جغرافيا",
        "sparql": """
SELECT DISTINCT ?cAr WHERE {
  ?c wdt:P30 wd:Q48 . ?c wdt:P31 wd:Q3624078 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?c rdfs:label ?cAr . }
}"""},
    "kq_south_american_countries": {
        "q": "اذكر دول أمريكا الجنوبية", "cat": "جغرافيا",
        "sparql": """
SELECT DISTINCT ?cAr WHERE {
  ?c wdt:P30 wd:Q18 . ?c wdt:P31 wd:Q3624078 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?c rdfs:label ?cAr . }
}"""},
    "kq_world_currencies": {
        "q": "اذكر عملات رسمية لدول العالم", "cat": "عام",
        "sparql": """
SELECT DISTINCT ?curAr WHERE {
  ?c wdt:P31 wd:Q3624078 . ?c wdt:P38 ?cur .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cur rdfs:label ?curAr . }
}"""},
    "kq_epl_clubs": {
        "q": "اذكر أندية لعبت في الدوري الإنجليزي الممتاز", "cat": "رياضة",
        "sparql": """
SELECT DISTINCT ?clAr WHERE {
  ?cl wdt:P31/wdt:P279* wd:Q476028 .
  FILTER NOT EXISTS { ?cl wdt:P31 wd:Q5 }
  ?cl p:P118 ?membership . ?membership ps:P118 wd:Q9448 . FILTER NOT EXISTS { ?membership wikibase:rank wikibase:DeprecatedRank }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cl rdfs:label ?clAr . }
}"""},
    "kq_laliga_clubs": {
        "q": "اذكر أندية لعبت في الدوري الإسباني", "cat": "رياضة",
        "sparql": """
SELECT DISTINCT ?clAr WHERE {
  ?cl wdt:P31/wdt:P279* wd:Q476028 .
  FILTER NOT EXISTS { ?cl wdt:P31 wd:Q5 }
  ?cl p:P118 ?membership . ?membership ps:P118 wd:Q324867 . FILTER NOT EXISTS { ?membership wikibase:rank wikibase:DeprecatedRank }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cl rdfs:label ?clAr . }
}"""},
    "kq_saudi_cities": {
        "q": "اذكر مدناً في السعودية", "cat": "جغرافيا",
        "sparql": """
SELECT DISTINCT ?cityAr WHERE {
  ?city wdt:P31/wdt:P279* wd:Q515 . ?city wdt:P17 wd:Q851 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?city rdfs:label ?cityAr . }
}"""},
    "kq_chemical_metals": {
        "q": "اذكر معادن من العناصر الكيميائية", "cat": "علوم",
        "sparql": """
SELECT DISTINCT ?eAr WHERE {
  ?e wdt:P31 wd:Q11344 . ?e wdt:P279* wd:Q11426 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?e rdfs:label ?eAr . }
}"""},
}

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")
# نمنع أي نص ديني من التسرب من Wikidata (يأتي حصراً من القائمة اليدوية)
_RELIGIOUS_GUARD = ("الله", "نبي", "رسول", "قرآن", "سورة", "آية", "حديث")


def _is_clean_arabic(text):
    """يقبل نصاً عربياً نظيفاً فقط (لا أرقام/رموز/لاتيني، لا ديني)."""
    if not text or len(text) < 2 or len(text) > 40:
        return False
    if any(g in text for g in _RELIGIOUS_GUARD):
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    # ≥80% من الحروف عربية
    ar = sum(1 for c in letters if c in _ARABIC_CHARS)
    if ar / len(letters) < 0.8:
        return False
    # نرفض ما فيه أرقام أو أقواس (labels فوضوية)
    if any(ch.isdigit() for ch in text) or "(" in text or ")" in text:
        return False
    return True


def _run_query(sparql):
    import re
    # اكتمال القائمة مهم للتحكيم؛ لا نخفي اقتطاع النتائج خلف LIMIT ثابت.
    sparql = re.sub(r"\s+LIMIT\s+[0-9]+\s*$", "", sparql, flags=re.I)
    field = re.search(r"SELECT\s+(?:DISTINCT\s+)?(\?[A-Za-z_][A-Za-z0-9_]*)", sparql, re.I)
    if not field: raise ValueError("استعلام قائمة غير معروف")
    out = {}; size = 200
    for page in range(50):
        rows = sparql_rows(sparql + f" ORDER BY {field.group(1)} LIMIT {size} OFFSET {page * size}", HEADERS)
        for row in rows:
            val = (row.get(field.group(1)[1:]) or {}).get("value", "").strip()
            if _is_clean_arabic(val): out.setdefault(canonical(val), val)
        if len(rows) < size: return sorted(out.values(), key=canonical)
    raise RuntimeError("القائمة تجاوزت حد الصفحات؛ لم نعتبرها مكتملة")


def _merge_answers(manual, automatic):
    groups = []
    for value in list(manual) + list(automatic):
        variants = [v.strip() for v in str(value).split("|") if v.strip()]
        keys = {canonical(v) for v in variants}
        if not keys: continue
        overlaps = [i for i, group in enumerate(groups) if group[1] & keys]
        if not overlaps:
            groups.append((variants, keys))
        else:
            first = overlaps[0]
            merged = groups[first][0] + variants
            all_keys = groups[first][1] | keys
            for i in overlaps[1:]: merged += groups[i][0];all_keys |= groups[i][1]
            groups[first] = (list(dict.fromkeys(merged)), all_keys)
            for i in reversed(overlaps[1:]): groups.pop(i)
    return ["|".join(variants) for variants, _ in groups]


def _run_once():
    with import_lock(STATE_FILE) as acquired:
        if not acquired: return {"status": "busy"}
        state = read_json(STATE_FILE, {})
        doc = read_json(_DATA_FILE, {"questions": []})
        by_id = {q["id"]: q for q in doc.setdefault("questions", [])}
        sources = state.setdefault("sources", {})
        stats = {"status": "success", "added": 0, "updated": 0, "answers_added": 0, "failed_sources": [], "ineligible_sources": [], "held_sources": []}
        all_queries = dict(QUERIES)
        all_queries.update({qid: t["sparql"] for qid, t in NEW_QUESTION_TEMPLATES.items()})
        for qid, query in all_queries.items():
            source = sources.setdefault(qid, {})
            # لا يعيد المصدر الآلي نشر قائمة معزولة أو معتمدة بمراجعة بشرية.
            if by_id.get(qid, {}).get("_curation", {}).get("hold_import") or by_id.get(qid, {}).get("active") is False:
                source["eligibility"] = "review_hold"
                source.pop("retry_after", None)
                stats["held_sources"].append(qid)
                continue
            if not due(source, positive_days("KNOWLEDGE_IMPORT_INTERVAL_DAYS")): continue
            if qid not in by_id and qid not in NEW_QUESTION_TEMPLATES: continue
            try:
                fetched = _run_query(query)
                if not fetched: raise RuntimeError("المصدر فارغ")
                if len(fetched) < 15:
                    # قائمة كاملة وصحيحة قد تكون أصغر من الحد الذي يتطلبه المحرك.
                    source["last_run"] = time.time();source.pop("retry_after", None)
                    source["eligibility"] = "below_game_minimum"
                    stats["ineligible_sources"].append(qid)
                    continue
                source["eligibility"] = "playable"
                question = by_id.get(qid)
                if question is None:
                    tmpl = NEW_QUESTION_TEMPLATES[qid]
                    question = {"id": qid, "q": tmpl["q"], "cat": tmpl["cat"], "manual_answers": [], "source": "wikidata"}
                    doc["questions"].append(question);by_id[qid] = question;stats["added"] += 1
                before = json.dumps(question, ensure_ascii=False, sort_keys=True)
                manual = question.get("manual_answers")
                if manual is None:
                    # المحتوى السابق بلا مصدر واضح يُحفظ للمراجعة، لا يُحذف تخميناً.
                    manual = [] if question.get("source") == "wikidata" else list(question.get("answers", []))
                old = question.get("answers", [])
                merged = _merge_answers(manual, fetched)
                question["manual_answers"] = manual;question["auto_answers"] = fetched;question["answers"] = merged
                if before != json.dumps(question, ensure_ascii=False, sort_keys=True): stats["updated"] += 1
                stats["answers_added"] += len({canonical(a.split('|')[0]) for a in merged} - {canonical(a.split('|')[0]) for a in old})
                source["last_run"] = time.time();source.pop("retry_after", None)
            except Exception as exc:
                source["retry_after"] = time.time() + 3600;stats["failed_sources"].append(qid)
                print(f" [knowledge-importer] فشل {qid}: {type(exc).__name__}")
        if stats["added"] or stats["updated"]:
            atomic_json(_DATA_FILE, doc)
            try:
                from app.domains.games.knowledge import events
                events._QCACHE['loaded'] = False
            except ImportError: pass
        pending = {key for key, source in sources.items() if source.get("retry_after")}
        stats["failed_sources"] = sorted(set(stats["failed_sources"]) | pending)
        stats["status"] = "partial" if stats["failed_sources"] else "success"
        atomic_json(STATE_FILE, record_result(state, stats))
        print(f" [knowledge-importer] {stats}")
        return stats


async def knowledge_auto_import_loop():
    if os.getenv("KNOWLEDGE_AUTO_IMPORT", "1").strip() == "0": return
    await asyncio.sleep(300)
    while True:
        try:
            if read_json(STATE_FILE, {}).get("schema_version") != 2 or due(read_json(STATE_FILE, {}), positive_days("KNOWLEDGE_IMPORT_INTERVAL_DAYS")):
                await asyncio.to_thread(_run_once)
        except Exception as exc:
            print(f" [knowledge-importer] خطأ الحالة/الحفظ: {type(exc).__name__}")
        await asyncio.sleep(300)


if __name__ == "__main__":
    print(_run_once())
