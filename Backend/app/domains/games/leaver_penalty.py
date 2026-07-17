"""
 نظام عقوبة الانسحاب المتكرر (Leaver Penalty)

مستوحى من Brawl Stars (نظام السمعة) + Dead by Daylight (سلّم تصاعدي):
- كل انسحاب يزيد عداد المخالفات
- 3 انسحابات خلال ساعة  تحذير (بطاقة صفراء)
- بعد التحذير، كل انسحاب  حظر مؤقت متصاعد يبدأ من 15 دقيقة
- التعافي: كل مباراة كاملة (بدون انسحاب) تقلّل العداد
- التلاشي: المخالفات تنخفض تلقائياً بمرور الوقت

 معطّل تماماً في وضع المطور (ALLOW_SAME_IP=1).
 in-memory الآن، Redis-ready (بنية dict بسيطة).
"""
import os
import time

# ==========================================
# الإعدادات (مبنية على بحث الأنظمة العالمية)
# ==========================================
LEAVER_WINDOW = 60 * 60          # نافذة عدّ الانسحابات: ساعة
WARNING_THRESHOLD = 3            # 3 انسحابات/ساعة  تحذير (متسامح)

# سلّم العقوبات التصاعدي (بالثواني) — يبدأ من 15 دقيقة كما هو مطلوب
# المخالفة رقم (بعد التحذير)  المدة
PENALTY_LADDER = [
    15 * 60,        # المخالفة 4  15 دقيقة
    30 * 60,        # المخالفة 5  30 دقيقة
    60 * 60,        # المخالفة 6  ساعة
    2 * 60 * 60,    # المخالفة 7  ساعتان
    24 * 60 * 60,   # المخالفة 8+  24 ساعة
]

# التعافي: كل مباراة كاملة تقلّل العداد بـ 1
# التلاشي الزمني: مخالفة تسقط بعد هذي المدة بدون انسحاب جديد
VIOLATION_DECAY = 6 * 60 * 60    # 6 ساعات


def _dev_mode() -> bool:
    """وضع المطور — يعطّل عقوبة الانسحاب (للاختبار المحلي المتكرر). يُقرأ لحظياً."""
    from app.core.dev_mode import is_dev_mode
    return is_dev_mode()


# ==========================================
# الحالة (in-memory)
# leaver_data[user_id] = {
#   'leaves': [timestamps...],   # أوقات الانسحابات ضمن النافذة
#   'penalty_count': int,         # كم عقوبة تلقّى (للسلّم التصاعدي)
#   'banned_until': float|None,   # وقت انتهاء الحظر الحالي
#   'warned': bool,               # هل تلقّى البطاقة الصفراء
# }
# ==========================================
leaver_data = {}


def _get(user_id):
    if user_id not in leaver_data:
        leaver_data[user_id] = {
            'leaves': [], 'penalty_count': 0, 'banned_until': None, 'warned': False
        }
    return leaver_data[user_id]


def _clean_old_leaves(data):
    cutoff = time.time() - LEAVER_WINDOW
    data['leaves'] = [t for t in data['leaves'] if t >= cutoff]


# ==========================================
# تسجيل انسحاب
# ==========================================
def record_leave(user_id) -> dict:
    """
    يُستدعى عند انسحاب لاعب من مباراة.
    يرجع: {'action': 'none'|'warning'|'ban', 'ban_seconds': int, 'msg': str}
    """
    if user_id is None or _dev_mode():
        return {'action': 'none', 'ban_seconds': 0, 'msg': ''}

    data = _get(user_id)
    _clean_old_leaves(data)
    data['leaves'].append(time.time())
    leave_count = len(data['leaves'])

    # تحت العتبة  لا شيء بعد
    if leave_count < WARNING_THRESHOLD:
        return {'action': 'none', 'ban_seconds': 0, 'msg': ''}

    # وصل العتبة بالضبط ولم يُحذّر  بطاقة صفراء
    if leave_count == WARNING_THRESHOLD and not data['warned']:
        data['warned'] = True
        return {
            'action': 'warning', 'ban_seconds': 0,
            'msg': '⚠️ بطاقة صفراء: الانسحاب المتكرر يؤدي لحظر مؤقت متصاعد'
        }

    # بعد التحذير  عقوبة متصاعدة
    idx = min(data['penalty_count'], len(PENALTY_LADDER) - 1)
    ban_seconds = PENALTY_LADDER[idx]
    data['penalty_count'] += 1
    data['banned_until'] = time.time() + ban_seconds

    mins = ban_seconds // 60
    if mins >= 60:
        dur_txt = f"{mins // 60} ساعة" + (" " if mins % 60 == 0 else f" و{mins % 60} دقيقة")
    else:
        dur_txt = f"{mins} دقيقة"

    return {
        'action': 'ban', 'ban_seconds': ban_seconds,
        'msg': f'🚫 حُظرت من البحث {dur_txt} بسبب الانسحاب المتكرر'
    }


# ==========================================
# فحص الحظر (يُستدعى قبل دخول الطابور)
# ==========================================
def get_leaver_ban(user_id) -> dict | None:
    """يرجع {'remaining_seconds', 'msg'} لو محظور، أو None."""
    if user_id is None or _dev_mode():
        return None
    data = leaver_data.get(user_id)
    if not data or not data['banned_until']:
        return None
    remaining = data['banned_until'] - time.time()
    if remaining <= 0:
        data['banned_until'] = None
        return None
    mins = int(remaining // 60) + 1
    return {
        'remaining_seconds': int(remaining),
        'msg': f'🚫 أنت محظور من البحث. متبقٍ ~{mins} دقيقة (بسبب الانسحاب المتكرر)'
    }


# ==========================================
# مكافأة السلوك الجيد (مباراة كاملة)
# ==========================================
def record_clean_match(user_id) -> None:
    """
    يُستدعى عند إكمال مباراة بدون انسحاب.
    يقلّل عداد المخالفات (تعافي السمعة مثل Brawl Stars).
    """
    if user_id is None or _dev_mode():
        return
    data = leaver_data.get(user_id)
    if not data:
        return
    # نزيل أقدم انسحاب (تعافي تدريجي)
    if data['leaves']:
        data['leaves'].pop(0)
    # نخفّض عداد العقوبة تدريجياً (سلوك جيد يعيد الثقة)
    if data['penalty_count'] > 0 and len(data['leaves']) == 0:
        data['penalty_count'] = max(0, data['penalty_count'] - 1)
        if data['penalty_count'] == 0:
            data['warned'] = False


# ==========================================
# تنظيف دوري (cron)
# ==========================================
def cleanup_leaver_data() -> int:
    """يحذف بيانات اللاعبين الذين تعافوا تماماً. يرجع العدد المحذوف."""
    removed = 0
    now = time.time()
    for uid in list(leaver_data.keys()):
        data = leaver_data[uid]
        _clean_old_leaves(data)
        ban_active = data['banned_until'] and data['banned_until'] > now
        # نحذف لو: لا انسحابات حديثة + لا حظر نشط + لا عقوبات متراكمة
        if not data['leaves'] and not ban_active and data['penalty_count'] == 0:
            del leaver_data[uid]
            removed += 1
    return removed
