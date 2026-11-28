import asyncio
import os
import secrets
import random
import time
import string

matchmaking_queue = {}
rooms = {}

# الأوضاع المسموح بها — تُشتق من GameRegistry تلقائياً عند أول استخدام
_VALID_MODES: set | None = None

def _get_valid_modes() -> set:
    """يجلب أوضاع اللعب المسجّلة في GameRegistry (lazy — بعد اكتمال التسجيل)."""
    global _VALID_MODES
    if _VALID_MODES is None:
        from app.domains.games.base import GameRegistry
        _VALID_MODES = set(GameRegistry.all_modes())
    return _VALID_MODES


def _create_game_state(game_mode, room_code, p1, p2):
    """
    مصنع حالة اللعبة حسب النوع — يعتمد على GameRegistry بالكامل.
    لا if/else هنا: أي لعبة جديدة تُسجّل نفسها تلقائياً.
    """
    from app.domains.games.base import GameRegistry
    players = [
        {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'],
         'token': p1.get('token'), 'user_id': p1.get('user_id'), 'color': 'green'},
        {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'],
         'token': p2.get('token'), 'user_id': p2.get('user_id'), 'color': 'orange'},
    ]
    game_class = GameRegistry.get(game_mode)
    if game_class is None:
        print(f" [core_manager] وضع لعب غير مسجّل: {game_mode!r}")
        return None
    # كل لعبة تحدّد كيف تبني حالتها عبر __init__ مباشر
    # نستدعي CareerGameState / HuroofGameState حسب ما يعيده GameRegistry
    import inspect
    state_cls_name = f"{game_class.__name__.replace('Game', 'GameState')}"
    # نجلب الـ engine module من نفس package اللعبة
    import importlib
    module_path = game_class.__module__.rsplit('.', 1)[0] + '.engine'
    try:
        engine_module = importlib.import_module(module_path)
        state_cls = getattr(engine_module, state_cls_name)
        return state_cls(p1['sid'], p2['sid'], room_code=room_code, players=players)
    except Exception as e:
        print(f" [core_manager] فشل إنشاء حالة {game_mode}: {e}")
        return None

# ⏱ مدة انتظار الغرفة الخاصة قبل حذفها (30 دقيقة)
WAITING_ROOM_TTL = 30 * 60

# مفتاح تطوير: لتجربة اللعبة محلياً (جهاز واحد، حسابات متعددة، تكرار)
# فعّل ALLOW_SAME_IP=1 في .env — يعطّل: فحص نفس الـ IP + منع المطابقة المتكررة
# (يبقى فحص "نفس المستخدم" فعّالاً دائماً — لا تلعب ضد نفس الحساب)
# يُقرأ لحظياً من .env (تعديله يسري خلال ثانية بدون إعادة تشغيل)
def _allow_same_ip() -> bool:
    from app.core.dev_mode import is_dev_mode
    return is_dev_mode()


def add_to_queue(sid, name, avatar, game_mode, token=None, user_id=None, ip=None, request_id=None):
    # رفض أوضاع اللعب غير المعروفة قبل الدخول للطابور
    valid = _get_valid_modes()
    if not game_mode or game_mode not in valid:
        return False, f"وضع لعب غير مدعوم: {game_mode!r} (المتاح: {', '.join(sorted(valid))})"

    if any(room.get('state') in ('starting','playing') and any(player.get('user_id') == user_id
               for player in room.get('players',[])) for room in rooms.values()) and user_id:
        return False, 'لديك مباراة جارية'
    if game_mode not in matchmaking_queue:
        matchmaking_queue[game_mode] = []
    from app.sockets.state import connected_players
    # ننظّف أي مدخل عالق لنفس المستخدم من جلسة ميتة (sid لم يعد متصلاً)
    if user_id is not None:
        matchmaking_queue[game_mode] = [
            p for p in matchmaking_queue[game_mode]
            if not (p.get('user_id') == user_id
                    and p.get('sid') != sid
                    and p.get('sid') not in connected_players)
        ]
    if any(p["sid"] == sid or (user_id and p.get("user_id") == user_id)
           for mode, queue in matchmaking_queue.items() if mode != game_mode for p in queue):
        return False, "لديك طلب بحث جارٍ في لعبة أخرى"
    for p in matchmaking_queue[game_mode]:
        if p['sid'] == sid:
            return False, "أنت بالفعل في طابور البحث!"
        # نفس المستخدم في جلسة حيّة فعلاً (جهاز/تبويب آخر)  نرفض
        if user_id is not None and p.get('user_id') == user_id \
                and p.get('sid') in connected_players:
            return False, "أنت بالفعل في البحث من جهاز آخر!"
    matchmaking_queue[game_mode].append({
        'sid': sid,
        'name': name,
        'avatar': avatar,
        'token': token,
        'user_id': user_id,
        'ip': ip,
        'requestId': request_id,
        'time': time.time()
    })
    return True, "تم الانضمام لطابور البحث"


