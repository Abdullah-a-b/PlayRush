"""
🔡 مولّد أسئلة "حروف" من Wikidata — حقائق ثابتة محصّنة من الهلوسة.

المبادئ الصارمة (شروط المطوّر — النسخة المنقّحة):
1. صفر هلوسة: قوالب نصية ثابتة + قيم verbatim من مصادر موثوقة.
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
- تُقبل فقط العلاقات الأحادية (دولة↔عاصمة، عنصر↔رمز/عدد ذري).
  قالب متعدد الإجابات الصحيحة ("لاعب لعب لنادي X") يظلم من أجاب
  إجابة صحيحة أخرى — مرفوض.
- عاصمة تظهر لدولتين → تُستبعد الدولتان (غموض).
- دولة بأكثر من عملة رسمية → سؤال عملتها يُتخطّى.

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
SELECT ?cLabelAr ?cLabelEn ?capAr ?capEn ?curAr ?curEn WHERE {
  ?c wdt:P31 wd:Q3624078 .
  FILTER NOT EXISTS { ?c wdt:P31 wd:Q3024240 }
  OPTIONAL { ?c wdt:P36 ?cap . }
  OPTIONAL { ?c wdt:P38 ?cur . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?c rdfs:label ?cLabelAr . ?cap rdfs:label ?capAr . ?cur rdfs:label ?curAr . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?c rdfs:label ?cLabelEn . ?cap rdfs:label ?capEn . ?cur rdfs:label ?curEn . }
}
"""

# ===== قالب 4-5: العناصر الكيميائية (أحادية مضمونة 100%) =====
QUERY_ELEMENTS = """
SELECT ?eLabelAr ?eLabelEn ?symbol ?z WHERE {
  ?e wdt:P31 wd:Q11344 .
  ?e wdt:P246 ?symbol .
  ?e wdt:P1086 ?z .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ar".
    ?e rdfs:label ?eLabelAr . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en".
    ?e rdfs:label ?eLabelEn . }
}
"""

_ARABIC_CHARS = set("ابتثجحخدذرزسشصضطظعغفقكلمنهويءآأؤإئى")

# 🛡️ الحارس الديني (دوره الجديد): يمنع تسرب أي نص ديني من القوالب
# *الخارجية* (Wikidata) — لأن labels الخارجية فوضوية والهلوسة ممنوعة
# في الديني قطعاً. المحتوى الديني يأتي حصراً من القائمة المنسّقة أدناه.
_RELIGIOUS_GUARD = ("الله", "نبي", "النبي", "رسول", "قرآن", "سورة", "آية",
                    "حديث", "صحاب", "إنجيل", "توراة", "كنيسة", "مسجد",
                    "معبد", "دير ", "قديس", "بابا ")

# ==========================================================
# 📖 القائمة المنسّقة: سور المصحف بترتيبها (حقيقة ثابتة — مصدرها
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
# 📌 حقائق منسّقة للحروف النادرة (نفس آلية SURAHS الموثوقة)
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
    from app.games.huroof.events import normalize_letter
    from app.games.huroof.engine import ARABIC_LETTERS
    t = (ans or "").strip()
    if t.startswith("ال") and len(t) > 3:
        t = t[2:]
    if not t:
        return None
    letter = normalize_letter(t[0])
    return letter if letter in ARABIC_LETTERS else None


def _variants(ar, en):
    """تنويعات الإملاء الحتمية (ج↔غ، حذف ألف المد...) — محرك مشترك."""
    from answer_variants import spelling_variants
    return spelling_variants(ar, en)


def _valid_answer(ans):
    """إجابة عربية سليمة: ليست QID خاماً، طول معقول، ≤ 4 كلمات."""
    return (_is_arabic(ans) and not ans.startswith("Q")
            and 2 <= len(ans) <= 40 and len(ans.split()) <= 4)


def fetch_rows(query):
    import requests
    r = requests.get(SPARQL_URL, params={"query": query, "format": "json"},
                     headers=HEADERS, timeout=90)
    r.raise_for_status()
    return r.json()["results"]["bindings"]


def _g(b, k):
    return (b.get(k) or {}).get("value", "").strip()


