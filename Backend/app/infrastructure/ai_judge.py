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


# ============================================================
#  توليد أسئلة حروف عبر الذكاء الاصطناعي
# ------------------------------------------------------------
#  يُستدعى حين تنفد أسئلة القاعدة لحرف معيّن، فيولّد سؤالاً جديداً
#  إجابته تبدأ بذلك الحرف. يعيد None بأمان عند أي فشل (فيتراجع
#  النظام للسلوك الاحتياطي).
# ============================================================
import json as _json
import re as _re2

_GEN_PROMPT = """أنت مولّد أسئلة للعبة معرفية عربية اسمها "خلية الحروف".
المطلوب: سؤال معلومات عامة إجابته كلمة أو كلمتان تبدأ بحرف "{letter}".

قواعد صارمة:
- الإجابة يجب أن تبدأ فعلاً بحرف "{letter}".
- سؤال واضح له إجابة واحدة قاطعة (لا رأي، لا غموض).
- تنويع المجالات (جغرافيا، علوم، تاريخ، رياضة، دين، ثقافة عامة).
- تجنّب الأسئلة السهلة جداً أو الغامضة جداً.

أعد النتيجة بصيغة JSON فقط بلا أي نص إضافي:
{{"question": "نص السؤال", "answer": "الإجابة", "category": "المجال", "difficulty": "easy أو medium أو hard"}}
"""


def _extract_json(text):
    """يستخرج أول كائن JSON من نصّ قد يحوي زيادات."""
    if not text:
        return None
    # نزيل أسوار الكود إن وُجدت
    text = text.replace("```json", "").replace("```", "").strip()
    m = _re2.search(r'\{.*\}', text, _re2.DOTALL)
    if not m:
        return None
    try:
        return _json.loads(m.group(0))
    except Exception:
        return None


async def generate_huroof_question(letter, timeout=8.0):
    """يولّد سؤالاً جديداً لحرف معيّن. None عند أي فشل.

    نتحقّق أن الإجابة تبدأ بالحرف المطلوب قبل القبول — حتى لا نُدخل
    سؤالاً لا ينتمي للحرف.
    """
    model = _get_model()
    if model is None:
        return None

    letter = (letter or "").strip()
    if not letter:
        return None

    prompt = _GEN_PROMPT.format(letter=letter)

    async def _call():
        def _sync():
            resp = model.generate_content(prompt)
            return (resp.text or "").strip()
        return await asyncio.to_thread(_sync)

    try:
        text = await asyncio.wait_for(_call(), timeout=timeout)
    except Exception:
        return None

    data = _extract_json(text)
    if not data or not data.get("question") or not data.get("answer"):
        return None

    answer = str(data["answer"]).strip()

    # تحقّق أن الإجابة تبدأ بالحرف المطلوب (بعد إزالة "ال" التعريف)
    bare = answer[2:] if answer.startswith("ال") else answer
    if not bare or bare[0] != letter:
        return None

    return {
        "question": str(data["question"]).strip(),
        "answer": answer,
        "category": str(data.get("category", "مُولّد")).strip() or "مُولّد",
        "difficulty": data.get("difficulty", "medium")
            if data.get("difficulty") in ("easy", "medium", "hard") else "medium",
        "accepted_answers": [],
        "generated": True,
    }
