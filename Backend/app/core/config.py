import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-123")
    ALGORITHM = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 10080))
    
    # روابط الأصول: فارغة افتراضياً → مسارات نسبية تعمل على أي عنوان (لابتوب/جوال/شبكة محلية).
    # في الإنتاج فقط: اضبط FRONTEND_URL/BACKEND_URL في .env بدومينك الحقيقي.
    FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip('/')
    BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip('/')
    
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT")

settings = Settings()