def build_country_questions(rows):
    """قوالب الدول الثلاثة — مع استبعاد الغموض."""
    # تجميع أولي لكشف الغموض (عاصمة لدولتين / دولة بعملتين)
    by_country = {}
    for b in rows:
        c = _g(b, "cLabelAr")
        if not _is_arabic(c):
            continue
        e = by_country.setdefault(c, {"en": _g(b, "cLabelEn"),
                                      "caps": set(), "caps_en": {},
                                      "curs": set(), "curs_en": {}})
        cap, cur = _g(b, "capAr"), _g(b, "curAr")
        if cap:
            e["caps"].add(cap)
            e["caps_en"][cap] = _g(b, "capEn")
        if cur:
            e["curs"].add(cur)
            e["curs_en"][cur] = _g(b, "curEn")

    # عاصمة مشتركة بين دولتين → غموض، تُستبعد الدولتان من قالب T1
    cap_owners = {}
    for c, e in by_country.items():
        for cap in e["caps"]:
            cap_owners.setdefault(cap, set()).add(c)
    ambiguous_caps = {cap for cap, owners in cap_owners.items() if len(owners) > 1}

    qs = []
    for country, e in sorted(by_country.items()):
        if _religious(country):
            continue
        # T2 يحتاج عاصمة واحدة محددة؛ أكثر من عاصمة = غموض → تخطٍّ
        cap = next(iter(e["caps"])) if len(e["caps"]) == 1 else None
        cap_en = e["caps_en"].get(cap, "") if cap else ""

        # T1: "دولة عاصمتها X" → الإجابة اسم الدولة (الحرف من الدولة)
        if cap and cap not in ambiguous_caps and _valid_answer(country) \
                and _is_arabic(cap) and not _religious(cap):
            letter = _answer_letter(country)
            if letter:
                qs.append({
                    "question_text": f"دولة عاصمتها {cap}",
                    "correct_answer": country,
                    "category": "جغرافيا",
                    "letter": letter,
                    "accepted_answers": _variants(country, e["en"]),
                })

        # T2: "عاصمة دولة X" → الإجابة العاصمة (الحرف من العاصمة)
        if cap and _valid_answer(cap) and not _religious(cap):
            letter = _answer_letter(cap)
            if letter:
                qs.append({
                    "question_text": f"عاصمة دولة {country}",
                    "correct_answer": cap,
                    "category": "جغرافيا",
                    "letter": letter,
                    "accepted_answers": _variants(cap, cap_en),
                })

        # T3: "العملة الرسمية لدولة X" — فقط لو للدولة عملة واحدة (أحادية)
        if len(e["curs"]) == 1:
            cur = next(iter(e["curs"]))
            if _valid_answer(cur) and not _religious(cur):
                letter = _answer_letter(cur)
                if letter:
                    qs.append({
                        "question_text": f"العملة الرسمية لدولة {country}",
                        "correct_answer": cur,
                        "category": "جغرافيا",
                        "letter": letter,
                        "accepted_answers": _variants(cur, e["curs_en"].get(cur, "")),
                    })
    return qs


def build_element_questions(rows):
    """قوالب العناصر — علاقة أحادية مضمونة (رمز/عدد ذري ↔ عنصر واحد)."""
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
                   "letter": letter, "accepted_answers": acc})
        qs.append({"question_text": f"العنصر الكيميائي ذو العدد الذري ({int(z)})",
                   "correct_answer": name, "category": "علوم",
                   "letter": letter, "accepted_answers": acc})
    return qs


def build_quran_questions():
    """📖 القالب الديني — من القائمة المنسّقة حصراً (لا Wikidata).
    علاقة أحادية مطلقة: رقم الترتيب ↔ سورة واحدة. قالب رصين ثابت —
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


def save_to_db(questions):
    """إدخال لجدول questions مع dedup بنص السؤال — لا يمس اليدوي."""
    from app.core.database import SessionLocal, Question
    db = SessionLocal()
    try:
        existing = {t for (t,) in db.query(Question.question_text).filter(
            Question.game_mode == "huroof").all()}
        added = 0
        for q in questions:
            if q["question_text"] in existing:
                continue
            existing.add(q["question_text"])
            db.add(Question(
                game_mode="huroof",
                question_text=q["question_text"],
                correct_answer=q["correct_answer"],
                category=q["category"],
                extra_data=json.dumps({
                    "letter": q["letter"],
                    "accepted_answers": q["accepted_answers"],
                    "source": "auto_wikidata",
                }, ensure_ascii=False),
            ))
            added += 1
        db.commit()
        return added
    finally:
        db.close()


def run_import():
    """قابلة للاستدعاء من خلفية المنصة. ترجع عدد الأسئلة المضافة."""
    rows_c = fetch_rows(QUERY_COUNTRIES)
    rows_e = fetch_rows(QUERY_ELEMENTS)
    qs = (build_country_questions(rows_c) + build_element_questions(rows_e)
          + build_quran_questions() + build_curated_questions())
    if len(qs) < 50:
        print(f"⚠️ [huroof-import] نتائج قليلة ({len(qs)}) — إلغاء الدفعة (تحصين)")
        return 0
    added = save_to_db(qs)
    # 📊 تقرير التغطية: الحروف المغطاة والناقصة (الناقصة تُغطى يدوياً —
    # المولد لا يخترع أبداً إجابة لحرف بلا كيان حقيقي)
    from app.games.huroof.engine import ARABIC_LETTERS
    covered = {}
    for q in qs:
        covered[q["letter"]] = covered.get(q["letter"], 0) + 1
    missing = [l for l in ARABIC_LETTERS if l not in covered]
    print(f"🔡 [huroof-import] وُلّد {len(qs)} سؤالاً، أُضيف {added} جديداً — "
          f"تغطية {len(covered)}/{len(ARABIC_LETTERS)} حرفاً")
    if missing:
        print(f"📊 [huroof-import] حروف بلا أسئلة مولّدة (تُغطى يدوياً): {' '.join(missing)}")
    return added


if __name__ == "__main__":
    run_import()
