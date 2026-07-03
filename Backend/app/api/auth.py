import os
import re
import time
import uuid
import string
import secrets
import asyncio
import datetime
import httpx
from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks, UploadFile, File, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.security import get_db, get_current_user, get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM
from app.core.security import sanitize_text
from app.services.email_service import send_real_email, send_password_changed_email, send_email_changed, send_welcome_email
from app.core.database import User
from app.core.limiter import limiter

router = APIRouter()


# ==========================================
# 🛡️ Validators (يُستخدم في كل endpoint بحاجة validation)
# ==========================================
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def validate_email_format(email: str) -> str:
    """تنظيف وفحص الإيميل. يرجع الإيميل النظيف أو يرفع 400."""
    if not email or not isinstance(email, str):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مطلوب")
    cleaned = email.strip().lower()
    if len(cleaned) > 254 or len(cleaned) < 5:
        raise HTTPException(status_code=400, detail="طول البريد الإلكتروني غير صالح")
    if not EMAIL_REGEX.match(cleaned):
        raise HTTPException(status_code=400, detail="صيغة البريد الإلكتروني غير صالحة")
    return cleaned


def validate_password_strength(password: str):
    """فحص قوة كلمة المرور."""
    if not password or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="كلمة المرور مطلوبة")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")
    if len(password) > 72:  # حد bcrypt
        raise HTTPException(status_code=400, detail="كلمة المرور طويلة جداً (حد أقصى 72 حرفاً)")
    # يجب أن تحتوي على حرف ورقم على الأقل
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تحتوي على حروف وأرقام")


def validate_otp_code(code: str):
    """فحص صيغة OTP — يجب أن يكون 6 أرقام بالضبط."""
    if not code or not isinstance(code, str):
        raise HTTPException(status_code=400, detail="الرمز مطلوب")
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="صيغة الرمز غير صحيحة")
    return code

# ==========================================
# إعدادات رفع الصور (مُحكمة الأمان)
# ==========================================
# ❌ نمنع SVG لأنه XML قابل للتنفيذ (يحتوي JS embedded)
# ❌ نمنع GIF لأنه polyglot attacks (GIFAR) و decompression bombs
# ✅ jpg/png/webp فقط — صيغ ثنائية pure raster
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

# Magic bytes للصيغ المسموحة (يجب التطابق)
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_IMAGE_DIMENSIONS = 4096  # 4096×4096 كحد أقصى (يمنع decompression bomb)

UPLOAD_DIR = "uploads/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT")
# ⚠️ لازم يكون رابط الفرونت إند كامل (http://host:port) — بدون ده أي إعادة توجيه بعد
# تسجيل الدخول بجوجل هتكسر (كانت تتحول لسلسلة نصية "None" فعليًا). لازم تحدده في .env
FRONTEND_BASE_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")
if not FRONTEND_BASE_URL:
    import logging
    logging.getLogger("playrush").warning(
        "⚠️ FRONTEND_URL غير مضبوط في .env — تسجيل الدخول بجوجل سيفشل عند إعادة التوجيه! "
        "مثال: FRONTEND_URL=http://127.0.0.1:5500"
    )


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


