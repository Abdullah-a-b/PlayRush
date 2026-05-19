"""
🛡️ Socket.IO Authentication Helper
التحقق من JWT في أحداث السوكيت الحساسة
"""
from app.core.database import SessionLocal
from app.core.security import get_user_from_token


def verify_socket_token(token: str | None) -> tuple:
    """
    يفك التوكن ويرجع (user, db) إذا صالح، أو (None, None) إذا فاشل.
    المستدعي مسؤول عن إغلاق db.
    يُستخدم في events السوكيت التي تحتاج هوية مؤكدة.
    """
    if not token:
        return None, None
    db = SessionLocal()
    user = get_user_from_token(db, token)
    if not user:
        db.close()
        return None, None
    if getattr(user, 'is_banned', False):
        db.close()
        return None, None
    return user, db
