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
        from app.games.base import GameRegistry
        _VALID_MODES = set(GameRegistry.all_modes())
    return _VALID_MODES


def _create_game_state(game_mode, room_code, p1, p2):
    """
    مصنع حالة اللعبة حسب النوع — يعتمد على GameRegistry بالكامل.
    لا if/else هنا: أي لعبة جديدة تُسجّل نفسها تلقائياً.
    """
    from app.games.base import GameRegistry
    players = [
        {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'],
         'token': p1.get('token'), 'user_id': p1.get('user_id'), 'color': 'green'},
        {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'],
         'token': p2.get('token'), 'user_id': p2.get('user_id'), 'color': 'orange'},
    ]
    game_class = GameRegistry.get(game_mode)
    if game_class is None:
        print(f"❌ [core_manager] وضع لعب غير مسجّل: {game_mode!r}")
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
        print(f"❌ [core_manager] فشل إنشاء حالة {game_mode}: {e}")
        return None

# ⏱️ مدة انتظار الغرفة الخاصة قبل حذفها (30 دقيقة)
WAITING_ROOM_TTL = 30 * 60

# 🛠️ مفتاح تطوير: لتجربة اللعبة محلياً (جهاز واحد، حسابات متعددة، تكرار)
# فعّل ALLOW_SAME_IP=1 في .env — يعطّل: فحص نفس الـ IP + منع المطابقة المتكررة
# (يبقى فحص "نفس المستخدم" فعّالاً دائماً — لا تلعب ضد نفس الحساب)
# يُقرأ لحظياً من .env (تعديله يسري خلال ثانية بدون إعادة تشغيل)
def _allow_same_ip() -> bool:
    from app.core.dev_mode import is_dev_mode
    return is_dev_mode()


def add_to_queue(sid, name, avatar, game_mode, token=None, user_id=None, ip=None):
    # 🛡️ رفض أوضاع اللعب غير المعروفة قبل الدخول للطابور
    valid = _get_valid_modes()
    if not game_mode or game_mode not in valid:
        return False, f"وضع لعب غير مدعوم: {game_mode!r} (المتاح: {', '.join(sorted(valid))})"

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
    for p in matchmaking_queue[game_mode]:
        if p['sid'] == sid:
            return False, "أنت بالفعل في طابور البحث!"
        # 🛡️ نفس المستخدم في جلسة حيّة فعلاً (جهاز/تبويب آخر) → نرفض
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
        'time': time.time()
    })
    return True, "تم الانضمام لطابور البحث"


def remove_from_queue(sid):
    for mode, queue in matchmaking_queue.items():
        for i, p in enumerate(queue):
            if p['sid'] == sid:
                queue.pop(i)
                return True
    return False


def pair_is_valid(p1, p2):
    """🛡️ كل فحوصات صلاحية التطابق (مستخرجة لتشاركها المسار المحلي
    والمسار العنقودي على Redis): نفس المستخدم/IP، تقابل حديث،
    حظر متبادل، صداقة (منع تواطؤ)."""
    from app.services.anti_collusion import were_recently_matched
    same_user = (p1.get('user_id') is not None and
                 p1.get('user_id') == p2.get('user_id'))
    same_ip = (not _allow_same_ip() and
               p1.get('ip') not in (None, 'unknown') and
               p1.get('ip') == p2.get('ip'))
    recently_matched = (not _allow_same_ip() and
                        were_recently_matched(p1.get('user_id'), p2.get('user_id')))
    is_blocked = False
    are_friends_pair = False
    if p1.get('user_id') and p2.get('user_id'):
        from app.services.friends import is_blocked_between, are_friends
        is_blocked = is_blocked_between(p1['user_id'], p2['user_id'])
        are_friends_pair = (not _allow_same_ip() and
                            are_friends(p1['user_id'], p2['user_id']))
    ok = (not same_user and not same_ip and not recently_matched
          and not is_blocked and not are_friends_pair)
    if not ok:
        print(f"🔎 [matchmaking] لم يتطابق p1={p1.get('user_id')} مع cand={p2.get('user_id')} | "
              f"same_user={same_user} same_ip={same_ip} recently={recently_matched} "
              f"blocked={is_blocked} friends={are_friends_pair} dev={_allow_same_ip()}")
    return ok