def validate_image_file(file_bytes: bytes, original_filename: str) -> tuple[str, bytes]:
    """
    التحقق الأمني الكامل من الصورة (مُحكم) + إعادة encoding آمن:

    الفحوصات:
    1. حجم الملف (≤ 2 MB)
    2. الامتداد (whitelist: jpg/png/webp)
    3. Magic Bytes تطابق المحتوى
    4. الصورة قابلة للفتح فعلاً عبر Pillow (يكشف الملفات التالفة/الخبيثة)
    5. الأبعاد (≤ 4096×4096) لمنع decompression bombs
    6. ✨ إعادة encoding كامل عبر Pillow — يدمّر أي metadata/exploit مدفونة
       (مثل polyglot, EXIF malware, hidden scripts)

    يُرجع: (extension_safe, image_bytes_clean)
    """
    # 1. الحجم
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"حجم الصورة يتجاوز الحد المسموح ({MAX_FILE_SIZE_BYTES // 1024 // 1024} MB)"
        )

    if len(file_bytes) < 8:
        raise HTTPException(status_code=400, detail="الملف تالف أو فارغ")

    # 2. الامتداد
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"نوع الملف غير مسموح. الأنواع المقبولة: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 3. Magic Bytes (للأنواع التي لها توقيع ثابت)
    detected_type = None
    for signature, img_type in IMAGE_SIGNATURES.items():
        if file_bytes[:len(signature)] == signature:
            detected_type = img_type
            break

    # WebP له توقيع خاص (RIFF + WEBP)
    if detected_type is None and file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        detected_type = "webp"

    if detected_type is None:
        raise HTTPException(
            status_code=400,
            detail="محتوى الملف لا يطابق أي صيغة صورة معروفة. رُفض."
        )

    # تطابق الامتداد مع المحتوى الفعلي
    normalized_ext = "jpg" if ext == "jpeg" else ext
    if normalized_ext != detected_type:
        raise HTTPException(
            status_code=400,
            detail=f"الامتداد ({ext}) لا يتطابق مع المحتوى الحقيقي ({detected_type}). رُفض."
        )

    # 4 + 5 + 6: استخدام Pillow للفحص العميق وإعادة الـ encoding
    try:
        from PIL import Image
        import io
    except ImportError:
        # لو Pillow غير مثبت — على الأقل المراحل 1-3 تحمينا. لكن نحذّر.
        print("⚠️ [SECURITY] Pillow غير مثبت — لن نتمكن من فحص الأبعاد أو إعادة الترميز")
        return detected_type, file_bytes

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()  # فحص integrity
    except Exception:
        raise HTTPException(status_code=400, detail="الصورة تالفة أو خبيثة. رُفضت.")

    # نفتحها ثانية لأن verify() يقفل الـ image object
    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
    except Exception:
        raise HTTPException(status_code=400, detail="فشل قراءة أبعاد الصورة.")

    # 5. الأبعاد
    if width > MAX_IMAGE_DIMENSIONS or height > MAX_IMAGE_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"أبعاد الصورة كبيرة جداً (الحد {MAX_IMAGE_DIMENSIONS}×{MAX_IMAGE_DIMENSIONS}). رُفضت."
        )

    if width < 16 or height < 16:
        raise HTTPException(status_code=400, detail="أبعاد الصورة صغيرة جداً.")

    # 6. ✨ إعادة encoding — أهم خطوة أمنية
    # نُعيد كتابة الصورة من الـ pixel data فقط، فأي metadata خبيثة (EXIF, ICC profiles,
    # polyglot scripts, embedded HTML) تُمسح تماماً. الـ output صورة "نظيفة" 100%.
    output = io.BytesIO()
    save_format_map = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}
    save_format = save_format_map[detected_type]

    # تحويل لـ RGB لو JPEG (يدعم RGBA فقط في PNG/WebP)
    if detected_type == "jpg" and img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    elif detected_type == "jpg" and img.mode != "RGB":
        img = img.convert("RGB")

    save_kwargs = {}
    if save_format == "JPEG":
        save_kwargs = {"quality": 85, "optimize": True}
    elif save_format == "PNG":
        save_kwargs = {"optimize": True}
    elif save_format == "WEBP":
        save_kwargs = {"quality": 85, "method": 4}

    try:
        img.save(output, format=save_format, **save_kwargs)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"فشل معالجة الصورة: {e}")

    clean_bytes = output.getvalue()
    return detected_type, clean_bytes


