"""استيراد دوري بقفل وحالة دائمة وتقارير تفصل الجديد عن المحدّث."""
import asyncio
import time
import os
from app.core.paths import DATA_DIR
from app.core.import_support import atomic_json, read_json, import_lock, positive_days, due, record_result
STATE_FILE = str(DATA_DIR / "bank_import_state.json")


def _run_once():
    with import_lock(STATE_FILE) as acquired:
        if not acquired:
            return {"status": "busy"}
        state = read_json(STATE_FILE, {})
        try:
            from scripts.bank_questions_import import run_import
            result = run_import()
            # دعم أي استدعاء قديم يرجع عدداً، بما فيه الصفر الناجح.
            if isinstance(result, int):
                result = {"status": "success", "added": result}
            if result.get("status") not in ("success", "partial"):
                raise RuntimeError("المصدر لم يكتمل")
            if result.get("added", 0) or result.get("updated", 0) or result.get("deactivated", 0):
                from app.domains.games.bank import events as bank_events
                bank_events._QUESTIONS = None
        except Exception as exc:
            result = {"status": "error", "error": type(exc).__name__}
            print(f" [bank-importer] فشلت الدورة؛ إعادة خلال ساعة: {type(exc).__name__}")
        atomic_json(STATE_FILE, record_result(state, result))
        print(f" [bank-importer] {result}")
        return result


async def bank_auto_import_loop():
    if os.getenv("BANK_AUTO_IMPORT", "1").strip() == "0":
        return
    await asyncio.sleep(300)
    while True:
        try:
            state = read_json(STATE_FILE, {})
            if state.get("schema_version") != 2 or due(state, positive_days("BANK_IMPORT_INTERVAL_DAYS")):
                await asyncio.to_thread(_run_once)
        except Exception as exc:
            print(f" [bank-importer] خطأ حالة: {type(exc).__name__}")
        await asyncio.sleep(300)
