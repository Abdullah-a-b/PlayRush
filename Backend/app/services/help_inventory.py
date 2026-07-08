"""
🎒 مخزون المساعدات (Help Inventory)

يخزّن كمية كل مساعدة يملكها اللاعب في جدول player_help_inventory.
- استخدام مساعدة في المباراة يستهلك 1 من المخزون.
- في وضع التطوير (ALLOW_SAME_IP=1) لا يُستهلك المخزون (لا نهائي للاختبار).
- المتجر يضيف للمخزون عند الشراء.
"""
from sqlalchemy import text
from app.core.database import SessionLocal, engine

_initialized = False


def _init():
    global _initialized
    if _initialized:
        return
    try:
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS player_help_inventory (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    help_id VARCHAR(40) NOT NULL,
                    quantity INTEGER DEFAULT 0,
                    UNIQUE(user_id, help_id)
                );
            """))
            conn.commit()
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_help_inv_user
                ON player_help_inventory(user_id);
            """))
            conn.commit()
        _initialized = True
    except Exception as e:
        print(f"🔥 خطأ تهيئة مخزون المساعدات: {e}")


def grant_starter_helps_once(user_id: int) -> bool:
    """يمنح اللاعب الجديد 1 من كل مساعدة أساسية (مرة واحدة فقط).
    يُستخدم علم في الجدول: نمنح فقط لو ما استلم من قبل."""
    if user_id is None:
        return False
    _init()
    db = SessionLocal()
    try:
        # هل سبق أن استلم الهدية؟ (نستخدم صفّاً علمياً help_id='__starter__')
        row = db.execute(text("""
            SELECT 1 FROM player_help_inventory
            WHERE user_id = :uid AND help_id = '__starter__' LIMIT 1
        """), {"uid": user_id}).fetchone()
        if row:
            return False  # استلم من قبل
        # نمنح 1 من كل مساعدة أساسية + نضع العلم
        from app.games.huroof.helps import DEFAULT_LOADOUT
        for hid in DEFAULT_LOADOUT:
            db.execute(text("""
                INSERT INTO player_help_inventory (user_id, help_id, quantity)
                VALUES (:uid, :hid, 1)
                ON CONFLICT (user_id, help_id)
                DO UPDATE SET quantity = player_help_inventory.quantity + 1
            """), {"uid": user_id, "hid": hid})
        # علم الاستلام
        db.execute(text("""
            INSERT INTO player_help_inventory (user_id, help_id, quantity)
            VALUES (:uid, '__starter__', 0)
            ON CONFLICT (user_id, help_id) DO NOTHING
        """), {"uid": user_id})
        db.commit()
        return True
    except Exception as e:
        print(f"🔥 خطأ منح هدية البداية: {e}")
        return False
    finally:
        db.close()


def get_inventory(user_id: int) -> dict:
    """يُرجع {help_id: quantity} لكل مساعدات اللاعب."""
    if user_id is None:
        return {}
    _init()
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT help_id, quantity FROM player_help_inventory
            WHERE user_id = :uid AND quantity > 0 AND help_id != '__starter__'
        """), {"uid": user_id}).fetchall()
        return {r.help_id: r.quantity for r in rows}
    finally:
        db.close()


def get_quantity(user_id: int, help_id: str) -> int:
    """كمية مساعدة محددة."""
    if user_id is None:
        return 0
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT quantity FROM player_help_inventory
            WHERE user_id = :uid AND help_id = :hid
        """), {"uid": user_id, "hid": help_id}).fetchone()
        return row.quantity if row else 0
    finally:
        db.close()


