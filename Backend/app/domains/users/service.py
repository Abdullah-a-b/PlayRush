import os
import re
import string
import secrets
import asyncio
import datetime
import logging

import httpx
from fastapi import HTTPException, BackgroundTasks
from jose import jwt, JWTError

from app.core.security import (
    get_password_hash, verify_password, create_access_token,
    sanitize_text, SECRET_KEY, ALGORITHM,
)
from app.core.content_filter import is_name_allowed
from app.core.audit import log_login
from app.core.dev_mode import is_dev_mode
from app.infrastructure.email_service import (
    send_real_email, send_password_changed_email, send_email_changed, send_welcome_email,
)
from app.domains.users.models import User
from app.domains.users.repository import UserRepository
from app.domains.users.validators import (
    validate_email_format, validate_password_strength, validate_otp_code,
    PLAYER_NAME_REGEX,
)
from app.domains.users.avatar import validate_default_avatar_url, remove_old_avatar

logger = logging.getLogger("playrush")
anticheat_logger = logging.getLogger("playrush.anticheat")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT")

# يجب أن يكون رابط الواجهة كاملاً (http://host:port) وإلا تنكسر إعادة
# التوجيه بعد تسجيل الدخول بجوجل. يُضبط في .env
FRONTEND_BASE_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")
# مخطط الرابط العميق للتطبيق (يطابق ما هو مسجّل في AndroidManifest)
APP_DEEP_LINK_SCHEME = os.environ.get("APP_DEEP_LINK_SCHEME", "playrush")
if not FRONTEND_BASE_URL:
    logger.warning(
        "FRONTEND_URL غير مضبوط في .env — تسجيل الدخول بجوجل سيفشل عند إعادة التوجيه. "
        "مثال: FRONTEND_URL=http://127.0.0.1:5500"
    )

OTP_TTL_MINUTES = 15
SIGNUP_BONUS = {"coins": 100, "gems": 3, "level": 0}

# هاش وهمي يُستخدم عند غياب المستخدم لتوحيد زمن التحقق (يمنع timing attacks)
_FAKE_BCRYPT_HASH = "$2b$12$KIXnT/xVc3OcWqJyxqGJl.ZyTrFRa5N5Q1xQ6w5h3xkZ1VYXrxHHC"


def generate_otp() -> str:
    """رمز تحقق من 6 أرقام عبر secrets."""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def _otp_expiry():
    return datetime.datetime.utcnow() + datetime.timedelta(minutes=OTP_TTL_MINUTES)


def _set_otp(user: User, code: str):
    user.verification_code = code
    if hasattr(user, 'verification_code_expires_at'):
        user.verification_code_expires_at = _otp_expiry()


def _clear_otp(user: User):
    user.verification_code = None
    if hasattr(user, 'verification_code_expires_at'):
        user.verification_code_expires_at = None


def _ensure_otp_not_expired(user: User):
    expires_at = getattr(user, 'verification_code_expires_at', None)
    if expires_at and expires_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="انتهت صلاحية الرمز. اطلب رمزاً جديداً.")


def _decode_token_email(token: str, verify_exp: bool = True) -> str | None:
    try:
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            options={"verify_exp": verify_exp},
        )
        return payload.get("sub")
    except JWTError:
        return None


async def register_user(repo: UserRepository, background_tasks: BackgroundTasks,
                        email: str, password: str) -> dict:
    email_clean = validate_email_format(email)
    validate_password_strength(password)

    if repo.email_exists(email_clean):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مسجل مسبقاً!")

    # التجزئة على thread منفصل لأن bcrypt يحجب event loop نحو 100ms
    hashed_password = await asyncio.to_thread(get_password_hash, password)
    verification_code = generate_otp()

    new_user = User(
        email=email_clean,
        hashed_password=hashed_password,
        verification_code=verification_code,
        verification_code_expires_at=_otp_expiry(),
        is_verified=False,
        player_id=repo.generate_unique_player_id(),
        **SIGNUP_BONUS,
    )
    repo.add(new_user)

    background_tasks.add_task(send_real_email, email_clean, verification_code)
    return {"message": "تم التسجيل بنجاح، يرجى التحقق من بريدك الإلكتروني"}


