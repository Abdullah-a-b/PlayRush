"""
 AI Enrichment — توليد answers_accepted مسبقاً (offline)

الغرض: حلّ بطء الـ AI Judge اللحظي. بدل استدعاء AI أثناء اللعب (1-3 ثواني تأخير)،
نولّد قائمة الإجابات المقبولة لكل سؤال **مرة واحدة offline** ونخزّنها في
extra_data. أثناء اللعب: مقارنة فورية مع القائمة الجاهزة = صفر تأخير.

حسب وثيقة PlayRush (ص4-6): "AI Enrichment يقلل الحاجة لـ AI real-time بـ 70%".

التشغيل:
    python scripts/ai_enrichment.py            # كل الأسئلة بلا accepted
    python scripts/ai_enrichment.py --game huroof --limit 100
    python scripts/ai_enrichment.py --dry-run  # معاينة بلا حفظ

المتطلبات:
    GEMINI_API_KEY في البيئة (.env). بدونه: السكربت يشرح ويتوقف بأمان.

ملاحظة: يستخدم Gemini Free Tier (1500/يوم). grounding على إجابة السؤال
الموجودة (لا يخترع حقائق — يولّد صيغاً بديلة للإجابة المعروفة فقط).
"""
import os
import sys
import json
import time
import argparse

# نضيف جذر المشروع للمسار
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.infrastructure.database import SessionLocal
from app.domains.games.models import Question


PROMPT_TEMPLATE = """أنت مساعد لتدقيق إجابات لعبة معرفية عربية.
السؤال: {question}
الإجابة الصحيحة المعتمدة: {answer}

مهمتك: أعطني قائمة بكل الصيغ البديلة المقبولة لهذه الإجابة الصحيحة فقط
(اختلافات إملائية شائعة، مرادفات، تشكيل، همزات، صيغ مكتوبة بطرق مختلفة،
نقل/ترجمة شائعة). لا تخترع إجابات جديدة — فقط صيغ بديلة لنفس الإجابة المعروفة.

أرجِع النتيجة كمصفوفة JSON من نصوص فقط، بلا أي شرح. مثال:
["القاهرة", "القاهره", "مصر القاهرة"]
"""


def _load_gemini():
    """يحمّل عميل Gemini (باختيار نموذج متاح تلقائياً). None بأمان."""
    try:
        from app.infrastructure.gemini_model import load_gemini_model
        return load_gemini_model()
    except ImportError:
        # لو استُدعي السكربت خارج سياق التطبيق، نرجع لطريقة مباشرة
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return None
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            for name in ("gemini-flash-latest", "gemini-2.5-flash",
                         "gemini-2.0-flash"):
                try:
                    return genai.GenerativeModel(name)
                except Exception:
                    continue
            return None
        except Exception as e:
            print(f" تعذّر تهيئة Gemini: {e}")
            return None


def _enrich_one(model, question_text, answer):
    """يولّد صيغ بديلة لإجابة واحدة. يرجع list (فارغة عند الفشل)."""
    prompt = PROMPT_TEMPLATE.format(question=question_text, answer=answer)
    try:
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        # ننظّف أي علامات markdown
        text = text.replace("```json", "").replace("```", "").strip()
        variants = json.loads(text)
        if isinstance(variants, list):
            # نتأكد أنها نصوص + نضيف الإجابة الأصلية + نزيل التكرار
            clean = {str(v).strip() for v in variants if str(v).strip()}
            clean.add(answer.strip())
            return sorted(clean)
    except json.JSONDecodeError:
        print(f"    رد غير صالح JSON للسؤال (تخطّي)")
    except Exception as e:
        print(f"    خطأ توليد: {e}")
    return [answer.strip()]


def _get_existing_accepted(q):
    """يقرأ accepted_answers الموجودة من extra_data (إن وُجدت)."""
    if not q.extra_data:
        return None
    try:
        data = json.loads(q.extra_data)
        return data.get("accepted_answers")
    except Exception:
        return None


def _save_accepted(q, accepted):
    """يحفظ accepted_answers في extra_data (يحافظ على باقي البيانات)."""
    data = {}
    if q.extra_data:
        try:
            data = json.loads(q.extra_data)
        except Exception:
            data = {}
    data["accepted_answers"] = accepted
    q.extra_data = json.dumps(data, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="AI Enrichment لإجابات الأسئلة")
    parser.add_argument("--game", default=None, help="حصر على لعبة (مثل huroof)")
    parser.add_argument("--limit", type=int, default=None, help="حد أقصى للأسئلة")
    parser.add_argument("--dry-run", action="store_true", help="معاينة بلا حفظ")
    parser.add_argument("--force", action="store_true", help="إعادة توليد حتى للموجود")
    parser.add_argument("--delay", type=float, default=1.0, help="ثواني بين الطلبات")
    args = parser.parse_args()

    model = _load_gemini()
    if model is None:
        print("=" * 55)
        print(" GEMINI_API_KEY غير موجود في البيئة.")
        print("=" * 55)
        print("لتشغيل الإثراء:")
        print("  1. احصل على مفتاح مجاني: https://aistudio.google.com/apikey")
        print("  2. أضِفه في .env:  GEMINI_API_KEY=مفتاحك")
        print("  3. ثبّت المكتبة:   pip install google-generativeai")
        print("  4. أعد التشغيل")
        print()
        print(" بدون الإثراء، التحكيم يعمل بطبقات NormalizeFuzzyToken")
        print("   (يحل ~80% من الحالات بلا AI).")
        return

    db = SessionLocal()
    try:
        query = db.query(Question)
        if args.game:
            query = query.filter(Question.game_mode == args.game)
        questions = query.all()
        if args.limit:
            questions = questions[: args.limit]

        total = len(questions)
        if total == 0:
            print(" لا توجد أسئلة في القاعدة. املأ الأسئلة أولاً.")
            return

        print(f" {total} سؤال للمعالجة"
              f"{' (لعبة ' + args.game + ')' if args.game else ''}")
        print(f"{' معاينة فقط' if args.dry_run else ' حفظ مُفعّل'}\n")

        enriched = skipped = failed = 0
        for i, q in enumerate(questions, 1):
            existing = _get_existing_accepted(q)
            if existing and not args.force:
                skipped += 1
                continue

            print(f"[{i}/{total}] {(q.question_text or '')[:45]}...")
            accepted = _enrich_one(model, q.question_text, q.correct_answer)
            if len(accepted) <= 1:
                failed += 1
            else:
                enriched += 1
                print(f"    {len(accepted)} صيغة: {accepted[:4]}...")

            if not args.dry_run:
                _save_accepted(q, accepted)
                db.commit()

            time.sleep(args.delay)  # احترام حدود Free Tier

        print(f"\n{'=' * 40}")
        print(f" مُثرى: {enriched} | ⏭ متخطّى: {skipped} |  فشل: {failed}")
        if args.dry_run:
            print(" (معاينة — لم يُحفظ شيء)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
