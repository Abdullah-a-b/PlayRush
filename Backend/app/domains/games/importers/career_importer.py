"""
 التجديد التلقائي للاعبي "مسيرة لاعب" — خلفية المنصة

يعمل دورياً (افتراضياً كل 7 أيام) بلا أي تدخل يدوي:
  - كل دورة يجلب دفعة جديدة (offset متقدّم محفوظ في ملف حالة)
     القاعدة تتوسّع تدريجياً نحو آلاف اللاعبين المشهورين تاريخياً.
  - أول تشغيل: يبدأ بعد 3 دقائق من إقلاع الخادم (لا يزاحم الإقلاع).
  - الاستيراد يعمل في thread منفصل (لا يحجب اللعب أبداً).

الضبط عبر البيئة (.env):
  CAREER_AUTO_IMPORT=1            (افتراضي مفعّل — 0 للتعطيل)
  CAREER_IMPORT_INTERVAL_DAYS=7
  CAREER_IMPORT_BATCH=150
"""
import os
import json
import time
import asyncio

from app.core.paths import DATA_DIR

STATE_FILE = str(DATA_DIR / "career_import_state.json")


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"offset": 0, "last_run": 0}


def _save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def _enabled():
    return os.environ.get("CAREER_AUTO_IMPORT", "1").strip() != "0"


def _interval_seconds():
    try:
        days = float(os.environ.get("CAREER_IMPORT_INTERVAL_DAYS", "7"))
    except ValueError:
        days = 7.0
    return max(0.5, days) * 86400


def _batch_size():
    try:
        return max(25, int(os.environ.get("CAREER_IMPORT_BATCH", "150")))
    except ValueError:
        return 150


async def career_auto_import_loop():
    """حلقة الخلفية — تُطلق من lifespan في main.py."""
    if not _enabled():
        print(" [auto-import] معطّل (CAREER_AUTO_IMPORT=0)")
        return

    await asyncio.sleep(180)  # لا نزاحم إقلاع الخادم

    while True:
        state = _load_state()
        due = (time.time() - state.get("last_run", 0)) >= _interval_seconds()
        if due:
            batch = _batch_size()
            offset = state.get("offset", 0)
            print(f" [auto-import] بدء دورة تجديد (offset={offset}, batch={batch})")
            try:
                from scripts.wikidata_import import run_import
                result = await asyncio.to_thread(
                    run_import, batch, 45, offset, False, False, False, False,
                    lambda m: print(f"[auto-import] {m}"))
                # لو الدفعة رجعت لاعبين  نتقدّم؛ لو فرغت  نعود للبداية (تحديث)
                if result.get("fetched", 0) > 0:
                    state["offset"] = offset + batch
                else:
                    state["offset"] = 0
                state["last_run"] = time.time()
                _save_state(state)
                print(f" [auto-import] اكتملت: +{result.get('added', 0)} لاعب "
                      f"(الإجمالي {result.get('total', '?')})")
            except Exception as e:
                print(f" [auto-import] فشل (سيُعاد لاحقاً): {e}")
                # لا نحدّث last_run بالكامل — نعيد بعد 6 ساعات
                state["last_run"] = time.time() - _interval_seconds() + 6 * 3600
                _save_state(state)
        await asyncio.sleep(3600)  # فحص كل ساعة
