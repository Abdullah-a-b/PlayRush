"""
 فلتر المحتوى (Profanity / Content Filter) — محلي بالكامل، صفر تكلفة

يفحص الأسماء والدردشة من الكلمات المسيئة (عربي فصحى + لهجات + إنجليزي).
يعتمد على:
1. تطبيع عربي (يكشف التحايل بالمسافات/التشكيل/تكرار الحروف/الحروف اللاتينية المدسوسة)
2. قائمة كلمات محظورة منظّمة بالفئات (قابلة للتوسيع عبر add_banned_word)
3. قائمة بيضاء تحمي الكلمات البريئة من الحظر الخاطئ
4. فحص على مستوى الكلمات (دقيق) + فحص ملتصق (يكشف التحايل بالمسافات)
5. كشف الروابط والمعرّفات (سبام/تصيّد)

سريع، محلي، بلا API ولا إنترنت. يُكمّل نظام البلاغات (وقاية قبل وقوع الضرر).
ملاحظة: لا فلتر كلمات «كامل» — وسّع القائمة من بلاغات اللاعبين الفعلية.
"""
import re
from app.core.text_processor import normalize_arabic

# قائمة الكلمات المحظورة (جذور — التطبيع يلتقط الاشتقاقات والمسافات والتكرار)
# مصدرها: تنقية يدوية + استخراج إحصائي من مجموعات بيانات عربية (L-HSAB, test set).
# اُستبعدت الجنسيات/الطوائف/السياسة (سني، درزي، فلسطيني...) لأنها ليست شتائم.
# تُوسّع باستمرار من بلاغات اللاعبين عبر add_banned_word.
_BANNED_ROOTS = [
    # ---- شتائم حيوانية / إهانة ----
    "كلب", "كلاب", "حمار", "حمير", "خنزير", "خنزيره", "خروف", "بهيم", "بهيمه",
    "بهايم", "جحش", "بغل", "حيوان", "وحش",
    # ---- إهانات الشخصية ----
    "حقير", "وقح", "وقاحه", "واطي", "رخيص", "حثاله", "خسيس", "نذل", "كذاب",
    "بشع", "بشعه", "غبي", "غبيه", "هبل", "اهبل", "هبيله", "تافه", "تافهه",
    "سافل", "منحط", "خايس", "خايسه", "معفن", "خاين", "صفيق", "متخلف", "متخلفه",
    "مقرف", "معتوه",
    # ---- قذارة ----
    "وسخ", "وسخه", "اوسخ", "قذر", "قذاره", "خرا", "خره", "خراء", "زباله",
    "مزبله", "زبال", "نجس", "زفت",
    # ---- لعن / دعاء بالسوء ----
    "لعن", "لعين", "لعنه", "ملعون", "ملعونه", "يلعن", "خراس", "اخرس", "طز",
    "صرمايه", "صرماي", "شحاطه", "عمى", "يخرب", "انقبر", "بوزك",
    # ---- ألفاظ جنسية / بذيئة (فصحى + لهجات) ----
    "عاهر", "عاهره", "شرموط", "شرموطه", "شراميط", "زاني", "زانيه", "لوطي", "قحبه", "قحاب",
    "خول", "خوال", "متناك", "متناكه", "ديوث", "معرص", "معرصه", "منيوك", "منيك",
    "منيكه", "نياك", "كس", "كسم", "كسمك", "كسامك", "نيك", "ينيك", "طيز", "طياز",
    "زب", "زبر", "عير", "خرى", "بعبص", "داعر", "داعره",
    # ---- إنجليزي شائع ----
    "fuck", "fucker", "fucking", "shit", "bitch", "asshole", "dick",
    "pussy", "cunt", "nigger", "nigga", "faggot", "whore", "slut",
    "bastard", "motherfucker", "cock", "dickhead", "retard", "rape",
    # ---- إساءات دينية (محافظة جداً — بلا جنسيات/طوائف) ----
    "كافر", "كفره", "ملحد", "زنديق", "مرتد",
]

