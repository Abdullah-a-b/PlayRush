"""
🚀 مشغّل الإنتاج — المرحلة ب

الاستخدام:
    python run_prod.py                 # worker واحد (الوضع الحالي الآمن)
    WORKERS=4 python run_prod.py       # multi-worker (يتطلب REDIS_URL)

✅ خارطة multi-worker:
  ب-1: بثّ Socket.IO عبر Redis + حضور عالمي + rate limit موحّد.
  ب-2: طابور مطابقة عالمي + نمط «الـ worker المالك» — الغرفة تعيش
       حيث أُنشئت، وأي حدث لعب يصل worker آخر يُحوَّل للمالك تلقائياً.
  ملاحظة انهيار worker: غرفه الجارية تُفقد (اللاعبون يعيدون التطابق) —
  الهجرة الكاملة لحالة اللعب إلى Redis قرار مستقبلي إن لزم.
"""
import os
import sys
import subprocess

# 📋 نحمّل .env من مجلد هذا الملف نفسه — حتى تُقرأ WORKERS/REDIS_URL/PORT
# منه مباشرة أياً كان المجلد الذي شُغّل منه الأمر
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass


def _run_multiport(workers, host, base_port):
    """🪟 وضع Windows: N عمليات uvicorn مستقلة على منافذ متتالية
    (8000، 8001، ...) بدل --workers الذي يشارك socket واحداً بين
    العمليات — مشاركة هشة على Windows (WinError 10022 عشوائي).
    العنقود لا يفرّق: نفس Redis يربط الجميع. للاختبار المحلي افتح
    متصفحاً على أي منفذ منها. (الإنتاج على Linux يستخدم --workers.)"""
    procs = []
    try:
        for i in range(workers):
            port = base_port + i
            cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
                   "--host", host, "--port", str(port), "--no-access-log"]
            procs.append(subprocess.Popen(cmd))
            print(f"🚀 [prod] worker مستقل على http://{host}:{port}")
        print(f"🪟 [prod] وضع المنافذ المتعددة: {workers} عمليات "
              f"({base_port}..{base_port + workers - 1}) — Ctrl+C يوقف الجميع")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


def main():
    workers = int(os.environ.get("WORKERS", "1"))
    redis_url = os.environ.get("REDIS_URL", "").strip()
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    if workers > 1 and not redis_url:
        print("❌ WORKERS>1 يتطلب REDIS_URL (بثّ Socket.IO عبر الـ workers).")
        print("   إمّا: WORKERS=1، أو اضبط REDIS_URL=redis://localhost:6379/0")
        sys.exit(1)

    # 🪟 Windows + عدة workers → منافذ متعددة (تجاوز هشاشة مشاركة socket)
    # يمكن فرضه على أي نظام بـ MULTIPORT=1 (مفيد للاختبار)
    multiport = workers > 1 and (os.name == "nt"
                                 or os.environ.get("MULTIPORT") == "1")
    if multiport:
        print("🕸️ ب-2 مفعّلة: أحداث الغرف تُحوَّل للـ worker المالك تلقائياً.")
        _run_multiport(workers, host, port)
        return

    if workers > 1:
        print("🕸️ ب-2 مفعّلة: أحداث الغرف تُحوَّل للـ worker المالك تلقائياً.")

    cmd = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", host,
        "--port", str(port),
        "--workers", str(workers),
        "--no-access-log",
    ]
    print(f"🚀 [prod] uvicorn × {workers} worker(s)"
          + (f" + Redis ({redis_url})" if redis_url else " (بلا Redis — وضع محلي)"))
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