def verify_account_code(repo: UserRepository, background_tasks: BackgroundTasks,
                        email: str, code: str, flow: str):
    email_clean = validate_email_format(email)
    code_clean = validate_otp_code(code)

    user = repo.get_by_email(email_clean)
    if not user or user.verification_code != code_clean:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح أو الحساب غير موجود")

    _ensure_otp_not_expired(user)

    if flow == "register":
        user.is_verified = True
        _clear_otp(user)
        if not user.welcome_email_sent:
            background_tasks.add_task(send_welcome_email, user.email)
            user.welcome_email_sent = True
        repo.commit()
        return {"message": "تم تفعيل الحساب بنجاح"}

    elif flow == "reset":
        return {"message": "الرمز صحيح"}


async def login_user(repo: UserRepository, background_tasks: BackgroundTasks,
                     username: str, password: str, client_ip: str) -> dict:
    """يرجع dict فيه المفتاح action عند الحاجة لتوجيه خاص (حساب غير مفعّل)."""
    try:
        email_clean = validate_email_format(username)
    except HTTPException:
        log_login(username[:50], client_ip, success=False, reason="invalid_email_format")
        raise HTTPException(status_code=400, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة")

    user = repo.get_by_email(email_clean)

    # نتحقق حتى لو المستخدم غير موجود لتوحيد زمن الاستجابة
    target_hash = user.hashed_password if user else _FAKE_BCRYPT_HASH
    is_valid = await asyncio.to_thread(verify_password, password, target_hash)

    if not user or not is_valid:
        log_login(email_clean, client_ip, success=False, reason="bad_credentials")
        raise HTTPException(status_code=400, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة")

    if getattr(user, 'is_banned', False):
        log_login(email_clean, client_ip, success=False, reason="banned_account")
        raise HTTPException(status_code=403, detail="تم حظر حسابك لانتهاك سياسات اللعب العادل والأمان.")

    if not user.is_verified:
        new_code = generate_otp()
        _set_otp(user, new_code)
        repo.commit()
        background_tasks.add_task(send_real_email, user.email, new_code)
        return {
            "action": "redirect_to_verify",
            "email": user.email,
            "detail": "حسابك غير مفعل. تم إرسال كود تحقق جديد إلى بريدك، جاري التوجيه...",
        }

    access_token = create_access_token(data={"sub": user.email})
    log_login(user.email, client_ip, success=True)
    return {
        "message": "تم تسجيل الدخول بنجاح",
        "token": access_token,
        "token_type": "bearer",
        "has_profile": bool(user.player_name),
    }


def request_password_reset(repo: UserRepository, background_tasks: BackgroundTasks,
                           email: str) -> dict:
    email_clean = validate_email_format(email)
    user = repo.get_by_email(email_clean)
    # رسالة موحدة سواء وُجد البريد أم لا (يمنع user enumeration)
    generic = {"message": "إذا كان البريد مسجلاً، سيصلك رمز الاستعادة"}
    if not user:
        return generic

    reset_code = generate_otp()
    _set_otp(user, reset_code)
    repo.commit()

    background_tasks.add_task(send_real_email, email_clean, reset_code, "إعادة تعيين كلمة المرور")
    return generic


async def reset_password(repo: UserRepository, background_tasks: BackgroundTasks,
                         email: str, code: str, new_password: str) -> dict:
    email_clean = validate_email_format(email)
    code_clean = validate_otp_code(code)
    validate_password_strength(new_password)

    user = repo.get_by_email(email_clean)
    if not user or user.verification_code != code_clean:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    _ensure_otp_not_expired(user)

    is_same = await asyncio.to_thread(verify_password, new_password, user.hashed_password)
    if is_same:
        raise HTTPException(status_code=400, detail="كلمة المرور مطابقة للقديمة")

    user.hashed_password = await asyncio.to_thread(get_password_hash, new_password)
    _clear_otp(user)
    repo.commit()
    background_tasks.add_task(send_password_changed_email, email_clean)
    return {"message": "تم تغيير كلمة المرور بنجاح"}


def build_google_auth_url(client: str = "web") -> str:
    """يبني رابط مصادقة جوجل.
    client="app" يعني أن الطلب صادر من تطبيق Capacitor، فنمرّره داخل state
    ليعرف الـcallback أن يعيد التوجيه إلى رابط عميق بدل موقع الويب."""
    state = "app" if client == "app" else "web"
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?response_type=code"
        f"&client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&state={state}"
    )


async def handle_google_callback(repo: UserRepository, background_tasks: BackgroundTasks,
                                 code: str, state: str = "web") -> str:
    """يبادل الكود مع Google ويرجع رابط إعادة التوجيه النهائي للواجهة."""
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    # timeout يمنع تعليق السيرفر إذا كان Google API بطيئاً أو متوقفاً
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(token_url, data=token_data)
            if token_response.status_code != 200:
                raise HTTPException(status_code=502, detail="فشل التواصل مع Google OAuth")
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="لم يُستلم access token من Google")

            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
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

    user = repo.get_by_email(email)
    needs_profile_setup = False

    # المحظور يُوجَّه لصفحة الحظر بدل JSON خام
    if user and getattr(user, 'is_banned', False):
        from urllib.parse import quote
        ban_msg = "تم تقييد حسابك بسبب مخالفة سياسات اللعب العادل والأمان."
        return f"{FRONTEND_BASE_URL}/banned.html?reason={quote(ban_msg)}"

    if not user:
        needs_profile_setup = True
        random_password = secrets.token_urlsafe(24)
        user = repo.add(User(
            email=email,
            hashed_password=get_password_hash(random_password),
            is_verified=True,
            welcome_email_sent=True,
            auth_provider="google",
            player_id=repo.generate_unique_player_id(),
            **SIGNUP_BONUS,
        ))
        background_tasks.add_task(send_welcome_email, user.email)
    elif not user.player_name:
        needs_profile_setup = True

    playrush_token = create_access_token(data={"sub": user.email})
    page = "profile-setup" if needs_profile_setup else "categories"

    # 📱 طلب صادر من التطبيق → رابط عميق يعيد التوكن للتطبيق نفسه
    # (بدل موقع الويب، وإلا انتهت الجلسة داخل المتصفح خارج التطبيق)
    if state == "app":
        return f"{APP_DEEP_LINK_SCHEME}://auth?token={playrush_token}&page={page}"

    return f"{FRONTEND_BASE_URL}/{page}.html?token={playrush_token}"


