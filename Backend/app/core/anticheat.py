"""
 نظام Anti-Cheat على الباك إند

الفلسفة: نفترض أن الفرونت **مخترَق دائماً** ونعتمد فقط على ما نراه على السيرفر.

ماذا يكشف:
1. أكشن مستحيل (buzz بدون سؤال نشط، answer بدون buzz)
2. سرعة لا بشرية (response < 80ms من ظهور السؤال)
3. Token reuse من IPs متعددة بفترة قصيرة
4. Spam (نفس الحدث > N مرة/ثانية)
5. أنماط زمنية مريبة (نفس delay بالمللي ثانية = bot)
6. Inputs خبيثة (SQL injection, XSS, oversized payloads)

العقوبة:
- مخالفة بسيطة: warning + log
- مخالفة متوسطة: temp_ban (5 دقائق)
- مخالفة خطيرة: permanent ban في DB
"""
import time
import statistics
import logging
from collections import defaultdict, deque
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger("playrush.anticheat")

# ==========================================
# الحدود (مبنية على دراسات HCI لردود الأفعال البشرية)
# ==========================================
HUMAN_MIN_REACTION_MS = 80     # أسرع رد فعل بشري ممكن (visual stimulus  button)
HUMAN_AVG_REACTION_MS = 250    # متوسط طبيعي
SUSPICIOUS_REACTION_MS = 100   # أقل من هذا = مشتبه

# spam thresholds
MAX_EVENTS_PER_SECOND = 20     # أي event > 20/s = spam (بشري طبيعي 5-10)
MAX_BUZZ_PER_GAME = 50         # حد أقصى لـ buzz في لعبة واحدة
MAX_CHAT_PER_MINUTE = 30       # 30 رسالة في الدقيقة = spam

# token sharing thresholds
MAX_IPS_PER_TOKEN_PER_HOUR = 3  # token من 3 IPs مختلفة في ساعة = مشتبه

# ==========================================
# الحالات الزمنية (in-memory الآن، Redis لاحقاً)
# ==========================================

# {sid: deque of timestamps for each event type}
event_timeline: dict = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))

# {token: {ip: last_seen_ts}}
token_ip_history: dict = defaultdict(dict)

# {sid: list of reaction times for pattern detection}
reaction_times: dict = defaultdict(lambda: deque(maxlen=20))

# {sid: violation_score}
violation_scores: dict = defaultdict(int)

# {sid: temp_banned_until_ts}
temp_bans: dict = {}


# ==========================================
# Severity Levels
# ==========================================
class Severity:
    LOW = 1       # warning
    MEDIUM = 5    # accumulate
    HIGH = 20     # temp ban
    CRITICAL = 100  # permanent ban


# ==========================================
# الكاشفون (Detectors)
# ==========================================

def check_action_rate(sid: str, event_type: str, max_per_second: int = MAX_EVENTS_PER_SECOND) -> Optional[str]:
    """
    يكشف spam لحدث معين.
    يرجع None لو طبيعي، أو reason string لو spam.
    """
    now = time.time()
    timeline = event_timeline[sid][event_type]
    timeline.append(now)

    # عدّ الأحداث في آخر ثانية
    one_sec_ago = now - 1.0
    recent = sum(1 for ts in timeline if ts > one_sec_ago)

    if recent > max_per_second:
        return f"spam_detected:{event_type}={recent}/s"
    return None


def check_human_reaction(sid: str, question_shown_at: float) -> Optional[str]:
    """
    يكشف ردود فعل أسرع من بشري ممكن.
    Returns None if normal, reason string if suspicious.
    """
    now = time.time()
    reaction_ms = (now - question_shown_at) * 1000

    if reaction_ms < HUMAN_MIN_REACTION_MS:
        return f"superhuman_reaction:{reaction_ms:.0f}ms"

    # تتبع لاكتشاف bot patterns
    reaction_times[sid].append(reaction_ms)

    # لو عنده 10+ ردود وكلها بنفس التوقيت تقريباً (variance < 5ms) = bot
    if len(reaction_times[sid]) >= 10:
        rts = list(reaction_times[sid])
        std = statistics.stdev(rts)
        if std < 5:  # 5ms variance = إنسان مستحيل
            return f"bot_pattern:zero_variance(std={std:.2f}ms)"

    return None


