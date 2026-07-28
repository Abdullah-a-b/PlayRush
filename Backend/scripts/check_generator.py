"""
اختبار مولّد أسئلة خلية الحروف.
التشغيل: python scripts/check_generator.py
يتطلب GEMINI_API_KEY في البيئة (موجود على Azure).
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.ai_judge import generate_huroof_question, _get_model


async def main():
    print("=" * 52)
    print("اختبار مولّد أسئلة خلية الحروف")
    print("=" * 52)

    model = _get_model()
    if model is None:
        print("[✗] النموذج غير متاح — تحقّق من GEMINI_API_KEY")
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
            print(f"     السؤال: {q['question']}")
            print(f"     الإجابة: {q['answer']}  |  الصعوبة: {q['difficulty']}")
        else:
            print(f"[✗] حرف '{letter}': لم يُولّد سؤالاً صالحاً")
        print()

    print("=" * 52)
    print(f"النتيجة: {ok}/{len(letters)} حرف نجح توليده")
    if ok == len(letters):
        print("✅ المولّد يعمل بشكل ممتاز")
    elif ok > 0:
        print("⚠️ المولّد يعمل جزئياً — قد يكون بسبب صرامة التحقّق")
    else:
        print("❌ المولّد لا يولّد — تحقّق من المفتاح والاتصال")


if __name__ == "__main__":
    asyncio.run(main())
