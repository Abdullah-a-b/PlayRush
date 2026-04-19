import asyncio
from app.core.database import SessionLocal
from app.models.user import User

async def cleanup_abandoned_accounts():
    """دالة المكنسة الآلية للحسابات التي لم تكمل التسجيل"""
    while True:
        try:
            db = SessionLocal()
            # بما أن الداتابيس القديمة لا تحوي created_at
            # سنقوم بمسح الحسابات الفارغة التي لم تُفعل إيميلها فقط
            abandoned_users = db.query(User).filter(
                User.player_name == None, 
                User.is_verified == False
            ).all()

            for user in abandoned_users:
                db.delete(user)
            
            db.commit()
            db.close()
        except Exception as e:
            print(f"🔥 [Cron] خطأ في التنظيف الآلي: {e}")
        
        # الانتظار 12 ساعة قبل المسح التالي
        await asyncio.sleep(12 * 60 * 60)