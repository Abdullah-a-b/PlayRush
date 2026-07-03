"""
👥 نظام الأصدقاء والحظر (Friends & Block)

نظام قياسي على نمط الألعاب العالمية:
- طلب صداقة → قبول/رفض → قائمة أصدقاء
- حظر: يمنع الشات + طلبات الصداقة + المطابقة في matchmaking

الجداول تُنشأ تلقائياً عند أول استخدام.

العلاقات في جدول واحد friendships بحالة status:
  pending  = طلب معلّق (requester → addressee)
  accepted = صداقة مقبولة
  blocked  = حظر (requester حظر addressee)
"""
from sqlalchemy import text
from app.core.database import SessionLocal, engine, User

_tables_ready = False


def _ensure_tables():
    # كل خطوة في اتصال منفصل — فشل خطوة لا يُفسد الباقي (PostgreSQL يلغي المعاملة عند الخطأ)
    def _try(sql):
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()
        except Exception:
            pass  # موجود بالفعل أو غير لازم

    _try("""
        CREATE TABLE IF NOT EXISTS friendships (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            friend_id INTEGER NOT NULL,
            status VARCHAR(15) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    _try("ALTER TABLE friendships ADD CONSTRAINT uq_friendship_pair UNIQUE (user_id, friend_id);")
    _try("CREATE INDEX IF NOT EXISTS idx_friend_addressee ON friendships(friend_id, status);")
    _try("CREATE INDEX IF NOT EXISTS idx_friend_requester ON friendships(user_id, status);")


def _init():
    global _tables_ready
    if not _tables_ready:
        _ensure_tables()
        _tables_ready = True


# ==========================================
# الصداقة
# ==========================================
def send_friend_request(user_id: int, friend_id: int) -> dict:
    """يرسل طلب صداقة. يرجع dict بالنتيجة."""
    _init()
    if user_id == friend_id:
        return {'ok': False, 'msg': 'لا يمكنك إضافة نفسك'}

    db = SessionLocal()
    try:
        # هل هناك حظر بين الطرفين؟
        blocked = db.execute(text("""
            SELECT 1 FROM friendships
            WHERE status = 'blocked'
              AND ((user_id = :a AND friend_id = :b)
                OR (user_id = :b AND friend_id = :a))
            LIMIT 1
        """), {"a": user_id, "b": friend_id}).fetchone()
        if blocked:
            return {'ok': False, 'msg': 'تعذّر إرسال الطلب'}

        # هل توجد علاقة بالفعل؟
        existing = db.execute(text("""
            SELECT status FROM friendships
            WHERE (user_id = :a AND friend_id = :b)
               OR (user_id = :b AND friend_id = :a)
            LIMIT 1
        """), {"a": user_id, "b": friend_id}).fetchone()
        if existing:
            if existing.status == 'accepted':
                return {'ok': False, 'msg': 'أنتما صديقان بالفعل'}
            return {'ok': False, 'msg': 'يوجد طلب صداقة بالفعل'}

        db.execute(text("""
            INSERT INTO friendships (user_id, friend_id, status)
            VALUES (:a, :b, 'pending')
        """), {"a": user_id, "b": friend_id})
        db.commit()
        return {'ok': True, 'msg': 'تم إرسال طلب الصداقة'}
    finally:
        db.close()


def respond_friend_request(friend_id: int, user_id: int, accept: bool) -> dict:
    """يقبل/يرفض طلب صداقة معلّق."""
    _init()
    db = SessionLocal()
    try:
        req = db.execute(text("""
            SELECT id FROM friendships
            WHERE user_id = :r AND friend_id = :a AND status = 'pending'
        """), {"r": user_id, "a": friend_id}).fetchone()
        if not req:
            return {'ok': False, 'msg': 'لا يوجد طلب معلّق'}

        if accept:
            db.execute(text("UPDATE friendships SET status='accepted' WHERE id=:id"), {"id": req.id})
            msg = 'تمت إضافة الصديق'
        else:
            db.execute(text("DELETE FROM friendships WHERE id=:id"), {"id": req.id})
            msg = 'تم رفض الطلب'
        db.commit()
        return {'ok': True, 'msg': msg}
    finally:
        db.close()


def get_friends(user_id: int) -> list:
    """قائمة الأصدقاء المقبولين مع أسمائهم وحالة الاتصال."""
    _init()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT u.id, u.player_name, u.avatar
            FROM friendships f
            JOIN users u ON u.id = CASE
                WHEN f.user_id = :uid THEN f.friend_id
                ELSE f.user_id END
            WHERE f.status = 'accepted'
              AND (:uid IN (f.user_id, f.friend_id))
        """), {"uid": user_id}).fetchall()
        return [{'id': r.id, 'name': r.player_name, 'avatar': r.avatar} for r in rows]
    finally:
        db.close()


