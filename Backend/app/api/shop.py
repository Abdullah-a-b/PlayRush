from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import User, get_db
from app.core.security import get_current_user
from app.core.limiter import limiter

router = APIRouter()


@router.post("/exchange")
@limiter.limit("10/minute")  # 🛡️ rate limit
async def exchange_coins_for_gems(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """⛔ مُعطّل: تحويل العملات محذوف نهائياً (مبدأ فصل العملتين — منع Pay-to-Win).
    الجواهر تُكتسب فقط من نظام المهام/التصنيف المستقبلي، لا تُشترى ولا تُحوّل.
    راجع وثيقة الاقتصاد §4 (فصل العملات)."""
    raise HTTPException(
        status_code=403,
        detail="تحويل العملات غير متاح. الكوينز والجواهر منفصلتان تماماً."
    )
