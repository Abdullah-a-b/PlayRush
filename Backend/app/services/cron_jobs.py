"""
🕒 Background cron jobs.

⚠️ مهم: لا نلتقط CancelledError هنا (ندعها تنتشر للـ supervisor)
الـ supervisor في main.py يميّز بين CancelledError والـ exceptions الأخرى.
"""
import asyncio
import logging
from app.core.database import SessionLocal
from app.models.user import User

logger = logging.getLogger("playrush.cron")


async def cleanup_abandoned_accounts():
    """مكنسة آلية للحسابات التي لم تكمل التسجيل — تعمل كل 12 ساعة."""
    while True:
        try:
            db = SessionLocal()
            try:
                abandoned = db.query(User).filter(
                    User.player_name == None,
                    User.is_verified == False
                ).all()
                count = len(abandoned)
                for user in abandoned:
                    db.delete(user)
                db.commit()
                if count:
                    logger.info(f"🧹 [cron] حُذف {count} حساب مهجور")
            finally:
                db.close()
        except Exception as e:
            # ✅ نلتقط الـ exceptions الأخرى فقط، CancelledError ينتشر طبيعياً
            logger.error(f"🔥 [cron] خطأ في تنظيف الحسابات: {e}")

        # ✅ asyncio.sleep يرفع CancelledError بنفسه — ندعه ينتشر للـ supervisor
        await asyncio.sleep(12 * 60 * 60)


async def cleanup_waiting_rooms():
    """يحذف غرف الـ waiting المتروكة كل 10 دقائق."""
    while True:
        try:
            from app.games.core_manager import cleanup_stale_waiting_rooms
            removed = cleanup_stale_waiting_rooms()
            if removed:
                logger.info(f"🧹 [cron] حُذفت {removed} غرفة waiting منتهية الصلاحية")
        except Exception as e:
            logger.error(f"🔥 [cron] خطأ في تنظيف الغرف: {e}")

        await asyncio.sleep(10 * 60)


async def cleanup_anticheat_data():
    """ينظف بيانات anti-cheat القديمة (event timelines, expired temp_bans) كل 30 دقيقة."""
    while True:
        try:
            from app.core.anticheat import cleanup_old_data
            cleaned = cleanup_old_data()
            if cleaned:
                logger.info(f"🧹 [cron] anti-cheat: نظّف {cleaned} entries")
        except Exception as e:
            logger.error(f"🔥 [cron] خطأ في تنظيف anti-cheat: {e}")

        await asyncio.sleep(30 * 60)

async def cleanup_collusion_data():
    """ينظف سجلات المواجهات القديمة (anti-collusion) كل ساعة."""
    while True:
        try:
            from app.services.anti_collusion import cleanup_old_matchups
            removed = cleanup_old_matchups()
            if removed:
                logger.info(f"🧹 [cron] anti-collusion: نظّف {removed} أزواج قديمة")
        except Exception as e:
            logger.error(f"🔥 [cron] خطأ في تنظيف anti-collusion: {e}")

        await asyncio.sleep(60 * 60)

async def release_expired_penalties():
    """يفك الحظر المنتهي تلقائياً (نظام البلاغات) كل 10 دقائق."""
    while True:
        try:
            from app.services.player_reports import release_expired_bans
            released = release_expired_bans()
        except Exception as e:
            logger.error(f"🔥 [cron] خطأ في فك الحظر المنتهي: {e}")

        await asyncio.sleep(10 * 60)

async def cleanup_leaver_data_job():
    """ينظّف بيانات عقوبات الانسحاب للمتعافين كل ساعة."""
    while True:
        try:
            from app.services.leaver_penalty import cleanup_leaver_data
            removed = cleanup_leaver_data()
            if removed:
                logger.info(f"🧹 [cron] leaver-penalty: نظّف {removed} لاعب متعافٍ")
        except Exception as e:
            logger.error(f"🔥 [cron] خطأ في تنظيف عقوبات الانسحاب: {e}")
        await asyncio.sleep(60 * 60)

async def cleanup_closed_tickets_job():
    """يحذف تذاكر الدعم المغلقة الأقدم من 30 يوم (يمنع التكدّس) — كل 12 ساعة."""
    while True:
        try:
            from app.services.support import cleanup_old_closed_tickets
            removed = cleanup_old_closed_tickets(days=30)
            if removed:
                logger.info(f"🧹 [cron] support: حذف {removed} تذكرة مغلقة قديمة")
        except Exception as e:
            logger.error(f"🔥 [cron] خطأ في تنظيف التذاكر: {e}")
        await asyncio.sleep(12 * 60 * 60)
