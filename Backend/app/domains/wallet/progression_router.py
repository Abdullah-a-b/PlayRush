from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.core.limiter import limiter
from app.infrastructure.database import get_db
from app.domains.users.models import User
from app.domains.wallet import ranking_service as RS
from app.domains.wallet import leaderboard_service as LB
from app.domains.wallet import quests_service as QS
from app.domains.wallet import pass_service as PS
from app.domains.wallet.period_keys import current_season

router = APIRouter()

VALID_GAMES = {"huroof", "bank", "career", "knowledge", "whoami"}


# ================= الرتب =================
@router.get("/rank/me")
@limiter.limit("60/minute")
async def my_ranks(request: Request, current_user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return {"season": current_season(), "ranks": RS.get_all_ranks(db, current_user.id)}


@router.get("/rank/{game_mode}")
@limiter.limit("60/minute")
async def game_rank(request: Request, game_mode: str,
                    current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if game_mode not in VALID_GAMES:
        return {"error": "لعبة غير معروفة"}
    return RS.get_rank_snapshot(db, current_user.id, game_mode)


# ================= الصدارة =================
@router.get("/leaderboard/{game_mode}")
@limiter.limit("30/minute")
async def game_leaderboard(request: Request, game_mode: str,
                           current_user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """قسما لوبي اللعبة: Ranked + Wins، مع موقع اللاعب."""
    if game_mode not in VALID_GAMES:
        return {"error": "لعبة غير معروفة"}
    return {
        "game_mode": game_mode,
        "ranked": LB.ranked_board(db, game_mode),
        "wins": LB.wins_board(db, game_mode),
        "me": LB.my_position(db, current_user.id, game_mode),
    }


@router.get("/leaderboard")
@limiter.limit("30/minute")
async def overall_leaderboard(request: Request,
                              current_user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    """صدارة categories العامة (متوسط Elo، ≥3 ألعاب)."""
    return {"season": current_season(), "global": LB.global_board(db)}


# ================= المهام =================
@router.get("/quests")
@limiter.limit("60/minute")
async def my_quests(request: Request, current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return {"quests": QS.get_quests(db, current_user.id)}


@router.post("/quests/claim")
@limiter.limit("30/minute")
async def claim_quest(request: Request, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    body = await request.json()
    quest_key = (body or {}).get("quest_key", "")
    return QS.claim_quest(db, current_user.id, quest_key)


# ================= الـPass =================
@router.get("/pass")
@limiter.limit("60/minute")
async def my_pass(request: Request, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return {"season": current_season(), "pass": PS.get_pass_state(db, current_user.id)}


@router.post("/pass/buy-premium")
@limiter.limit("10/minute")
async def buy_premium(request: Request, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return PS.buy_premium(db, current_user.id)


@router.post("/pass/claim")
@limiter.limit("60/minute")
async def claim_pass_tier(request: Request, current_user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    body = await request.json()
    tier = int((body or {}).get("tier", 0))
    track = (body or {}).get("track", "free")
    if track not in ("free", "premium"):
        return {"ok": False, "msg": "مسار غير صالح"}
    return PS.claim_tier(db, current_user.id, tier, track)
