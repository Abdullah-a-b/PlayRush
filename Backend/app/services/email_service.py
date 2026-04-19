import os
import smtplib
import ssl
import random
from email.message import EmailMessage

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
FRONTEND_BASE_URL = os.environ.get("FRONTEND_URL")

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