# كلمات بريئة تحتوي جذراً محظوراً (تُستثنى من الحظر)
_WHITELIST = [
    "كسب", "كسر", "كسرت", "كستناء", "مكسب", "اكتساب", "انكسر", "كسوف",
    "كسل", "كسلان", "مكسور", "كساء", "كسارة", "كسره", "تكسب", "كسكس",
    "زبدة", "زبادي", "زبرجد", "زبيب", "مزبد", "زبون", "زبائن",
    "عيار", "معيار", "شعير", "عيره",
    "خرائط", "خريطه", "اخرى", "اخراج", "خروج", "خراف", "خرطوم",
]


def _has_url(text: str) -> bool:
    """يكشف الروابط (يُمنع نشرها في الأسماء/الدردشة لمنع السبام/التصيّد)."""
    patterns = [
        r'https?://', r'www\.', r'\.com', r'\.net', r'\.org',
        r'\.io', r't\.me/', r'@[a-zA-Z0-9_]{3,}',  # تيليجرام/منشن
    ]
    low = text.lower()
    return any(re.search(p, low) for p in patterns)


# ============================================================
# الطبقة 2: معالجة الفرانكو (Arabizi  عربي)
# يحوّل الأرقام والحروف اللاتينية الشائعة في الكتابة العربية المعرّبة
# مثال: "kalb"  "كلب"، "5ara"  "خرا"، "3ahr"  "عاهر"
# ============================================================
_ARABIZI_MAP = {
    '2': 'ا', '3': 'ع', '4': 'غ', '5': 'خ', '6': 'ط', '7': 'ح', '8': 'ق', '9': 'ص',
    'b': 'ب', 't': 'ت', 'th': 'ث', 'j': 'ج', 'g': 'ج', 'd': 'د',
    'r': 'ر', 'z': 'ز', 's': 'س', 'sh': 'ش', 'f': 'ف', 'q': 'ق', 'k': 'ك',
    'l': 'ل', 'm': 'م', 'n': 'ن', 'h': 'ه', 'w': 'و', 'y': 'ي',
    'c': 'ك', 'p': 'ب', 'v': 'ف', 'x': 'كس',
}
# الحروف اللاتينية المتحركة (a,e,i,o,u) غالباً لا تُكتب في العربية،
# لذا نولّد نسختين: واحدة تُسقط المتحركات وأخرى تحوّلها لحروف علّة.
_ARABIZI_VOWELS = {'a': 'ا', 'e': 'ي', 'i': 'ي', 'o': 'و', 'u': 'و'}

def _arabizi_to_arabic(token: str, drop_vowels: bool = True) -> str:
    """يحوّل كلمة فرانكو لعربي. يعالج الثنائيات (sh, th) أولاً.
    drop_vowels=True يُسقط a/e/i/o/u (الأصح للعربي: 'kalb''كلب')."""
    t = token.lower()
    out = []
    i = 0
    while i < len(t):
        two = t[i:i+2]
        if two in ('sh', 'th'):
            out.append(_ARABIZI_MAP[two]); i += 2; continue
        ch = t[i]; i += 1
        if ch in _ARABIZI_VOWELS:
            if not drop_vowels:
                out.append(_ARABIZI_VOWELS[ch])
            # لو drop_vowels: نتجاهل المتحرك
            continue
        out.append(_ARABIZI_MAP.get(ch, ch))
    return ''.join(out)


# ============================================================
# الطبقة 3: التطابق التقريبي (Levenshtein Distance)
# يحسب المسافة الإملائية بين كلمتين. "كللب" تبعد 1 عن "كلب"  تُحظر.
# ============================================================
def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost))
        prev = cur
    return prev[-1]


# ============================================================
# الطبقة 4: التجريد (Stemming) — إزالة السوابق واللواحق
# "ولكلابهم"  "كلاب"  يطابق الجذر. يحمي من الالتفاف بالإضافات.
# ============================================================
_PREFIXES = ('وال', 'فال', 'بال', 'كال', 'لل', 'ال', 'و', 'ف', 'ب', 'ك', 'ل', 'يا')
_SUFFIXES = ('هم', 'هن', 'كم', 'كن', 'نا', 'ها', 'ين', 'ون', 'ات', 'ه', 'ك', 'ي', 'ا')

