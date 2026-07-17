"""
 ملكية التجميليات (Cosmetics Ownership)

يخزّن ما يملكه اللاعب من تجميليات (أفاتارات/ثيمات/إيموجيات/عبارات)
في جدول player_cosmetics. التجميلي يُشترى مرة واحدة (يُمتلك للأبد).
"""
from sqlalchemy import text
from app.infrastructure.database import SessionLocal, engine

_initialized = False


def _init():
    global _initialized
    if _initialized:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS player_cosmetics (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    item_id VARCHAR(60) NOT NULL,
                    category VARCHAR(30),
                    acquired_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(user_id, item_id)
                );
            """))
            conn.commit()
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cosmetics_user
                ON player_cosmetics(user_id);
            """))
            conn.commit()
        _initialized = True
    except Exception as e:
        print(f" خطأ تهيئة التجميليات: {e}")


def get_owned_cosmetics(user_id: int) -> list:
    """قائمة معرّفات التجميليات التي يملكها اللاعب."""
    if user_id is None:
        return []
    _init()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT item_id FROM player_cosmetics WHERE user_id = :uid
        """), {"uid": user_id}).fetchall()
        return [r.item_id for r in rows]
    finally:
        db.close()


def owns_cosmetic(user_id: int, item_id: str) -> bool:
    if user_id is None:
        return False
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT 1 FROM player_cosmetics WHERE user_id = :uid AND item_id = :iid LIMIT 1
        """), {"uid": user_id, "iid": item_id}).fetchone()
        return row is not None
    finally:
        db.close()


def grant_cosmetic(user_id: int, item_id: str, category: str = None) -> bool:
    """يمنح اللاعب تجميلياً (عند الشراء). آمن من التكرار."""
    if user_id is None:
        return False
    _init()
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO player_cosmetics (user_id, item_id, category)
            VALUES (:uid, :iid, :cat)
            ON CONFLICT (user_id, item_id) DO NOTHING
        """), {"uid": user_id, "iid": item_id, "cat": category})
        db.commit()
        return True
    except Exception as e:
        print(f" خطأ منح تجميلي: {e}")
        return False
    finally:
        db.close()
