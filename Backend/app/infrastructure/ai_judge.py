"""حكم اختياري لإجابات غير محسومة.

الأسماء والحقائق ذات البدائل المحددة تُطابق محليًا. عند استدعاء الحكم، تشمل
المهلة تهيئة النموذج وطلبه، وينفذ عاملان فقط الطلبات المتزامنة. غياب الخدمة
أو الرد غير المطابق لا يمنح نقاطًا، ولا تُفسر الجمل المنفية كموافقة.
"""
import os
import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor

_JUDGE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="answer-judge")


# نتيجة آمنة عند تعذر التحقق
_LENIENT_DEFAULT = {"accept": False, "source": "unavailable"}


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

    # Fallback مباشر: نستخدم list_models بدل ping لكل نموذج (أسرع وأوفر)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        _PREFERRED = [
            "gemini-3.5-flash-lite",
            "gemini-flash-latest",
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.0-flash-001",
            "gemini-1.5-flash-latest",
            "gemini-1.5-flash",
        ]

        # نحاول list_models أولاً (لا يكلّف quota)
        try:
            available = set()
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    available.add(m.name.split("/")[-1])
            for name in _PREFERRED:
                if name in available:
                    return genai.GenerativeModel(name)
            # أي flash متاح كملاذ أخير
            flash = sorted(n for n in available if "flash" in n)
            if flash:
                return genai.GenerativeModel(flash[0])
            if available:
                return genai.GenerativeModel(sorted(available)[0])
        except Exception:
            pass

        # fallback نهائي: جرّب كل اسم مفضّل بطلب ping واحد
        for name in _PREFERRED:
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
    """يحكم على إجابة حدّية ضمن مهلة تشمل التهيئة، ويرفض عند تعذر التحقق.
    """
    def _sync_call():
        model = _get_model()
        if model is None:
            return {"accept": False, "source": "unavailable"}
        prompt = _JUDGE_PROMPT.format(question=question_text, correct=correct_answer, player=player_answer)
        response = model.generate_content(prompt)
        text = (response.text or '').strip().lower().strip(' .!؟')
        return {"accept": text in {'نعم', 'yes'}, "source": "ai_judge"}
    try:
        task = asyncio.get_running_loop().run_in_executor(_JUDGE_EXECUTOR, _sync_call)
        return await asyncio.wait_for(task, timeout=timeout)
    except asyncio.TimeoutError:
        return {"accept": False, "source": "timeout"}
    except Exception:
        return {"accept": False, "source": "error"}


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
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
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

    # تحقّق أن الإجابة تبدأ بالحرف المطلوب (بعد إزالة "ال" التعريف).
    # نطبّع الحروف المتشابهة (أ/إ/آ→ا، ة→ه، ى→ي) قبل المقارنة.
    def _norm(ch):
        return {'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ة': 'ه', 'ى': 'ي', 'ی': 'ي'}.get(ch, ch)

    bare = answer[2:] if answer.startswith("ال") else answer
    if not bare or _norm(bare[0]) != _norm(letter):
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
