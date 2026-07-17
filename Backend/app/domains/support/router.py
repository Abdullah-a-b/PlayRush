from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.domains.users.models import User
from app.infrastructure.database import get_db
from app.core.security import get_current_user
from app.core.limiter import limiter
from app.domains.support.service import submit_ticket, get_my_tickets, get_ticket_count_summary, CATEGORIES

router = APIRouter()


class TicketIn(BaseModel):
    category: str
    subject: str = ""
    message: str


@router.get("/categories")
async def list_categories():
    """فئات التذاكر المتاحة (للواجهة)."""
    return {"categories": CATEGORIES}


@router.post("/ticket")
@limiter.limit("10/minute")
async def create_ticket(
    request: Request,
    payload: TicketIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """يقدّم تذكرة دعم + إشعار تيليجرام للأدمن."""
    result = submit_ticket(
        user_id=current_user.id,
        category=payload.category,
        subject=payload.subject,
        message=payload.message,
    )

    # إشعار تيليجرام (لا يفشل الطلب لو تعذّر)
    if result.get('ok'):
        try:
            from app.infrastructure.telegram_bot import notify_new_ticket_sync
            notify_new_ticket_sync(
                ticket_id=result.get('ticket_id'),
                player_name=current_user.player_name or current_user.email,
                category_label=CATEGORIES.get(payload.category, 'أخرى'),
                subject=payload.subject,
                message=payload.message,
            )
        except Exception:
            pass

    return result


@router.get("/my-tickets")
@limiter.limit("30/minute")
async def my_tickets(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """تذاكر اللاعب الحالية مع حالتها والردود."""
    return {
        "tickets": get_my_tickets(current_user.id),
        "summary": get_ticket_count_summary(current_user.id),
    }
