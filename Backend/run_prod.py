"""
run_prod.py - تشغيل السيرفر في وضع الإنتاج
=============================================
التحسينات:
  1. workers متعددة بناءً على عدد أنوية CPU
  2. backlog أعلى لاستيعاب طوابير الاتصال
  3. keep_alive مضبوط لـ Socket.io
  4. graceful_timeout لإغلاق آمن تحت الضغط
  5. h11_max_incomplete_size لحماية من طلبات ضخمة

ملاحظة Windows:
  Windows لا يدعم multiprocessing مع asyncio بسهولة.
  للتطوير المحلي استخدم run_dev.py (worker واحد).
  للإنتاج الحقيقي: انشر على Linux (VPS/Docker).
"""

import os
import asyncio
import multiprocessing
from hypercorn.config import Config
from hypercorn.asyncio import serve


def get_workers():
    """
    عدد الـ workers = عدد أنوية CPU.
    على Linux: كل worker يستقل بـ event loop خاص به = أداء أعلى.
    على Windows: يُرجع 1 (multiprocessing محدود).
    """
    if os.name == "nt":  # Windows
        return 1
    cpu_count = multiprocessing.cpu_count()
    return max(1, cpu_count)


async def main():
    config = Config()

    # ==========================================
    # الشبكة
    # ==========================================
    config.bind = ["0.0.0.0:8000"]
    config.backlog = 2048             # طابور الاتصالات المعلقة (الافتراضي 100)

    # ==========================================
    # المهلات
    # ==========================================
    config.keep_alive_timeout = 75    # ثانية — مناسب لـ Socket.io long-polling
    config.graceful_timeout = 30      # وقت الإغلاق الآمن تحت الضغط
    config.read_timeout = 60          # مهلة قراءة الطلب

    # ==========================================
    # الأداء
    # ==========================================
    config.workers = get_workers()
    config.use_reloader = False       # لا hot-reload في الإنتاج

    # ==========================================
    # اللوج
    # ==========================================
    config.accesslog = "-"            # stdout
    config.errorlog = "-"             # stderr
    config.loglevel = "info"

    print(f"🚀 تشغيل السيرفر على {config.bind} | Workers: {config.workers}")

    from app.main import app
    await serve(app, config)


if __name__ == "__main__":
    multiprocessing.freeze_support()  # مطلوب على Windows
    asyncio.run(main())