def get_client_ip(request: Request) -> str:
    """جلب IP الحقيقي للمستخدم (يدعم reverse proxy)"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ==========================================
# Routes
# ==========================================

@router.post("/register")
@limiter.limit("5/hour")  # 🛡️ يمنع إنشاء عشرات الحسابات من نفس IP
async def register(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 🛡️ التحقق من صيغة الإيميل
    email_clean = validate_email_format(email)
    # 🛡️ التحقق من قوة كلمة المرور
    validate_password_strength(password)

    db_user = db.query(User).filter(User.email == email_clean).first()
    if db_user:
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجل مسبقاً!")

    # ✅ Hashing على thread منفصل لمنع حجب event loop (~100ms لـ bcrypt)
    hashed_password = await asyncio.to_thread(get_password_hash, password)
    verification_code = generate_otp()  # ✅ secrets

    new_user = User(
        email=email_clean,
        hashed_password=hashed_password,
        verification_code=verification_code,
        verification_code_expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=15),  # ✅ ينتهي بعد 15 دقيقة
        is_verified=False,
        coins=100,
        gems=3,
        level=0,
        player_id=generate_player_id(db)
    )
    db.add(new_user)
    db.commit()

    background_tasks.add_task(send_real_email, email_clean, verification_code)

    return {"message": "تم التسجيل بنجاح، يرجى التحقق من بريدك الإلكتروني"}


@router.post("/verify-code")
@limiter.limit("10/minute")  # 🛡️ يمنع brute force على OTP
async def verify_code(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    flow: str = Form("register"),
    db: Session = Depends(get_db)
):
    email_clean = validate_email_format(email)
    code_clean = validate_otp_code(code)

    user = db.query(User).filter(User.email == email_clean).first()
    if not user or user.verification_code != code_clean:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح أو الحساب غير موجود")

    # 🛡️ التحقق من انتهاء صلاحية الرمز (إن وُجد expiry)
    expires_at = getattr(user, 'verification_code_expires_at', None)
    if expires_at and expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="انتهت صلاحية الرمز. اطلب رمزاً جديداً.")

    if flow == "register":
        user.is_verified = True
        user.verification_code = None
        if hasattr(user, 'verification_code_expires_at'):
            user.verification_code_expires_at = None
        if not user.welcome_email_sent:
            background_tasks.add_task(send_welcome_email, user.email)
            user.welcome_email_sent = True
        db.commit()
        return {"message": "تم تفعيل الحساب بنجاح"}

    elif flow == "reset":
        return {"message": "الرمز صحيح"}


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    background_tasks: BackgroundTasks,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    from app.core.audit import log_login

    client_ip = get_client_ip(request)

    # 🛡️ تنظيف الإيميل
    try:
        email_clean = validate_email_format(form_data.username)
    except HTTPException:
        log_login(form_data.username[:50], client_ip, success=False, reason="invalid_email_format")
        raise HTTPException(status_code=400, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة")

    user = db.query(User).filter(User.email == email_clean).first()

    # ✅ verify_password على thread منفصل (bcrypt يستهلك CPU ~100ms)
    # نشغّلها حتى لو user=None لمنع timing attacks
    fake_hash = "$2b$12$KIXnT/xVc3OcWqJyxqGJl.ZyTrFRa5N5Q1xQ6w5h3xkZ1VYXrxHHC"
    target_hash = user.hashed_password if user else fake_hash
    is_valid = await asyncio.to_thread(verify_password, form_data.password, target_hash)

    if not user or not is_valid:
        log_login(email_clean, client_ip, success=False, reason="bad_credentials")
        raise HTTPException(status_code=400, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة")

    # 🛡️ التحقق من الحظر
    if getattr(user, 'is_banned', False):
        log_login(email_clean, client_ip, success=False, reason="banned_account")
        raise HTTPException(status_code=403, detail="تم حظر حسابك لانتهاك سياسات اللعب العادل والأمان.")

    if not user.is_verified:
        new_code = generate_otp()  # ✅ secrets
        user.verification_code = new_code
        if hasattr(user, 'verification_code_expires_at'):
            user.verification_code_expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
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
    log_login(user.email, client_ip, success=True)
    return {
        "message": "تم تسجيل الدخول بنجاح",
        "token": access_token,
        "token_type": "bearer",
        "has_profile": bool(user.player_name)
    }


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = validate_email_format(email)
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        # ✅ لا نكشف إذا كان البريد مسجلاً أم لا (user enumeration)
        return {"message": "إذا كان البريد مسجلاً، سيصلك رمز الاستعادة"}

    reset_code = generate_otp()  # ✅ secrets
    user.verification_code = reset_code
    if hasattr(user, 'verification_code_expires_at'):
        user.verification_code_expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    db.commit()

    background_tasks.add_task(send_real_email, email_clean, reset_code, "إعادة تعيين كلمة المرور")
    return {"message": "إذا كان البريد مسجلاً، سيصلك رمز الاستعادة"}


@router.post("/reset-password")
@limiter.limit("5/minute")  # 🛡️ يمنع brute force على reset
async def reset_password(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = validate_email_format(email)
    code_clean = validate_otp_code(code)
    validate_password_strength(new_password)

    user = db.query(User).filter(User.email == email_clean).first()
    if not user or user.verification_code != code_clean:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    # 🛡️ التحقق من انتهاء صلاحية الرمز
    expires_at = getattr(user, 'verification_code_expires_at', None)
    if expires_at and expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="انتهت صلاحية الرمز. اطلب رمزاً جديداً.")

    # ✅ verify_password على thread (bcrypt)
    is_same = await asyncio.to_thread(verify_password, new_password, user.hashed_password)
    if is_same:
        raise HTTPException(status_code=400, detail="كلمة المرور مطابقة للقديمة")

    # ✅ get_password_hash على thread (bcrypt يحجز ~100ms)
    user.hashed_password = await asyncio.to_thread(get_password_hash, new_password)
    user.verification_code = None
    if hasattr(user, 'verification_code_expires_at'):
        user.verification_code_expires_at = None
    db.commit()
    background_tasks.add_task(send_password_changed_email, email_clean)
    return {"message": "تم تغيير كلمة المرور بنجاح"}


@router.get("/google/login")
@limiter.limit("10/minute")  # 🛡️ يمنع redirect spam
async def google_login(request: Request):
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
@limiter.limit("10/minute")  # 🛡️ يمنع abuse
async def google_callback(request: Request, code: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    # ✅ timeout 10 ثوان لمنع تعليق السيرفر إذا Google API بطيء أو down
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(token_url, data=token_data)
            if token_response.status_code != 200:
                raise HTTPException(status_code=502, detail="فشل التواصل مع Google OAuth")
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="لم يُستلم access token من Google")

            user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {"Authorization": f"Bearer {access_token}"}
            user_info_response = await client.get(user_info_url, headers=headers)
            if user_info_response.status_code != 200:
                raise HTTPException(status_code=502, detail="فشل جلب بيانات المستخدم من Google")
            user_info = user_info_response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="انتهت مهلة الاتصال بـ Google. حاول مرة أخرى.")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"خطأ شبكة مع Google: {str(e)[:50]}")

    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="حساب Google لا يحتوي على بريد إلكتروني")
    user = db.query(User).filter(User.email == email).first()
    needs_profile_setup = False

    # 🛡️ الحماية من الحظر للاعبي جوجل — نوجّه لصفحة الحظر اللائقة بدل JSON خام
    if user and getattr(user, 'is_banned', False):
        ban_msg = "تم تقييد حسابك بسبب مخالفة سياسات اللعب العادل والأمان."
        from urllib.parse import quote
        return RedirectResponse(
            url=f"{FRONTEND_BASE_URL}/banned.html?reason={quote(ban_msg)}"
        )

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
@limiter.limit("10/hour")  # 🛡️ يمنع spam لرفع الصور وتغيير الاسم
async def setup_profile(
    request: Request,
    player_name: str = Form(...),
    country: str = Form(...),
    avatar_url: str = Form(None),
    avatar_file: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 🛡️ تنظيف النصوص من XSS قبل أي شيء
    safe_player_name = sanitize_text(player_name, max_length=20)
    safe_country = sanitize_text(country, max_length=50)

    # 🛡️ فحص اسم اللاعب: 3-20 حرف، حروف وأرقام و _ فقط (لا spaces في البداية/النهاية)
    if not safe_player_name or len(safe_player_name) < 3:
        raise HTTPException(status_code=400, detail="اسم اللاعب يجب أن يكون 3 أحرف على الأقل")
    if not re.match(r'^[\w\u0600-\u06FF][\w\u0600-\u06FF\s]{1,18}[\w\u0600-\u06FF]$', safe_player_name):
        raise HTTPException(status_code=400, detail="اسم اللاعب يحتوي على رموز غير مسموحة")

    # 🛡️ فلتر المحتوى المسيء في الاسم (يطبّق بند الشروط)
    from app.core.content_filter import is_name_allowed
    _name_check = is_name_allowed(safe_player_name)
    if not _name_check['clean']:
        raise HTTPException(status_code=400, detail=f"اسم اللاعب غير مسموح: {_name_check['reason']}")

    existing_user = db.query(User).filter(User.player_name == safe_player_name).first()
    if existing_user and existing_user.email != current_user.email:
        raise HTTPException(status_code=400, detail="الاسم مستخدم مسبقاً")

    old_avatar = current_user.avatar
    new_path = old_avatar

    def cleanup(path):
        """
        🛡️ يمسح الأفاتار القديم بأمان كامل ضد path traversal.
        نستخدم realpath للتأكد إن الملف فعلاً داخل /uploads/avatars/ بعد resolve كل symlinks و '..'.
        """
        if not path or not path.startswith("/uploads/"):
            return
        try:
            p = path.lstrip("/")
            # احصل على المسار المطلق المُحلّل
            abs_target = os.path.realpath(p)
            abs_uploads = os.path.realpath("uploads/avatars")
            # تأكد إن المسار فعلاً داخل uploads/avatars
            if not abs_target.startswith(abs_uploads + os.sep):
                print(f"⚠️ [SECURITY] محاولة حذف ملف خارج uploads/avatars: {abs_target}")
                return
            if os.path.exists(abs_target) and os.path.isfile(abs_target):
                os.remove(abs_target)
        except Exception as e:
            print(f"⚠️ cleanup error: {e}")

    if avatar_file and avatar_file.filename:
        # 🔒 رفع الصور المخصصة مُعطّل حالياً (ميزة مؤجّلة) — لمنع المحتوى المسيء.
        # يُقبل فقط الأفاتارات الجاهزة عبر avatar_url. (الكود محفوظ للإرجاع المستقبلي).
        raise HTTPException(
            status_code=403,
            detail="رفع الصور المخصصة غير متاح حالياً. اختر من الأفاتارات الجاهزة."
        )

    elif avatar_url:
        # ✅ إصلاح ثغرات path traversal + XSS + SSRF في avatar_url:
        # نقبل فقط مسارات الأفاتارات الافتراضية الموجودة في FrontEnd/assets/avatars/
        # بصيغة آمنة بالضبط: "assets/avatars/avatar_<N>.svg" (بدون أي رموز خاصة)
        avatar_pattern = re.compile(r'^(?:\.\./)?assets/avatars/avatar_\d{1,3}\.svg$')

        if not avatar_pattern.match(avatar_url):
            raise HTTPException(
                status_code=400,
                detail="رابط الأفاتار غير صالح. يجب أن يكون أفاتار افتراضي من قائمة المنصة."
            )

        # نطبّع المسار: نشيل الـ "../" إن وُجدت
        normalized = avatar_url.replace("../", "")

        # تأكد إضافي بعد التطبيع
        if not re.match(r'^assets/avatars/avatar_\d{1,3}\.svg$', normalized):
            raise HTTPException(status_code=400, detail="رابط الأفاتار غير صالح بعد التطبيع.")

        cleanup(old_avatar)
        new_path = normalized

    current_user.player_name = safe_player_name
    current_user.country = safe_country
    current_user.avatar = new_path
    db.commit()
    return {"message": "Success", "new_avatar": new_path}


@router.get("/me")
@limiter.limit("60/minute")  # 🛡️ يمنع profile scraping
async def get_my_profile(
    request: Request,
    current_user: User = Depends(get_current_user),
):
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
@limiter.limit("3/minute")  # 🛡️ يمنع spam emails
async def request_settings_otp(
    request: Request,
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
    if hasattr(user, 'verification_code_expires_at'):
        user.verification_code_expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    db.commit()
    background_tasks.add_task(send_real_email, user.email, security_code, "رمز التحقق لتعديل الإعدادات")
    return {"message": "تم إرسال رمز التحقق"}


@router.post("/settings/update-security")
@limiter.limit("5/minute")  # 🛡️ يمنع brute force على OTP
async def update_security(
    request: Request,
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

    otp_clean = validate_otp_code(otp)
    if not user or user.verification_code != otp_clean:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    # 🛡️ التحقق من انتهاء صلاحية الـ OTP
    expires_at = getattr(user, 'verification_code_expires_at', None)
    if expires_at and expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="انتهت صلاحية الرمز. اطلب رمزاً جديداً.")

    if action == "email":
        new_email = validate_email_format(new_value)
        if db.query(User).filter(User.email == new_email).first():
            raise HTTPException(status_code=400, detail="البريد مستخدم مسبقاً")
        background_tasks.add_task(send_email_changed, user.email, new_email)
        user.email = new_email
        new_token = create_access_token(data={"sub": user.email})
        user.verification_code = None
        if hasattr(user, 'verification_code_expires_at'):
            user.verification_code_expires_at = None
        db.commit()
        return {"message": "تم تغيير البريد الإلكتروني بنجاح", "new_token": new_token}

    elif action == "password":
        validate_password_strength(new_value)
        # ✅ bcrypt على thread
        user.hashed_password = await asyncio.to_thread(get_password_hash, new_value)
        background_tasks.add_task(send_password_changed_email, user.email)
        user.verification_code = None
        if hasattr(user, 'verification_code_expires_at'):
            user.verification_code_expires_at = None
        db.commit()
        return {"message": "تم تغيير كلمة المرور بنجاح"}

    else:
        raise HTTPException(status_code=400, detail="عملية غير مدعومة")


@router.delete("/delete-account")
@limiter.limit("3/hour")  # 🛡️ نادراً ما يحدث، rate limit للحماية
async def delete_account(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(current_user)
    db.commit()
    return {"message": "تم الحذف نهائياً"}


@router.delete("/cancel-registration")
@limiter.limit("5/hour")
async def cancel_registration(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.player_name is not None:
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء حساب مكتمل من هنا")
    db.delete(current_user)
    db.commit()
    return {"message": "تم إلغاء التسجيل"}


@router.post("/resend-otp")
@limiter.limit("3/minute")  # 🛡️ يمنع spam emails
async def resend_otp(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    email_clean = validate_email_format(email)
    user = db.query(User).filter(User.email == email_clean).first()
    if not user:
        # ✅ نخفي وجود الحساب لمنع enumeration (نفس فلسفة forgot-password)
        return {"message": "إذا كان البريد مسجلاً، سيصلك رمز جديد"}

    if user.is_verified:
        raise HTTPException(status_code=400, detail="الحساب مفعل مسبقاً، يمكنك تسجيل الدخول")

    new_code = generate_otp()  # ✅ secrets
    user.verification_code = new_code
    if hasattr(user, 'verification_code_expires_at'):
        user.verification_code_expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    db.commit()

    background_tasks.add_task(send_real_email, email_clean, new_code, "رمز تفعيل جديد - PlayRush")

    return {"message": "تم إرسال رمز جديد بنجاح"}


# ==========================================
# 🛡️ Anti-Cheat: حظر فوري عبر REST
# يستخدمه الـ anti_cheat.js لضمان الحظر حتى لو السوكيت غير متصل
# ==========================================
@router.post("/self-ban", tags=["Anti-Cheat"])
@limiter.limit("5/minute")
async def self_ban(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    🚫 يحظر اللاعب الذي تجاوز محاولات فتح أدوات المطور.
    يُستدعى من الفرونت (anti_cheat.js) عند الوصول لـ MAX_CHEAT_ATTEMPTS.

    ملاحظة: لا نستخدم get_current_user هنا لأنها ترفض المحظور بـ 403،
    وهنا نريد فقط فك التوكن وتحديد المستخدم لحظره (إن لم يكن محظوراً).
    """
    # استخراج التوكن من Authorization أو query أو form
    token = None
    if request.query_params.get("token"):
        token = request.query_params.get("token")
    elif request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    else:
        try:
            form = await request.form()
            token = form.get("token")
        except Exception:
            pass

    if not token:
        raise HTTPException(status_code=401, detail="التوكن مفقود")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    if not getattr(user, 'is_banned', False):
        user.is_banned = True
        db.commit()
        print(f"🚫 [self-ban] حظر {user.player_name} | السبب: DevTools breach")

    return {"message": "تم تطبيق الحظر", "banned": True}