def setup_profile(repo: UserRepository, current_user: User, player_name: str,
                  country: str, avatar_url: str | None, has_avatar_file: bool) -> dict:
    # تنظيف النصوص من XSS قبل أي شيء
    safe_player_name = sanitize_text(player_name, max_length=20)
    safe_country = sanitize_text(country, max_length=50)

    if not safe_player_name or len(safe_player_name) < 3:
        raise HTTPException(status_code=400, detail="اسم اللاعب يجب أن يكون 3 أحرف على الأقل")
    if not PLAYER_NAME_REGEX.match(safe_player_name):
        raise HTTPException(status_code=400, detail="اسم اللاعب يحتوي على رموز غير مسموحة")

    # فلتر المحتوى المسيء في الاسم (تطبيقاً لبنود الشروط)
    name_check = is_name_allowed(safe_player_name)
    if not name_check['clean']:
        raise HTTPException(status_code=400, detail=f"اسم اللاعب غير مسموح: {name_check['reason']}")

    existing_user = repo.get_by_player_name(safe_player_name)
    if existing_user and existing_user.email != current_user.email:
        raise HTTPException(status_code=400, detail="الاسم مستخدم مسبقاً")

    old_avatar = current_user.avatar
    new_path = old_avatar

    if has_avatar_file:
        # رفع الصور المخصصة مُعطّل حالياً لمنع المحتوى المسيء —
        # يُقبل فقط الأفاتار الجاهز عبر avatar_url
        raise HTTPException(
            status_code=403,
            detail="رفع الصور المخصصة غير متاح حالياً. اختر من الأفاتارات الجاهزة."
        )

    elif avatar_url:
        normalized = validate_default_avatar_url(avatar_url)
        remove_old_avatar(old_avatar)
        new_path = normalized

    current_user.player_name = safe_player_name
    current_user.country = safe_country
    current_user.avatar = new_path
    repo.commit()
    return {"message": "Success", "new_avatar": new_path}


