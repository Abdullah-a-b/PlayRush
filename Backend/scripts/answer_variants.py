"""
 محرك تنويعات الإملاء الحتمي — مشترك بين مولّدي حروف والبنك.

المشكلة: الأسماء الأجنبية تُكتب بأشكال متعددة كلها صحيحة عرفاً:
سانتياغو / سانتياجو / سنتياغو / سنتياجو — ورفض أحدها ظلم للاعب.

الحل: قواعد تحويل حتمية (صفر AI، صفر هلوسة) تولّد الأشكال الشائعة:
  1. ج  غ (صوت g في التعريب: سانتياغوسانتياجو، بلجيكابلغيكا)
  2. حذف ألف مدّ داخلية واحدة (سانتياغوسنتياغو، سانتيغو)
  3. تركيب القاعدتين معاً (سنتياجو)
+ الشكل بلا "ال" + الاسم الإنجليزي (للطبقة الرابعة AI Judge).

ملاحظات أمان:
- التنويعات تُضاف لقائمة accepted_answers فقط — توسّع القبول ولا
  ترفض شيئاً أبداً. أسوأ حالة: قبول إملاء غريب لنفس السؤال (بلا ضرر).
- الإجابة الرسمية (correct_answer) تبقى الشكل القياسي الأصلي.
- باقي الفروق (ة/ه، أ/إ/آ/ا، ى/ي، المسافات) يطبّعها المحكّم أصلاً
  في clean_text_for_match — لا نكررها هنا.
"""


def _jg_swaps(s):
    out = {s}
    if 'ج' in s:
        out.add(s.replace('ج', 'غ'))
    if 'غ' in s:
        out.add(s.replace('غ', 'ج'))
    return out


def _alef_elisions(s):
    """حذف ألف مدّ داخلية واحدة في كل مرة (لا الأولى ولا الأخيرة)."""
    out = set()
    for i in range(1, len(s) - 1):
        if s[i] == 'ا':
            out.add(s[:i] + s[i + 1:])
    return out


def spelling_variants(ar, en=None, cap=15):
    """يرجع قائمة الأشكال المقبولة للإجابة — حتمية ومرتبة.
    الأشكال الأساسية (الأصل + بلا ال + الإنجليزي) محمية من السقف."""
    ar = (ar or "").strip()
    if not ar:
        return []
    base = {ar}
    if ar.startswith("ال") and len(ar) > 4:
        base.add(ar[2:])

    pool = set(base)
    for b in list(pool):
        pool |= _jg_swaps(b)
    for b in list(pool):
        pool |= _alef_elisions(b)
    for b in list(pool):          # تركيب: حذف الألف ثم قلب ج/غ
        pool |= _jg_swaps(b)

    extras = sorted(pool - base)[: max(0, cap - len(base))]
    out = sorted(base) + extras
    if en:
        out.append(en.strip().lower())
    # ترتيب ثابت مع إزالة التكرار حفاظاً على حتمية المخرجات
    seen, final = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            final.append(v)
    return final
