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
    db: Session = Depends(get_db),  # ✅ إصلاح: get_db بدل SessionLocal
):
    """1000 كوين = 5 جواهر"""
    COST = 1000
    REWARD = 5

    # ✅ إصلاح race condition: نقفل الصف قبل التعديل
    # SELECT ... FOR UPDATE — يمنع لاعب يبعت 10 طلبات متزامنة ويستفيد 10 مرات من نفس الـ coins
    user_locked = db.query(User).filter(User.id == current_user.id).with_for_update().first()
    if not user_locked:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    if (user_locked.coins or 0) < COST:
        raise HTTPException(status_code=400, detail=f"تحتاج {COST} كوين للاستبدال")

    user_locked.coins -= COST
    user_locked.gems = (user_locked.gems or 0) + REWARD
    db.commit()

    return {
        "success": True,
        "coins": user_locked.coins,
        "gems": user_locked.gems,
        "message": f"تم الاستبدال! حصلت على {REWARD} جواهر 💎"
    }
