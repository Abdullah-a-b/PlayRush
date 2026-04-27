import redis.asyncio as redis

# إنشاء اتصال دائم بالعقل المركزي المشترك (Redis)
# نستخدم decode_responses=True لكي تعود البيانات كنصوص بدلاً من Bytes

# ✅ Connection pool لتجنب مشاكل multi-worker
redis_db = redis.Redis(
    host='127.0.0.1',
    port=6379,
    decode_responses=True,
    max_connections=20,        # أضف هذا
    socket_keepalive=True,     # أضف هذا
    socket_timeout=5,          # أضف هذا
)