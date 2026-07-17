import re
from fastapi import HTTPException

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# الاسم: 3-20 حرفاً، حروف عربية/لاتينية وأرقام و _ ومسافات داخلية فقط
PLAYER_NAME_REGEX = re.compile(r'^[\w\u0600-\u06FF][\w\u0600-\u06FF\s]{1,18}[\w\u0600-\u06FF]$')


def validate_email_format(email: str) -> str:
    """تنظيف وفحص البريد الإلكتروني. يرجع البريد النظيف أو يرفع 400."""
    if not email or not isinstance(email, str):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني مطلوب")
    cleaned = email.strip().lower()
    if len(cleaned) > 254 or len(cleaned) < 5:
        raise HTTPException(status_code=400, detail="طول البريد الإلكتروني غير صالح")
    if not EMAIL_REGEX.match(cleaned):
        raise HTTPException(status_code=400, detail="صيغة البريد الإلكتروني غير صالحة")
    return cleaned


def validate_password_strength(password: str):
    """فحص قوة كلمة المرور: 8-72 حرفاً وتحتوي حروفاً وأرقاماً."""
    if not password or not isinstance(password, str):
        raise HTTPException(status_code=400, detail="كلمة المرور مطلوبة")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")
    if len(password) > 72:  # حد bcrypt
        raise HTTPException(status_code=400, detail="كلمة المرور طويلة جداً (حد أقصى 72 حرفاً)")
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تحتوي على حروف وأرقام")


def validate_otp_code(code: str) -> str:
    """فحص صيغة رمز التحقق — 6 أرقام بالضبط."""
    if not code or not isinstance(code, str):
        raise HTTPException(status_code=400, detail="الرمز مطلوب")
    code = code.strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(status_code=400, detail="صيغة الرمز غير صحيحة")
    return code