def get_pending_requests(user_id: int) -> list:
    """الطلبات الواردة المعلّقة."""
    _init()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT u.id, u.player_name, u.avatar
            FROM friendships f
            JOIN users u ON u.id = f.user_id
            WHERE f.friend_id = :uid AND f.status = 'pending'
        """), {"uid": user_id}).fetchall()
        return [{'id': r.id, 'name': r.player_name, 'avatar': r.avatar} for r in rows]
    finally:
        db.close()


# ==========================================
# الحظر
# ==========================================
def block_user(blocker_id: int, target_id: int) -> dict:
    """
    يحظر لاعباً: يحذف أي صداقة/طلب قائم، ويسجّل حظراً.
    أثره: يمنع الشات + طلبات الصداقة + المطابقة في matchmaking.
    """
    _init()
    if blocker_id == target_id:
        return {'ok': False, 'msg': 'لا يمكنك حظر نفسك'}

    db = SessionLocal()
    try:
        # نحذف أي علاقة قائمة بين الطرفين
        db.execute(text("""
            DELETE FROM friendships
            WHERE (user_id = :a AND friend_id = :b)
               OR (user_id = :b AND friend_id = :a)
        """), {"a": blocker_id, "b": target_id})
        # نسجّل الحظر (blocker → target)
        db.execute(text("""
            INSERT INTO friendships (user_id, friend_id, status)
            VALUES (:a, :b, 'blocked')
        """), {"a": blocker_id, "b": target_id})
        db.commit()
        return {'ok': True, 'msg': 'تم حظر اللاعب'}
    finally:
        db.close()


def unblock_user(blocker_id: int, target_id: int) -> dict:
    """يلغي حظر لاعب."""
    _init()
    db = SessionLocal()
    try:
        db.execute(text("""
            DELETE FROM friendships
            WHERE user_id = :a AND friend_id = :b AND status = 'blocked'
        """), {"a": blocker_id, "b": target_id})
        db.commit()
        return {'ok': True, 'msg': 'تم إلغاء الحظر'}
    finally:
        db.close()


def i_blocked_them(my_id: int, target_id: int) -> bool:
    """هل أنا من حظر هذا الشخص؟ (لأتمكّن من رفع الحظر). يُرجع True لو الصفّ موجود باتجاهي."""
    if my_id is None or target_id is None:
        return False
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT 1 FROM friendships
            WHERE user_id = :me AND friend_id = :t AND status = 'blocked'
            LIMIT 1
        """), {"me": my_id, "t": target_id}).fetchone()
        return row is not None
    finally:
        db.close()


def is_blocked_between(user_a: int, user_b: int) -> bool:
    """
    هل أحدهما حظر الآخر؟ (في أي اتجاه)
    يُستخدم في matchmaking والشات.
    """
    if user_a is None or user_b is None:
        return False
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT 1 FROM friendships
            WHERE status = 'blocked'
              AND ((user_id = :a AND friend_id = :b)
                OR (user_id = :b AND friend_id = :a))
            LIMIT 1
        """), {"a": user_a, "b": user_b}).fetchone()
        return row is not None
    finally:
        db.close()


def are_friends(user_a: int, user_b: int) -> bool:
    """
    هل اللاعبان صديقان (علاقة مقبولة)؟
    يُستخدم في matchmaking لمنع تطابق الأصدقاء في المباريات المصنّفة (نزاهة).
    """
    if user_a is None or user_b is None or user_a == user_b:
        return False
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT 1 FROM friendships
            WHERE status = 'accepted'
              AND ((user_id = :a AND friend_id = :b)
                OR (user_id = :b AND friend_id = :a))
            LIMIT 1
        """), {"a": user_a, "b": user_b}).fetchone()
        return row is not None
    finally:
        db.close()