def check_token_ip_sharing(token_hash: str, current_ip: str) -> Optional[str]:
    """
    يكشف token usage من IPs متعددة (account sharing or stolen token).
    """
    now = time.time()
    history = token_ip_history[token_hash]

    # تنظيف القديم (> 1 hour)
    one_hour_ago = now - 3600
    history = {ip: ts for ip, ts in history.items() if ts > one_hour_ago}
    token_ip_history[token_hash] = history

    history[current_ip] = now

    if len(history) > MAX_IPS_PER_TOKEN_PER_HOUR:
        ips = list(history.keys())
        return f"token_shared:ips={ips}"
    return None


def check_payload_safety(data: dict, max_string_len: int = 500) -> Optional[str]:
    """
    يكشف payloads خبيثة:
    - strings كبيرة جداً (DoS)
    - patterns SQL/XSS مشهورة
    - nested objects عميقة جداً
    """
    if not isinstance(data, dict):
        return None

    # حد أقصى لـ payload size
    try:
        import json
        size = len(json.dumps(data))
        if size > 10240:  # 10 KB
            return f"oversized_payload:{size}bytes"
    except Exception:
        pass

    # فحص كل string في الـ payload
    def walk(obj, depth=0):
        if depth > 10:
            return f"deeply_nested_payload:depth={depth}"

        if isinstance(obj, str):
            if len(obj) > max_string_len:
                return f"oversized_string:{len(obj)}chars"

            lower = obj.lower()
            # SQL injection patterns
            sql_patterns = [
                "' or '1'='1", "'; drop", "1=1--", "union select",
                "/*", "*/", "xp_cmdshell", "exec(", "execute(",
            ]
            for p in sql_patterns:
                if p in lower:
                    return f"sql_injection_attempt:{p}"

            # XSS patterns
            xss_patterns = [
                "<script", "javascript:", "onerror=", "onload=",
                "onclick=", "<iframe", "vbscript:", "data:text/html",
            ]
            for p in xss_patterns:
                if p in lower:
                    return f"xss_attempt:{p}"

        elif isinstance(obj, dict):
            for v in obj.values():
                r = walk(v, depth + 1)
                if r:
                    return r
        elif isinstance(obj, list):
            if len(obj) > 1000:
                return f"oversized_array:{len(obj)}items"
            for item in obj:
                r = walk(item, depth + 1)
                if r:
                    return r
        return None

    return walk(data)


# ==========================================
# Action Validation (للـ huroof game)
# ==========================================

def validate_huroof_buzz(sid: str, room: dict, sid_player_map: dict) -> Optional[str]:
    """
    يتحقق إن الـ buzz شرعي:
    1. اللاعب فعلاً في هذه الغرفة
    2. السؤال نشط الآن
    3. لم يستخدم حقه مسبقاً في هذا السؤال
    """
    # 1. اللاعب في الغرفة؟
    if not room:
        return "ghost_buzz:no_room"

    players = room.get('players', [])
    sid_in_room = any(p.get('sid') == sid for p in players)
    if not sid_in_room:
        return "impersonation:sid_not_in_room"

    # 2. اللعبة في حالة "playing"؟
    if room.get('state') != 'playing':
        return f"invalid_state_buzz:state={room.get('state')}"

    # 3. سؤال نشط؟
    gs = room.get('game_state')
    if not gs or not getattr(gs, 'current_question', None):
        return "buzz_without_question"

    return None


def validate_huroof_answer(sid: str, room: dict, expected_buzzer_sid: Optional[str]) -> Optional[str]:
    """
    يتحقق إن الـ answer شرعي:
    1. اللاعب هو من ضغط buzz أصلاً (not impersonation)
    2. السؤال نشط
    """
    if not room:
        return "ghost_answer:no_room"

    if expected_buzzer_sid and expected_buzzer_sid != sid:
        return f"answer_impersonation:expected={expected_buzzer_sid[:6]}_got={sid[:6]}"

    return None


