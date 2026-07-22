"""
تحقّق من عمل Redis — شغّله من داخل مجلد Backend:  python redis_check.py

يفحص:
  1) هل REDIS_URL مضبوط؟
  2) اتصال فعلي (PING)
  3) كتابة/قراءة/حذف مفتاح تجريبي (نفس آلية رموز الجمعات)
  4) هل مفاتيح رموز الجمعات تُكتب فعلاً؟ (يعرض pr:hostcode:* الموجودة)
"""
import os
import asyncio

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

REDIS_URL = os.environ.get("REDIS_URL")


async def main():
    print("-" * 55)
    if not REDIS_URL:
        print("❌ REDIS_URL غير مضبوط في .env — لن تُشارك الرموز بين الـ workers.")
        return
    print(f"✅ REDIS_URL مضبوط (يبدأ بـ: {REDIS_URL.split('@')[-1][:40]} ...)")

    try:
        import redis.asyncio as aioredis
    except Exception:
        print("❌ مكتبة redis غير مثبّتة. ثبّتها: pip install redis")
        return

    try:
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception as e:
        print(f"❌ فشل إنشاء الاتصال: {e}")
        return

    # 1) PING
    try:
        pong = await r.ping()
        print(f"✅ PING ناجح: {pong}")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Redis (هل الخادم شغّال؟): {e}")
        print("   على ويندوز جرّب: تشغيل redis عبر Memurai/WSL، أو استخدم Redis سحابي.")
        await r.close()
        return

    # 2) SET/GET/DEL
    try:
        await r.setex("pr:selftest", 10, "ok")
        v = await r.get("pr:selftest")
        await r.delete("pr:selftest")
        print(f"✅ كتابة/قراءة/حذف ناجحة (القيمة المقروءة: {v})")
    except Exception as e:
        print(f"❌ فشل SET/GET/DEL: {e}")
        await r.close()
        return

    # 3) عرض رموز الجمعات الحالية إن وُجدت
    try:
        keys = []
        async for k in r.scan_iter(match="pr:hostcode:*"):
            keys.append(k)
        linked = []
        async for k in r.scan_iter(match="pr:linked:*"):
            linked.append(k)
        print(f"ℹ️ رموز جمعات نشطة الآن: {len(keys)} — روابط مضيف نشطة: {len(linked)}")
        print("   (أنشئ رمزاً من اللوبي ثم أعد تشغيل هذا السكربت لتشوف pr:hostcode:* يزيد)")
    except Exception as e:
        print(f"⚠️ فحص المفاتيح فشل: {e}")

    await r.close()
    print("-" * 55)
    print("✅ Redis يعمل بشكل سليم — مشاركة الرموز بين الـ workers ستعمل.")


if __name__ == "__main__":
    asyncio.run(main())