def build_profile_response(user: User) -> dict:
    return {
        "player_name": user.player_name,
        "avatar": user.avatar,
        "coins": user.coins,
        "gems": user.gems,
        "level": user.level,
        "email": user.email,
        "player_id": user.player_id,
        "country": user.country,
        "auth_provider": getattr(user, 'auth_provider', 'local'),
        "xp": user.xp,
    }


def request_settings_otp(repo: UserRepository, background_tasks: BackgroundTasks,
                         token: str) -> dict:
    user_email = _decode_token_email(token)
    if user_email is None:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")
    user = repo.get_by_email(user_email)

    if not user or user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="طلب غير صالح")

    security_code = generate_otp()
    _set_otp(user, security_code)
    repo.commit()
    background_tasks.add_task(send_real_email, user.email, security_code, "رمز التحقق لتعديل الإعدادات")
    return {"message": "تم إرسال رمز التحقق"}


async def update_security(repo: UserRepository, background_tasks: BackgroundTasks,
                          token: str, otp: str, action: str, new_value: str) -> dict:
    user_email = _decode_token_email(token)
    user = repo.get_by_email(user_email) if user_email else None
    if user_email is None:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    otp_clean = validate_otp_code(otp)
    if not user or user.verification_code != otp_clean:
        raise HTTPException(status_code=400, detail="الرمز غير صحيح")

    _ensure_otp_not_expired(user)

    if action == "email":
        new_email = validate_email_format(new_value)
        if repo.email_exists(new_email):
            raise HTTPException(status_code=400, detail="البريد مستخدم مسبقاً")
        background_tasks.add_task(send_email_changed, user.email, new_email)
        user.email = new_email
        new_token = create_access_token(data={"sub": user.email})
        _clear_otp(user)
        repo.commit()
        return {"message": "تم تغيير البريد الإلكتروني بنجاح", "new_token": new_token}

    elif action == "password":
        validate_password_strength(new_value)
        user.hashed_password = await asyncio.to_thread(get_password_hash, new_value)
        background_tasks.add_task(send_password_changed_email, user.email)
        _clear_otp(user)
        repo.commit()
        return {"message": "تم تغيير كلمة المرور بنجاح"}

    raise HTTPException(status_code=400, detail="عملية غير مدعومة")


def delete_account(repo: UserRepository, user: User) -> dict:
    repo.delete(user)
    return {"message": "تم الحذف نهائياً"}


def cancel_registration(repo: UserRepository, user: User) -> dict:
    if user.player_name is not None:
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء حساب مكتمل من هنا")
    repo.delete(user)
    return {"message": "تم إلغاء التسجيل"}


def resend_otp(repo: UserRepository, background_tasks: BackgroundTasks, email: str) -> dict:
    email_clean = validate_email_format(email)
    user = repo.get_by_email(email_clean)
    if not user:
        # نخفي وجود الحساب لمنع enumeration (نفس منطق forgot-password)
        return {"message": "إذا كان البريد مسجلاً، سيصلك رمز جديد"}

    if user.is_verified:
        raise HTTPException(status_code=400, detail="الحساب مفعل مسبقاً، يمكنك تسجيل الدخول")

    new_code = generate_otp()
    _set_otp(user, new_code)
    repo.commit()

    background_tasks.add_task(send_real_email, email_clean, new_code, "رمز تفعيل جديد - PlayRush")
    return {"message": "تم إرسال رمز جديد بنجاح"}


