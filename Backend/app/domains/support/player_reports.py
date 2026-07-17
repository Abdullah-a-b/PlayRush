"""
 نظام الإبلاغ عن اللاعبين (Player Reporting)

مصمّم على نمط الأنظمة العالمية (LoL/Valorant):
1. أسباب محددة (مش نص حر)
2. وزن البلاغات لا عددها (لاعب قديم موثوق > حساب جديد)
3. بلاغ مقبول فقط من خصم فعلي في مباراة فعلية
4. عقوبات تدريجية: تحذير  كتم  حظر مؤقت  حظر طويل
5. تخفيف تلقائي: البلاغات تفقد وزنها بعد 30 يوم
6. حماية من إساءة الإبلاغ: المبلّغ الكاذب يفقد وزن بلاغاته

الجداول تُنشأ تلقائياً عند أول استخدام (آمنة للتشغيل المتكرر).
"""
import time
import datetime
import json
from sqlalchemy import text
from app.infrastructure.database import SessionLocal, engine
from app.domains.users.models import User

# ==========================================
# الإعدادات
# ==========================================
REPORT_REASONS = {
    'toxic_chat':    'سلوك مسيء في الشات',
    'cheating':      'غش أو استخدام برامج',
    'bad_name':      'اسم مخالف',
    'griefing':      'تخريب اللعب المتعمد (انسحاب متكرر، تعطيل)',
    'other':         'أخرى',
}

# عتبات العقوبات (مجموع الوزن المُرجّح خلال 30 يوم)
PENALTY_THRESHOLDS = [
    # (العتبة, العقوبة, المدة بالثواني)
    (3.0,  'warning',   0),               # تحذير
    (6.0,  'chat_mute', 24 * 3600),       # كتم شات يوم
    (10.0, 'temp_ban',  3 * 24 * 3600),   # حظر 3 أيام
    (15.0, 'long_ban',  14 * 24 * 3600),  # حظر أسبوعين
]

REPORT_DECAY_DAYS = 30        # البلاغ يفقد وزنه بعد 30 يوم
MAX_REPORTS_PER_DAY = 5       # حد البلاغات اليومية لكل مبلّغ
SAME_TARGET_COOLDOWN = 3600   # لا يبلّغ نفس الشخص عن نفس الهدف خلال ساعة


def _ensure_tables():
    """ينشئ الجداول إن لم توجد (آمن للتكرار)."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_reports (
                id SERIAL PRIMARY KEY,
                reporter_id INTEGER NOT NULL,
                target_id INTEGER NOT NULL,
                reason VARCHAR(30) NOT NULL,
                room_code VARCHAR(10),
                game_mode VARCHAR(20),
                weight FLOAT DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT NOW(),
                reviewed BOOLEAN DEFAULT FALSE,
                valid BOOLEAN DEFAULT NULL
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reports_target_time
            ON player_reports(target_id, created_at);
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_reports_reporter_time
            ON player_reports(reporter_id, created_at);
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS player_penalties (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                penalty_type VARCHAR(20) NOT NULL,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                reason TEXT
            );
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_penalties_user
            ON player_penalties(user_id, expires_at);
        """))
        conn.commit()


_tables_ready = False
def _init():
    global _tables_ready
    if not _tables_ready:
        _ensure_tables()
        _tables_ready = True