def remove_from_queue(sid, request_id=None):
    for mode, queue in matchmaking_queue.items():
        for i, p in enumerate(queue):
            if p['sid'] == sid and (request_id is None or p.get('requestId') == request_id):
                queue.pop(i)
                return True
    return False


# Initial calibration: noisier single-answer formats need more observations.
SKILL_PRIOR_MATCHES = {"huroof": 8, "career": 14, "whoami": 16, "bank": 10, "knowledge": 12}


def estimated_strength(wins, losses, mode):
    prior = SKILL_PRIOR_MATCHES.get(mode, 12)
    return (wins + prior / 2) / (wins + losses + prior)


class CandidateList(list):
    """Ordered reservation attempts and eligible counts within the evaluated sample."""


def alternatives(choices, i, j):
    """Other eligible opponents at decision time, independently for each player."""
    if isinstance(choices, CandidateList):
        return {k: choices.counts[k] - 1 for k in (i, j)}
    return {k: sum(k in pair for pair in choices) - 1 for k in (i, j)}


def sampled_pairs(size, now):
    # افحص كل الأزواج في الطوابير الصغيرة، ودوّر المرشحين في الطوابير الكبيرة.
    from itertools import combinations
    if size <= 25:
        yield from combinations(range(size), 2)
        return
    half = size // 2
    for step in range(min(12, half)):
        distance = 1 + (int(now) * 12 + step) % half
        count = half if distance * 2 == size else size
        for i in range(count):
            j = (i + distance) % size
            yield (i, j) if i < j else (j, i)


def candidate_pairs(entries, blocked, friends, previous, now, strengths=None):
    """Rank eligible pairs by unlocked class, then by the older request."""
    import heapq
    from collections import Counter
    counts = Counter()
    def scored():
        for i, j in sampled_pairs(len(entries), now):
            first, second = entries[i], entries[j]
            ids = first.get('user_id'), second.get('user_id')
            if not all(ids) or ids[0] == ids[1]:
                continue
            pair = tuple(sorted(ids))
            oldest = min(first['time'], second['time'])
            elapsed = now - oldest
            if pair in blocked or elapsed >= 30:
                continue
            same_net = first.get('ip') not in (None, 'unknown') and first['ip'] == second.get('ip')
            if pair in friends:
                threshold = 20
            elif same_net:
                threshold = 15 if pair in previous else 10
            else:
                threshold = 5 if pair in previous else 0
            if elapsed >= threshold:
                gap = abs(strengths.get(ids[0], .5) - strengths.get(ids[1], .5)) if strengths else 0
                counts[i] += 1
                counts[j] += 1
                yield threshold, oldest, gap, max(first['time'], second['time']), i, j
    choices = CandidateList((i,j) for *_,i,j in heapq.nsmallest(64, scored()))
    choices.counts = counts
    return choices


