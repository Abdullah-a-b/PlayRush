"""
⚽ API مسيرة لاعب — قائمة شعارات الأندية (للتحميل المسبق في اللوبي)

الفكرة (تحسين الأداء):
  اللوبي يجلب قائمة الشعارات ويحمّلها مسبقاً (Image preload) → كاش المتصفح
  → داخل اللعبة تظهر الشعارات فوراً بلا انتظار شبكة.
"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db, CareerPlayer

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
