"""
🔡 التجديد التلقائي لأسئلة "حروف" — خلفية المنصة

يعمل دورياً (افتراضياً كل 7 أيام) بلا تدخل:
  - يولّد أسئلة حقائق ثابتة من Wikidata (دول/عواصم/عملات/عناصر)
    بقوالب حتمية أحادية العلاقة — صفر هلوسة، الحرف يُشتق من الإجابة.
  - أول تشغيل بعد 7 دقائق من الإقلاع (متأخر عن المسيرة 3د والبنك 5د —
    لا تزاحم على Wikidata).
  - في thread منفصل + يصفّر كاش أسئلة حروف بعد النجاح
    (تحديث حيّ بلا إعادة تشغيل ولا انتظار TTL).

الضبط عبر البيئة (.env):
  HUROOF_AUTO_IMPORT=1              (افتراضي مفعّل — 0 للتعطيل)
  HUROOF_IMPORT_INTERVAL_DAYS=7
"""
import os
import json
import time
import asyncio

STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "data", "huroof_import_state.json")


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
        print(f"⚠️ [huroof-importer] حفظ الحالة: {e}")


def _run_once():
    """توليد دفعة (thread منفصل)."""
    try:
        import sys
        scripts = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from huroof_questions_import import run_import
        n = run_import()
        if n:
            # 🔄 تحديث حيّ: نصفّر كاش أسئلة حروف — الجديد يدخل اللعب فوراً
            try:
                from app.games.huroof import events as huroof_events
                huroof_events._HUROOF_QCACHE['ts'] = 0.0
                print("🔡 [huroof-importer] كاش الأسئلة صُفّر — الجديد يُحمّل فوراً")
            except Exception:
                pass
        return n
    except Exception as e:
        print(f"⚠️ [huroof-importer] فشل التوليد (يُعاد الدورة القادمة): {e}")
        return 0


async def huroof_auto_import_loop():
    if os.getenv("HUROOF_AUTO_IMPORT", "1") != "1":
        print("🔡 [huroof-importer] معطّل (HUROOF_AUTO_IMPORT=0)")
        return
    interval_days = float(os.getenv("HUROOF_IMPORT_INTERVAL_DAYS", "7"))
    interval = interval_days * 24 * 3600
    await asyncio.sleep(420)  # بعد 7 دقائق من الإقلاع
    while True:
        st = _load_state()
        due = (time.time() - st.get("last_run", 0)) >= interval
        if due:
            print("🔡 [huroof-importer] بدء توليد دوري…")
            n = await asyncio.to_thread(_run_once)
            if n:
                st["last_run"] = time.time()
                _save_state(st)
                print(f"🔡 [huroof-importer] اكتمل: {n} سؤال جديد")
        await asyncio.sleep(6 * 3600)  # فحص كل 6 ساعات
