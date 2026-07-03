"""🎯 تشكيل المساعدات"""
from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.games.huroof.helps import DEFAULT_LOADOUT, is_valid_help
_initialized = False
def _init():
    global _initialized
    if _initialized: return
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS player_help_loadout (user_id INTEGER PRIMARY KEY, slots TEXT NOT NULL);"))
            conn.commit()
        _initialized = True
    except Exception as e:
        print(f"🔥 خطأ تهيئة التشكيل: {e}")
def get_loadout(user_id, level=0):
    if user_id is None: return list(DEFAULT_LOADOUT)
    _init(); db = SessionLocal()
    try:
        row = db.execute(text("SELECT slots FROM player_help_loadout WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        if row and row.slots:
            import json
            try:
                saved = json.loads(row.slots)
                if isinstance(saved, list) and saved: return saved
            except Exception: pass
        return list(DEFAULT_LOADOUT)
    finally: db.close()
def set_loadout(user_id, slots, max_slots):
    if user_id is None: return {"ok": False, "msg": "مستخدم غير صالح"}
    if not isinstance(slots, list): return {"ok": False, "msg": "تشكيل غير صالح"}
    seen = set(); clean = []
    for s in slots:
        if s in seen: continue
        if not is_valid_help(s): return {"ok": False, "msg": "مساعدة غير صالحة"}
        seen.add(s); clean.append(s)
    if len(clean) > max_slots: return {"ok": False, "msg": f"الحد الأقصى {max_slots} خانات"}
    _init(); db = SessionLocal()
    try:
        import json
        db.execute(text("""INSERT INTO player_help_loadout (user_id, slots) VALUES (:uid, :slots)
            ON CONFLICT (user_id) DO UPDATE SET slots = :slots"""), {"uid": user_id, "slots": json.dumps(clean)})
        db.commit(); return {"ok": True, "msg": "تم حفظ التشكيل", "loadout": clean}
    except Exception as e:
        print(f"🔥 خطأ حفظ التشكيل: {e}"); return {"ok": False, "msg": "فشل الحفظ"}
    finally: db.close()