def self_ban(repo: UserRepository, token: str | None) -> dict:
    """حظر اللاعب الذي تجاوز محاولات فتح أدوات المطور.

    لا نستخدم get_current_user هنا لأنها ترفض المحظور بـ 403،
    والمطلوب فقط فك التوكن وتحديد المستخدم لحظره إن لم يكن محظوراً.
    """
    if not token:
        raise HTTPException(status_code=401, detail="التوكن مفقود")

    user_email = _decode_token_email(token)
    if user_email is None:
        raise HTTPException(status_code=401, detail="التوكن غير صالح")

    user = repo.get_by_email(user_email)
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    if not getattr(user, 'is_banned', False):
        user.is_banned = True
        repo.commit()
        print(f"[self-ban] حظر {user.player_name} | السبب: DevTools breach")

    return {"message": "تم تطبيق الحظر", "banned": True}


def record_anticheat_report(repo: UserRepository, token: str | None,
                            reason: str, client_ip: str) -> dict:
    """يستقبل تقارير anti-cheat من الواجهة ويسجلها ويزيد violation_score.

    الواجهة تدير منطق المحاولات الثلاث وترسل self-ban صراحةً عند تجاوزها؛
    هذا المسار يسجّل للمراقبة فقط مع حدّ احتياطي عالٍ (10) لمنع التلاعب الصريح.
    """
    if not token:
        return {"received": False}

    user_email = _decode_token_email(token)
    if user_email is None:
        return {"received": False}

    user = repo.get_by_email(user_email)
    if not user:
        return {"received": False}

    # في وضع التطوير: تسجيل فقط، بلا حظر وبلا زيادة score
    if is_dev_mode():
        return {"received": True, "dev_mode": True, "score": getattr(user, 'anticheat_score', 0) or 0}

    anticheat_logger.warning(
        f"[anticheat-report] user={user.email} ip={client_ip} reason={reason[:200]}"
    )

    current_score = getattr(user, 'anticheat_score', 0) or 0
    new_score = current_score + 1

    if hasattr(user, 'anticheat_score'):
        user.anticheat_score = new_score
        if new_score >= 10 and not user.is_banned:
            user.is_banned = True
            anticheat_logger.error(
                f"[anticheat] auto-ban user={user.email} بعد 10+ تقارير (حد احتياطي)"
            )
        repo.commit()

    return {"received": True, "score": new_score}


def check_ban_status(repo: UserRepository, token: str | None) -> dict:
    """يفحص حالة الحظر الحالية — مصدر الحقيقة الوحيد للواجهة.

    لا يحتاج مصادقة كاملة: يفك التوكن دون التحقق من الانتهاء لأن المطلوب
    الحالة فقط، فلو فكّ الأدمن الحظر في قاعدة البيانات يدخل اللاعب مباشرة
    دون مسح localStorage يدوياً.
    """
    if not token:
        # لا توكن = ليس محظوراً (لاعب جديد محتمل)
        return {"banned": False, "reason": "no_token", "dev_mode": is_dev_mode()}

    try:
        # فك التوكن دون التحقق من الانتهاء — نريد البريد فقط
        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
        user_email = payload.get("sub")
    except JWTError:
        return {"banned": False, "reason": "invalid_token"}

    if not user_email:
        return {"banned": False, "reason": "no_email"}

    user = repo.get_by_email(user_email)
    if not user:
        return {"banned": False, "reason": "user_not_found"}

    _dev = is_dev_mode()

    if user.is_banned:
        return {
            "banned": True,
            "reason": "account_banned",
            "anticheat_score": getattr(user, 'anticheat_score', 0) or 0,
            "dev_mode": _dev,
        }

    # غير محظور — السيرفر هو المصدر الموثوق
    return {"banned": False, "dev_mode": _dev}
