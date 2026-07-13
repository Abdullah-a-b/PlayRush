"""
🔴 عميل Redis — نواة المرحلة ب (التوسعة الأفقية)

التفعيل عبر البيئة:
    REDIS_URL=redis://localhost:6379/0
بدون REDIS_URL: المنصة تعمل single-worker بالذاكرة كما كانت تماماً
(صفر تغيير سلوكي) — Redis اختياري حتى لحظة التوسعة.

الأدوار عند التفعيل:
  1. Socket.IO AsyncRedisManager → البثّ يعبر كل الـ workers.
  2. مخزن الحضور العالمي (presence) → snapshot يرى لاعبي كل الـ workers.
  3. مخزن rate limiting (slowapi) → الحدود موحّدة عبر الـ workers.
"""
import os

REDIS_URL = os.environ.get("REDIS_URL", "").strip()

_redis = None
_checked = False
_available = False
_last_fail_ts = 0.0
_last_warn_ts = 0.0
_FAIL_COOLDOWN = 10   # لا نعيد محاولة ping أكثر من مرة كل 10ث عند الفشل
_WARN_COOLDOWN = 60   # تحذير واحد بالدقيقة كحد أقصى (كان يُطبع لكل استدعاء)


def redis_url():
    return REDIS_URL


def redis_enabled() -> bool:
    """هل REDIS_URL مضبوط؟ (لا يضمن أنه حي — انظر redis_available)"""
    return bool(REDIS_URL)


def get_redis():
    """عميل redis.asyncio كسول — None إذا Redis غير مفعّل."""
    global _redis
    if not REDIS_URL:
        return None
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            max_connections=200,
            socket_timeout=5,
            socket_connect_timeout=3,
            retry_on_timeout=True,
        )
    return _redis


async def redis_available() -> bool:
    """فحص حيّ مُهدَّأ: نجاح يُخزَّن؛ فشل يُخزَّن 10ث (لا نضرب منفذاً
    ميتاً بكل طلب) والتحذير مرة بالدقيقة. لو عاد Redis للحياة نلتقطه
    بالمحاولة التالية بعد الـ cooldown — تعافٍ ذاتي بلا إعادة تشغيل."""
    global _checked, _available, _last_fail_ts, _last_warn_ts
    if not REDIS_URL:
        return False
    if _checked and _available:
        return True
    import time as _t
    now = _t.time()
    if _checked and not _available and (now - _last_fail_ts) < _FAIL_COOLDOWN:
        return False  # فشل حديث — لا نعيد المحاولة بعد
    try:
        r = get_redis()
        await r.ping()
        if _checked and not _available:
            print("✅ [redis] عاد للعمل — الميزات العنقودية استُؤنفت")
        _checked = True
        _available = True
        return True
    except Exception as e:
        if (now - _last_warn_ts) >= _WARN_COOLDOWN:
            print(f"⚠️ [redis] غير متاح ({e}) — استمرار بالوضع المحلي "
                  f"(سيُعاد الفحص تلقائياً)")
            _last_warn_ts = now
        _checked = True
        _available = False
        _last_fail_ts = now
        return False