def ranked_pairs(entries, game_mode):
    if len(entries) < 2:
        return []
    from sqlalchemy import text
    from app.domains.users import friends as social
    from app.infrastructure.database import SessionLocal
    ids = list({p['user_id'] for p in entries if p.get('user_id')})
    social._init()
    with SessionLocal() as db:
        from app.domains.users.models import GameStat, User
        from app.domains.games.models import FairPlayAccount
        from datetime import datetime
        allowed = set(row[0] for row in db.query(User.id).outerjoin(FairPlayAccount, FairPlayAccount.user_id==User.id)
            .filter(User.id.in_(ids),User.is_banned.is_(False),User.is_verified.is_(True),
                    (FairPlayAccount.suspended_until.is_(None)) | (FairPlayAccount.suspended_until<=datetime.utcnow())))
        indices = sorted((i for i, entry in enumerate(entries) if entry.get('user_id') in allowed),
                         key=lambda i: entries[i]['time'])
        eligible = [entries[i] for i in indices]
        now = time.time()
        lows, highs = [], []
        for i, j in sampled_pairs(len(eligible), now):
            low, high = sorted((eligible[i]['user_id'], eligible[j]['user_id']))
            lows.append(low)
            highs.append(high)
        query = text("""
            SELECT p.lo, p.hi, f.status, r.status, EXISTS (
                SELECT 1 FROM pair_settlements h WHERE h.low_id=p.lo AND h.high_id=p.hi)
            FROM unnest(CAST(:lo AS integer[]), CAST(:hi AS integer[])) AS p(lo,hi)
            LEFT JOIN friendships f ON f.user_id=p.lo AND f.friend_id=p.hi
            LEFT JOIN friendships r ON r.user_id=p.hi AND r.friend_id=p.lo
            WHERE f.status IN ('accepted','blocked') OR r.status IN ('accepted','blocked')
               OR EXISTS (SELECT 1 FROM pair_settlements h WHERE h.low_id=p.lo AND h.high_id=p.hi)
        """)
        blocked, friends, previous = set(), set(), set()
        for low, high, forward, reverse, played in db.execute(query, {'lo': lows, 'hi': highs}):
            pair = (low, high)
            if 'blocked' in (forward, reverse):
                blocked.add(pair)
            elif 'accepted' in (forward, reverse):
                friends.add(pair)
            if played:
                previous.add(pair)
        strengths = {uid: estimated_strength(w or 0, l or 0, game_mode)
                     for uid, w, l in db.query(GameStat.user_id, GameStat.wins, GameStat.losses)
                     .filter(GameStat.user_id.in_(ids), GameStat.game_mode == game_mode)}
    choices = candidate_pairs(eligible, blocked, friends, previous, now, strengths)
    mapped = CandidateList((indices[i], indices[j]) for i,j in choices)
    mapped.counts = {indices[i]: n for i,n in choices.counts.items()}
    return mapped


def create_match_room(p1, p2, game_mode, room_code=None):
    """ينشئ غرفة مباراة لزوج متطابق (مستخرجة للمشاركة مع المسار
    العنقودي). الغرفة تعيش بذاكرة هذا الـ worker = هو مالكها."""
    players = [p1, p2]
    random.shuffle(players)
    p1, p2 = players[0], players[1]

    # room_code بـ secrets بدل random
    alphabet = string.ascii_uppercase + string.digits
    room_code = room_code or ''.join(secrets.choice(alphabet) for _ in range(6))

    rooms[room_code] = {
        'code': room_code,
        'type': 'public',
        'game_mode': game_mode,
        'state': 'starting',
        'created_at': time.time(),
        'players': [
            {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'],
             'token': p1.get('token'), 'user_id': p1.get('user_id'), 'role': 'host', 'color': 'green', 'alternatives': p1.get('alternatives')},
            {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'],
             'token': p2.get('token'), 'user_id': p2.get('user_id'), 'role': 'guest', 'color': 'orange', 'alternatives': p2.get('alternatives')},
        ],
        'game_state': _create_game_state(game_mode, room_code, p1, p2),
    }

    room_players_data = {
        'green':  {'name': p1['name'], 'avatar': p1['avatar'], 'sid': p1['sid']},
        'orange': {'name': p2['name'], 'avatar': p2['avatar'], 'sid': p2['sid']},
    }

    # نسجّل المواجهة (anti-collusion) + نمرّر user_ids للغرفة للمكافآت
    rooms[room_code]['user_ids'] = {
        p1['sid']: p1.get('user_id'),
        p2['sid']: p2.get('user_id'),
    }
    return room_code, [p1, p2], room_players_data


async def persist_reservation(room_code, matched):
    from uuid import uuid4
    from app.domains.games.match_recovery import register
    mid = uuid4().hex
    await asyncio.to_thread(register, {"code":room_code, "players":matched}, mid, True)
    room = rooms.get(room_code)
    if room is not None:
        room["settlement_id"] = mid


