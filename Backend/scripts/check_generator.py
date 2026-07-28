"""
اختبار مولّد أسئلة خلية الحروف.
التشغيل: python scripts/check_generator.py
يتطلب GEMINI_API_KEY في ملف .env أو في متغيرات البيئة مباشرةً.
"""
import asyncio
import sys
import os

# ① حدّد مسار Backend (الأب المباشر لـ scripts/)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

# ② حمّل .env قبل أي import من app — هذا هو سبب الخطأ الأصلي:
#    السكربت يقفز مباشرةً إلى ai_judge.py متجاوزاً config.py الذي
#    يستدعي load_dotenv() داخل التطبيق الرئيسي.
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(_BACKEND_DIR, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        print(f"[i] تم تحميل .env من: {_env_path}")
    else:
        print("[i] ملف .env غير موجود — سيُستخدم GEMINI_API_KEY من البيئة مباشرةً")
except ImportError:
    print("[i] python-dotenv غير مثبّت — سيُستخدم GEMINI_API_KEY من البيئة مباشرةً")
    print("    للتثبيت: pip install python-dotenv")

# ③ الآن بأمان نستورد من app
from app.infrastructure.ai_judge import generate_huroof_question, _get_model


async def main():
    print("=" * 52)
    print("اختبار مولّد أسئلة خلية الحروف")
    print("=" * 52)

    # تحقّق أوّلي من وجود المفتاح قبل محاولة تحميل النموذج
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[✗] GEMINI_API_KEY غير موجود في البيئة ولا في ملف .env")
        print("    — أضفه في Backend/.env أو مرّره مباشرةً:")
        print("      Windows: $env:GEMINI_API_KEY='مفتاحك'; python scripts/check_generator.py")
        print("      Linux:   GEMINI_API_KEY='مفتاحك' python scripts/check_generator.py")
        return

    print(f"[i] GEMINI_API_KEY موجود ({api_key[:8]}...{api_key[-4:]})")
    print()

    model = _get_model()
    if model is None:
        print("[✗] النموذج غير متاح — تحقّق من صلاحية GEMINI_API_KEY والاتصال بالإنترنت")
        return
    print("[✓] النموذج جاهز")
    print()

    # نجرّب توليد أسئلة لعدة حروف
    letters = ["ب", "س", "م", "ع", "ذ", "خ"]
    ok = 0
    for letter in letters:
        try:
            q = await generate_huroof_question(letter, timeout=12.0)
        except Exception as e:
            print(f"[✗] حرف '{letter}': خطأ — {e}")
            continue

        if q and q.get("answer"):
            ok += 1
            print(f"[✓] حرف '{letter}':")
            print(f"     السؤال : {q['question']}")
            print(f"     الإجابة: {q['answer']}  |  الصعوبة: {q['difficulty']}")
        else:
            print(f"[✗] حرف '{letter}': لم يُولّد سؤالاً صالحاً")
        print()

    print("=" * 52)
    print(f"النتيجة: {ok}/{len(letters)} حرف نجح توليده")
    if ok == len(letters):
        print("✅ المولّد يعمل بشكل ممتاز")
    elif ok > 0:
        print("⚠️  المولّد يعمل جزئياً — قد يكون بسبب صرامة التحقّق")
    else:
        print("❌ المولّد لا يولّد — تحقّق من المفتاح والاتصال")


if __name__ == "__main__":
    asyncio.run(main())