# ==========================================
# 🛡️ Anti-Cheat: تقرير محاولة (قبل الـ ban)
# ==========================================
@router.post("/anticheat-report", tags=["Anti-Cheat"])
@limiter.limit("20/minute")  # حد عالي للسماح بالتقارير المتعددة
async def anticheat_report(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    📊 يستقبل تقارير anti-cheat من الفرونت (warning level).
    يسجلها في DB للمراجعة + يزيد violation_score.
    عند تراكم تقارير → ban تلقائي.
    """
    import logging
    anticheat_logger = logging.getLogger("playrush.anticheat")

    # استخراج التوكن
    token = None
    if request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    try:
        form = await request.form()
        if not token:
            token = form.get("token")
        reason = form.get("reason", "unknown")
    except Exception:
        return {"received": False}

    if not token:
        return {"received": False}

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
    except JWTError:
        return {"received": False}

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        return {"received": False}

    # 🛠️ في وضع التطوير: نسجّل فقط، لا نحظر ولا نزيد score
    from app.core.dev_mode import is_dev_mode
    if is_dev_mode():
        return {"received": True, "dev_mode": True, "score": getattr(user, 'anticheat_score', 0) or 0}

    # IP للتتبع
    client_ip = get_client_ip(request)

    anticheat_logger.warning(
        f"🚨 [anticheat-report] user={user.email} ip={client_ip} reason={reason[:200]}"
    )

    # الفرونت يدير منطق الـ 3 محاولات ويرسل executeBan صراحةً عند تجاوزها.
    # هذا الـ endpoint يسجّل فقط للمراقبة + حدّ احتياطي عالٍ (10) لمنع التلاعب الصريح.
    current_score = getattr(user, 'anticheat_score', 0) or 0
    new_score = current_score + 1

    if hasattr(user, 'anticheat_score'):
        user.anticheat_score = new_score
        # حدّ احتياطي عالٍ فقط (الحظر الفعلي يأتي من /auth/self-ban بعد 3 محاولات فرونت)
        if new_score >= 10 and not user.is_banned:
            user.is_banned = True
            anticheat_logger.error(
                f"🚫 [anticheat] auto-ban user={user.email} after 10+ reports (احتياطي)"
            )
        db.commit()

    return {"received": True, "score": new_score}


# ==========================================
# 🔍 Ban Status Check — مصدر الحقيقة الوحيد
# الفرونت يستدعيه عند تحميل أي صفحة ليتأكد من حالة الحظر
# الهدف: لو الأدمن فك الحظر في DB، يُسمح للاعب بالدخول مباشرة
# بدون الحاجة لمسح localStorage يدوياً
# ==========================================
@router.get("/ban-status", tags=["Anti-Cheat"])
@limiter.limit("60/minute")
async def ban_status(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    🔍 يفحص حالة الحظر الحالية للمستخدم.

    لا يحتاج auth (يعمل حتى لو التوكن منتهي):
    - يستخرج التوكن إن وُجد
    - يفك ترميزه (بدون التحقق من expiry — نريد الحالة فقط)
    - يفحص is_banned في DB

    Returns:
        { "banned": false } لو غير محظور
        { "banned": true, "reason": "..." } لو محظور
    """
    token = None
    if request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
    elif request.query_params.get("token"):
        token = request.query_params.get("token")

    if not token:
        # لا يوجد توكن = ليس محظوراً (لاعب جديد محتمل)
        from app.core.dev_mode import is_dev_mode
        return {"banned": False, "reason": "no_token", "dev_mode": is_dev_mode()}

    try:
        # ✅ نفك التوكن بدون التحقق من expiry
        # (نريد فقط الـ email حتى لو التوكن منتهي)
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            options={"verify_exp": False}
        )
        user_email = payload.get("sub")
    except JWTError:
        return {"banned": False, "reason": "invalid_token"}

    if not user_email:
        return {"banned": False, "reason": "no_email"}

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        return {"banned": False, "reason": "user_not_found"}

    # 🛠️ وضع التطوير من .env (يُقرأ لحظياً) — مصدر موثوق، اللاعب لا يتحكم به
    from app.core.dev_mode import is_dev_mode
    _dev = is_dev_mode()

    if user.is_banned:
        return {
            "banned": True,
            "reason": "account_banned",
            "anticheat_score": getattr(user, 'anticheat_score', 0) or 0,
            "dev_mode": _dev,
        }

    # ✅ غير محظور — السيرفر هو المصدر الموثوق
    return {"banned": False, "dev_mode": _dev}