"""
🏦 التجديد التلقائي لأسئلة البنك — خلفية المنصة

يعمل دورياً (افتراضياً كل 7 أيام) بلا تدخل:
  - يولّد أسئلة حقائق ثابتة من Wikidata (عواصم/عملات/قارات) بقوالب حتمية.
  - أول تشغيل بعد 5 دقائق من الإقلاع (لا يزاحم).
  - في thread منفصل + يصفّر كاش الأسئلة بعد النجاح (تحديث حيّ بلا إعادة تشغيل).

الضبط عبر البيئة (.env):
  BANK_AUTO_IMPORT=1              (افتراضي مفعّل — 0 للتعطيل)
  BANK_IMPORT_INTERVAL_DAYS=7
"""
import os
import json
import time
import asyncio

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "data", "bank_import_state.json")


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_run": 0}


def _save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except Exception as e:
        print(f"⚠️ [bank-importer] حفظ الحالة: {e}")


def _run_once():
    """توليد دفعة (thread منفصل)."""
    try:
        import sys
        scripts = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from bank_questions_import import run_import
        n = run_import()
        if n:
            # 🔄 تحديث حيّ: نصفّر كاش الأسئلة ليُعاد تحميلها بالدمج الجديد
            try:
                from app.games.bank import events as bank_events
                bank_events._QUESTIONS = None
                print("🏦 [bank-importer] كاش الأسئلة صُفّر — الجديد يُحمّل فوراً")
            except Exception:
                pass
        return n
    except Exception as e:
        print(f"⚠️ [bank-importer] فشل التوليد (يُعاد الدورة القادمة): {e}")
        return 0


async def bank_auto_import_loop():
    if os.getenv("BANK_AUTO_IMPORT", "1") != "1":
        print("🏦 [bank-importer] معطّل (BANK_AUTO_IMPORT=0)")
        return
    interval_days = float(os.getenv("BANK_IMPORT_INTERVAL_DAYS", "7"))
    interval = interval_days * 24 * 3600
    await asyncio.sleep(300)  # بعد 5 دقائق من الإقلاع
    while True:
        st = _load_state()
        due = (time.time() - st.get("last_run", 0)) >= interval
        if due:
            print("🏦 [bank-importer] بدء توليد دوري…")
            n = await asyncio.to_thread(_run_once)
            if n:
                st["last_run"] = time.time()
                _save_state(st)
                print(f"🏦 [bank-importer] اكتمل: {n} سؤال مولّد")
        await asyncio.sleep(6 * 3600)  # فحص كل 6 ساعات
