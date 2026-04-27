import os
from pathlib import Path
from sqlalchemy import create_engine, event, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BACKEND_ROOT / "users.db"

# احذف +asyncpg من الرابط ليعمل مع create_engine
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:abodibatheeb2@localhost:5432/playrush_db")

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.close()
else:
    # PostgreSQL — مضبوط لـ 4 workers على Windows
    engine = create_engine(
        DATABASE_URL,
        poolclass=pool.QueuePool,
        pool_size=5,          # 5 × 4 workers = 20 connection ثابتة ✅
        max_overflow=5,       # 5 × 4 = 20 إضافية في الذروة ✅
        pool_pre_ping=True,
        pool_recycle=1800,    # تجديد كل 30 دقيقة (أسرع من ساعة)
        pool_timeout=30,      # انتظر 30 ثانية قبل error
        echo=False,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

from app.models.user import User, GameStat, Friendship, Notification, Question