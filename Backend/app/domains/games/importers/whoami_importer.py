"""
🎭 مولّد شخصيات «من أنا» من Wikidata — تلميحات قوالب حتمية (لا AI يهلوس).

المبدأ:
- نجلب أشخاصاً مشاهير (كتّاب/علماء/رياضيين/قادة تاريخيين) لهم مقال عربي
  وشهرة عالية (sitelinks) — الشهرة شرط: اللعبة تعتمد أن اللاعب يعرفهم.
- 5 تلميحات لكل شخصية من الأغمض للأوضح، بقوالب حتمية من خصائص موثوقة:
  1) القرن/الحقبة (P569/P570)   2) الجنسية (P27)
  3) المهنة (P106)               4) اشتهرت بـ/مجالي (وصف عام بالمهنة+الحقبة)
  5) أول حرف من اسمي.
- تحصين: يُقبل فقط من اكتملت حقوله العربية؛ حارس ديني (الشخصيات الدينية
  تأتي حصراً من القائمة اليدوية المراجَعة، لا من التوليد الآلي).
- الدمج لا يحذف اليدوي أبداً (المفتاح id فريد ببادئة wd_).

التشغيل اليدوي:  python -m app.domains.games.importers.whoami_importer
"""
import json
import os
import time

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "PlayRushWhoami/1.0 (educational game)",
           "Accept": "application/sparql-results+json"}

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "data")
_DATA_FILE = os.path.join(_DATA_DIR, "whoami_characters.json")
STATE_FILE = os.path.join(_DATA_DIR, "whoami_import_state.json")

# فئات مهنية مستهدفة (QID المهنة → تصنيف عربي للعبة)
OCCUPATIONS = {
    "Q36180":   "كتّاب وأدباء",     # writer
    "Q901":     "علماء",            # scientist
    "Q937857":  "رياضيون",          # association football player
    "Q82955":   "قادة وسياسيون",    # politician
    "Q33999":   "فنانون وممثلون",   # actor
    "Q177220":  "فنانون وممثلون",   # singer
    "Q170790":  "علماء",            # mathematician
    "Q169470":  "علماء",            # physicist
}

# استعلام واحد لكل مهنة: مشاهير (sitelinks عالية) بحقول مكتملة
QUERY_TMPL = """
SELECT ?pAr ?pEn ?natAr ?occAr ?birth ?death ?links WHERE {
  ?p wdt:P106 wd:%(occ)s .
  ?p wdt:P27 ?nat .
  ?p wdt:P569 ?birth .
  OPTIONAL { ?p wdt:P570 ?death . }
  ?p wikibase:sitelinks ?links .
  FILTER(?links >= 60)
  ?p rdfs:label ?pAr . FILTER(LANG(?pAr) = "ar")
  ?p rdfs:label ?pEn . FILTER(LANG(?pEn) = "en")
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?nat rdfs:label ?natAr . wd:%(occ)s rdfs:label ?occAr . }
}
ORDER BY DESC(?links)
LIMIT 60
"""

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")
# الشخصيات الدينية حصراً من القائمة اليدوية المراجَعة — لا توليد آلي
_RELIGIOUS_GUARD = ("الله", "نبي", "رسول", "صحابي", "خليفة", "إمام", "قديس")


def _is_arabic(s):
    return bool(s) and any(ch in _ARABIC_CHARS for ch in s)


def _century_ar(year):
    """القرن بالعربية (1879 → التاسع عشر)."""
    c = (year - 1) // 100 + 1
    names = {15: "الخامس عشر", 16: "السادس عشر", 17: "السابع عشر",
             18: "الثامن عشر", 19: "التاسع عشر", 20: "العشرين",
             21: "الحادي والعشرين"}
    return names.get(c, f"الـ{c}")


def _year_of(iso):
    try:
        s = str(iso).lstrip("+")
        return int(s[:4])
    except Exception:
        return None


def build_hints(name_ar, nat_ar, occ_ar, birth_y, death_y):
    """5 تلميحات حتمية: أغمض ← أوضح."""
    if death_y:
        h1 = (f"وُلدت في القرن {_century_ar(birth_y)} "
              f"وتوفيت في القرن {_century_ar(death_y)}.")
        h4 = f"عشت بين عامي {birth_y} و{death_y} تقريباً."
    else:
        h1 = f"وُلدت في القرن {_century_ar(birth_y)} وما زلت على قيد الحياة."
        h4 = f"وُلدت عام {birth_y} تقريباً."
    h2 = f"أنتمي إلى دولة {nat_ar}."
    h3 = f"مجال شهرتي: {occ_ar}."
    first = name_ar.strip()[0] if name_ar.strip() else "؟"
    h5 = f"اسمي يبدأ بحرف «{first}»."
    return [h1, h2, h3, h4, h5]