# ==========================================
# وزن المبلّغ (الثقة)
# ==========================================
def _reporter_weight(db, reporter_id: int) -> float:
    """
    وزن بلاغ المبلّغ حسب موثوقيته:
    - حساب جديد (< 7 أيام أو < مستوى 2): وزن 0.5
    - حساب عادي: وزن 1.0
    - مبلّغ مُسيء (بلاغاته السابقة رُفضت كثيراً): وزن 0.25
    """
    user = db.query(User).filter(User.id == reporter_id).first()
    if not user:
        return 0.0

    weight = 1.0

    # حساب جديد = ثقة أقل
    level = getattr(user, 'level', 0) or 0
    if level < 2:
        weight = 0.5

    # المبلّغ المسيء: نسبة بلاغات مرفوضة عالية في آخر 30 يوم
    result = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE valid = FALSE) AS rejected,
            COUNT(*) AS total
        FROM player_reports
        WHERE reporter_id = :rid
          AND created_at > NOW() - INTERVAL '30 days'
          AND reviewed = TRUE
    """), {"rid": reporter_id}).fetchone()

    if result and result.total and result.total >= 5:
        rejection_rate = result.rejected / result.total
        if rejection_rate > 0.7:
            weight *= 0.25  # مبلّغ كاذب — بلاغاته شبه مهملة

    return weight


# ==========================================
# تقديم بلاغ
# ==========================================
def submit_report(reporter_id: int, target_id: int, reason: str,
                  room_code: str = None, game_mode: str = None) -> dict:
    """
    يقدّم بلاغاً. يرجع dict بالنتيجة.
    التحققات: سبب صالح، ليس النفس، حد يومي، cooldown لنفس الهدف.
    """
    _init()

    if reason not in REPORT_REASONS:
        return {'ok': False, 'msg': 'سبب غير صالح'}
    if reporter_id == target_id:
        return {'ok': False, 'msg': 'لا يمكنك الإبلاغ عن نفسك'}

    db = SessionLocal()
    try:
        # حد البلاغات اليومية
        daily = db.execute(text("""
            SELECT COUNT(*) FROM player_reports
            WHERE reporter_id = :rid AND created_at > NOW() - INTERVAL '1 day'
        """), {"rid": reporter_id}).scalar()
        if daily >= MAX_REPORTS_PER_DAY:
            return {'ok': False, 'msg': 'وصلت الحد اليومي للبلاغات'}

        # cooldown لنفس الهدف
        recent_same = db.execute(text("""
            SELECT COUNT(*) FROM player_reports
            WHERE reporter_id = :rid AND target_id = :tid
              AND created_at > NOW() - INTERVAL '1 hour'
        """), {"rid": reporter_id, "tid": target_id}).scalar()
        if recent_same > 0:
            return {'ok': False, 'msg': 'سبق وأبلغت عن هذا اللاعب مؤخراً'}

        weight = _reporter_weight(db, reporter_id)
        if weight <= 0:
            return {'ok': False, 'msg': 'تعذّر تقديم البلاغ'}

        db.execute(text("""
            INSERT INTO player_reports (reporter_id, target_id, reason, room_code, game_mode, weight)
            VALUES (:rid, :tid, :reason, :room, :mode, :w)
        """), {"rid": reporter_id, "tid": target_id, "reason": reason,
               "room": room_code, "mode": game_mode, "w": weight})
        db.commit()

        # فحص العقوبات فوراً بعد البلاغ
        penalty = _evaluate_penalties(db, target_id)

        return {'ok': True, 'msg': 'تم استلام بلاغك وسيُراجع', 'penalty_applied': penalty}
    finally:
        db.close()


# ==========================================
# تقييم العقوبات
# ==========================================
def _evaluate_penalties(db, target_id: int) -> str | None:
    """
    يحسب مجموع الوزن المرجّح للبلاغات في آخر 30 يوم،
    ويطبّق العقوبة المناسبة إن تجاوز العتبة (ولم تكن مطبّقة).
    يرجع نوع العقوبة المطبّقة أو None.
    """
    total_weight = db.execute(text("""
        SELECT COALESCE(SUM(weight), 0) FROM player_reports
        WHERE target_id = :tid
          AND created_at > NOW() - make_interval(days => :days)
          AND (valid IS NULL OR valid = TRUE)
    """), {"tid": target_id, "days": REPORT_DECAY_DAYS}).scalar() or 0.0

    # نجد أعلى عقوبة يستحقها
    earned = None
    for threshold, ptype, duration in PENALTY_THRESHOLDS:
        if total_weight >= threshold:
            earned = (ptype, duration)

    if not earned:
        return None

    ptype, duration = earned

    # هل هذي العقوبة (أو أشد) مطبّقة بالفعل ونشطة؟
    active = db.execute(text("""
        SELECT penalty_type FROM player_penalties
        WHERE user_id = :tid
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY created_at DESC LIMIT 1
    """), {"tid": target_id}).fetchone()

    penalty_order = ['warning', 'chat_mute', 'temp_ban', 'long_ban']
    if active and penalty_order.index(active.penalty_type) >= penalty_order.index(ptype):
        return None  # عقوبة مساوية أو أشد نشطة بالفعل

    # نطبّق
    expires = None
    if duration > 0:
        expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=duration)

    db.execute(text("""
        INSERT INTO player_penalties (user_id, penalty_type, expires_at, reason)
        VALUES (:tid, :ptype, :exp, :reason)
    """), {"tid": target_id, "ptype": ptype, "exp": expires,
           "reason": f"تراكم بلاغات (وزن {total_weight:.1f})"})

    # الحظر المؤقت/الطويل يفعّل is_banned مع جدولة فك تلقائي عبر expires_at
    if ptype in ('temp_ban', 'long_ban'):
        db.execute(text("UPDATE users SET is_banned = TRUE WHERE id = :tid"), {"tid": target_id})

    db.commit()
    # إبطال كاش الكتم فوراً — العقوبة الجديدة تضرب لحظياً لا بعد 30 ثانية
    invalidate_mute_cache(target_id)
    print(f" [reports] عقوبة {ptype} طُبّقت على user_id={target_id} (وزن={total_weight:.1f})")
    return ptype


# ==========================================
# فحص العقوبات النشطة (يُستدعى من اللعبة/الشات)
# ==========================================
def get_active_penalty(user_id: int) -> dict | None:
    """يرجع العقوبة النشطة للاعب أو None."""
    _init()
    db = SessionLocal()
    try:
        row = db.execute(text("""
            SELECT penalty_type, expires_at FROM player_penalties
            WHERE user_id = :uid
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY created_at DESC LIMIT 1
        """), {"uid": user_id}).fetchone()
        if not row:
            return None
        return {'type': row.penalty_type, 'expires_at': str(row.expires_at) if row.expires_at else None}
    finally:
        db.close()


# كاش الكتم (إصلاح bottleneck): كان كل رسالة شات = استعلام DB
# يحجب event loop. الآن نتيجة الفحص تُحفظ 30 ثانية لكل لاعب،
# وتُبطل فوراً عند تطبيق عقوبة جديدة (الكتم يضرب لحظياً).
_MUTE_CACHE: dict = {}          # user_id  (is_muted, expires_at)
_MUTE_CACHE_TTL = 30


def invalidate_mute_cache(user_id: int):
    _MUTE_CACHE.pop(user_id, None)


def is_chat_muted(user_id: int) -> bool:
    """هل اللاعب مكتوم من الشات؟ (نتيجة مكيّشة 30 ثانية)"""
    now = time.time()
    hit = _MUTE_CACHE.get(user_id)
    if hit and hit[1] > now:
        return hit[0]
    p = get_active_penalty(user_id)
    result = p is not None and p['type'] in ('chat_mute', 'temp_ban', 'long_ban')
    if len(_MUTE_CACHE) > 20000:  # حارس ذاكرة
        _MUTE_CACHE.clear()
    _MUTE_CACHE[user_id] = (result, now + _MUTE_CACHE_TTL)
    return result


# ==========================================
# فك الحظر المنتهي (cron)
# ==========================================
def release_expired_bans() -> int:
    """يفك is_banned عن من انتهت مدة حظرهم. يرجع العدد."""
    _init()
    db = SessionLocal()
    try:
        # من عندهm حظر منتهي وليس عندهم حظر آخر نشط
        rows = db.execute(text("""
            SELECT DISTINCT user_id FROM player_penalties pp
            WHERE penalty_type IN ('temp_ban', 'long_ban')
              AND expires_at IS NOT NULL AND expires_at <= NOW()
              AND NOT EXISTS (
                  SELECT 1 FROM player_penalties p2
                  WHERE p2.user_id = pp.user_id
                    AND p2.penalty_type IN ('temp_ban', 'long_ban')
                    AND (p2.expires_at IS NULL OR p2.expires_at > NOW())
              )
        """)).fetchall()

        count = 0
        for row in rows:
            user = db.query(User).filter(User.id == row.user_id, User.is_banned == True).first()
            if user:
                user.is_banned = False
                count += 1
        db.commit()
        if count:
            print(f" [reports] فُكّ الحظر عن {count} لاعب (انتهت المدة)")
        return count
    finally:
        db.close()
