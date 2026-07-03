"""
🛠️ قارئ وضع التطوير (Dev Mode)

يقرأ ALLOW_SAME_IP من ملف .env **مباشرة** (لا من ذاكرة العملية)،
فتعديل .env يسري خلال ثانية بدون إعادة تشغيل السيرفر.

مع cache قصير (ثانية واحدة) لتجنّب قراءة القرص عند كل طلب.
"""
import os
import time

# مسار .env (في جذر Backend)
_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    '.env'
)

_cache_value = False
_cache_time = 0.0
_CACHE_TTL = 1.0  # ثانية واحدة


def _read_env_file_flag() -> bool:
    """يقرأ ALLOW_SAME_IP من ملف .env مباشرة."""
    try:
        with open(_ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # نتجاهل التعليقات والفراغات
                if not line or line.startswith('#'):
                    continue
                if line.startswith('ALLOW_SAME_IP'):
                    # ALLOW_SAME_IP=1  أو  ALLOW_SAME_IP = 1
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        val = parts[1].strip().strip('"').strip("'")
                        return val == '1'
        return False  # المفتاح غير موجود = إنتاج
    except FileNotFoundError:
        # لا يوجد .env → نرجع لمتغير البيئة (احتياط)
        return os.environ.get("ALLOW_SAME_IP", "0") == "1"
    except Exception:
        return False


def is_dev_mode() -> bool:
    """
    هل وضع التطوير مفعّل؟ يقرأ .env لحظياً (مع cache ثانية).

    تعديل .env (تعليق/إلغاء تعليق ALLOW_SAME_IP=1) يسري خلال ثانية،
    بدون إعادة تشغيل السيرفر.
    """
    global _cache_value, _cache_time
    now = time.time()
    if now - _cache_time >= _CACHE_TTL:
        _cache_value = _read_env_file_flag()
        _cache_time = now
    return _cache_value
