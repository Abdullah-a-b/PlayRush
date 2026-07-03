"""🎨 التجميليات المُجهّزة (Equipped Cosmetics)"""
from sqlalchemy import text
from app.core.database import SessionLocal, engine
_initialized = False
def _init():
    global _initialized
    if _initialized: return
    try:
        with engine.connect() as conn:
            conn.execute(text("""CREATE TABLE IF NOT EXISTS player_equipped (
                user_id INTEGER NOT NULL, slot_type VARCHAR(30) NOT NULL,
                item_id VARCHAR(60), PRIMARY KEY (user_id, slot_type));"""))
            conn.commit()
        _initialized = True
    except Exception as e:
        print(f"🔥 خطأ تهيئة التجهيز: {e}")
def get_equipped(user_id):
    if user_id is None: return {}
    _init(); db = SessionLocal()
    try:
        rows = db.execute(text("SELECT slot_type, item_id FROM player_equipped WHERE user_id = :uid"), {"uid": user_id}).fetchall()
        return {r.slot_type: r.item_id for r in rows}
    finally: db.close()
def set_equipped(user_id, slot_type, item_id):
    if user_id is None or not slot_type: return False
    _init(); db = SessionLocal()
    try:
        db.execute(text("""INSERT INTO player_equipped (user_id, slot_type, item_id)
            VALUES (:uid, :st, :iid) ON CONFLICT (user_id, slot_type) DO UPDATE SET item_id = :iid"""),
            {"uid": user_id, "st": slot_type, "iid": item_id})
        db.commit(); return True
    except Exception as e:
        print(f"🔥 خطأ التجهيز: {e}"); return False
    finally: db.close()
