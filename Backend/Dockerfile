# ============================================================
#  PlayRush Backend — Dockerfile للنشر على Fly.io
#  صورة رسمية خفيفة لبايثون 3.12 (نفس إصدار التطوير)
# ============================================================
FROM python:3.12-slim

# متغيرات بايثون للإنتاج: لا ملفات .pyc، إخراج فوري للسجلات
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# مكتبات نظام يحتاجها psycopg2 و Pillow (بناء بعض الحزم)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# نثبّت المكتبات أولاً (طبقة كاش مستقلة تُعاد فقط لو تغيّر requirements)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# ننسخ بقية الكود
COPY . .

# Fly يوجّه الحركة إلى المنفذ في fly.toml (8080). uvicorn يقرأ PORT من البيئة.
EXPOSE 8080

# تشغيل مباشر بـ uvicorn (worker واحد). للتوسّع: ارفع عبر Fly scale + Redis.
# لا نستخدم run_prod.py هنا لأن Fly يدير العملية مباشرة (أبسط وأمتن).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
