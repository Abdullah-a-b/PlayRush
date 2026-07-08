"""
🏦 مولّد أسئلة البنك من Wikidata — حقائق ثابتة محصّنة من الخطأ.

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
SELECT ?cLabelAr ?cLabelEn ?capAr ?capEn ?curAr ?curEn ?contAr WHERE {
  ?c wdt:P31 wd:Q3624078 .          # دولة ذات سيادة
  FILTER NOT EXISTS { ?c wdt:P31 wd:Q3024240 }   # ليست دولة تاريخية
  OPTIONAL { ?c wdt:P36 ?cap . }
  OPTIONAL { ?c wdt:P38 ?cur . }
  OPTIONAL { ?c wdt:P30 ?cont . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?c rdfs:label ?cLabelAr . ?cap rdfs:label ?capAr .
    ?cur rdfs:label ?curAr . ?cont rdfs:label ?contAr . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?c rdfs:label ?cLabelEn . ?cap rdfs:label ?capEn . ?cur rdfs:label ?curEn . }
}
"""

# دول مشهورة → أسئلتها سهلة؛ البقية متوسطة/صعبة
FAMOUS = {"السعودية", "مصر", "الإمارات", "الكويت", "قطر", "الأردن", "العراق",
          "المغرب", "الجزائر", "تونس", "فرنسا", "ألمانيا", "إيطاليا",
          "إسبانيا", "المملكة المتحدة", "الولايات المتحدة", "روسيا", "الصين",
          "اليابان", "تركيا", "البرازيل", "الأرجنتين", "الهند"}

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")


def _is_arabic(s):
    return bool(s) and any(ch in _ARABIC_CHARS for ch in s)


def _variants(ar, en):
    out = {ar}
    if ar.startswith("ال") and len(ar) > 4:
        out.add(ar[2:])
    if en:
        out.add(en.lower())
    return sorted(out)


def fetch_rows():
    import requests
    r = requests.get(SPARQL_URL, params={"query": QUERY, "format": "json"},
                     headers=HEADERS, timeout=90)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def build_questions(rows):
    qs, seen_keys = [], set()
    for b in rows:
        def g(k):
            return (b.get(k) or {}).get("value", "").strip()
        country = g("cLabelAr")
        if not _is_arabic(country) or country in seen_keys:
            continue
        seen_keys.add(country)
        famous = country in FAMOUS
        cap_ar, cap_en = g("capAr"), g("capEn")
        cur_ar, cur_en = g("curAr"), g("curEn")
        cont_ar = g("contAr")
        # 🛡️ تحصين: نقبل الحقل فقط إن كانت قيمته عربية سليمة (لا QIDs خام)
        if _is_arabic(cap_ar) and not cap_ar.startswith("Q"):
            qs.append({"id": f"wd_cap_{len(qs)}", "q": f"ما عاصمة {country}؟",
                       "a": cap_ar, "accepted": _variants(cap_ar, cap_en),
                       "cat": "جغرافيا", "diff": "easy" if famous else "medium"})
        if _is_arabic(cur_ar) and not cur_ar.startswith("Q"):
            qs.append({"id": f"wd_cur_{len(qs)}", "q": f"ما العملة الرسمية في {country}؟",
                       "a": cur_ar, "accepted": _variants(cur_ar, cur_en),
                       "cat": "عام", "diff": "medium" if famous else "hard"})
        if _is_arabic(cont_ar) and not cont_ar.startswith("Q"):
            qs.append({"id": f"wd_cont_{len(qs)}", "q": f"في أي قارة تقع {country}؟",
                       "a": cont_ar, "accepted": _variants(cont_ar, None),
                       "cat": "جغرافيا", "diff": "easy" if famous else "medium"})
    return qs


def run_import():
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "bank_questions_auto.json")
    rows = fetch_rows()
    qs = build_questions(rows)
    if len(qs) < 30:
        print(f"⚠️ [bank-import] نتائج قليلة ({len(qs)}) — أُبقي الملف القديم (تحصين)")
        return 0
    json.dump(qs, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"🏦 [bank-import] وُلّد {len(qs)} سؤال → {out_path}")
    return len(qs)


if __name__ == "__main__":
    t = time.time()
    n = run_import()
    print(f"انتهى ({n} سؤال، {time.time()-t:.1f}ث)")
