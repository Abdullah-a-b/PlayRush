"""
🤖 اختيار نموذج Gemini المتاح تلقائياً

المشكلة: Google توقف أسماء نماذج قديمة (gemini-1.5-flash صار 404).
الحل: نجرب قائمة أسماء حديثة بالترتيب، ونسقط لأول متاح فعلاً.
ونكتشف القائمة الحقيقية عبر list_models كملاذ أخير — فلن يتكرر
خطأ 404 حين توقف Google أي اسم مستقبلاً.

الاستخدام:
    from app.core.gemini_model import load_gemini_model
    model = load_gemini_model()   # None لو المفتاح غائب أو لا نموذج متاح
"""
import os

# أسماء مفضّلة بالترتيب (الأحدث/الأرخص أولاً). نبقيها محدّثة، لكن
# آلية list_models تحتنا تضمن العمل حتى لو تغيّرت كلها.
_PREFERRED = [
    "gemini-flash-latest",      # ✅ اسم مستقر — يعمل مع مفاتيح Free Tier الجديدة
    "gemini-3.5-flash",         # ✅ احتياط أول
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
]

_cached_model = None
_cache_tried = False
_cache_failed = False  # 🛡️ جديد: نفرّق بين "لم نحاول" و"حاولنا وفشلنا"


def _pick_available_name(genai):
    """يكتشف اسم نموذج يدعم generateContent فعلاً لهذا المفتاح."""
    # 1) جرّب list_models أولاً (الأدق)
    try:
        available = set()
        for m in genai.list_models():
            methods = getattr(m, "supported_generation_methods", []) or []
            if "generateContent" in methods:
                available.add(m.name.split("/")[-1])
        for name in _PREFERRED:
            if name in available:
                return name
        # أي نموذج flash متاح (أرخص)، وإلا أول متاح أياً كان
        flash = sorted([n for n in available if "flash" in n])
        if flash:
            return flash[0]
        if available:
            return sorted(available)[0]
    except Exception as e:
        print(f"⚠️ [gemini] تعذّر سرد النماذج ({e}) — نجرّب المفضّلة مباشرةً")

    # 2) fallback: جرّب كل اسم مفضّل مباشرةً بطلب بسيط
    for name in _PREFERRED:
        try:
            m = genai.GenerativeModel(name)
            # اختبار بسيط أن النموذج يقبل الطلب
            resp = m.generate_content("ping")
            if resp:
                print(f"⚠️ [gemini] list_models فشل، لكن {name!r} يعمل مباشرةً")
                return name
        except Exception:
            continue

    return None


def load_gemini_model(force_reload=False):
    """يحمّل نموذج Gemini متاحاً (مع كاش). None لو المفتاح غائب/لا نموذج.

    force_reload=True يُعيد المحاولة حتى لو فشلت سابقاً (للـ /ai-status).
    """
    global _cached_model, _cache_tried, _cache_failed
    # لو المودل محمّل ومؤكد → ارجعه
    if _cache_tried and _cached_model is not None:
        return _cached_model
    # لو فشل سابقاً وما في force_reload → لا تحاول مرة أخرى (توفير طلبات)
    if _cache_failed and not force_reload:
        return None
    _cache_tried = True

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        name = _pick_available_name(genai)
        if not name:
            print("⚠️ [gemini] لا يوجد نموذج يدعم generateContent لهذا المفتاح")
            _cache_failed = True
            return None
        _cached_model = genai.GenerativeModel(name)
        _cache_failed = False  # نجحنا → نمسح علامة الفشل
        print(f"🤖 [gemini] النموذج المستخدم: {name}")
        return _cached_model
    except ImportError:
        print("⚠️ [gemini] مكتبة google-generativeai غير مثبّتة "
              "(pip install google-generativeai)")
        _cache_failed = True
        return None
    except Exception as e:
        print(f"⚠️ [gemini] تعذّر التهيئة: {e}")
        _cache_failed = True
        return None


def reset_cache():
    """يُعيد ضبط الكاش (مفيد بعد تغيير GEMINI_API_KEY بدون إعادة تشغيل)."""
    global _cached_model, _cache_tried, _cache_failed
    _cached_model = None
    _cache_tried = False
    _cache_failed = False
