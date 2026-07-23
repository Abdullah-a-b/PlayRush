from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from app.infrastructure.redis_client import redis_enabled, redis_url


def get_real_ip(request: Request) -> str:
    """يقرأ IP الحقيقي من X-Forwarded-For (Azure/Nginx proxy).
    
    Azure App Service يضع reverse proxy أمام التطبيق، فكل الطلبات تأتي
    من IP داخلي (169.254.x.x). هذه الدالة تقرأ الـ IP الأصلي للمستخدم
    من هيدر X-Forwarded-For الذي يُعبّئه Azure تلقائياً.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For قد يحتوي سلسلة: "client, proxy1, proxy2"
        # نأخذ الأول دائماً — هو IP العميل الحقيقي
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# المرحلة ب: مع REDIS_URL تُخزَّن الحدود في Redis — موحّدة عبر كل
# الـ workers (in-memory لا يعمل مع multi-worker: كل worker حدوده وحده).
# بدونه: in-memory كما كان — سليم لworker واحد.
if redis_enabled():
    limiter = Limiter(key_func=get_real_ip, storage_uri=redis_url())
    print(" [limiter] تخزين الحدود على Redis (موحّد عبر الـ workers)")
else:
    limiter = Limiter(key_func=get_real_ip)
