from sqlalchemy import create_engine, event, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BACKEND_ROOT / "users.db"
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{DEFAULT_DB_PATH}"  # مطلق، ليس نسبي
)

# ==========================================
# Scalability: إعدادات قاعدة البيانات
# ==========================================

if DATABASE_URL.startswith("sqlite"):
    # SQLite: مناسب للتطوير فقط
    # للإنتاج مع آلاف المستخدمين: استخدم PostgreSQL
    # DATABASE_URL = "postgresql://user:password@localhost/dbname"
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")      # قراءة وكتابة متوازية
        cursor.execute("PRAGMA synchronous=NORMAL")    # أداء أفضل مع أمان كافٍ
        cursor.execute("PRAGMA cache_size=-64000")     # 64MB cache في الذاكرة
        cursor.execute("PRAGMA temp_store=MEMORY")     # عمليات مؤقتة في الذاكرة
        cursor.execute("PRAGMA mmap_size=268435456")   # 256MB memory-mapped I/O
        cursor.close()

else:
    # PostgreSQL/MySQL: للإنتاج مع آلاف المستخدمين
    engine = create_engine(
        DATABASE_URL,
        poolclass=pool.QueuePool,
        pool_size=20,           # 20 اتصال ثابت
        max_overflow=30,        # 30 اتصال إضافي عند الذروة
        pool_pre_ping=True,     # فحص الاتصالات قبل الاستخدام
        pool_recycle=3600,      # تجديد الاتصالات كل ساعة
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from app.models.user import User, GameStat, Friendship, Notification, Question
