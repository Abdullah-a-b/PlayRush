"""استيراد دوري بقفل وحالة دائمة وتقارير تفصل الجديد عن المحدّث."""
import asyncio
import time
import os
from app.core.paths import DATA_DIR
from app.core.import_support import atomic_json, read_json, import_lock, positive_days, due, record_result
STATE_FILE = str(DATA_DIR / "huroof_import_state.json")
IMPORT_REVISION = 'huroof-quality-20261120'


def sync_curated_questions():
    """توسعات الحزمة تصل فور النشر، لا تنتظر سبعة أيام أو خدمة خارجية."""
    import hashlib
    import json
    from app.core.paths import SEED_DATA_DIR
    from scripts.huroof_questions_import import build_curated_questions, save_to_db
    questions = build_curated_questions()
    version = hashlib.sha256(json.dumps(questions, ensure_ascii=False, sort_keys=True).encode()
                             + (SEED_DATA_DIR / 'huroof_review_rules.json').read_bytes()).hexdigest()
    state_file = DATA_DIR / 'huroof_curated_state.json'
    with import_lock(STATE_FILE) as acquired:
        if not acquired:
            return {'status': 'busy'}
        if read_json(state_file, {}).get('version') == version:
            return {'status': 'unchanged'}
        # هذه قائمة جزئية؛ بعض أسئلة القرآن القديمة تحمل هوية curated أيضاً.
        # تعطيل الغائبين يخص الاستيراد الكامل فقط، لا مزامنة التوسعة المحلية.
        result = save_to_db(questions)
        atomic_json(state_file, {'version': version, 'synced_at': time.time(), 'result': result})
        return {'status': 'success', **result}


def _run_once():
    with import_lock(STATE_FILE) as acquired:
        if not acquired:
            return {"status": "busy"}
        state = read_json(STATE_FILE, {})
        try:
            from scripts.huroof_questions_import import run_import
            result = run_import()
            # دعم أي استدعاء قديم يرجع عدداً، بما فيه الصفر الناجح.
            if isinstance(result, int):
                result = {"status": "success", "added": result}
            if result.get("status") not in ("success", "partial"):
                raise RuntimeError("المصدر لم يكتمل")
            if result.get("added", 0) or result.get("updated", 0) or result.get("deactivated", 0):
                from app.domains.games.huroof import events as huroof_events
                huroof_events._HUROOF_QCACHE['ts'] = 0.0
        except Exception as exc:
            result = {"status": "error", "error": type(exc).__name__}
            print(f" [huroof-importer] فشلت الدورة؛ إعادة خلال ساعة: {type(exc).__name__}")
        state = record_result(state, result)
        if result.get('status') == 'success':
            state['import_revision'] = IMPORT_REVISION
        atomic_json(STATE_FILE, state)
        print(f" [huroof-importer] {result}")
        return result


async def huroof_auto_import_loop():
    # مستقل عن زر تعطيل الاستيراد الخارجي وعن موعده؛ يعاد حتى تنجح المزامنة.
    while True:
        try:
            result = await asyncio.to_thread(sync_curated_questions)
            if result.get('status') != 'busy':
                from app.domains.games.huroof import events as huroof_events
                huroof_events._HUROOF_QCACHE['ts'] = 0.0
                break
        except Exception as exc:
            print(f" [huroof-curated] إعادة مزامنة الأسئلة المحلية: {type(exc).__name__}")
        await asyncio.sleep(30)
    if os.getenv("HUROOF_AUTO_IMPORT", "1").strip() == "0":
        return
    await asyncio.sleep(420)
    while True:
        try:
            state = read_json(STATE_FILE, {})
            revised = state.get('import_revision') != IMPORT_REVISION and not state.get('retry_after')
            if revised or due(state, positive_days("HUROOF_IMPORT_INTERVAL_DAYS")):
                await asyncio.to_thread(_run_once)
        except Exception as exc:
            print(f" [huroof-importer] خطأ حالة: {type(exc).__name__}")
        await asyncio.sleep(300)