def _stem(word: str, max_prefix: int = 2) -> str:
    """يجرّد الكلمة من السوابق واللواحق (محافظ — لا يبالغ في التجريد).
    max_prefix: أقصى عدد سوابق تُزال (1 أو 2). لاحقة واحدة دائماً. يبقي ≥3 حروف."""
    w = word
    for _ in range(max_prefix):
        stripped = False
        for p in _PREFIXES:
            if w.startswith(p) and len(w) - len(p) >= 3:
                w = w[len(p):]; stripped = True
                break
        if not stripped:
            break
    for s in _SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[:-len(s)]
            break
    return w


def _normalize_for_filter(text: str) -> str:
    """تطبيع للكشف: يزيل المسافات/الرموز بين الحروف (يكشف 'ك ل ب' و 'ك.ل.ب')."""
    # نطبّع عربياً أولاً (يزيل التشكيل، يوحّد الألف/الهمزة...)
    t = normalize_arabic(text)
    low = t.lower()
    # نختصر تكرار الحروف أولاً (كلllب  كلlب  ...) قبل إزالة الرموز
    low = re.sub(r'(.)\1{1,}', r'\1', low)
    # نزيل المسافات والرموز الفاصلة (تحايل شائع)
    low = re.sub(r'[\s\.\-_*#@/\\|]+', '', low)
    # نزيل أي حرف لاتيني مدسوس وسط نص عربي (كلlب) — نفصل النسختين:
    arabic_only = re.sub(r'[^\u0600-\u06FF]', '', low)
    return low, arabic_only


