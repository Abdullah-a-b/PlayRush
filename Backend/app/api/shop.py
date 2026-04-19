from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, User
from app.core.security import get_current_user

router = APIRouter()

@router.post("/exchange")
async def exchange_coins_for_gems(current_user: User = Depends(get_current_user), db: Session = Depends(SessionLocal)):
    """1000 كوين = 5 جواهر"""
    COST = 1000
    REWARD = 5
    
    if (current_user.coins or 0) < COST:
        raise HTTPException(status_code=400, detail=f"تحتاج {COST} كوين للاستبدال")
        
    current_user.coins -= COST
    current_user.gems = (current_user.gems or 0) + REWARD
    db.commit()
    
    return {
        "success": True, 
        "coins": current_user.coins, 
        "gems": current_user.gems,
        "message": f"تم الاستبدال! حصلت على {REWARD} جواهر 💎"
    }