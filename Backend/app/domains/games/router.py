"""
 API مسيرة لاعب — قائمة شعارات الأندية (للتحميل المسبق في اللوبي)

الفكرة (تحسين الأداء):
  اللوبي يجلب قائمة الشعارات ويحمّلها مسبقاً (Image preload)  كاش المتصفح
   داخل اللعبة تظهر الشعارات فوراً بلا انتظار شبكة.
"""
import json
import os as _os
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.infrastructure.database import get_db
from app.domains.games.models import CareerPlayer

router = APIRouter()

# كاش بسيط في الذاكرة (يتجدد كل 10 دقائق) — القائمة لا تتغير إلا مع الاستيراد
_cache = {"logos": None, "ts": 0}
_CACHE_TTL = 600


@router.get("/logos")
async def get_club_logos(db: Session = Depends(get_db)):
    """قائمة أسماء ملفات شعارات الأندية المستخدمة في اللعبة (للتحميل المسبق)."""
    import time
    if _cache["logos"] is not None and (time.time() - _cache["ts"]) < _CACHE_TTL:
        return {"logos": _cache["logos"]}

    logos = set()
    rows = db.query(CareerPlayer.clubs).filter(CareerPlayer.active == True).all()
    for (clubs_raw,) in rows:
        if not clubs_raw:
            continue
        try:
            for club in json.loads(clubs_raw):
                if club.get("logo"):
                    logos.add(club["logo"])
        except Exception:
            continue

    result = sorted(logos)
    _cache["logos"] = result
    _cache["ts"] = time.time()
    return {"logos": result}


# ============================================================
#  🩹 تصحيح مؤقت للشعارات القديمة (اسم ملف بدل رابط) — لمرة واحدة
# ------------------------------------------------------------
# محمي بمفتاح سرّي (ADMIN_BACKFILL_SECRET بمتغيرات بيئة Azure) لا بحساب
# مستخدم — لا أحد (المطوّر أو غيره) يملك اتصالاً مباشراً بقاعدة البيانات؛
# التطبيق نفسه فقط من يلمسها، بنفس الاتصال الذي يستخدمه لكل طلب عادي.
# يُحذف هذا القسم بعد إتمام التصحيح لمرة واحدة.
# ============================================================
_backfill_state = {"running": False, "checked": 0, "fixed": 0,
                    "total": 0, "done": False, "error": None}


def _check_admin_secret(request: Request):
    secret = _os.environ.get("ADMIN_BACKFILL_SECRET")
    if not secret or request.headers.get("X-Admin-Secret") != secret:
        raise HTTPException(status_code=403, detail="ممنوع")


async def _run_backfill(known_good_filenames):
    from scripts.wikidata_import import backfill_broken_logos

    def _progress(checked, fixed, total):
        _backfill_state.update(checked=checked, fixed=fixed, total=total)

    _backfill_state.update(running=True, done=False, error=None,
                            checked=0, fixed=0, total=0)
    try:
        result = await asyncio.to_thread(
            backfill_broken_logos, known_good_filenames, print, _progress)
        _backfill_state.update(result)
    except Exception as e:
        _backfill_state["error"] = str(e)
    finally:
        _backfill_state["running"] = False
        _backfill_state["done"] = True


@router.post("/admin/backfill-logos")
async def admin_backfill_logos(request: Request):
    """يبدأ التصحيح بالخلفية (لا ننتظره هنا — قد يأخذ عشرات الدقائق).
    تابع التقدّم عبر GET لنفس الرابط."""
    _check_admin_secret(request)
    if _backfill_state["running"]:
        return {"message": "التصحيح شغّال أصلاً", "state": _backfill_state}
    try:
        body = await request.json()
    except Exception:
        body = {}
    known_good = body.get("known_good_filenames") or []
    asyncio.create_task(_run_backfill(known_good))
    return {"message": "بدأ التصحيح بالخلفية — تابع الحالة بنفس الرابط (GET)"}


@router.get("/admin/backfill-logos")
async def admin_backfill_logos_status(request: Request):
    _check_admin_secret(request)
    return _backfill_state
