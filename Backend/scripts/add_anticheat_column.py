"""
🛢️ Migration: إضافة الأعمدة والـ indexes الجديدة

الاستخدام:
    cd Backend
    python -m scripts.add_anticheat_column

✅ آمن للتشغيل عدة مرات (IF NOT EXISTS)
✅ يفحص ويطبع حالة كل عمود/index
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import engine
from sqlalchemy import text, inspect


def column_exists(conn, table: str, column: str) -> bool:
    """يفحص لو العمود موجود."""
    result = conn.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = :t AND column_name = :c
    """), {"t": table, "c": column}).fetchone()
    return result is not None


def index_exists(conn, index_name: str) -> bool:
    """يفحص لو الـ index موجود."""
    result = conn.execute(text("""
        SELECT 1 FROM pg_indexes WHERE indexname = :n
    """), {"n": index_name}).fetchone()
    return result is not None


def run_migrations():
    print("🚀 بدء الـ migration...\n")

    indexes_to_create = [
        ("idx_users_player_name", "users(player_name)"),
        ("idx_users_is_verified", "users(is_verified)"),
        ("idx_users_is_banned", "users(is_banned)"),
        ("idx_users_xp", "users(xp)"),
    ]

    columns_to_add = [
        ("users", "anticheat_score", "INTEGER DEFAULT 0"),
        ("users", "verification_code_expires_at", "TIMESTAMP"),
        ("users", "is_banned", "BOOLEAN DEFAULT FALSE"),
    ]

    with engine.connect() as conn:
        # 1. إضافة الأعمدة المفقودة
        print("📋 فحص الأعمدة...")
        for table, col, definition in columns_to_add:
            if column_exists(conn, table, col):
                print(f"   ⏭️  {table}.{col} موجود فعلاً")
            else:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                    conn.commit()
                    print(f"   ✅ أُضيف {table}.{col}")
                except Exception as e:
                    print(f"   ❌ فشل {table}.{col}: {e}")

        print("\n🔍 فحص الـ indexes...")
        for idx_name, target in indexes_to_create:
            if index_exists(conn, idx_name):
                print(f"   ⏭️  {idx_name} موجود فعلاً")
            else:
                try:
                    conn.execute(text(f"CREATE INDEX {idx_name} ON {target}"))
                    conn.commit()
                    print(f"   ✅ أُنشئ {idx_name}")
                except Exception as e:
                    print(f"   ❌ فشل {idx_name}: {e}")

    print("\n🎉 Migration مكتمل")


if __name__ == "__main__":
    run_migrations()