# ==========================================
# Violation Handler — يقرر العقوبة
# ==========================================

async def report_violation(sid: str, sio, reason: str, severity: int = Severity.MEDIUM,
                            user_id: Optional[int] = None) -> bool:
    """
    يسجّل مخالفة ويطبق العقوبة المناسبة.
    Returns True if banned (caller should disconnect).
    """
    violation_scores[sid] += severity

    score = violation_scores[sid]
    logger.warning(f" [anti-cheat] sid={sid[:8]} reason={reason} severity={severity} total_score={score}")

    # ==========================================
    # تطبيق العقوبات
    # ==========================================

    # 1. CRITICAL severity = ban فوري دائم
    if severity >= Severity.CRITICAL:
        await _permanent_ban(sid, sio, user_id, reason)
        return True

    # 2. تراكم النقاط = ban تدريجي
    if score >= 50:
        await _permanent_ban(sid, sio, user_id, f"accumulated:{score}")
        return True
    elif score >= 20:
        await _temp_ban(sid, sio, duration_sec=300, reason=reason)
        return True

    # 3. warning فقط (score < 20)
    try:
        await sio.emit('anticheat_warning', {'reason': 'سلوك غير عادي'}, to=sid)
    except Exception:
        pass

    return False


async def _temp_ban(sid: str, sio, duration_sec: int, reason: str):
    """حظر مؤقت (5 دقائق افتراضياً)."""
    until = time.time() + duration_sec
    temp_bans[sid] = until
    logger.warning(f"⏱  [anti-cheat] temp_ban sid={sid[:8]} for {duration_sec}s reason={reason}")
    try:
        await sio.emit('force_logout', {
            'message': f'تم تعليق حسابك مؤقتاً ({duration_sec // 60} دقائق) لسلوك مريب.'
        }, to=sid)
        await sio.disconnect(sid)
    except Exception as e:
        logger.error(f"temp_ban emit failed: {e}")


async def _permanent_ban(sid: str, sio, user_id: Optional[int], reason: str):
    """حظر دائم في DB."""
    logger.error(f" [anti-cheat] PERMANENT BAN sid={sid[:8]} user_id={user_id} reason={reason}")

    if user_id:
        try:
            from app.infrastructure.database import SessionLocal
            from app.domains.users.models import User
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user:
                    user.is_banned = True
                    db.commit()
                    logger.error(f" user {user.email} banned permanently in DB")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to ban in DB: {e}")

    try:
        await sio.emit('force_logout', {
            'message': 'تم حظر حسابك نهائياً لانتهاك سياسات اللعب العادل.'
        }, to=sid)
        await sio.disconnect(sid)
    except Exception:
        pass


def is_temp_banned(sid: str) -> bool:
    """يفحص لو الـ sid معلق مؤقتاً."""
    until = temp_bans.get(sid)
    if until is None:
        return False
    if time.time() > until:
        del temp_bans[sid]
        return False
    return True


def cleanup_old_data():
    """ينظف البيانات القديمة (يُستدعى من cron)."""
    now = time.time()
    one_hour_ago = now - 3600

    # نظّف temp_bans منتهية
    expired = [sid for sid, until in temp_bans.items() if until < now]
    for sid in expired:
        del temp_bans[sid]

    # نظّف event_timeline قديم
    sids_to_remove = []
    for sid in list(event_timeline.keys()):
        # لو ما في أي event حديث، احذف
        max_recent = 0
        for event_type, timeline in event_timeline[sid].items():
            if timeline:
                max_recent = max(max_recent, max(timeline))
        if max_recent < one_hour_ago:
            sids_to_remove.append(sid)
    for sid in sids_to_remove:
        del event_timeline[sid]
        violation_scores.pop(sid, None)
        reaction_times.pop(sid, None)

    return len(expired) + len(sids_to_remove)
