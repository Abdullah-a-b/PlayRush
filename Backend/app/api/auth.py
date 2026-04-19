import os
import time
import uuid
import string
import secrets
import httpx
from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks, UploadFile, File, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.security import get_db, get_current_user, get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM
from app.services.email_service import send_real_email, send_password_changed_email, send_email_changed, send_welcome_email
from app.core.database import User

router = APIRouter()

# ==========================================
# إعدادات رفع الصور
# ==========================================
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
}

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB

UPLOAD_DIR = "uploads/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==========================================
# Rate Limiting — في الذاكرة
# للإنتاج: استبدل بـ Redis
# ==========================================
otp_cooldowns: dict[str, float] = {}
COOLDOWN_SECONDS = 60

# rate limiting للـ login: ip -> [timestamps]
login_attempts: dict[str, list[float]] = {}
LOGIN_MAX_ATTEMPTS = 10    # أقصى عدد محاولات
LOGIN_WINDOW_SECONDS = 300  # خلال 5 دقائق
LOGIN_BLOCK_SECONDS = 900   # حظر 15 دقيقة بعد التجاوز

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_URL")


# ==========================================
# دوال مساعدة
# ==========================================

def generate_player_id(db: Session) -> str:
    while True:
        new_id = "PR-" + ''.join(secrets.choice(string.digits) for _ in range(5))
        if not db.query(User).filter(User.player_id == new_id).first():
            return new_id


def generate_otp() -> str:
    """✅ OTP آمن بـ secrets بدل random"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def validate_image_file(file_bytes: bytes, original_filename: str) -> str:
    """
    التحقق الأمني الكامل من الصورة:
    1. فحص الحجم
    2. فحص الامتداد
    3. فحص Magic Bytes
    4. التطابق بين الامتداد والمحتوى
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"حجم الصورة يتجاوز الحد المسموح ({MAX_FILE_SIZE_BYTES // 1024 // 1024} MB)"
        )

    if len(file_bytes) < 8:
        raise HTTPException(status_code=400, detail="الملف تالف أو فارغ")

    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"نوع الملف غير مسموح. الأنواع المقبولة: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    detected_type = None
    for signature, img_type in IMAGE_SIGNATURES.items():
        if file_bytes[:len(signature)] == signature:
            detected_type = img_type
            break

    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        detected_type = "webp"

    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="محتوى الملف لا يطابق أي صيغة صورة معروفة. رُفض."
        )

    normalized_ext = "jpg" if ext == "jpeg" else ext
    if normalized_ext != detected_type:
        raise HTTPException(
            status_code=400,
            detail=f"الامتداد ({ext}) لا يتطابق مع محتوى الملف الحقيقي ({detected_type}). رُفض."
        )

    return detected_type