def add_help(user_id: int, help_id: str, amount: int = 1) -> bool:
    """يضيف كمية لمساعدة (عند الشراء أو المكافأة)."""
    if user_id is None or amount <= 0:
        return False
    _init()
    db = SessionLocal()
    try:
        db.execute(text("""
            INSERT INTO player_help_inventory (user_id, help_id, quantity)
            VALUES (:uid, :hid, :amt)
            ON CONFLICT (user_id, help_id)
            DO UPDATE SET quantity = player_help_inventory.quantity + :amt
        """), {"uid": user_id, "hid": help_id, "amt": amount})
        db.commit()
        return True
    except Exception as e:
        print(f"🔥 خطأ إضافة مساعدة: {e}")
        return False
    finally:
        db.close()


def consume_help(user_id: int, help_id: str) -> bool:
    """يستهلك 1 من مساعدة. يُرجع True لو نجح (كان عنده رصيد)."""
    if user_id is None:
        return False
    _init()
    db = SessionLocal()
    try:
        # ننقص فقط لو الكمية > 0 (ذرّي)
        result = db.execute(text("""
            UPDATE player_help_inventory
            SET quantity = quantity - 1
            WHERE user_id = :uid AND help_id = :hid AND quantity > 0
        """), {"uid": user_id, "hid": help_id})
        db.commit()
        return result.rowcount > 0
    except Exception as e:
        print(f"🔥 خطأ استهلاك مساعدة: {e}")
        return False
    finally:
        db.close()


def grant_career_starter(user_id):
    """يمنح مساعدات مسيرة لاعب الأساسية ×1 (مرة واحدة، علم '__career_starter__')."""
    from sqlalchemy import text
    from app.core.database import SessionLocal
    if user_id is None:
        return False
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""SELECT 1 FROM player_help_inventory
            WHERE user_id = :uid AND help_id = '__career_starter__' LIMIT 1"""),
            {"uid": user_id}).fetchone()
        if row:
            return False
        from app.games.career.helps import DEFAULT_LOADOUT as CAREER_DEFAULTS
        for hid in CAREER_DEFAULTS:
            db.execute(text("""INSERT INTO player_help_inventory (user_id, help_id, quantity)
                VALUES (:uid, :hid, 1) ON CONFLICT (user_id, help_id)
                DO UPDATE SET quantity = player_help_inventory.quantity + 1"""),
                {"uid": user_id, "hid": hid})
        db.execute(text("""INSERT INTO player_help_inventory (user_id, help_id, quantity)
            VALUES (:uid, '__career_starter__', 0)
            ON CONFLICT (user_id, help_id) DO NOTHING"""), {"uid": user_id})
        db.commit()
        return True
    finally:
        db.close()


def grant_bank_starter(user_id):
    """يمنح مساعدات البنك الأساسية ×1 — علم لكل مساعدة على حدة
    (حصين: لو مُنح جزئياً بنسخة قديمة، يكمل الناقص ولا يكرر الممنوح)."""
    from sqlalchemy import text
    from app.core.database import SessionLocal
    if user_id is None:
        return False
    _init()
    db = SessionLocal()
    granted_any = False
    try:
        from app.games.bank.helps import DEFAULT_LOADOUT as BANK_DEFAULTS
        for hid in BANK_DEFAULTS:
            flag = f'__bank_starter_{hid}__'
            row = db.execute(text("""SELECT 1 FROM player_help_inventory
                WHERE user_id = :uid AND help_id = :flag LIMIT 1"""),
                {"uid": user_id, "flag": flag}).fetchone()
            if row:
                continue  # هذه المساعدة مُنحت سابقاً
            db.execute(text("""INSERT INTO player_help_inventory (user_id, help_id, quantity)
                VALUES (:uid, :hid, 1) ON CONFLICT (user_id, help_id)
                DO UPDATE SET quantity = player_help_inventory.quantity + 1"""),
                {"uid": user_id, "hid": hid})
            db.execute(text("""INSERT INTO player_help_inventory (user_id, help_id, quantity)
                VALUES (:uid, :flag, 0)
                ON CONFLICT (user_id, help_id) DO NOTHING"""),
                {"uid": user_id, "flag": flag})
            granted_any = True
        db.commit()
        return granted_any
    finally:
        db.close()

