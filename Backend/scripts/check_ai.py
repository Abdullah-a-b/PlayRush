"""فحص جاهزية الـ AI (Gemini) من التيرمينال.

الاستخدام من مجلد Backend:
    python scripts/check_ai.py

يطبع: حالة المفتاح، النموذج المختار، زمن الاستجابة، ونتيجة اختبار حكم فعلي.
"""
import os
import sys
import time

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_BASE, ".env"))


def main():
    print("=" * 52)
    print("فحص الـ AI — PlayRush")
    print("=" * 52)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("[X] GEMINI_API_KEY غير موجود في .env")
        print("    التحكيم داخل الألعاب سيعمل بالوضع المتساهل (قبول عند الشك).")
        sys.exit(1)
    print(f"[/] المفتاح موجود ({api_key[:6]}...{api_key[-4:]})")

    from app.infrastructure.gemini_model import load_gemini_model

    t0 = time.time()
    model = load_gemini_model(force_reload=True)
    load_ms = int((time.time() - t0) * 1000)
    if model is None:
        print(f"[X] فشل تحميل النموذج ({load_ms}ms) — تحقق من صلاحيات المفتاح أو الحصة (quota).")
        sys.exit(1)

    name = (getattr(model, "_model_name", None)
            or getattr(model, "model_name", None) or str(model))
    if "/" in name:
        name = name.split("/")[-1]
    print(f"[/] النموذج المختار: {name} (التحميل {load_ms}ms)")

    # اختبار توليد مباشر
    t0 = time.time()
    try:
        resp = model.generate_content("قل: جاهز")
        gen_ms = int((time.time() - t0) * 1000)
        text = (resp.text or "").strip()
        print(f"[/] الاتصال يعمل — الرد: {text[:40]!r} ({gen_ms}ms)")
    except Exception as e:
        gen_ms = int((time.time() - t0) * 1000)
        print(f"[X] فشل التوليد ({gen_ms}ms): {e}")
        sys.exit(1)

    # اختبار حكم فعلي بنفس مسار اللعبة (judge_answer)
    import asyncio
    from app.infrastructure.ai_judge import judge_answer

    t0 = time.time()
    verdict = asyncio.run(judge_answer(
        question="اذكر لوناً من ألوان قوس قزح",
        player_answer="أحمر",
        accepted_answers=["أحمر", "أزرق", "أخضر"],
    ))
    judge_ms = int((time.time() - t0) * 1000)
    print(f"[/] judge_answer: accept={verdict.get('accept')} "
          f"source={verdict.get('source')} ({judge_ms}ms)")

    print("-" * 52)
    print("الخلاصة: الـ AI جاهز ويعمل داخل الألعاب.")


if __name__ == "__main__":
    main()
