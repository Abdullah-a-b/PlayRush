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


def _run_once():
    from app.core.import_support import import_lock, read_json, atomic_json, due, record_result
    with import_lock(STATE_FILE) as acquired:
        if not acquired: return {"status": "busy"}
        state = read_json(STATE_FILE, {})
        sources = state.setdefault("sources", {})
        results = {}; failed = []
        for lane in ("refresh", "discover"):
            source = sources.setdefault(lane, {})
            from app.core.import_support import positive_days
            interval = positive_days("CAREER_REFRESH_INTERVAL_DAYS", 1) if lane == "refresh" else _interval_seconds()
            if not due(source, interval): continue
            try:
                from scripts.wikidata_import import run_import
                offset, batch = source.get("offset", 0), _batch_size()
                if lane == "refresh":
                    from app.infrastructure.database import SessionLocal
                    from app.domains.games.models import CareerPlayer
                    db = SessionLocal()
                    try:
                        qids = [q for (q,) in db.query(CareerPlayer.wikidata_id).filter(CareerPlayer.wikidata_id.isnot(None)).order_by(CareerPlayer.id).offset(offset).limit(batch).all()]
                    finally: db.close()
                    if not qids:
                        source["offset"] = 0
                        result = {"fetched": 0, "added": 0, "updated": 0}
                    else:
                        result = run_import(refresh=True, player_qids=qids, log=lambda m: print(f" [auto-import] {m}"))
                else:
                    result = run_import(limit=batch, min_sitelinks=45, offset=offset, refresh=True, log=lambda m: print(f" [auto-import] {m}"))
                source["offset"] = offset + result.get("fetched", 0) if result.get("fetched", 0) >= batch else 0
                source["last_run"] = time.time();source.pop("retry_after", None)
                results[lane] = result
            except Exception as exc:
                source["retry_after"] = time.time() + 3600
                failed.append(lane)
                print(f" [auto-import] فشل {lane}: {type(exc).__name__}")
        if not results and not failed: return {"status": "not_due"}
        result = {"status": "partial" if failed else "success", "lanes": results, "failed_sources": failed}
        atomic_json(STATE_FILE, record_result(state, result))
        print(f" [auto-import] {result}")
        return result


async def career_auto_import_loop():
    from app.core.import_support import read_json, due
    if not _enabled(): return
    await asyncio.sleep(180)
    while True:
        try:
            await asyncio.to_thread(_run_once)
        except Exception as exc:
            print(f" [auto-import] خطأ الحالة/الحفظ: {type(exc).__name__}")
        await asyncio.sleep(300)
