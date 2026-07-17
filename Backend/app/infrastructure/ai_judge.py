"""
 AI Judge — الطبقة الرابعة من التحكيم (للحالات الحدّية فقط)

 حلّ مشكلة البطء (latency):
هذا الـ Judge **لا يُستدعى لكل إجابة** — فقط للحالات الحدّية النادرة (~3%)
التي تعطيها الطبقات 1-3 حُكم 'maybe'. أي:
  • الطبقات 1-3 (Normalize/Fuzzy/Token) = فورية، تحل ~97%.
  • AI Enrichment (offline) = يملأ accepted_answers مسبقاً، يقلل maybe أكثر.
  • AI Judge (هنا) = الملاذ الأخير للـ 3% المتبقية فقط.

 ضمانات ضد البطء:
  1. Timeout صارم (افتراضي 2 ثانية) — لا ينتظر أبداً أكثر.
  2. Lenient default — عند Timeout أو فشل: نقبل الإجابة (نعطي اللاعب الفائدة).
  3. لا يُستدعى إلا عند verdict == 'maybe' (نادر).

حسب وثيقة PlayRush (ص7): "Timeout 2s + lenient default. ~3% فقط تصله".
"""
import os
import asyncio
import json


# نتيجة افتراضية متساهلة (نعطي اللاعب الفائدة عند أي شك/فشل)
_LENIENT_DEFAULT = {"accept": True, "source": "lenient_default"}


def _get_model():
    """يحمّل Gemini (باختيار نموذج متاح تلقائياً). None بأمان لو غير متاح.

    يطابق نمط _load_gemini() في ai_enrichment.py:
      - يحاول load_gemini_model() أولاً (المسار الطبيعي داخل التطبيق).
      - لو فشل الـ import (سياق خارجي أو خطأ)، يرجع لطريقة مباشرة
        مع نفس قائمة النماذج المفضّلة من gemini_model.py.
      - أي فشل ينتهي بـ None بأمان (lenient fallback في judge_answer).
    """
    # المسار الأساسي: نفس gemini_model.py الذي يستخدمه ai_enrichment
    try:
        from app.infrastructure.gemini_model import load_gemini_model
        return load_gemini_model()
    except ImportError:
        pass
    except Exception:
        return None

    # Fallback مباشر (نفس ترتيب _PREFERRED في gemini_model.py)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        for name in (
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
        ):
            try:
                m = genai.GenerativeModel(name)
                if m.generate_content("ping"):
                    return m
            except Exception:
                continue
    except Exception:
        pass
    return None


_JUDGE_PROMPT = """أنت حكم لإجابات لعبة معرفية عربية. كن متساهلاً مع الأخطاء الإملائية.
السؤال: {question}
الإجابة الصحيحة: {correct}
إجابة اللاعب: {player}

هل إجابة اللاعب صحيحة (نفس المعنى/المقصود رغم اختلاف الكتابة)؟
أجب بكلمة واحدة فقط: "نعم" أو "لا".
"""


async def judge_answer(question_text, correct_answer, player_answer, timeout=2.0):
    """يحكم على إجابة حدّية. يرجع dict: {accept: bool, source: str}.

     يضمن عدم تجاوز timeout (افتراضي 2s). عند أي تأخير/فشل  lenient (accept).
    """
    model = _get_model()
    if model is None:
        # لا AI متاح  متساهل (لا نعاقب اللاعب على غياب الإعداد)
        return dict(_LENIENT_DEFAULT)

    prompt = _JUDGE_PROMPT.format(
        question=question_text, correct=correct_answer, player=player_answer
    )

    async def _call():
        # نشغّل الاستدعاء المتزامن في thread حتى لا يحجب event loop
        def _sync():
            resp = model.generate_content(prompt)
            return (resp.text or "").strip()
        return await asyncio.to_thread(_sync)

    try:
        # timeout صارم — لا ننتظر أبداً أكثر منه
        text = await asyncio.wait_for(_call(), timeout=timeout)
        verdict = "نعم" in text or "صحيح" in text or text.lower().startswith("yes")
        return {"accept": bool(verdict), "source": "ai_judge"}
    except asyncio.TimeoutError:
        # تجاوز الوقت  متساهل (الأهم: لا نُبطئ اللعبة)
        return {"accept": True, "source": "ai_timeout_lenient"}
    except Exception:
        # أي خطأ آخر  متساهل
        return {"accept": True, "source": "ai_error_lenient"}


def should_use_judge(verdict):
    """هل نحتاج AI Judge لهذه الحالة؟ فقط للحالات الحدّية 'maybe'."""
    return verdict == "maybe"
