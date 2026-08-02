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
# 🩹 مؤقّت: إعادة حساب difficulty لكل لاعبي career بالعتبات الجديدة
# (difficulty_for في wikidata_import.py). يُستخدم مرة واحدة فقط ثم يُحذف
# — نفس نمط باك-فيل الشعارات السابق. محمي بسر بيئة (ADMIN_BACKFILL_SECRET)
# ولا يحتاج أي صلاحية وصول لقاعدة البيانات من جهاز شخصي.
# ============================================================
_backfill_state = {"running": False, "done": 0, "total": 0, "result": None, "error": None}


def _check_admin_secret(request: Request):
    secret = _os.environ.get("ADMIN_BACKFILL_SECRET")
    if not secret:
        raise HTTPException(status_code=404)
    if request.headers.get("X-Admin-Secret") != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _run_backfill_difficulty():
    from scripts.wikidata_import import backfill_difficulty
    _backfill_state["running"] = True
    _backfill_state["error"] = None
    try:
        def _progress(done, total):
            _backfill_state["done"] = done
            _backfill_state["total"] = total
        result = backfill_difficulty(log=print, on_progress=_progress)
        _backfill_state["result"] = result
    except Exception as e:
        _backfill_state["error"] = str(e)
    finally:
        _backfill_state["running"] = False


@router.post("/admin/backfill-difficulty")
async def start_backfill_difficulty(request: Request):
    _check_admin_secret(request)
    if _backfill_state["running"]:
        return {"ok": False, "msg": "already running"}
    _backfill_state.update({"running": True, "done": 0, "total": 0, "result": None, "error": None})
    asyncio.create_task(asyncio.to_thread(_run_backfill_difficulty))
    return {"ok": True, "msg": "started"}


@router.get("/admin/backfill-difficulty")
async def get_backfill_difficulty_progress(request: Request):
    _check_admin_secret(request)
    return _backfill_state


# 🩹 مؤقّت: إعادة بناء أندية اللاعبين اللي فيهم شعار مفقود (فشلت كل
# مصادر الشعار وقت استيرادهم — راجع تعليق backfill_missing_club_logos).
_logos_backfill_state = {"running": False, "done": 0, "total": 0, "result": None, "error": None}


def _run_backfill_missing_logos():
    from scripts.wikidata_import import backfill_missing_club_logos
    _logos_backfill_state["running"] = True
    _logos_backfill_state["error"] = None
    try:
        def _progress(done, total):
            _logos_backfill_state["done"] = done
            _logos_backfill_state["total"] = total
        result = backfill_missing_club_logos(log=print, on_progress=_progress)
        _logos_backfill_state["result"] = result
    except Exception as e:
        _logos_backfill_state["error"] = str(e)
    finally:
        _logos_backfill_state["running"] = False


@router.post("/admin/backfill-missing-logos")
async def start_backfill_missing_logos(request: Request):
    _check_admin_secret(request)
    if _logos_backfill_state["running"]:
        return {"ok": False, "msg": "already running"}
    _logos_backfill_state.update({"running": True, "done": 0, "total": 0, "result": None, "error": None})
    asyncio.create_task(asyncio.to_thread(_run_backfill_missing_logos))
    return {"ok": True, "msg": "started"}


@router.get("/admin/backfill-missing-logos")
async def get_backfill_missing_logos_progress(request: Request):
    _check_admin_secret(request)
    return _logos_backfill_state


@router.get("/admin/find-club-logo")
async def find_club_logo(q: str, request: Request, db: Session = Depends(get_db)):
    """🩹 مؤقّت: تشخيص فقط (قراءة، بلا تعديل) — يبحث عن نادٍ باسمه ضمن بيانات
    career_players ويُرجع قيمة الشعار المخزّنة فعلياً في قاعدة الإنتاج، عشان
    نقارنها بالمتوقّع بدون أي وصول مباشر لقاعدة البيانات من جهاز شخصي."""
    _check_admin_secret(request)
    rows = db.query(CareerPlayer.name, CareerPlayer.clubs).filter(
        CareerPlayer.active == True).all()
    matches = []
    for name, clubs_raw in rows:
        if not clubs_raw:
            continue
        try:
            clubs = json.loads(clubs_raw)
        except Exception:
            continue
        for c in clubs:
            if q in (c.get("name") or ""):
                matches.append({"player": name, "club_name": c.get("name"),
                                 "logo": c.get("logo")})
        if len(matches) >= 30:
            break
    return {"query": q, "matches": matches}
