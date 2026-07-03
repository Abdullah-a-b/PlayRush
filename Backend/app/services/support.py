"""
🎧 نظام تذاكر الدعم الفني (Support Tickets)

اللاعب يرسل تذكرة → تُحفظ في DB → إشعار تيليجرام للأدمن → اللاعب يتابع حالتها.

الحالات: open (مفتوحة) → in_progress (قيد المعالجة) → closed (مغلقة)
الفئات: ban_appeal (مراجعة حظر), payment (دفع), technical (تقني),
        suggestion (اقتراح), other (أخرى)

الجدول يُنشأ تلقائياً عند أول استخدام.
"""
import datetime
from sqlalchemy import text
from app.core.database import SessionLocal, engine

_table_ready = False

CATEGORIES = {
    'ban_appeal': 'مراجعة حظر',
    'payment': 'مشكلة دفع',
    'technical': 'مشكلة تقنية',
    'suggestion': 'اقتراح',
    'other': 'أخرى',
}

MAX_TICKETS_PER_DAY = 5          # حد التذاكر اليومية لكل لاعب
MAX_OPEN_TICKETS = 3            # حد التذاكر المفتوحة في آن واحد


def _ensure_table():
    def _try(sql):
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception:
            pass

    _try("""
        CREATE TABLE IF NOT EXISTS support_tickets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            category VARCHAR(20) NOT NULL,
            subject VARCHAR(150),
            message TEXT NOT NULL,
            status VARCHAR(15) NOT NULL DEFAULT 'open',
            admin_reply TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    _try("CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id, status);")


def _init():
    global _table_ready
    if not _table_ready:
        _ensure_table()
        _table_ready = True


def submit_ticket(user_id: int, category: str, subject: str, message: str) -> dict:
    """يقدّم تذكرة دعم جديدة."""
    _init()

    if category not in CATEGORIES:
        category = 'other'
    message = (message or '').strip()
    subject = (subject or '').strip()[:150]
    if len(message) < 5:
        return {'ok': False, 'msg': 'الرجاء كتابة وصف أوضح للمشكلة'}
    if len(message) > 2000:
        message = message[:2000]

    db = SessionLocal()
    try:
        # حد يومي
        daily = db.execute(text("""
            SELECT COUNT(*) FROM support_tickets
            WHERE user_id = :uid AND created_at > NOW() - INTERVAL '1 day'
        """), {"uid": user_id}).scalar()
        if daily >= MAX_TICKETS_PER_DAY:
            return {'ok': False, 'msg': 'وصلت الحد اليومي للتذاكر، حاول غداً'}

        # حد التذاكر المفتوحة
        open_count = db.execute(text("""
            SELECT COUNT(*) FROM support_tickets
            WHERE user_id = :uid AND status IN ('open', 'in_progress')
        """), {"uid": user_id}).scalar()
        if open_count >= MAX_OPEN_TICKETS:
            return {'ok': False, 'msg': 'لديك تذاكر مفتوحة كثيرة، انتظر الرد عليها أولاً'}

        row = db.execute(text("""
            INSERT INTO support_tickets (user_id, category, subject, message)
            VALUES (:uid, :cat, :subj, :msg)
            RETURNING id
        """), {"uid": user_id, "cat": category, "subj": subject, "msg": message}).fetchone()
        db.commit()
        return {'ok': True, 'msg': 'تم استلام تذكرتك وسنرد عليك قريباً', 'ticket_id': row.id}
    finally:
        db.close()


def get_my_tickets(user_id: int, limit: int = 20) -> list:
    """تذاكر اللاعب مع حالتها والرد."""
    _init()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT id, category, subject, message, status, admin_reply, created_at
            FROM support_tickets
            WHERE user_id = :uid
            ORDER BY created_at DESC
            LIMIT :lim
        """), {"uid": user_id, "lim": limit}).fetchall()
        return [{
            'id': r.id,
            'category': r.category,
            'category_label': CATEGORIES.get(r.category, 'أخرى'),
            'subject': r.subject,
            'message': r.message,
            'status': r.status,
            'admin_reply': r.admin_reply,
            'created_at': str(r.created_at),
        } for r in rows]
    finally:
        db.close()


def get_ticket_count_summary(user_id: int) -> dict:
    """ملخص: كم تذكرة مفتوحة (لشارة)."""
    _init()
    db = SessionLocal()
    try:
        open_count = db.execute(text("""
            SELECT COUNT(*) FROM support_tickets
            WHERE user_id = :uid AND status IN ('open', 'in_progress')
        """), {"uid": user_id}).scalar() or 0
        replied = db.execute(text("""
            SELECT COUNT(*) FROM support_tickets
            WHERE user_id = :uid AND admin_reply IS NOT NULL AND status != 'closed'
        """), {"uid": user_id}).scalar() or 0
        return {'open': open_count, 'replied': replied}
    finally:
        db.close()


# ==========================================
# 🔧 دوال الأدمن (تُستدعى من بوت التيليجرام)
# ==========================================
def admin_reply_ticket(ticket_id: int, reply_text: str) -> dict:
    """
    يردّ الأدمن على تذكرة. يحفظ الرد + يحوّل الحالة لـ in_progress.
    يرجع dict فيه user_id لإشعار اللاعب.
    """
    _init()
    reply_text = (reply_text or '').strip()
    if not reply_text:
        return {'ok': False, 'msg': 'الرد فارغ'}

    db = SessionLocal()
    try:
        row = db.execute(text("SELECT user_id FROM support_tickets WHERE id = :id"),
                         {"id": ticket_id}).fetchone()
        if not row:
            return {'ok': False, 'msg': f'لا توجد تذكرة #{ticket_id}'}

        db.execute(text("""
            UPDATE support_tickets
            SET admin_reply = :reply, status = 'in_progress', updated_at = NOW()
            WHERE id = :id
        """), {"reply": reply_text[:2000], "id": ticket_id})
        db.commit()
        return {'ok': True, 'msg': f'تم الرد على التذكرة #{ticket_id}', 'user_id': row.user_id}
    finally:
        db.close()


def admin_close_ticket(ticket_id: int) -> dict:
    """يقفل تذكرة (status = closed)."""
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT user_id FROM support_tickets WHERE id = :id"),
                         {"id": ticket_id}).fetchone()
        if not row:
            return {'ok': False, 'msg': f'لا توجد تذكرة #{ticket_id}'}
        db.execute(text("""
            UPDATE support_tickets SET status = 'closed', updated_at = NOW()
            WHERE id = :id
        """), {"id": ticket_id})
        db.commit()
        return {'ok': True, 'msg': f'أُغلقت التذكرة #{ticket_id}', 'user_id': row.user_id}
    finally:
        db.close()


def get_ticket_owner(ticket_id: int) -> int | None:
    """يرجع user_id صاحب التذكرة (لإشعاره)."""
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT user_id FROM support_tickets WHERE id = :id"),
                         {"id": ticket_id}).fetchone()
        return row.user_id if row else None
    finally:
        db.close()


def cleanup_old_closed_tickets(days: int = 30) -> int:
    """
    يحذف التذاكر المغلقة الأقدم من X يوم (يمنع التكدّس).
    يُستدعى من cron. يرجع العدد المحذوف.
    """
    _init()
    db = SessionLocal()
    try:
        result = db.execute(text("""
            DELETE FROM support_tickets
            WHERE status = 'closed'
              AND updated_at < NOW() - make_interval(days => :days)
        """), {"days": days})
        db.commit()
        return result.rowcount or 0
    finally:
        db.close()