def check_text(text: str) -> dict:
    """
    يفحص نصاً. يرجع: {'clean': bool, 'reason': str|None}
    clean=True يعني آمن.
    """
    if not text or not text.strip():
        return {'clean': True, 'reason': None}

    raw = text.strip()

    # 1) روابط
    if _has_url(raw):
        return {'clean': False, 'reason': 'يُمنع نشر الروابط أو المعرّفات'}

    # 2) فحص على مستوى الكلمات (أدق من البحث في النص كله)
    norm_full, norm_arabic = _normalize_for_filter(raw)

    # قائمة بيضاء مطبّعة (للمقارنة السريعة)
    white_norm = set()
    for w in _WHITELIST:
        wf, _ = _normalize_for_filter(w)
        white_norm.add(wf)

    # نقسّم النص لكلمات (بعد التطبيع الأصلي مع إبقاء المسافات)
    norm_spaced = normalize_arabic(raw).lower()
    norm_spaced = re.sub(r'(.)\1{1,}', r'\1', norm_spaced)  # اختصار التكرار
    words = re.split(r'[\s\.\-_*#@/\\|،,!?؟]+', norm_spaced)

    # كشف التحايل بتفريق الحروف (ك ل ب): ندمج الأحرف المفردة المتتالية في "كلمة" واحدة
    # مثال: ["ك","ل","ب","حقير"]  نضيف "كلب" كرمز للفحص.
    merged_singletons = []
    run = []
    for w in words + ['']:
        wc = re.sub(r'[^\u0600-\u06FFa-z]', '', w)
        if len(wc) == 1:
            run.append(wc)
        else:
            if len(run) >= 2:
                merged_singletons.append(''.join(run))
            run = []
    # نعامل الكلمات المدموجة كأنها كلمات عادية تخضع لكل الطبقات
    words = words + merged_singletons

    # نجهّز نسخاً مجرّدة + مُعرّبة لكل كلمة (الطبقات 2 و4)
    prepared = []  # (wclean, stemmed, arabized_stemmed)
    for word in words:
        if not word:
            continue
        wclean = re.sub(r'[^\u0600-\u06FFa-z0-9]', '', word)
        if not wclean:
            continue
        # نسخة عربية فقط (بلا أرقام ولا لاتيني) للمطابقة والتجريد
        wclean_ar = re.sub(r'[^\u0600-\u06FF]', '', wclean)
        # تجريدان: مرة واحدة (وكلابكلاب) ومرتين (ولكلابهمكلاب) لتفادي القص الزائد
        if wclean_ar:
            stemmed = (_stem(wclean_ar, max_prefix=1), _stem(wclean_ar, max_prefix=2))
        else:
            stemmed = ('', '')
        # الطبقة 2: لو الكلمة لاتينية بالكامل (فرانكو) نحوّلها لعربي ثم نجرّدها
        arabized = None
        if re.fullmatch(r'[a-z0-9]+', wclean):
            ar_list = []
            for dv in (True, False):  # نسخة بإسقاط المتحركات وأخرى بتحويلها
                a = _arabizi_to_arabic(wclean, drop_vowels=dv)
                a = re.sub(r'(.)\1{1,}', r'\1', a)
                ar_list.append(_stem(a))
            arabized = ar_list
        prepared.append((wclean_ar, stemmed, arabized))

    # جذور قصيرة (≤4 حروف) معرّضة للاصطدام بكلمات بريئة كجزء منها
    # (خول⊂دخول، عمى⊂العميد، خره⊂صخره، لعن⊂العنايه، بشع⊂بشعور...).
    # لذا نطابقها ككلمة كاملة أو كجذر مجرّد فقط — لا كسلسلة جزئية.
    for root in _BANNED_ROOTS:
        rf, ra = _normalize_for_filter(root)
        if not rf:
            continue
        # عتبة الطول التي يُسمح فيها بالمطابقة الجزئية (substring):
        # ≤4 حروف  كلمة كاملة/جذر فقط (يمنع دخول/العميد/صخره)
        # ≥5 حروف  يُسمح بالجزئية (شرموط، معرص، حثاله نادراً ما تصطدم)
        allow_substring = len(rf) >= 5

        for wcl_ar, stems, arabized in prepared:
            # stems = (stem1, stem2) — نفحص الكلمة وكلا مستويي التجريد
            if (wcl_ar and wcl_ar in white_norm) or any(s and s in white_norm for s in stems):
                continue
            matched = False
            if allow_substring:
                matched = (rf in wcl_ar or any(rf in s for s in stems))
                # الطبقة 3: تطابق تقريبي — للجذور الطويلة (≥6) فقط
                if not matched and len(rf) >= 6:
                    if _levenshtein(wcl_ar, rf) <= 1 or any(_levenshtein(s, rf) <= 1 for s in stems):
                        matched = True
            else:
                # جذر قصير/متوسط: تطابق تام للكلمة أو لأحد جذريها المجرّدين فقط
                matched = (wcl_ar == rf or any(s == rf for s in stems))
            # الطبقة 2: فحص النُّسخ المُعرّبة من الفرانكو (بنفس قاعدة الطول)
            if not matched and arabized:
                for a in arabized:
                    if allow_substring:
                        if rf in a or (len(rf) >= 6 and _levenshtein(a, rf) <= 1):
                            matched = True; break
                    else:
                        if a == rf:
                            matched = True; break
            if matched:
                return {'clean': False, 'reason': 'يحتوي على لفظ غير لائق'}

    # 3) فحص إضافي على النص الملتصق (يكشف التحايل بالمسافات: ك ل ب  كلب)
    #    فقط للجذور الطويلة (≥5) لتجنّب الإيجابيات الكاذبة من الجذور القصيرة
    for root in _BANNED_ROOTS:
        rf, ra = _normalize_for_filter(root)
        if rf and len(rf) >= 5:
            if rf in norm_full or (ra and len(ra) >= 5 and ra in norm_arabic):
                # تأكد أنه ليس ضمن كلمة بيضاء ملتصقة
                if not any(rf in wn for wn in white_norm):
                    return {'clean': False, 'reason': 'يحتوي على لفظ غير لائق'}

    return {'clean': True, 'reason': None}


def is_name_allowed(name: str) -> dict:
    """فحص اسم اللاعب (أصرم: يمنع الروابط + الألفاظ + الرموز الغريبة)."""
    if not name or len(name.strip()) < 2:
        return {'clean': False, 'reason': 'الاسم قصير جداً'}
    if len(name) > 30:
        return {'clean': False, 'reason': 'الاسم طويل جداً'}
    return check_text(name)


def is_chat_allowed(message: str) -> dict:
    """فحص رسالة دردشة."""
    return check_text(message)


def add_banned_word(word: str):
    """يضيف كلمة للقائمة وقت التشغيل (للأدمن مستقبلاً)."""
    w = word.strip().lower()
    if w and w not in _BANNED_ROOTS:
        _BANNED_ROOTS.append(w)