def _run_query(sparql):
    import requests
    r = requests.get(SPARQL_URL, params={"query": sparql, "format": "json"},
                     headers=HEADERS, timeout=90)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def _gen_accepted(name_ar, name_en):
    """صيغ القبول: الاسم الكامل + آخر كلمة (اللقب) + أول كلمة + الإنجليزي."""
    out = {name_ar}
    parts = name_ar.split()
    if len(parts) >= 2:
        out.add(parts[-1])
        out.add(parts[0])
    if name_en:
        out.add(name_en.lower())
        en_parts = name_en.split()
        if len(en_parts) >= 2:
            out.add(en_parts[-1].lower())
    return sorted(out)


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
        print(f"⚠️ [whoami-importer] حفظ الحالة: {e}")


def _run_once():
    """يولّد شخصيات ويدمجها (لا يحذف اليدوي أبداً)."""
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        doc = {"characters": []}
    chars = doc.setdefault("characters", [])
    existing_names = {c.get("name", "").strip() for c in chars}
    existing_ids = {c.get("id") for c in chars}

    added = 0
    for occ_qid, category in OCCUPATIONS.items():
        try:
            rows = _run_query(QUERY_TMPL % {"occ": occ_qid})
        except Exception as e:
            print(f"⚠️ [whoami-importer] استعلام {occ_qid} فشل: {e}")
            continue
        for b in rows:
            def g(k):
                return (b.get(k) or {}).get("value", "").strip()
            name_ar, name_en = g("pAr"), g("pEn")
            nat_ar, occ_ar = g("natAr"), g("occAr")
            birth_y = _year_of(g("birth"))
            death_y = _year_of(g("death")) if g("death") else None
            # 🛡️ تحصين: اكتمال عربي + لا نص ديني + لا تكرار
            if not (_is_arabic(name_ar) and _is_arabic(nat_ar)
                    and _is_arabic(occ_ar) and birth_y):
                continue
            if any(w in name_ar for w in _RELIGIOUS_GUARD):
                continue
            if name_ar in existing_names:
                continue
            cid = f"wd_{occ_qid}_{len(chars)}"
            if cid in existing_ids:
                continue
            chars.append({
                "id": cid, "name": name_ar,
                "accepted_answers": _gen_accepted(name_ar, name_en),
                "category": category,
                "hints": build_hints(name_ar, nat_ar, occ_ar, birth_y, death_y),
            })
            existing_names.add(name_ar)
            existing_ids.add(cid)
            added += 1
        time.sleep(1.2)  # احترام حدود Wikidata

    if added:
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        print(f"🎭 [whoami-importer] +{added} شخصية (الإجمالي {len(chars)})")
        # تحديث حيّ: تصفير كاش الشخصيات
        try:
            from app.domains.games.whoami import events as _wev
            _wev._chars_cache = None
        except Exception:
            pass
    _save_state({"last_run": time.time()})
    return added


async def whoami_auto_import_loop():
    """حلقة أسبوعية تلقائية (WHOAMI_AUTO_IMPORT=1 افتراضي)."""
    import asyncio
    if os.getenv("WHOAMI_AUTO_IMPORT", "1") != "1":
        print("🎭 [whoami-importer] معطّل")
        return
    interval = float(os.getenv("WHOAMI_IMPORT_INTERVAL_DAYS", "7")) * 86400
    await asyncio.sleep(420)  # بعد 7 دقائق من الإقلاع (تفادي زحمة الإقلاع)
    while True:
        st = _load_state()
        if (time.time() - st.get("last_run", 0)) >= interval:
            print("🎭 [whoami-importer] بدء توليد دوري…")
            n = await __import__("asyncio").to_thread(_run_once)
            if n is not None:
                print(f"🎭 [whoami-importer] اكتمل ({n} جديدة)")
        await __import__("asyncio").sleep(6 * 3600)


if __name__ == "__main__":
    print(f"انتهى: +{_run_once()} شخصية")
