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
  ?e wdt:P31 wd:Q11344 .
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
  ?cl wdt:P118 wd:Q9448 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cl rdfs:label ?clAr . }
}"""},
    "kq_laliga_clubs": {
        "q": "اذكر أندية لعبت في الدوري الإسباني", "cat": "رياضة",
        "sparql": """
SELECT DISTINCT ?clAr WHERE {
  ?cl wdt:P118 wd:Q324867 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?cl rdfs:label ?clAr . }
}"""},
    "kq_saudi_cities": {
        "q": "اذكر مدناً في السعودية", "cat": "جغرافيا",
        "sparql": """
SELECT DISTINCT ?cityAr WHERE {
  ?city wdt:P31/wdt:P279* wd:Q515 . ?city wdt:P17 wd:Q851 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar". ?city rdfs:label ?cityAr . }
} LIMIT 120"""},
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


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_run": 0}


def _save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception as e:
        print(f" [knowledge-importer] حفظ الحالة: {e}")


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
    import requests
    import time as _t
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(SPARQL_URL,
                             params={"query": sparql, "format": "json"},
                             headers=HEADERS, timeout=45)
            if r.status_code in (403, 429, 503):
                # Wikidata يحدّ المعدل أحياناً  ننتظر ونعيد
                last_err = f"HTTP {r.status_code}"
                _t.sleep(3 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            out = []
            for row in data.get("results", {}).get("bindings", []):
                for v in row.values():
                    val = (v.get("value") or "").strip()
                    if _is_clean_arabic(val):
                        out.append(val)
            return out
        except Exception as e:
            last_err = str(e)[:80]
            _t.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Wikidata تعذّر بعد 3 محاولات: {last_err}")


def _run_once():
    """يوسّع قوائم الأسئلة من Wikidata، يدمجها مع الموجود (لا يحذف)."""
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        print(f" [knowledge-importer] قراءة الملف: {e}")
        return 0

    by_id = {q["id"]: q for q in doc.get("questions", [])}
    added_total = 0

    # 🆕 إنشاء أسئلة قوائم جديدة كاملة (إن لم تكن موجودة)
    for qid, tmpl in NEW_QUESTION_TEMPLATES.items():
        if qid in by_id:
            continue
        try:
            fetched = _run_query(tmpl["sparql"])
        except Exception as e:
            print(f" [knowledge-importer] قالب {qid} فشل: {e}")
            continue
        if len(fetched) < 8:
            continue  # 🛡️ قائمة قصيرة جداً = سؤال ضعيف، نتخطاه
        new_q = {"id": qid, "q": tmpl["q"], "cat": tmpl["cat"],
                 "answers": fetched}
        doc["questions"].append(new_q)
        by_id[qid] = new_q
        added_total += len(fetched)
        print(f" [knowledge-importer] 🆕 سؤال جديد: {tmpl['q']} "
              f"({len(fetched)} إجابة)")

    for qid, sparql in QUERIES.items():
        if qid not in by_id:
            continue  # نوسّع الموجود فقط (لا ننشئ أسئلة جديدة عمياء)
        try:
            fetched = _run_query(sparql)
        except Exception as e:
            print(f" [knowledge-importer] استعلام {qid} فشل: {e}")
            continue
        if not fetched:
            continue
        # الإجابات الحالية (نطبّع للمقارنة: أول متغيّر قبل |)
        existing = set()
        for ans in by_id[qid].get("answers", []):
            existing.add(str(ans).split("|")[0].strip())
        # نضيف الجديد فقط
        added = 0
        for val in fetched:
            if val not in existing:
                by_id[qid]["answers"].append(val)
                existing.add(val)
                added += 1
        if added:
            added_total += added
            print(f" [knowledge-importer] {qid}: +{added} إجابة "
                  f"(الإجمالي {len(by_id[qid]['answers'])})")

    if added_total > 0:
        try:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            print(f" [knowledge-importer] أُضيف {added_total} إجابة إجمالاً")
            # نصفّر كاش الأسئلة (تحديث حيّ بلا إعادة تشغيل)
            try:
                from app.domains.games.knowledge import events as _kev
                _kev._QCACHE['loaded'] = False
                _kev._load_questions()
            except Exception as e:
                print(f" [knowledge-importer] تصفير الكاش: {e}")
        except Exception as e:
            print(f" [knowledge-importer] كتابة الملف: {e}")

    _save_state({"last_run": time.time()})
    return added_total


async def knowledge_auto_import_loop():
    """حلقة الخلفية: أول تشغيل بعد 5 دقائق، ثم كل INTERVAL أيام."""
    if os.environ.get("KNOWLEDGE_AUTO_IMPORT", "1") != "1":
        print(" [knowledge-importer] معطّل (KNOWLEDGE_AUTO_IMPORT=0)")
        return
    interval_days = float(os.environ.get("KNOWLEDGE_IMPORT_INTERVAL_DAYS", "7"))
    interval = interval_days * 86400
    await asyncio.sleep(300)  # 5 دقائق بعد الإقلاع
    while True:
        st = _load_state()
        if time.time() - st.get("last_run", 0) >= interval:
            print(" [knowledge-importer] بدء دورة توسيع الأسئلة…")
            try:
                await asyncio.to_thread(_run_once)
            except Exception as e:
                print(f" [knowledge-importer] دورة فشلت: {e}")
        await asyncio.sleep(3600)  # نفحص كل ساعة


if __name__ == "__main__":
    # تشغيل يدوي فوري: python -m app.domains.games.importers.knowledge_importer
    n = _run_once()
    print(f"تم. أُضيف {n} إجابة.")
