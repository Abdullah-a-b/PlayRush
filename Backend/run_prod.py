"""
⚠️ ملاحظة: هذا الملف معطّل حالياً.
السيرفر يُشغّل الآن بـ uvicorn مباشرة:
    uvicorn app.main:app --host 0.0.0.0 --port 8000

سيُعاد بناء هذا الملف عند تنفيذ نظام Redis الجديد.
"""
import sys
import multiprocessing
import subprocess

def get_workers():
    """✅ عدد workers = عدد CPUs × 2 + 1"""
    cpu = multiprocessing.cpu_count()
    return min(cpu * 2 + 1, 9)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    workers = 1
    
    print(f"🚀 جاري تشغيل السيرفر الإنتاجي على 0.0.0.0:8000 | {workers} workers", flush=True)
    
    # استخدام وحدة التشغيل المدمجة يحل جميع مشاكل تجميد العمليات الفرعية
    cmd = [
        sys.executable, "-m", "hypercorn", "app.main:app",
        "--bind", "0.0.0.0:8000",
        "--workers", str(workers),
        "--backlog", "4096",
        "--graceful-timeout", "5",
        "--keep-alive", "5"
    ]
    
    try:
        # سيتم توجيه الضغط على Ctrl+C تلقائياً لجميع العمليات بشكل نظيف
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n✅ تم الإيقاف بالكامل بشكل نظيف!", flush=True)
        sys.exit(0)