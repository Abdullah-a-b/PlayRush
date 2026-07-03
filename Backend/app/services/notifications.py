"""
🔔 نظام الإشعارات (Notifications)

يخزّن الإشعارات في جدول notifications (موجود مسبقاً) ويدفعها حيّاً لو اللاعب متصل.
يُستخدم لطلبات الصداقة وغيرها.

أنواع الإشعارات:
  friend_request = طلب صداقة وارد
  friend_accepted = قُبل طلب صداقتك
  system = إشعار نظام عام
"""
import datetime
from sqlalchemy import text
from app.core.database import SessionLocal, engine

_table_ready = False


def _ensure_table():
    """ينشئ جدول notifications لو غير موجود (آمن)."""
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    type VARCHAR(30),
                    message VARCHAR(255),
                    is_read BOOLEAN DEFAULT FALSE,
                    sender_id INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
            conn.commit()
        # ترقية آمنة: نضيف sender_id لو الجدول قديم بلا العمود
        with engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE notifications ADD COLUMN IF NOT EXISTS sender_id INTEGER;
            """))
            conn.commit()
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_notif_user
                ON notifications(user_id, is_read);
            """))
            conn.commit()
    except Exception:
        pass


def _init():
    global _table_ready
    if not _table_ready:
        _ensure_table()
        _table_ready = True


def add_notification(user_id: int, ntype: str, message: str, sender_id: int = None) -> dict | None:
    """يضيف إشعاراً ويرجع dict به (للدفع الحي). sender_id اختياري (لفتح بروفايل المُرسِل)."""
    if user_id is None:
        return None
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            INSERT INTO notifications (user_id, type, message, is_read, sender_id)
            VALUES (:uid, :t, :m, FALSE, :sid)
            RETURNING id, created_at
        """), {"uid": user_id, "t": ntype, "m": message, "sid": sender_id}).fetchone()
        db.commit()
        return {
            'id': row.id, 'type': ntype, 'message': message,
            'is_read': False, 'created_at': str(row.created_at),
            'sender_id': sender_id
        }
    finally:
        db.close()


def get_notifications(user_id: int, limit: int = 30) -> list:
    """يجلب آخر إشعارات اللاعب."""
    _init()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT id, type, message, is_read, created_at, sender_id
            FROM notifications
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"uid": user_id, "lim": limit}).fetchall()
        return [{
            'id': r.id, 'type': r.type, 'message': r.message,
            'is_read': r.is_read, 'created_at': str(r.created_at),
            'sender_id': r.sender_id
        } for r in rows]
    finally:
        db.close()


def get_unread_count(user_id: int) -> int:
    """عدد الإشعارات غير المقروءة (للشارة على الجرس)."""
    _init()
    db = SessionLocal()
    try:
        return db.execute(text("""
            SELECT COUNT(*) FROM notifications
            WHERE user_id = :uid AND (is_read = FALSE OR is_read IS NULL)
        """), {"uid": user_id}).scalar() or 0
    finally:
        db.close()


def mark_all_read(user_id: int) -> None:
    """يعلّم كل إشعارات اللاعب كمقروءة."""
    _init()
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE notifications SET is_read = TRUE
            WHERE user_id = :uid AND (is_read = FALSE OR is_read IS NULL)
        """), {"uid": user_id})
        db.commit()
    finally:
        db.close()


def find_online_sid(user_id: int) -> str | None:
    """يبحث عن sid متصل لهذا الـ user_id (للدفع الحي) عبر connected_players."""
    from app.sockets.state import connected_players
    for sid, info in connected_players.items():
        if info.get('user_id') == user_id:
            return sid
    return None
