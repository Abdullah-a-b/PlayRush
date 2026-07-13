from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.redis_client import redis_enabled, redis_url

# 🔴 المرحلة ب: مع REDIS_URL تُخزَّن الحدود في Redis — موحّدة عبر كل
# الـ workers (in-memory لا يعمل مع multi-worker: كل worker حدوده وحده).
# بدونه: in-memory كما كان — سليم لworker واحد.
if redis_enabled():
    limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url())
    print("🔴 [limiter] تخزين الحدود على Redis (موحّد عبر الـ workers)")
else:
    limiter = Limiter(key_func=get_remote_address)