async def check_queue_for_match(game_mode):
    queue = matchmaking_queue.get(game_mode, [])
    if len(queue) < 2:
        return False,None,None,None
    snapshot = list(queue)
    choices = await asyncio.to_thread(ranked_pairs,snapshot,game_mode)
    # Cancellations/other searches can run during the database read.
    live_queue = matchmaking_queue.get(game_mode, [])
    live_ids = {id(entry) for entry in live_queue}
    for i,j in choices:
        p1,p2 = snapshot[i],snapshot[j]
        if id(p1) not in live_ids or id(p2) not in live_ids:
            continue
        if time.time()-min(p1['time'],p2['time']) >= 30:
            continue
        counts = alternatives(choices, i, j)
        room_code,matched,rp_data = create_match_room(dict(p1, alternatives=counts[i]), dict(p2, alternatives=counts[j]), game_mode)
        live_queue.remove(p1)
        live_queue.remove(p2)
        try:
            await persist_reservation(room_code, matched)
        except Exception:
            rooms.pop(room_code, None)
            raise
        return True,room_code,matched,rp_data
    return False,None,None,None


def create_room(room_code, sid, host_name, max_players, game_mode, ip_address, avatar, room_type="private"):
    rooms[room_code] = {
        'code': room_code,
        'host': sid,
        'max_players': max_players,
        'game_mode': game_mode,
        'ip': ip_address,
        'state': 'waiting',
        'type': room_type,
        'created_at': time.time(),   # ⏱ لمتابعة عمر الغرفة
        'players': [{'sid': sid, 'name': host_name, 'avatar': avatar, 'role': 'host', 'color': 'green'}],
        'game_state': None,
    }
    return rooms[room_code]


def join_room(room_code, sid, player_name, avatar, user_id=None):
    room = rooms.get(room_code)
    if not room:
        return False, "الغرفة غير موجودة"

    if room['state'] in ['starting', 'playing']:
        # نفس الـ sid موجود = reconnect جاهز
        for p in room['players']:
            if p['sid'] == sid:
                return True, "reconnected_ready"

        # إصلاح: اللاعب انتقل من اللوبي للعبة (sid تغيّر)
        # نربط الـ sid الجديد باللاعب حسب user_id أولاً (ثابت وموثوق 100%)
        # — الاسم فقط كخيار احتياطي (لو مافيش user_id، مثلاً زائر)
        # الربط بالاسم فقط خطير: لاعبَين بنفس الاسم يتسببوا بربط خاطئ ويعلّقوا المباراة
        if user_id is not None:
            for p in room['players']:
                if p.get('user_id') == user_id:
                    old_sid = p.get('sid')
                    p['old_sid'] = old_sid
                    p['sid'] = sid
                    p['avatar'] = avatar
                    return True, "reconnected"

        return False, "اللعبة جارية بالفعل"

    if room['state'] == 'waiting':
        for p in room['players']:
            if p['sid'] == sid:
                return True, "already_in_room"
        if len(room['players']) >= room['max_players']:
            return False, "الغرفة ممتلئة"
        room['players'].append({
            'sid': sid, 'name': player_name, 'avatar': avatar, 'role': 'guest', 'color': 'orange', 'user_id': user_id
        })
        return True, "joined"

    return False, "حالة الغرفة غير صالحة"


def leave_room(sid):
    for room_code, room in list(rooms.items()):
        # لو الـ sid المنقطع هو old_sid للاعب أعاد الربط بالفعل  نتجاهله
        # (انتقال صفحة من اللوبي للعبة ينتج socket قديم ينقطع — ليس انسحاباً)
        for p in room['players']:
            if p.get('old_sid') == sid and p.get('sid') and p.get('sid') != sid:
                return None, None  # اللاعب موجود بـ sid جديد، تجاهل القديم

        for p in room['players']:
            if p.get('sid') == sid:
                if room.get('is_solo') and room.get('game_mode') in ('knowledge', 'whoami'):
                    del rooms[room_code]
                    return room_code, None
                if room['state'] == 'waiting':
                    room['players'] = [x for x in room['players'] if x.get('sid') != sid]
                    if not room['players']:
                        del rooms[room_code]
                    return room_code, None
                else:
                    old_sid = p['sid']
                    p['old_sid'] = old_sid
                    p['sid'] = None
                    return room_code, room
    return None, None


def get_room_state(room_code):
    return rooms.get(room_code)


def cleanup_stale_waiting_rooms():
    """
    يحذف غرف الـ waiting التي تجاوز عمرها WAITING_ROOM_TTL.
    يُستدعى من cron_jobs.
    """
    now = time.time()
    stale = [
        code for code, r in list(rooms.items())
        if r.get('state') == 'waiting' and (now - r.get('created_at', now)) > WAITING_ROOM_TTL
    ]
    for code in stale:
        del rooms[code]
        print(f" [cleanup] حُذفت غرفة waiting متروكة: {code}")
    return len(stale)