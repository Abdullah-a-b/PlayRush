import os
from pathlib import Path
from sqlalchemy import create_engine, pool
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

# ✅ تحميل .env من جذر الـ Backend قبل قراءة أي متغير بيئة
ENV_PATH = BACKEND_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# ==========================================
# 🛡️ DATABASE_URL مطلوب — PostgreSQL فقط
# ==========================================
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "❌ DATABASE_URL غير مضبوط في .env\n"
        "هذه المنصة تتطلب PostgreSQL. مثال:\n"
        "DATABASE_URL=postgresql://user:pass@host:5432/dbname"
    )

if not DATABASE_URL.startswith("postgresql"):
    raise RuntimeError(
        f"❌ DATABASE_URL يجب أن يبدأ بـ postgresql:// — قيمة حالية تبدأ بـ {DATABASE_URL.split('://')[0]}://\n"
        "تم حذف دعم SQLite. استخدم PostgreSQL."
    )

# طباعة DB المتصلة (مع إخفاء الباسوورد)
if "@" in DATABASE_URL:
    scheme, rest = DATABASE_URL.split("://", 1)
    _, host_part = rest.split("@", 1)
    print(f"✅ [DB] متصل بـ: {scheme}://***@{host_part}")

# ==========================================
# Engine — Connection Pool مضبوط
# ==========================================
engine = create_engine(
    DATABASE_URL,
    poolclass=pool.QueuePool,
    pool_size=20,        # ⬆️ كان 5 — اتصالات دائمة (رُفع ضمن مرحلة التوسعة أ)
    max_overflow=30,     # ⬆️ كان 5 — إضافية بالذروة (إجمالي 50 بدل 10)
    pool_pre_ping=True,  # يفحص الاتصال قبل الاستخدام
    pool_recycle=1800,   # تجديد كل 30 دقيقة
    pool_timeout=30,     # انتظار 30 ثانية قبل error
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Database connection — كل القراءات والكتابات."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


from app.models.user import User, GameStat, Friendship, Notification, Question, CareerPlayer, BankSeen, CareerSeen, KnowledgeSeen  # 🔧 جميع النماذج مستوردة صراحةً → Base.metadata يضمها كلها → create_all تنشئها
