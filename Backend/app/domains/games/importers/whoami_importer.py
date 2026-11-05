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

from app.core.paths import DATA_DIR
from app.core.import_support import atomic_json, read_json, import_lock, canonical, stable_id, positive_days, due, record_result, sparql_rows
_DATA_FILE = str(DATA_DIR / "whoami_characters.json")
STATE_FILE = str(DATA_DIR / "whoami_import_state.json")

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
SELECT ?p ?pAr ?pEn ?natAr ?occAr ?birth ?death ?links WHERE {
  %(selection)s
  ?p wdt:P27 ?nat; wdt:P569 ?birth .
  OPTIONAL { ?p wdt:P570 ?death . }
  ?p rdfs:label ?pAr . FILTER(LANG(?pAr) = "ar")
  OPTIONAL { ?p rdfs:label ?pEn . FILTER(LANG(?pEn) = "en") }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?nat rdfs:label ?natAr . wd:%(occ)s rdfs:label ?occAr . }
} ORDER BY ?p ?natAr
"""


def _query_for(occupation, offset=0, qids=None):
    if qids is not None:
        import re
        safe = [q for q in qids if re.fullmatch(r"Q[1-9][0-9]*", q)]
        selection = "VALUES ?p { " + " ".join("wd:" + q for q in safe) + " }"
    else:
        selection = "{ SELECT ?p ?links WHERE { ?p wdt:P106 wd:" + occupation + "; wikibase:sitelinks ?links . FILTER(?links >= 60) } ORDER BY DESC(?links) ?p LIMIT 60 OFFSET " + str(int(offset)) + " }"
    return QUERY_TMPL % {"selection": selection, "occ": occupation}

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")
# الشخصيات الدينية حصراً من القائمة اليدوية المراجَعة — لا توليد آلي
_RELIGIOUS_GUARD = ("الله", "نبي", "رسول", "صحابي", "خليفة", "إمام", "قديس")


def _is_arabic(s):
    return bool(s) and any(ch in _ARABIC_CHARS for ch in s)


def _century_ar(year):
    """القرن بالعربية (1879 → التاسع عشر)."""
    c = (abs(year) - 1) // 100 + 1
    names = {15: "الخامس عشر", 16: "السادس عشر", 17: "السابع عشر",
             18: "الثامن عشر", 19: "التاسع عشر", 20: "العشرين",
             21: "الحادي والعشرين"}
    return names.get(c, f"الـ{c}") + (" قبل الميلاد" if year < 0 else "")


def _year_of(iso):
    import re
    match = re.match(r"^([+-]?[0-9]+)-", str(iso))
    return int(match.group(1)) if match else None


def build_hints(name_ar, nat_ar, occ_ar, birth_y, death_y):
    """5 تلميحات حتمية: أغمض ← أوضح."""
    if death_y:
        h1 = (f"وُلدت في القرن {_century_ar(birth_y)} "
              f"وتوفيت في القرن {_century_ar(death_y)}.")
        h4 = f"عشت بين عامي {birth_y} و{death_y} تقريباً."
    else:
        h1 = f"وُلدت في القرن {_century_ar(birth_y)}."
        h4 = f"وُلدت عام {birth_y} تقريباً."
    h2 = f"أنتمي إلى دولة {nat_ar}."
    h3 = f"مجال شهرتي: {occ_ar}."
    first = name_ar.strip()[0] if name_ar.strip() else "؟"
    h5 = f"اسمي يبدأ بحرف «{first}»."
    return [h1, h2, h3, h4, h5]


def _run_query(sparql):
    return sparql_rows(sparql, HEADERS)


def _gen_accepted(name_ar, name_en):
    # الاسم الأول وحده لا يحدد الشخصية.
    out = {name_ar}
    for name in (name_ar, name_en):
        if not name:
            continue
        out.add(name.lower())
        parts = name.split()
        if len(parts) >= 2 and len(parts[-1]) >= 4:
            out.add(parts[-1].lower())
    return sorted(out)


def _character_rows(rows, occupation, category):
    groups = {}
    for b in rows:
        def g(k): return (b.get(k) or {}).get("value", "").strip()
        qid = g("p").rsplit("/", 1)[-1]
        if not qid.startswith("Q") or not _is_arabic(g("pAr")) or not _is_arabic(g("natAr")) or not _is_arabic(g("occAr")):
            continue
        group = groups.setdefault(qid, {"name": g("pAr"), "en": g("pEn"), "nations": set(), "births": set(), "deaths": set(), "occupation": g("occAr")})
        group["nations"].add(g("natAr"))
        if _year_of(g("birth")) is not None: group["births"].add(_year_of(g("birth")))
        if g("death") and _year_of(g("death")) is not None: group["deaths"].add(_year_of(g("death")))
    out = []
    import datetime
    for qid, g in groups.items():
        if len(g["births"]) != 1 or len(g["deaths"]) > 1 or any(w in g["name"] for w in _RELIGIOUS_GUARD):
            continue
        birth = next(iter(g["births"])); death = next(iter(g["deaths"]), None)
        if birth > datetime.date.today().year or (death is not None and (death < birth or death > datetime.date.today().year)):
            continue
        out.append({"id": stable_id("person", qid), "wikidata_id": qid, "name": g["name"], "accepted_answers": _gen_accepted(g["name"], g["en"]), "category": category, "hints": build_hints(g["name"], " و".join(sorted(g["nations"])), g["occupation"], birth, death), "source": {"provider": "wikidata", "occupation": occupation}})
    return out


def _run_once():
    with import_lock(STATE_FILE) as acquired:
        if not acquired: return {"status": "busy"}
        state = read_json(STATE_FILE, {})
        doc = read_json(_DATA_FILE, {"characters": []})
        chars = doc.setdefault("characters", [])
        by_qid = {c["wikidata_id"]: c for c in chars if c.get("wikidata_id")}
        by_name = {canonical(c.get("name")): c for c in chars}
        sources = state.setdefault("sources", {})
        stats = {"status": "success", "added": 0, "updated": 0, "unchanged": 0, "failed_sources": [], "manual_protected": 0}
        interval = positive_days("WHOAMI_IMPORT_INTERVAL_DAYS")
        for occ, category in OCCUPATIONS.items():
            known = [c["wikidata_id"] for c in chars if c.get("wikidata_id") and (c.get("source", {}) if isinstance(c.get("source"), dict) else {}).get("occupation") == occ]
            for lane in ("refresh", "discover"):
                key = occ + ":" + lane
                source = sources.setdefault(key, {})
                if not due(source, interval): continue
                if lane == "refresh" and not known:
                    source["last_run"] = time.time()
                    continue
                try:
                    if lane == "refresh":
                        rows = []
                        for i in range(0, len(known), 50): rows.extend(_run_query(_query_for(occ, qids=known[i:i+50])))
                    else:
                        rows = _run_query(_query_for(occ, source.get("offset", 0)))
                    candidates = _character_rows(rows, occ, category)
                    for new in candidates:
                        old = by_qid.get(new["wikidata_id"]) or by_name.get(canonical(new["name"]))
                        if old:
                            old_source = old.get("source", {}) if isinstance(old.get("source"), dict) else {}
                            if old.get("wikidata_id") and old["wikidata_id"] != new["wikidata_id"]:
                                stats["manual_protected"] += 1; continue
                            if old_source.get("occupation") not in (None, occ):
                                stats["unchanged"] += 1; continue
                            if not old.get("wikidata_id") and not str(old.get("id", "")).startswith("wd_"):
                                stats["manual_protected"] += 1; continue
                            new["id"] = old["id"]  # الحفاظ على مشاهدات الشخصية القديمة
                            if old != new:
                                old.update(new); stats["updated"] += 1
                            else: stats["unchanged"] += 1
                            by_qid[new["wikidata_id"]] = old
                            by_name[canonical(new["name"])] = old
                        else:
                            chars.append(new);by_qid[new["wikidata_id"]] = new;by_name[canonical(new["name"])] = new;stats["added"] += 1
                    if lane == "discover": source["offset"] = source.get("offset", 0) + 60 if rows else 0
                    source["last_run"] = time.time();source.pop("retry_after", None)
                except Exception as exc:
                    source["retry_after"] = time.time() + 3600
                    stats["failed_sources"].append(key)
                    print(f" [whoami-importer] فشل {key}: {type(exc).__name__}")
        if stats["added"] or stats["updated"]:
            atomic_json(_DATA_FILE, doc)
            try:
                from app.domains.games.whoami import events
                events._chars_cache = None
            except ImportError: pass
        pending = {key for key, source in sources.items() if source.get("retry_after")}
        stats["failed_sources"] = sorted(set(stats["failed_sources"]) | pending)
        stats["status"] = "partial" if stats["failed_sources"] else "success"
        atomic_json(STATE_FILE, record_result(state, stats))
        print(f" [whoami-importer] {stats}")
        return stats


async def whoami_auto_import_loop():
    import asyncio
    if os.getenv("WHOAMI_AUTO_IMPORT", "1").strip() == "0": return
    await asyncio.sleep(420)
    while True:
        try:
            state = read_json(STATE_FILE, {})
            if state.get("schema_version") != 2 or due(state, positive_days("WHOAMI_IMPORT_INTERVAL_DAYS")):
                await asyncio.to_thread(_run_once)
        except Exception as exc:
            print(f" [whoami-importer] خطأ الحالة/الحفظ: {type(exc).__name__}")
        await asyncio.sleep(300)


if __name__ == "__main__":
    print(_run_once())