def create_match_room(p1, p2, game_mode):
    """ينشئ غرفة مباراة لزوج متطابق (مستخرجة للمشاركة مع المسار
    العنقودي). الغرفة تعيش بذاكرة هذا الـ worker = هو مالكها."""
    from app.services.anti_collusion import record_matchup
    players = [p1, p2]
    random.shuffle(players)
    p1, p2 = players[0], players[1]

    # 🛡️ room_code بـ secrets بدل random
    alphabet = string.ascii_uppercase + string.digits
    room_code = ''.join(secrets.choice(alphabet) for _ in range(6))

    rooms[room_code] = {
        'code': room_code,
        'type': 'public',
        'game_mode': game_mode,
        'state': 'starting',
        'created_at': time.time(),
        'players': [
            {'sid': p1['sid'], 'name': p1['name'], 'avatar': p1['avatar'],
             'token': p1.get('token'), 'user_id': p1.get('user_id'), 'role': 'host', 'color': 'green'},
            {'sid': p2['sid'], 'name': p2['name'], 'avatar': p2['avatar'],
             'token': p2.get('token'), 'user_id': p2.get('user_id'), 'role': 'guest', 'color': 'orange'},
        ],
        'game_state': _create_game_state(game_mode, room_code, p1, p2),
    }

    room_players_data = {
        'green':  {'name': p1['name'], 'avatar': p1['avatar'], 'sid': p1['sid']},
        'orange': {'name': p2['name'], 'avatar': p2['avatar'], 'sid': p2['sid']},
    }

    # 🛡️ نسجّل المواجهة (anti-collusion) + نمرّر user_ids للغرفة للمكافآت
    record_matchup(p1.get('user_id'), p2.get('user_id'))
    rooms[room_code]['user_ids'] = {
        p1['sid']: p1.get('user_id'),
        p2['sid']: p2.get('user_id'),
    }
    return room_code, [p1, p2], room_players_data


def check_queue_for_match(game_mode):
    queue = matchmaking_queue.get(game_mode, [])
    if len(queue) < 2:
        return False, None, None, None

    # 🛡️ نبحث عن أول زوج صالح (الفحوصات في pair_is_valid المشتركة)
    p1 = queue[0]
    p2_index = None
    for i in range(1, len(queue)):
        if pair_is_valid(p1, queue[i]):
            p2_index = i
            break

    # ما لقينا خصم صالح لـ p1 الآن (كلهم نفس المستخدم/الشبكة) → ننتظر
    if p2_index is None:
        print(f"🔎 [matchmaking] لا يوجد خصم صالح لـ p1={p1.get('user_id')} (طابور={len(queue)})")
        return False, None, None, None
    print(f"🔎 [matchmaking] ✅ تطابق! p1={p1.get('user_id')} مع cand رقم {p2_index}")

    # نخرج الزوج الصالح من الطابور
    p2 = queue.pop(p2_index)
    p1 = queue.pop(0)

    room_code, matched, rp_data = create_match_room(p1, p2, game_mode)
    return True, room_code, matched, rp_data


def create_room(room_code, sid, host_name, max_players, game_mode, ip_address, avatar, room_type="private"):
    rooms[room_code] = {
        'code': room_code,
        'host': sid,
        'max_players': max_players,
        'game_mode': game_mode,
        'ip': ip_address,
        'state': 'waiting',
        'type': room_type,
        'created_at': time.time(),   # ⏱️ لمتابعة عمر الغرفة
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

        # 🔧 إصلاح: اللاعب انتقل من اللوبي للعبة (sid تغيّر)
        # نربط الـ sid الجديد باللاعب حسب user_id أولاً (ثابت وموثوق 100%)
        # — الاسم فقط كخيار احتياطي (لو مافيش user_id، مثلاً زائر)
        # ⚠️ الربط بالاسم فقط خطير: لاعبَين بنفس الاسم يتسببوا بربط خاطئ ويعلّقوا المباراة
        if user_id is not None:
            for p in room['players']:
                if p.get('user_id') == user_id:
                    old_sid = p.get('sid')
                    p['old_sid'] = old_sid
                    p['sid'] = sid
                    p['avatar'] = avatar
                    return True, "reconnected"

        # نقبل الربط بالاسم فقط لو ما لقيناش user_id مطابق (زائر بلا حساب مثلاً)
        for p in room['players']:
            if p.get('user_id') is None and p['name'] == player_name:
                old_sid = p.get('sid')
                p['old_sid'] = old_sid          # نحفظ القديم للمرجع
                p['sid'] = sid                  # نربط الجديد
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
            'sid': sid, 'name': player_name, 'avatar': avatar, 'role': 'guest', 'color': 'orange'
        })
        return True, "joined"

    return False, "حالة الغرفة غير صالحة"


def leave_room(sid):
    for room_code, room in list(rooms.items()):
        # 🔧 لو الـ sid المنقطع هو old_sid للاعب أعاد الربط بالفعل → نتجاهله
        # (انتقال صفحة من اللوبي للعبة ينتج socket قديم ينقطع — ليس انسحاباً)
        for p in room['players']:
            if p.get('old_sid') == sid and p.get('sid') and p.get('sid') != sid:
                return None, None  # اللاعب موجود بـ sid جديد، تجاهل القديم

        for p in room['players']:
            if p.get('sid') == sid:
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
        print(f"🧹 [cleanup] حُذفت غرفة waiting متروكة: {code}")
    return len(stale)