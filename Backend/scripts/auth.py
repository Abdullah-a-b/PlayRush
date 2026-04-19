from fastapi import APIRouter, Depends, HTTPException, Form, BackgroundTasks, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from Backend.app.core.database import SessionLocal, User, pwd_context
import secrets
import random
import smtplib
import ssl
from email.message import EmailMessage
import httpx
from fastapi.responses import JSONResponse, RedirectResponse
import string
import time
import os
from dotenv import load_dotenv
import html  # سنحتاجه لاحقاً للحماية
from fastapi import Request, Depends, HTTPException # تأكد من وجودها
from jose import jwt, JWTError # المكتبة المسؤولة عن فك التوكن
from datetime import datetime, timedelta
import shutil
import uuid

load_dotenv()

# تأكد من وجود مجلد رفع الصور
UPLOAD_DIR = "uploads/avatars"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 🛡️ استدعاء البيانات الحساسة بأمان من البيئة
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_URL")

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-123")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # التوكن صالح لمدة أسبوع

def create_access_token(data: dict):
    """توليد توكن مشفر ومختوم"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

router = APIRouter()

otp_cooldowns = {}
COOLDOWN_SECONDS = 60

# ==========================================
# 🛡️ دوال الأمان (تمنع انهيار bcrypt) 
# ==========================================
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
# ==========================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """حارس الأمن المطور: يصطاد التوكن من أي مكان يرسله الفرونت اند"""
    token = None
    
    # 1. البحث في الرابط (مثل طلبات /me?token=...)
    if request.query_params.get("token"):
        token = request.query_params.get("token")
        
    # 2. البحث في الـ Headers (الأسلوب القياسي)
    elif request.headers.get("Authorization"):
        auth_header = request.headers.get("Authorization")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            
    # 3. البحث في الـ FormData (مثل طلبات setup-profile)
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
        
    return user

def send_real_email(receiver_email: str, code: str, subject: str = "كود تفعيل حسابك في PlayRush"):
    msg = EmailMessage()
    invisible_spaces = "\u200b" * random.randint(1, 25)
    msg['Subject'] = f"{subject}{invisible_spaces}"
    msg['From'] = f"PlayRush Team <{SENDER_EMAIL}>" 
    msg['To'] = receiver_email
    msg['Reply-To'] = "noreply@playrush.com"

    html_content = f"""
    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background-color: #09090b; padding: 40px 20px; color: #ffffff;">
        <div style="max-width: 550px; margin: auto; background-color: #18181b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05);">
            <div style="background: linear-gradient(90deg, #facc15, #f43f5e); height: 4px; width: 100%;"></div>
            <div style="padding: 40px 30px; text-align: center;">
                <h1 style="margin: 0; font-size: 34px; letter-spacing: 1px;">
                    <span style="color: #facc15;">Play</span><span style="color: #f43f5e; font-style: italic;">Rush</span>
                </h1>
                <p style="color: #a1a1aa; font-size: 14px; margin-top: 5px; letter-spacing: 2px;">العب .. فكّر .. اربح</p>
                <h2 style="font-size: 24px; color: #f8fafc; margin-top: 40px; margin-bottom: 10px;">أهلاً بك في عالمنا! 🚀</h2>
                <p style="font-size: 16px; color: #d4d4d8; line-height: 1.6;">
                    لقد اقتربت خطوة واحدة من بدء مغامرتك.<br>استخدم رمز التحقق أدناه لتأكيد حسابك:
                </p>
                <div style="background: rgba(244, 63, 94, 0.08); border: 1px solid rgba(244, 63, 94, 0.2); color: #facc15; font-size: 40px; font-weight: 900; letter-spacing: 15px; padding: 25px; border-radius: 12px; margin: 35px auto; width: fit-content; text-shadow: 0 0 15px rgba(250, 204, 21, 0.4);">
                    {code}
                </div>
                <p style="font-size: 14px; color: #71717a;">هذا الرمز صالح لفترة محدودة، يرجى عدم مشاركته مع أحد.</p>
            </div>
            <div style="background-color: #131316; padding: 20px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                <p style="font-size: 12px; color: #52525b; margin: 0; line-height: 1.8;">
                    هذه رسالة آلية من نظام الحماية. يرجى عدم الرد.<br>
                    © 2026 PlayRush. جميع الحقوق محفوظة.
                </p>
            </div>
        </div>
    </div>
    """
    msg.set_content(f"مرحباً بك في PlayRush. رمز التحقق الخاص بك هو: {code}")
    msg.add_alternative(html_content, subtype='html')

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"[-] خطأ في إرسال الإيميل: {e}")

def send_password_changed_email(receiver_email: str):
    msg = EmailMessage()
    invisible_spaces = "\u200b" * random.randint(1, 25)
    msg['Subject'] = f"إشعار أمني: تم تغيير كلمة المرور بنجاح 🛡️{invisible_spaces}"
    msg['From'] = f"PlayRush Team <{SENDER_EMAIL}>"
    msg['To'] = receiver_email
    msg['Reply-To'] = "noreply@playrush.com"

    html_content = f"""
    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background-color: #09090b; padding: 40px 20px; color: #ffffff;">
        <div style="max-width: 550px; margin: auto; background-color: #18181b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05);">
            <div style="background: linear-gradient(90deg, #00ff88, #00b8ff); height: 4px; width: 100%;"></div>
            <div style="padding: 40px 30px; text-align: center;">
                <h1 style="margin: 0; font-size: 34px; letter-spacing: 1px;">
                    <span style="color: #facc15;">Play</span><span style="color: #f43f5e; font-style: italic;">Rush</span>
                </h1>
                <h2 style="font-size: 24px; color: #00ff88; margin-top: 40px; margin-bottom: 15px;">تم تغيير كلمة المرور! ✅</h2>
                <p style="font-size: 16px; color: #d4d4d8; line-height: 1.8;">
                    مرحباً بك،<br>
                    نود إعلامك بأنه قد تم تحديث كلمة المرور الخاصة بحسابك بنجاح. يمكنك الآن الدخول لساحة اللعب باستخدام بياناتك الجديدة.
                </p>
                <div style="background: rgba(255, 255, 255, 0.03); border-right: 4px solid #f43f5e; padding: 20px; border-radius: 8px; margin-top: 35px; text-align: right;">
                    <p style="font-size: 14px; color: #f8fafc; margin: 0; line-height: 1.6;">
                        <span style="font-size: 18px;">🛡️</span> <b style="color: #f43f5e;">تنبيه أمني:</b><br>
                        إذا لم تقم أنت بهذا التغيير، يرجى التوجه فوراً للموقع واستعادة حسابك لحمايته.
                    </p>
                </div>
            </div>
            <div style="background-color: #131316; padding: 20px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                <p style="font-size: 12px; color: #52525b; margin: 0; line-height: 1.8;">
                    هذه رسالة آلية من نظام الحماية. يرجى عدم الرد.<br>
                    © 2026 PlayRush. جميع الحقوق محفوظة.
                </p>
            </div>
        </div>
    </div>
    """
    msg.set_content("مرحباً بك في PlayRush. تم تغيير كلمة المرور الخاصة بحسابك بنجاح.")
    msg.add_alternative(html_content, subtype='html')

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"[-] خطأ في إرسال الإيميل: {e}")

def send_email_changed(receiver_email: str, new_email: str):
    msg = EmailMessage()
    invisible_spaces = "\u200b" * random.randint(1, 25)
    msg['Subject'] = f"إشعار أمني: تم تغيير حسابك بنجاح 🛡️{invisible_spaces}"
    msg['From'] = f"PlayRush Team <{SENDER_EMAIL}>"
    msg['To'] = receiver_email
    msg['Reply-To'] = "noreply@playrush.com"

    html_content = f"""
    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background-color: #09090b; padding: 40px 20px; color: #ffffff;">
        <div style="max-width: 550px; margin: auto; background-color: #18181b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05);">
            <div style="background: linear-gradient(90deg, #00ff88, #00b8ff); height: 4px; width: 100%;"></div>
            <div style="padding: 40px 30px; text-align: center;">
                <h1 style="margin: 0; font-size: 34px; letter-spacing: 1px;">
                    <span style="color: #facc15;">Play</span><span style="color: #f43f5e; font-style: italic;">Rush</span>
                </h1>
                <h2 style="font-size: 24px; color: #00ff88; margin-top: 40px; margin-bottom: 15px;">تم تغيير حسابك بنجاح! ✅</h2>
                <p style="font-size: 16px; color: #d4d4d8; line-height: 1.8;">
                    مرحباً بك،<br>
                    نود إعلامك بأنه قد تم تغيير الحساب الخاص بك بنجاح الى {new_email}. يمكنك الآن الدخول لساحة اللعب باستخدام بياناتك الجديدة.
                </p>
                <div style="background: rgba(255, 255, 255, 0.03); border-right: 4px solid #f43f5e; padding: 20px; border-radius: 8px; margin-top: 35px; text-align: right;">
                    <p style="font-size: 14px; color: #f8fafc; margin: 0; line-height: 1.6;">
                        <span style="font-size: 18px;">🛡️</span> <b style="color: #f43f5e;">تنبيه أمني:</b><br>
                        إذا لم تقم أنت بهذا التغيير، يرجى التوجه فوراً للموقع واستعادة حسابك لحمايته عن طريق التواصل مع الدعم الفني.
                    </p>
                </div>
            </div>
            <div style="background-color: #131316; padding: 20px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                <p style="font-size: 12px; color: #52525b; margin: 0; line-height: 1.8;">
                    هذه رسالة آلية من نظام الحماية. يرجى عدم الرد.<br>
                    © 2026 PlayRush. جميع الحقوق محفوظة.
                </p>
            </div>
        </div>
    </div>
    """
    msg.set_content("مرحباً بك في PlayRush. تم تغيير كلمة المرور الخاصة بحسابك بنجاح.")
    msg.add_alternative(html_content, subtype='html')

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"[-] خطأ في إرسال الإيميل: {e}")

def send_welcome_email(receiver_email: str):
    msg = EmailMessage()
    invisible_spaces = "\u200b" * random.randint(1, 25)
    msg['Subject'] = f"مرحباً بك في عائلة PlayRush! 🎮{invisible_spaces}"
    msg['From'] = f"PlayRush Team <{SENDER_EMAIL}>"
    msg['To'] = receiver_email
    msg['Reply-To'] = "noreply@playrush.com"

    html_content = f"""
    <div dir="rtl" style="font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background-color: #09090b; padding: 40px 20px; color: #ffffff;">
        <div style="max-width: 550px; margin: auto; background-color: #18181b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05);">
            <div style="background: linear-gradient(90deg, #facc15, #f43f5e); height: 4px; width: 100%;"></div>
            <div style="padding: 40px 30px; text-align: center;">
                <h1 style="margin: 0; font-size: 38px; letter-spacing: 1px;">
                    <span style="color: #facc15;">Play</span><span style="color: #f43f5e; font-style: italic;">Rush</span>
                </h1>
                <h2 style="font-size: 26px; color: #f8fafc; margin-top: 35px; margin-bottom: 10px;">أهلاً بالأسطورة! 🎉</h2>
                <p style="font-size: 16px; color: #d4d4d8; line-height: 1.8;">
                    شكراً لانضمامك إلى منصتنا. نحن متحمسون جداً لرؤيتك تتسلق قوائم المتصدرين وتثبت مهارتك في ساحات اللعب. 
                    <br>لقد تم تجهيز حسابك بالكامل، وكل شيء جاهز لانطلاقتك!
                </p>
                <div style="margin: 30px 0;">
                    <a href="{FRONTEND_BASE_URL}/categories.html" style="background: linear-gradient(45deg, #f43f5e, #e11d48); color: white; text-decoration: none; padding: 14px 35px; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 5px 15px rgba(225, 29, 72, 0.4);">
                    ادخل اللوبي الآن 🚀
                </a>
                </div>
                <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.05); margin: 30px 0;">
                <h3 style="color: #facc15; font-size: 18px; margin-bottom: 15px;">تحتاج مساعدة؟ أو تبغى تشاركنا إنجازاتك؟</h3>
                <p style="font-size: 14px; color: #a1a1aa; line-height: 1.6;">
                    فريق الدعم الفني دائماً في خدمتك عبر البريد الإلكتروني:<br>
                    <a href="mailto:playrush.online@gmail.com" style="color: #00b8ff; text-decoration: none; font-weight: bold;">playrush.online@gmail.com</a>
                </p>
            </div>
            <div style="background-color: #131316; padding: 20px; text-align: center; border-top: 1px solid rgba(255,255,255,0.05);">
                <p style="font-size: 12px; color: #52525b; margin: 0; line-height: 1.8;">
                    أنت تتلقى هذا البريد لأنك سجلت في منصة PlayRush.<br>
                    © 2026 PlayRush. جميع الحقوق محفوظة.
                </p>
            </div>
        </div>
    </div>
    """
    msg.set_content("مرحباً بك في PlayRush! شكراً لانضمامك إلينا. ادخل اللوبي الآن وابدأ اللعب!")
    msg.add_alternative(html_content, subtype='html')

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"[-] خطأ في إرسال الإيميل الترحيبي: {e}")

@router.post("/register")
async def register(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    password: str = Form(...),
    # 🗑️ تم حذف coins و gems و level من هنا نهائياً
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

    # استخدام دالتنا الآمنة للتشفير
    hashed_password = get_password_hash(password)
    verification_code = ''.join(secrets.choice(string.digits) for _ in range(6))

    new_user = User(
        email=email,
        hashed_password=hashed_password,
        verification_code=verification_code,
        is_verified=False,
        # 🔒 القيم الافتراضية محمية ومفروضة من السيرفر مباشرة
        coins=100,  # 🎁 هدية الترحيب
        gems=3,   # 🎁 3 جواهر ترحيب
        level=0,
        player_id=generate_player_id(db)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    invisible_spaces = "\u200b" * random.randint(1, 15)
    background_tasks.add_task(send_real_email, email, verification_code, f"تفعيل حسابك في PlayRush{invisible_spaces}")
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
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود أو انتهت الجلسة")
    
    if user.verification_code != code:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح")
        
    if flow == "register":
        if user.is_verified:
            return {"message": "الحساب مفعل مسبقاً"}
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
    # 🚀 التصحيح هنا: نكتفي بكتابة النوع فقط لكي يقوم FastAPI بحقنها تلقائياً
    background_tasks: BackgroundTasks, 
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    # البحث عن المستخدم
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="البريد الإلكتروني أو كلمة المرور غير صحيحة")

    # إذا كان الحساب غير مفعل
    if not user.is_verified:
        # إنشاء كود جديد وإلغاء القديم
        new_code = "".join([str(random.randint(0, 9)) for _ in range(6)])
        user.verification_code = new_code
        db.commit()

        # إرسال الكود فوراً للإيميل في الخلفية
        background_tasks.add_task(send_real_email, user.email, new_code)

        # التوجيه لصفحة التحقق
        return JSONResponse(
            status_code=403, 
            content={
                "action": "redirect_to_verify",
                "email": user.email,
                "detail": "حسابك غير مفعل. تم إرسال كود تحقق جديد إلى بريدك، جاري التوجيه..."
            }
        )

    # 3. 🚀 التغيير الجذري (JWT): توليد الختم المشفر الذي يحمل إيميل اللاعب داخله
    # (لم نعد نكتب أي شيء في قاعدة البيانات هنا!)
    access_token = create_access_token(data={"sub": user.email})
    
    # 4. إعادة التوكن للفرونت اند بنفس اسم المتغير القديم "token" لكي لا ينكسر كود الـ JS
    return {
        "message": "تم تسجيل الدخول بنجاح", 
        "token": access_token, 
        "token_type": "bearer", # إضافة قياسية في عالم الـ APIs
        "has_profile": bool(user.player_name) 
    }

@router.post("/forgot-password")
async def forgot_password(
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
    
    reset_code = str(random.randint(100000, 999999))
    user.verification_code = reset_code
    db.commit()

    invisible_spaces = "\u200b" * random.randint(1, 15)
    background_tasks.add_task(send_real_email, email, reset_code, f"إعادة تعيين كلمة المرور - PlayRush{invisible_spaces}")
    otp_cooldowns[email] = current_time

    return {"message": "تم إرسال رمز استعادة كلمة المرور"}

@router.post("/reset-password")
async def reset_password(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    
    if user.verification_code != code:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح أو منتهي الصلاحية")
    
    # استخدام دالتنا الآمنة للتحقق
    if verify_password(new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="كلمة المرور الجديدة مطابقة للقديمة")

    # استخدام دالتنا الآمنة للتشفير
    user.hashed_password = get_password_hash(new_password)
    user.verification_code = None 
    db.commit()

    background_tasks.add_task(send_password_changed_email, email)

    return {"message": "تم تغيير كلمة المرور بنجاح"}

@router.get("/google/login")
async def google_login():
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&scope=openid%20email%20profile&access_type=offline"
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
        
        if not access_token:
            raise HTTPException(status_code=400, detail="فشل في تسجيل الدخول عبر جوجل")

        user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        user_info_response = await client.get(user_info_url, headers=headers)
        user_info = user_info_response.json()
        
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="لا يمكن جلب الإيميل من جوجل")

    user = db.query(User).filter(User.email == email).first()
    needs_profile_setup = False
    
    if not user:
        needs_profile_setup = True
        random_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(16))
        
        new_user = User(
            email=email,
            # استخدام دالتنا الآمنة للتشفير
            hashed_password=get_password_hash(random_password),
            verification_code=None,
            is_verified=True, # تم تفعيل الحساب تلقائياً لأن جوجل يضمن لنا صحة الإيميل
            welcome_email_sent=True,
            auth_provider="google",
            player_id=generate_player_id(db),
            # 💰 التحديث الاقتصادي: إضافة المكافأة الافتراضية
            coins=100,  # 🎁 هدية الترحيب
            gems=3,   # 🎁 3 جواهر ترحيب
            level=0
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user
        background_tasks.add_task(send_welcome_email, user.email)
    
    elif not user.player_name:
        needs_profile_setup = True

    # 🚀 التحديث الأمني: استخدام الـ JWT بدلاً من التوكن العشوائي
    playrush_token = create_access_token(data={"sub": user.email})
    
    # 🗑️ تم حذف السطور القديمة التي تحفظ التوكن في الداتا بيس:
    # user.session_token = playrush_token 
    # db.commit() 
    
    # توجيه اللاعب للصفحة المناسبة مع التوكن المشفّر في الرابط
    if needs_profile_setup:
        target_url = f"{FRONTEND_BASE_URL}/profile-setup.html?token={playrush_token}"
    else:
        target_url = f"{FRONTEND_BASE_URL}/categories.html?token={playrush_token}"
        
    print(f"[Google Auth] Success! Redirecting to: {target_url}")
    return RedirectResponse(url=target_url)

@router.post("/logout")
async def logout(token: str = Form(...), db: Session = Depends(get_db)):
    """🛡️ تسجيل الخروج باستخدام نظام JWT"""
    try:
        # التحقق من أن التوكن صالح وتابع للاعب لدينا
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        user = db.query(User).filter(User.email == user_email).first()
        
        if not user:
            raise HTTPException(status_code=401, detail="الحساب غير موجود")
            
        # لا حاجة لتعديل قاعدة البيانات (session_token = None) 
        # لأن نظام JWT يعتمد على حذف التوكن من جهة العميل (المتصفح)
        
    except JWTError:
        # إذا كان التوكن منتهياً أو تالفاً، نعتبره خارج النظام أصلاً
        pass 
        
    return {"message": "تم تسجيل الخروج بنجاح وتأمين الحساب"}

@router.post("/setup-profile")
async def setup_profile(
    player_name: str = Form(...),
    country: str = Form(...),
    avatar_url: str = Form(None),
    avatar_file: UploadFile = File(None), # لاستقبال ملف من الجهاز
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # حماية الاسم
    existing_user = db.query(User).filter(User.player_name == player_name).first()
    if existing_user and existing_user.email != current_user.email:
        raise HTTPException(status_code=400, detail="الاسم مستخدم مسبقاً")

    old_avatar = current_user.avatar
    new_path = old_avatar

    # دالة الحذف لتوفير مساحة السيرفر
    def cleanup(path):
        if path and path.startswith("/uploads/"):
            p = path.lstrip("/")
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

    # إذا رفع ملف جديد
    if avatar_file and avatar_file.filename:
        cleanup(old_avatar) # احذف القديم
        ext = avatar_file.filename.split('.')[-1]
        filename = f"{uuid.uuid4().hex}.{ext}"
        save_path = f"uploads/avatars/{filename}"
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(avatar_file.file, buffer)
        new_path = f"/{save_path}"

    # إذا اختار أيقونة جاهزة
    elif avatar_url:
        cleanup(old_avatar) # احذف أي ملف مرفوع سابقاً
        new_path = avatar_url.replace("../", "")

    current_user.player_name = player_name
    current_user.country = country
    current_user.avatar = new_path
    
    if not current_user.player_id:
        current_user.player_id = generate_player_id(db)
        
    db.commit()
    return {"message": "Success", "new_avatar": new_path}

@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    # حارس الأمن تحقق من التوكن وأحضر لنا اللاعب (current_user) جاهزاً!
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
    # 🚀 التحديث: فك تشفير الـ JWT للوصول إلى المستخدم بدلاً من البحث عن session_token القديم
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        user = db.query(User).filter(User.email == user_email).first()
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح أو منتهي الصلاحية")

    if not user or user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="طلب غير صالح")
    
    email = user.email

    current_time = time.time()
    if email in otp_cooldowns:
        time_passed = current_time - otp_cooldowns[email]
        if time_passed < COOLDOWN_SECONDS:
            remaining = int(COOLDOWN_SECONDS - time_passed)
            raise HTTPException(status_code=429, detail=f"الرجاء الانتظار {remaining} ثانية قبل طلب رمز جديد.")

    security_code = str(random.randint(100000, 999999))
    user.verification_code = security_code
    db.commit()

    invisible_spaces = "\u200b" * random.randint(1, 15)
    background_tasks.add_task(send_real_email, email, security_code, f"رمز التحقق لتعديل إعدادات الأمان - PlayRush{invisible_spaces}")
    otp_cooldowns[email] = current_time
    
    return {"message": "تم إرسال رمز التحقق إلى بريدك الإلكتروني"}

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
        user_email = payload.get("sub") # هذا الإيميل القديم المخزن في التوكن
        user = db.query(User).filter(User.email == user_email).first()
    except JWTError:
        raise HTTPException(status_code=401, detail="التوكن غير صالح أو منتهي الصلاحية")
    
    if not user or user.verification_code != otp:
        raise HTTPException(status_code=400, detail="رمز التحقق غير صحيح")
    
    if action == "email":
        check_email = db.query(User).filter(User.email == new_value).first()
        if check_email:
            raise HTTPException(status_code=400, detail="البريد الإلكتروني الجديد مستخدم مسبقاً")
        
        background_tasks.add_task(send_email_changed, user_email, new_value)
        # تغيير الإيميل في الداتابيس
        user.email = new_value
        msg_text = "تم تغيير البريد الإلكتروني بنجاح"
        
        # 🚀 الحل الذهبي: توليد توكن جديد يختم بالإيميل الجديد!
        new_token = create_access_token(data={"sub": user.email})
        
        user.verification_code = None
        db.commit()
        
        # إرسال التوكن الجديد للفرونت إند
        return {"message": msg_text, "new_token": new_token}
        
    elif action == "password":
        user.hashed_password = get_password_hash(new_value)
        msg_text = "تم تغيير كلمة المرور بنجاح"
        background_tasks.add_task(send_password_changed_email, user.email)
        
        user.verification_code = None
        db.commit()
        return {"message": msg_text}

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

    new_code = str(random.randint(100000, 999999))
    user.verification_code = new_code
    db.commit()

    invisible_spaces = "\u200b" * random.randint(1, 15)
    background_tasks.add_task(send_real_email, email, new_code, f"رمز تفعيل جديد - PlayRush{invisible_spaces}")
    otp_cooldowns[email] = current_time

    return {"message": "تم إرسال رمز جديد بنجاح"}

def generate_player_id(db: Session) -> str:
    """توليد ID مميز وعشوائي للاعب مثل PR-84925"""
    while True:
        new_id = "PR-" + ''.join(random.choices(string.digits, k=5))
        # التأكد من أن الـ ID غير مكرر في قاعدة البيانات
        if not db.query(User).filter(User.player_id == new_id).first():
            return new_id

@router.delete("/delete-account")
async def delete_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        db.delete(current_user)
        db.commit()
        return {"message": "تم حذف الحساب نهائياً بنجاح"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="حدث خطأ داخلي أثناء الحذف")

@router.delete("/cancel-registration")
async def cancel_registration(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # حماية: نمنع حذف الحساب إذا كان قد أكمل الإعداد بالفعل
    if current_user.player_name is not None:
        raise HTTPException(status_code=400, detail="لا يمكن إلغاء حساب مكتمل من هنا")
    
    db.delete(current_user)
    db.commit()
    return {"message": "تم إلغاء التسجيل وحذف الحساب"}