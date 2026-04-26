import redis.asyncio as redis

# إنشاء اتصال دائم بالعقل المركزي المشترك (Redis)
# نستخدم decode_responses=True لكي تعود البيانات كنصوص بدلاً من Bytes
redis_db = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)