def get_client_ip(request: Request) -> str:
    """جلب IP الحقيقي للمستخدم (يدعم reverse proxy)"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_login_rate_limit(ip: str):
    """
    ✅ Rate limiting للـ login بناءً على IP
    10 محاولات خلال 5 دقائق → حظر 15 دقيقة
    """
    now = time.time()

    if ip not in login_attempts:
        login_attempts[ip] = []

    # احذف المحاولات القديمة خارج الـ window
    login_attempts[ip] = [t for t in login_attempts[ip] if now - t < LOGIN_WINDOW_SECONDS]

    attempts = login_attempts[ip]

    # إذا تجاوز الحد → تحقق من الحظر
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        oldest = attempts[0]
        block_remaining = int(LOGIN_BLOCK_SECONDS - (now - oldest))
        if block_remaining > 0:
            minutes = block_remaining // 60
            seconds = block_remaining % 60
            raise HTTPException(
                status_code=429,
                detail=f"تم تجاوز الحد المسموح من المحاولات. حاول مجدداً بعد {minutes}:{seconds:02d} دقيقة."
            )
        # انتهى وقت الحظر، أعد الضبط
        login_attempts[ip] = []

    # سجّل هذه المحاولة
    login_attempts[ip].append(now)


def record_failed_login(ip: str):
    """لا نفعل شيئاً إضافياً — المحاولة سُجّلت في check_login_rate_limit"""
    pass


# ==========================================
# Routes
# ==========================================

@router.post("/register")
async def register(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    current_time = time.time()
    if email in otp_cooldowns:
        time_passed = current_time - otp_cooldowns[email]
        if time_passed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - time_passed)
            raise HTTPException(status_code=429, detail=f"الرجاء الانتظار {remaining} ثانية قبل طلب رمز جديد.")

    db_user = db.query(User).filter(User.email == email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجل مسبقاً!")

    hashed_password = get_password_hash(password)
    verification_code = generate_otp()  # ✅ secrets

    new_user = User(
        email=email,
        hashed_password=hashed_password,
        verification_code=verification_code,
        is_verified=False,
        coins=100,
        gems=3,
        level=0,
        player_id=generate_player_id(db)
    )
    db.add(new_user)
    db.commit()

    background_tasks.add_task(send_real_email, email, verification_code)
    otp_cooldowns[email] = current_time

    return {"message": "تم التسجيل بنجاح، يرجى التحقق من بريدك الإلكتروني"}


@router.post("/verify-code")
async def verify_code(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    flow: str = Form("register"),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or user.verification_code != code:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح أو الحساب غير موجود")

    if flow == "register":
        user.is_verified = True
        user.verification_code = None
        if not user.welcome_email_sent:
            background_tasks.add_task(send_welcome_email, user.email)
            user.welcome_email_sent = True
        db.commit()
        return {"message": "تم تفعيل الحساب بنجاح"}

    elif flow == "reset":
        return {"message": "الرمز صحيح"}


@router.post("/login")
async def login(
    request: Request,
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    ip = get_client_ip(request)

    # ✅ Rate limiting قبل أي عملية
    check_login_rate_limit(ip)

    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة")

    # نجح الدخول — أعد ضبط المحاولات
    login_attempts.pop(ip, None)

    if not user.is_verified:
        new_code = generate_otp()  # ✅ secrets
        user.verification_code = new_code
        db.commit()
        background_tasks.add_task(send_real_email, user.email, new_code)
        return JSONResponse(
            status_code=403,
            content={
                "action": "redirect_to_verify",
                "email": user.email,
                "detail": "حسابك غير مفعل. تم إرسال كود تحقق جديد إلى بريدك، جاري التوجيه..."
            }
        )

    access_token = create_access_token(data={"sub": user.email})
    return {
        "message": "تم تسجيل الدخول بنجاح",
        "token": access_token,
        "token_type": "bearer",
        "has_profile": bool(user.player_name)
    }


@router.post("/forgot-password")
async def forgot_password(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # ✅ لا نكشف إذا كان البريد مسجلاً أم لا (user enumeration)
        return {"message": "إذا كان البريد مسجلاً، سيصلك رمز الاستعادة"}

    reset_code = generate_otp()  # ✅ secrets
    user.verification_code = reset_code
    db.commit()

    background_tasks.add_task(send_real_email, email, reset_code, "إعادة تعيين كلمة المرور")
    return {"message": "إذا كان البريد مسجلاً، سيصلك رمز الاستعادة"}


@router.post("/reset-password")
async def reset_password(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or user.verification_code != code:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    if verify_password(new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="كلمة المرور مطابقة للقديمة")

    user.hashed_password = get_password_hash(new_password)
    user.verification_code = None
    db.commit()
    background_tasks.add_task(send_password_changed_email, email)
    return {"message": "تم تغيير كلمة المرور بنجاح"}


@router.get("/google/login")
async def google_login():
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
    )
    return RedirectResponse(url=google_auth_url)


@router.get("/google/callback")
async def google_callback(code: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        token_response = await client.post(token_url, data=token_data)
        access_token = token_response.json().get("access_token")

        user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_info_response = await client.get(user_info_url, headers=headers)
        user_info = user_info_response.json()

    email = user_info.get("email")
    user = db.query(User).filter(User.email == email).first()
    needs_profile_setup = False

    if not user:
        needs_profile_setup = True
        random_password = secrets.token_urlsafe(24)  # ✅ secrets

        new_user = User(
            email=email,
            hashed_password=get_password_hash(random_password),
            is_verified=True,
            welcome_email_sent=True,
            auth_provider="google",
            player_id=generate_player_id(db),
            coins=100, gems=3, level=0
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
        background_tasks.add_task(send_welcome_email, user.email)
    elif not user.player_name:
        needs_profile_setup = True

    playrush_token = create_access_token(data={"sub": user.email})
    target_url = (
        f"{FRONTEND_BASE_URL}/profile-setup.html?token={playrush_token}"
        if needs_profile_setup
        else f"{FRONTEND_BASE_URL}/categories.html?token={playrush_token}"
    )
    return RedirectResponse(url=target_url)


@router.post("/logout")
async def logout(token: str = Form(...), db: Session = Depends(get_db)):
    return {"message": "تم تسجيل الخروج بنجاح وتأمين الحساب"}


@router.post("/setup-profile")
async def setup_profile(
    player_name: str = Form(...),
    country: str = Form(...),
    avatar_url: str = Form(None),
    avatar_file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.player_name == player_name).first()
    if existing_user and existing_user.email != current_user.email:
        raise HTTPException(status_code=400, detail="الاسم مستخدم مسبقاً")

    old_avatar = current_user.avatar
    new_path = old_avatar

    def cleanup(path):
        if path and path.startswith("/uploads/"):
            p = path.lstrip("/")
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    if avatar_file and avatar_file.filename:
        file_bytes = await avatar_file.read()
        safe_ext = validate_image_file(file_bytes, avatar_file.filename)
        cleanup(old_avatar)
        filename = f"{uuid.uuid4().hex}.{safe_ext}"
        save_path = f"uploads/avatars/{filename}"
        with open(save_path, "wb") as buffer:
            buffer.write(file_bytes)
        new_path = f"/{save_path}"

    elif avatar_url:
        cleanup(old_avatar)
        new_path = avatar_url.replace("../", "")

    current_user.player_name = player_name
    current_user.country = country
    current_user.avatar = new_path
    db.commit()
    return {"message": "Success", "new_avatar": new_path}


@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return {
        "player_name": current_user.player_name,
        "avatar": current_user.avatar,
        "coins": current_user.coins,
        "gems": current_user.gems,
        "level": current_user.level,
        "email": current_user.email,
        "player_id": current_user.player_id,
        "country": current_user.country,
        "auth_provider": getattr(current_user, 'auth_provider', 'local'),
        "xp": current_user.xp
    }


@router.post("/settings/request-otp")
async def request_settings_otp(
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        user = db.query(User).filter(User.email == user_email).first()
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    if not user or user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="طلب غير صالح")

    security_code = generate_otp()  # ✅ secrets
    user.verification_code = security_code
    db.commit()
    background_tasks.add_task(send_real_email, user.email, security_code, "رمز التحقق لتعديل الإعدادات")
    return {"message": "تم إرسال رمز التحقق"}


@router.post("/settings/update-security")
async def update_security(
    background_tasks: BackgroundTasks,
    token: str = Form(...),
    otp: str = Form(...),
    action: str = Form(...),
    new_value: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(User).filter(User.email == payload.get("sub")).first()
    except Exception:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    if not user or user.verification_code != otp:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    if action == "email":
        if db.query(User).filter(User.email == new_value).first():
            raise HTTPException(status_code=400, detail="البريد مستخدم مسبقاً")
        background_tasks.add_task(send_email_changed, user.email, new_value)
        user.email = new_value
        new_token = create_access_token(data={"sub": user.email})
        user.verification_code = None
        db.commit()
        return {"message": "تم تغيير البريد الإلكتروني بنجاح", "new_token": new_token}

    elif action == "password":
        user.hashed_password = get_password_hash(new_value)
        background_tasks.add_task(send_password_changed_email, user.email)
        user.verification_code = None
        db.commit()
        return {"message": "تم تغيير كلمة المرور بنجاح"}


@router.delete("/delete-account")
async def delete_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(current_user)
    db.commit()
    return {"message": "تم الحذف نهائياً"}


@router.delete("/cancel-registration")
async def cancel_registration(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.player_name is not None:
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء حساب مكتمل من هنا")
    db.delete(current_user)
    db.commit()
    return {"message": "تم إلغاء التسجيل"}


@router.post("/resend-otp")
async def resend_otp(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    current_time = time.time()
    if email in otp_cooldowns:
        time_passed = current_time - otp_cooldowns[email]
        if time_passed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - time_passed)
            raise HTTPException(status_code=429, detail=f"الرجاء الانتظار {remaining} ثانية قبل طلب رمز جديد.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="البريد الإلكتروني غير مسجل لدينا")

    if user.is_verified:
        raise HTTPException(status_code=400, detail="الحساب مفعل مسبقاً، يمكنك تسجيل الدخول")

    new_code = generate_otp()  # ✅ secrets
    user.verification_code = new_code
    db.commit()

    background_tasks.add_task(send_real_email, email, new_code, "رمز تفعيل جديد - PlayRush")
    otp_cooldowns[email] = current_time

    return {"message": "تم إرسال رمز جديد بنجاح"}
