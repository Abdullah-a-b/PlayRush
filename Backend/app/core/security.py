import os
import secrets
import hmac
import html
from datetime import datetime, timedelta, timezone
from fastapi import Request, HTTPException, Depends
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.infrastructure.database import get_db
from app.domains.users.models import User
from app.core.config import settings

# إعدادات التشفير
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

def get_password_hash(password: str) -> str:
    """تشفير كلمة المرور مع ضمان عدم تجاوز الحد الأقصى 72 بايت"""
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """التحقق من كلمة المرور مع ضمان عدم تجاوز الحد الأقصى 72 بايت"""
    if len(plain_password) > 72:
        plain_password = plain_password[:72]
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict):
    """توليد توكن مشفر ومختوم"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def session_is_valid(user, payload):
    epoch = getattr(user, 'session_token', None)
    claimed = payload.get('sv')
    # التوكن القديم يظل صالحًا حتى أول تدوير جلسة، لتجنب إخراج الجميع عند النشر.
    return (not epoch and not claimed) or (isinstance(epoch, str) and isinstance(claimed, str)
            and hmac.compare_digest(epoch, claimed))


def issue_user_token(user):
    if not user.session_token:
        user.session_token = secrets.token_urlsafe(32)
    return create_access_token({'sub': user.email, 'sv': user.session_token})


def revoke_user_sessions(user):
    user.session_token = secrets.token_urlsafe(32)


async def disconnect_user_sessions(user_id):
    from app.sockets.state import connected_players
    from app.main import sio
    for sid, player in list(connected_players.items()):
        if player.get('user_id') == user_id:
            await sio.emit('session_expired', {'msg':'انتهت الجلسة؛ سجل الدخول مجددًا'}, to=sid)
            await sio.disconnect(sid)


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """حارس الأمن المطور: يصطاد التوكن من أي مكان يرسله الفرونت اند"""
    token = None
    
    # 🔒 أُزيل قبول التوكن من query string — كان يتسرب لسجلات nginx
    # وتاريخ المتصفح. المعتمد: Authorization header ثم form body.
    # 1. البحث في الـ Headers
    if request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    # 3. البحث في الـ FormData
    else:
        try:
            form = await request.form()
            token = form.get("token")
        except:
            pass

    if not token:
        raise HTTPException(status_code=401, detail="التوكن مفقود، يرجى تسجيل الدخول")
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email: str = payload.get("sub")
        if user_email is None:
            raise HTTPException(status_code=401, detail="بيانات التوكن تالفة")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن منتهي الصلاحية أو مزور")
        
    user = db.query(User).filter(User.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="حساب اللاعب لم يعد موجوداً")

    if not session_is_valid(user, payload):
        raise HTTPException(status_code=401, detail='انتهت الجلسة، يرجى تسجيل الدخول')

    # فحص الحظر — يمنع المحظور من استخدام أي API محمي
    if getattr(user, 'is_banned', False):
        raise HTTPException(status_code=403, detail="تم حظر حسابك لانتهاك سياسات اللعب العادل والأمان.")

    return user

def get_user_from_token(db: Session, token: str):
    """دالة مساعدة لفك تشفير التوكن وجلب المستخدم (تُستخدم للسوكيت والمهام الخلفية)"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email: str = payload.get("sub")
        if user_email is None:
            return None
        
        user = db.query(User).filter(User.email == user_email).first()
        return user if user and session_is_valid(user, payload) else None
    except JWTError:
        return None


def sanitize_text(text: str, max_length: int = 255) -> str:
    """
    فلتر أمني لتنظيف أي نص قادم من المستخدم
    1. يزيل المسافات الزائدة
    2. يقص النص إذا كان طويلاً جداً (لمنع هجمات إغراق الذاكرة)
    3. يحول الأقواس والرموز الخطيرة إلى نصوص عادية (HTML Escaping)
    """
    if not text:
        return ""

    # تحويل النص لـ String احتياطياً وإزالة المسافات
    cleaned = str(text).strip()

    # قص النص حسب الحد المسموح
    cleaned = cleaned[:max_length]

    # السحر هنا: تحويل <script> إلى &lt;script&gt; لكي لا يعمل ككود
    cleaned = html.escape(cleaned)

    return cleaned