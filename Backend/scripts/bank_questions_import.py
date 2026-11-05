"""
 مولّد أسئلة البنك من Wikidata — حقائق ثابتة بقوالب حتمية.

المبدأ: قوالب حتمية (عاصمة/عملة/قارة الدول) — لا توليد لغوي قد يهلوس.
- طلب SPARQL واحد يجلب كل الدول ذات السيادة + P36/P38/P30 بالعربية والإنجليزية.
- يُقبل فقط ما اكتملت حقوله العربية (تحصين) — الناقص يُتخطّى.
- الإخراج: data/bank_questions_auto.json (منفصل عن اليدوي — لا يفسده).
- معرّفات بادئة wd_ (لا تتصادم مع q***).

التشغيل اليدوي:  python scripts/bank_questions_import.py
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SPARQL_URL = "https://query.wikidata.org/sparql"
HEADERS = {"User-Agent": "PlayRushBankQuestions/1.0 (educational game)",
           "Accept": "application/sparql-results+json"}

QUERY = """
SELECT ?c ?cap ?cur ?cont ?cLabelAr ?cLabelEn ?capAr ?capEn ?curAr ?curEn ?contAr WHERE {
  ?c wdt:P31 wd:Q3624078 .          # دولة ذات سيادة
  FILTER NOT EXISTS { ?c wdt:P31 wd:Q3024240 }   # ليست دولة تاريخية
  OPTIONAL { ?c p:P36 ?capClaim . ?capClaim ps:P36 ?cap . FILTER NOT EXISTS { ?capClaim pq:P582 ?endedCap } FILTER NOT EXISTS { ?capClaim wikibase:rank wikibase:DeprecatedRank } }
  OPTIONAL { ?c p:P38 ?curClaim . ?curClaim ps:P38 ?cur . FILTER NOT EXISTS { ?curClaim pq:P582 ?endedCur } FILTER NOT EXISTS { ?curClaim wikibase:rank wikibase:DeprecatedRank } }
  OPTIONAL { ?c wdt:P30 ?cont . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?c rdfs:label ?cLabelAr . ?cap rdfs:label ?capAr .
    ?cur rdfs:label ?curAr . ?cont rdfs:label ?contAr . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?c rdfs:label ?cLabelEn . ?cap rdfs:label ?capEn . ?cur rdfs:label ?curEn . }
}
"""

# دول مشهورة  أسئلتها سهلة؛ البقية متوسطة/صعبة
FAMOUS = {"السعودية", "مصر", "الإمارات", "الكويت", "قطر", "الأردن", "العراق",
          "المغرب", "الجزائر", "تونس", "فرنسا", "ألمانيا", "إيطاليا",
          "إسبانيا", "المملكة المتحدة", "الولايات المتحدة", "روسيا", "الصين",
          "اليابان", "تركيا", "البرازيل", "الأرجنتين", "الهند"}

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")


def _is_arabic(s):
    return bool(s) and any(ch in _ARABIC_CHARS for ch in s)


def _variants(ar, en):
    """تنويعات الإملاء الحتمية (جغ، حذف ألف المد: سانتياغو/سانتياجو/
    سنتياغو...) — محرك مشترك مع مولّد حروف (answer_variants.py)."""
    try:
        from scripts.answer_variants import spelling_variants
        return spelling_variants(ar, en)
    except ImportError:
        out = {ar}
        if ar.startswith("ال") and len(ar) > 4:
            out.add(ar[2:])
        if en:
            out.add(en.lower())
        return sorted(out)


def fetch_rows():
    from app.core.import_support import sparql_rows
    return sparql_rows(QUERY, HEADERS)


def build_questions(rows):
    from scripts.wikidata_facts import country_facts
    qs = []
    for fact in country_facts(rows):
        kind, country = fact["kind"], fact["country"]
        famous = country in FAMOUS
        text = {"cap": f"ما عاصمة {country}؟", "cur": f"ما العملة الرسمية في {country}؟", "cont": f"في أي قارة تقع {country}؟"}[kind]
        qs.append({"id": fact["id"], "source_id": fact["id"], "q": text, "a": fact["answer"], "accepted": _variants(fact["answer"], fact["english"]), "cat": "عام" if kind == "cur" else "جغرافيا", "diff": ("medium" if famous else "hard") if kind == "cur" else ("easy" if famous else "medium"), "source": "wikidata", "entity_id": fact["country_id"]})
    from app.core.import_support import unambiguous_questions
    return unambiguous_questions(qs)


def run_import():
    from app.core.paths import DATA_DIR
    from app.core.import_support import atomic_json, canonical, read_json
    out_path = DATA_DIR / "bank_questions_auto.json"
    qs = build_questions(fetch_rows())
    if len(qs) < 30:
        raise RuntimeError(f"نتائج قليلة ({len(qs)})؛ لم يُمس الملف الحالي")
    old = read_json(out_path, [])
    by_text = {canonical(q.get("q")): q for q in old}
    added = updated = unchanged = 0
    used_ids = set()
    for q in qs:
        previous = by_text.get(canonical(q["q"]))
        # ترحيل آمن: سؤال قديم معروف يحتفظ بمعرّفه ومشاهداته.
        if previous and previous.get("id") not in used_ids:
            q["id"] = previous["id"]
        used_ids.add(q["id"])
        if previous is None:
            added += 1
        elif any(previous.get(k) != q.get(k) for k in ("q", "a", "accepted", "cat", "diff")):
            updated += 1
        else:
            unchanged += 1
    atomic_json(out_path, qs)
    result = {"status": "success", "fetched": len(qs), "added": added, "updated": updated, "unchanged": unchanged, "total": len(qs)}
    print(f" [bank-import] {result}")
    return result


if __name__ == "__main__":
    print(run_import())
