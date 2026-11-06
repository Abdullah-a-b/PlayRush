"""
 معالج النصوص العربية — لفحص إجابات اللعبة

يحل مشكلة رفض الإجابات الصحيحة بسبب اختلاف طريقة الكتابة:
- "عَمّان" vs "عمان" (تشكيل)
- "المدينة" vs "المدينه" (ة/ه)
- "سانتياغو" vs "سانتياجو" (غ/ج)
- "برنابيو ستاديوم" vs "برنابيو" (كلمات إضافية)
- أخطاء إملائية بسيطة

التصميم: 3 طبقات متتالية (cascade)
1. Normalize + Exact match (الأسرع)
2. Fuzzy match (للأخطاء الإملائية)
3. Token analysis (للكلمات الجزئية الصحيحة)

 صفر مكتبات خارجية — كل شي مكتوب يدوياً ليعمل فوراً بدون تثبيت.
"""
import re
import unicodedata


# ==========================================
# 1. التطبيع (Normalization)
# ==========================================

# حروف التشكيل العربية (الحركات)
_TASHKEEL = re.compile(r'[\u064B-\u0652\u0670\u0640]')  # فتحة، ضمة، كسرة، شدة، سكون، تطويل

# كلمات الوصل الشائعة (تُحذف في token analysis فقط)
_STOP_WORDS = {
    'في', 'من', 'على', 'الى', 'إلى', 'عن', 'مع', 'هو', 'هي',
    'the', 'a', 'an', 'is', 'of', 'in', 'at', 'on', 'to',
}


def normalize_arabic(text: str) -> str:
    """
    يوحّد النص العربي لإزالة الفروق غير الجوهرية.

    "عَمّان، العاصمة!"  "عمان العاصمه"
    """
    if not text:
        return ""

    text = str(text).strip()

    # 1. إزالة التشكيل والتطويل
    text = _TASHKEEL.sub('', text)

    # 2. توحيد الألف (أ إ آ ٱ  ا)
    text = re.sub(r'[أإآٱ]', 'ا', text)

    # 3. توحيد الياء (ى  ي) والهمزات
    text = text.replace('ى', 'ي')
    text = text.replace('ؤ', 'و').replace('ئ', 'ي').replace('ء', '')

    # 4. توحيد التاء المربوطة (ة  ه) — يحل المدينة/المدينه
    text = text.replace('ة', 'ه')

    # 5. توحيد الهاء/الكاف الفارسية
    text = text.replace('ک', 'ك').replace(' گ', 'ك')

    # 6. إزالة علامات الترقيم (عربية وإنجليزية)
    text = re.sub(r'[^\w\s]', ' ', text)

    # 7. توحيد المسافات + lowercase (للإنجليزي)
    text = ' '.join(text.split()).strip().lower()

    return text


def normalize_for_letter_game(text: str) -> str:
    """
    تطبيع خاص بلعبة حروف: يشيل المسافات أيضاً للمقارنة الصارمة.
    يُستخدم بحذر — يشيل 'ال' فقط لو الكلمة أطول من 3 أحرف (يحمي 'الله').
    """
    normalized = normalize_arabic(text)
    compact = normalized.replace(' ', '')

    # نشيل "ال" التعريف فقط لو الكلمة طويلة (يحمي كلمات مثل "الله", "الم")
    if compact.startswith('ال') and len(compact) > 4:
        compact = compact[2:]

    return compact


# ==========================================
# 2. Fuzzy Matching (Levenshtein) — صفر مكتبات
# ==========================================

def _levenshtein(a: str, b: str) -> int:
    """يحسب المسافة بين نصين (عدد التعديلات لتحويل a لـ b)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # نستخدم صفّين فقط (توفير ذاكرة)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(
                prev[j + 1] + 1,   # حذف
                curr[j] + 1,       # إضافة
                prev[j] + cost     # استبدال
            ))
        prev = curr
    return prev[-1]


def similarity_ratio(a: str, b: str) -> float:
    """
    نسبة التشابه بين نصين (0.0 - 1.0).
    1.0 = متطابقان، 0.0 = مختلفان تماماً.
    """
    if not a and not b:
        return 1.0
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    distance = _levenshtein(a, b)
    return 1.0 - (distance / max_len)


# ==========================================
# 3. Token Analysis (للكلمات الجزئية)
# ==========================================

def _tokenize(text: str) -> list[str]:
    """يقسّم النص لكلمات بعد التطبيع، يشيل stop words."""
    normalized = normalize_arabic(text)
    tokens = [t for t in normalized.split() if t and t not in _STOP_WORDS]
    return tokens


def _bare(token: str) -> str:
    """يزيل «ال» التعريف من بداية الكلمة للمقارنة فقط.
    «الشيكل» → «شيكل» — لازم لأن الإجابات المستوردة كثيراً ما تبدأ بأل."""
    if token.startswith('ال') and len(token) > 4:
        return token[2:]
    return token


def _token_weight(token: str) -> float:
    """
    وزن الكلمة — الكلمات الطويلة/النادرة أهم.
    'برنابيو' (طويلة) أهم من 'ملعب' (شائعة قصيرة).
    """
    if len(token) <= 2:
        return 0.3
    if len(token) <= 4:
        return 0.7
    return 1.0


# ==========================================
# 4. الواجهة الرئيسية — الـ Cascade
# ==========================================

def check_answer(player_answer: str, correct_answer: str, accepted_answers=None, required_letter=None) -> dict:
    """الأسماء والحقائق تقبل الإجابة الكاملة أو بديلها المراجع فقط."""
    from app.core.huroof_answers import check_answer as match_full_answer
    return match_full_answer(player_answer, correct_answer, accepted_answers, required_letter)
