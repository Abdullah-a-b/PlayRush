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

def check_answer(player_answer: str, correct_answer: str,
                 accepted_answers: list[str] = None,
                 required_letter: str = None,
                 fuzzy_threshold: float = 0.85) -> dict:
    """
    يفحص إجابة اللاعب عبر 3 طبقات.

    Returns:
        {
            'verdict': 'accept' | 'reject' | 'maybe',
            'confidence': 0.0-1.0,
            'method': 'exact' | 'fuzzy' | 'token' | 'none',
            'matched_answer': str | None,   # أي إجابة تطابقت
        }

    'maybe' = حالة حدية، يُنصح بإحالتها لـ AI Judge لاحقاً.
    """
    accepted_answers = accepted_answers or []
    all_correct = [correct_answer] + list(accepted_answers)

    p_norm = normalize_arabic(player_answer)

    if not p_norm:
        return {'verdict': 'reject', 'confidence': 1.0, 'method': 'empty', 'matched_answer': None}

    # فحص الحرف المطلوب (خاص بلعبة حروف)
    # مهم: نفحص الحرف على النص المطبّع العادي (قبل إزالة ال) لتجنب الأخطاء
    if required_letter:
        p_first = p_norm.replace(' ', '')
        req_compact = normalize_arabic(required_letter).replace(' ', '')
        if req_compact:
            # نقبل لو الكلمة تبدأ بالحرف، أو تبدأ بـ "ال" + الحرف
            starts_ok = (
                p_first.startswith(req_compact) or
                p_first.startswith('ال' + req_compact) or
                p_first.startswith('ل' + req_compact)  # بعد تطبيع نادر
            )
            if not starts_ok:
                return {'verdict': 'reject', 'confidence': 1.0,
                        'method': 'wrong_letter', 'matched_answer': None}

    # ==========================================
    # الطبقة 1: Exact match (بعد التطبيع)
    # ==========================================
    for correct in all_correct:
        if p_norm == normalize_arabic(correct):
            return {'verdict': 'accept', 'confidence': 1.0,
                    'method': 'exact', 'matched_answer': correct}

    # ==========================================
    # الطبقة 1.5: مطابقة الكلمة المفتاحية (رأس الإجابة)
    # ==========================================
    # الإجابات المستوردة كثيراً ما تكون وصفاً كاملاً:
    #   «شيكل إسرائيلي جديد» / «الريال السعودي»
    # واللاعب ينطق الجوهر فقط: «شيكل» / «ريال».
    # بدون هذه الطبقة تسقط الإجابة الصحيحة في حساب التغطية
    # (1 من 3 = 0.33 < 0.5) وتُرفض قبل أن تصل للذكاء الاصطناعي.
    p_tokens_head = _tokenize(player_answer)
    if len(p_tokens_head) == 1:
        p_head = p_tokens_head[0]
        for correct in all_correct:
            c_tokens = _tokenize(correct)
            if not c_tokens:
                continue
            # كلمة مفتاحية مميّزة (4 أحرف فأكثر) تكفي وحدها
            if _bare(p_head) == _bare(c_tokens[0]) and len(_bare(p_head)) >= 4:
                return {'verdict': 'accept', 'confidence': 0.9,
                        'method': 'head_word', 'matched_answer': correct}
            # كلمة قصيرة أو ليست الأولى → حالة حدّية يحسمها الذكاء الاصطناعي
            if _bare(p_head) in [_bare(t) for t in c_tokens]:
                return {'verdict': 'maybe', 'confidence': 0.7,
                        'method': 'token_in_answer', 'matched_answer': correct}

    # ==========================================
    # الطبقة 2: Fuzzy match
    # ==========================================
    best_ratio = 0.0
    best_match = None
    for correct in all_correct:
        c_norm = normalize_arabic(correct)
        ratio = similarity_ratio(p_norm, c_norm)
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = correct

    if best_ratio >= fuzzy_threshold:
        return {'verdict': 'accept', 'confidence': best_ratio,
                'method': 'fuzzy', 'matched_answer': best_match}

    # ==========================================
    # الطبقة 3: Token analysis (للكلمات الجزئية)
    # ==========================================
    player_tokens = _tokenize(player_answer)
    if player_tokens:
        correct_tokens = set(_tokenize(correct_answer))
        # نجمع كل tokens الإجابات المقبولة
        accepted_token_set = set(correct_tokens)
        for correct in all_correct:
            accepted_token_set.update(_tokenize(correct))

        if accepted_token_set and correct_tokens:
            player_set = set(player_tokens)

            # دالة: هل token اللاعب يطابق أي token مقبول (مع fuzzy)؟
            def token_matches(ptoken, token_set):
                if ptoken in token_set:
                    return True
                # fuzzy داخل الكلمات (يحل بيرنابيو/برنابيو)
                for t in token_set:
                    if len(ptoken) >= 4 and similarity_ratio(ptoken, t) >= 0.8:
                        return True
                return False

            # كم غطّى اللاعب من الإجابة الصحيحة (مع fuzzy)
            covered = sum(1 for ct in correct_tokens
                          if any(token_matches(pt, {ct}) for pt in player_set))
            coverage = covered / len(correct_tokens)

            # كم من كلمات اللاعب صحيحة
            matched_count = sum(1 for pt in player_set if token_matches(pt, accepted_token_set))
            match_ratio = matched_count / len(player_set)

            # غطّى الإجابة الصحيحة كاملة  accept حتى لو فيه كلمات إضافية
            # ("برنابيو ستاديوم" يغطّي "برنابيو" بالكامل)
            if coverage >= 1.0:
                # لكن نرفض لو الـ noise كثير جداً ويغيّر المعنى
                if match_ratio >= 0.4:
                    return {'verdict': 'accept', 'confidence': 0.85,
                            'method': 'token_full_coverage', 'matched_answer': correct_answer}
                else:
                    return {'verdict': 'maybe', 'confidence': 0.6,
                            'method': 'token_noisy', 'matched_answer': correct_answer}

            # تطابق جزئي  maybe (لـ AI لاحقاً)
            if coverage >= 0.5:
                return {'verdict': 'maybe', 'confidence': coverage,
                        'method': 'token_partial', 'matched_answer': correct_answer}

    # ==========================================
    # لا تطابق
    # ==========================================
    # لو الـ fuzzy كان قريباً (لكن تحت العتبة)  maybe
    if best_ratio >= 0.5:
        return {'verdict': 'maybe', 'confidence': best_ratio,
                'method': 'fuzzy_low', 'matched_answer': best_match}

    return {'verdict': 'reject', 'confidence': 1.0 - best_ratio,
            'method': 'none', 'matched_answer': None}
