import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

# إعداد الـ Connection Pool الحالي الخاص بك مع ضبط متوازن
pool = ConnectionPool(
    host='127.0.0.1',
    port=6379,
    decode_responses=True,
    max_connections=1000,  # 🚀 رقم متوازن يمنع الـ Error ويتحمله جهازك
    socket_keepalive=True,
    socket_timeout=5,
    socket_connect_timeout=3,
    retry_on_timeout=True,
)

redis_db = redis.Redis(connection_pool=pool)