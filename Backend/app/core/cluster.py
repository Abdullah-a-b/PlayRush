"""
🕸️ طبقة العنقود (Cluster) — المرحلة ب-2: multi-worker كامل

المشكلة: غرف الألعاب تعيش في ذاكرة worker واحد (كائنات Python حية
بمؤقتات وإصدارات). مع عدة workers، لاعبا المباراة قد يتصلان بworkers
مختلفة — الأحداث تصل worker لا يملك الغرفة.

الحل: نمط «الـ worker المالك» (Owner-Worker):
  1. الغرفة تعيش حيث أُنشئت — منشئها هو مالكها (سجل في Redis).
  2. أي حدث لعبة يصل worker غير المالك → يُحوَّل للمالك عبر
     Redis pub/sub، والمالك يعالجه بحالته المحلية كأن الحدث وصله
     مباشرة. البثّ الناتج يعبر كل الـ workers (AsyncRedisManager من ب-1).
  3. عضوية غرف socket.io يجب أن تُسجَّل على worker *اتصال* اللاعب —
     لذا enter_room/leave_room مُرقّعتان: لو الاتصال يعيش على worker
     آخر، تُرسل أمر تنفيذ محلي له.
  4. انقطاع لاعب على worker غير المالك → بثّ sid_gone، والمالك
     يشغّل مسار الانقطاع المعتاد (مؤقت 30ث... إلخ).
  5. مفاتيح Redis كلها بـ TTL يجدده نبض دوري — انهيار worker =
     تنظيف ذاتي، وفشل Redis = سقوط رشيق للسلوك المحلي.

النتيجة: صفر تعديل داخل محركات الألعاب الثلاثة.
بدون REDIS_URL: هذه الطبقة خاملة تماماً (سلوك worker واحد كما هو).
"""
import os
import json
import uuid
import asyncio

from app.core.redis_client import redis_enabled, redis_available, get_redis

WORKER_ID = os.environ.get("WORKER_ID") or uuid.uuid4().hex[:10]

_CH = 'pr:cluster:'           # قناة كل worker: pr:cluster:{WORKER_ID}
_CH_BCAST = 'pr:cluster:bcast'
_K_CONN = 'pr:conn:'          # sid → worker المالك للاتصال
_K_OWNER = 'pr:room_owner:'   # room_code → worker المالك للغرفة
_K_SIDROOM = 'pr:sid_room:'   # sid → room_code
_TTL = 120

# أحداث الغرف/الألعاب التي تُحوَّل للمالك
_FWD_PREFIXES = ('huroof_', 'bank_', 'career_', 'knowledge_')
_FWD_EVENTS = {
    'join_room', 'start_game', 'send_room_chat_message',
    'request_ai_question', 'join_party_mode',
    'report_opponent', 'block_opponent', 'unblock_opponent',
    'friend_request_opponent', 'remove_friend_opponent',
}

# مرجعا الدوال الأصلية بعد الترقيع
_orig_trigger = None
_orig_enter = None
_orig_leave = None
# يسجّلها connection.py: تُستدعى عند sid_gone قادم من worker آخر
on_remote_sid_gone = None


def is_forwardable(event: str) -> bool:
    return event in _FWD_EVENTS or event.startswith(_FWD_PREFIXES)


async def _r():
    if not redis_enabled():
        return None
    if not await redis_available():
        return None
    return get_redis()


# ---------- سجلات (كلها best-effort: فشل Redis لا يكسر شيئاً) ----------
async def register_conn(sid):
    r = await _r()
    if r is None:
        return
    try:
        await r.set(_K_CONN + sid, WORKER_ID, ex=_TTL)
    except Exception:
        pass


async def unregister_conn(sid):
    r = await _r()
    if r is None:
        return
    try:
        await r.delete(_K_CONN + sid, _K_SIDROOM + sid)
    except Exception:
        pass


async def conn_worker(sid):
    r = await _r()
    if r is None:
        return None
    try:
        return await r.get(_K_CONN + sid)
    except Exception:
        return None


async def claim_room(room_code):
    """يسجّل هذا الـ worker مالكاً للغرفة — يُستدعى عند إنشائها."""
    r = await _r()
    if r is None:
        return
    try:
        await r.set(_K_OWNER + room_code, WORKER_ID, ex=_TTL)
    except Exception:
        pass


async def room_owner(room_code):
    if not room_code:
        return None
    r = await _r()
    if r is None:
        return None
    try:
        return await r.get(_K_OWNER + room_code)
    except Exception:
        return None


async def sid_room(sid):
    r = await _r()
    if r is None:
        return None
    try:
        return await r.get(_K_SIDROOM + sid)
    except Exception:
        return None


async def _send(worker_id, payload):
    r = await _r()
    if r is None:
        return False
    try:
        await r.publish(_CH + worker_id, json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"⚠️ [cluster] إرسال فشل: {e}")
        return False


async def broadcast_sid_gone(sid):
    r = await _r()
    if r is None:
        return
    try:
        await r.publish(_CH_BCAST, json.dumps(
            {'t': 'sid_gone', 'sid': sid, 'origin': WORKER_ID}))
    except Exception:
        pass


# ---------- الترقيع ----------
def patch(sio):
    """يرقّع sio: تحويل أحداث الغرف للمالك + توجيه enter/leave_room
    لworker الاتصال. بدون REDIS_URL لا يُستدعى أصلاً."""
    global _orig_trigger, _orig_enter, _orig_leave
    _orig_trigger = sio._trigger_event
    _orig_enter = sio.enter_room
    _orig_leave = sio.leave_room

    async def _trigger(event, namespace, *args):
        # أحداث العملاء: args = (sid, data?) — الداخلية (connect/disconnect) تمر
        if is_forwardable(event) and args:
            try:
                sid = args[0]
                data = args[1] if len(args) > 1 else None
                room_code = None
                if isinstance(data, dict):
                    room_code = data.get('room_code') or data.get('roomCode')
                if not room_code:
                    room_code = await sid_room(sid)
                owner = await room_owner(room_code)
                if owner and owner != WORKER_ID:
                    ok = await _send(owner, {'t': 'ev', 'e': event,
                                             'sid': sid, 'd': data})
                    if ok:
                        return  # سيعالجه المالك
            except Exception as e:
                print(f"⚠️ [cluster] تحويل {event}: {e} — معالجة محلية")
        return await _orig_trigger(event, namespace, *args)

    async def _enter(sid, room, namespace=None):
        # نربط sid↔room دائماً (يُستخدم لتوجيه الأحداث اللاحقة)
        r = await _r()
        if r is not None:
            try:
                await r.set(_K_SIDROOM + sid, room, ex=_TTL)
            except Exception:
                pass
            w = await conn_worker(sid)
            if w and w != WORKER_ID:
                # الاتصال يعيش على worker آخر — العضوية تُسجَّل هناك
                if await _send(w, {'t': 'enter', 'sid': sid, 'room': room}):
                    return
        return await _orig_enter(sid, room, namespace)

    async def _leave(sid, room, namespace=None):
        r = await _r()
        if r is not None:
            try:
                await r.delete(_K_SIDROOM + sid)
            except Exception:
                pass
            w = await conn_worker(sid)
            if w and w != WORKER_ID:
                if await _send(w, {'t': 'leave', 'sid': sid, 'room': room}):
                    return
        return await _orig_leave(sid, room, namespace)

    sio._trigger_event = _trigger
    sio.enter_room = _enter
    sio.leave_room = _leave
    print(f"🕸️ [cluster] worker {WORKER_ID} — تحويل أحداث الغرف مفعّل")


# ---------- المستمع والنبض (supervised) ----------
async def cluster_subscriber_loop(sio):
    """يستمع لقناة هذا الـ worker + قناة البث: أحداث محوَّلة، أوامر
    عضوية، وإشعارات انقطاع.
    🛡️ صامد داخلياً: لو Redis غير متاح (أو انقطع) لا ينهار للـ supervisor
    كل 5ث — ينتظر بهدوء ويعيد الاتصال بنفسه، برسالة واحدة بالدقيقة."""
    if not redis_enabled():
        return
    announced_down = 0.0
    while True:
        try:
            r = get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(_CH + WORKER_ID, _CH_BCAST)
            print(f"🕸️ [cluster] worker {WORKER_ID} يستمع")
            announced_down = 0.0
            async for msg in pubsub.listen():
                if msg.get('type') != 'message':
                    continue
                try:
                    p = json.loads(msg['data'])
                    t = p.get('t')
                    if t == 'ev':
                        d = p.get('d')
                        args = (p['sid'], d) if d is not None else (p['sid'],)
                        await _orig_trigger(p['e'], '/', *args)
                    elif t == 'enter':
                        await _orig_enter(p['sid'], p['room'])
                    elif t == 'leave':
                        await _orig_leave(p['sid'], p['room'])
                    elif t == 'sid_gone':
                        if p.get('origin') != WORKER_ID and on_remote_sid_gone:
                            await on_remote_sid_gone(p['sid'])
                except Exception as e:
                    print(f"⚠️ [cluster] معالجة رسالة: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import time as _t
            now = _t.time()
            if now - announced_down >= 60:
                print(f"🕸️ [cluster] Redis غير متاح للمستمع ({type(e).__name__}) — "
                      f"إعادة محاولة هادئة كل 10ث حتى يعود")
                announced_down = now
            await asyncio.sleep(10)


async def cluster_heartbeat_loop(*_):
    """يجدد TTL: اتصالات هذا الـ worker + غرفه وارتباطات لاعبيها."""
    if not redis_enabled():
        return
    while True:
        await asyncio.sleep(30)
        r = await _r()
        if r is None:
            continue
        try:
            from app.sockets.state import connected_players
            from app.games.core_manager import rooms
            pipe = r.pipeline()
            for s in list(connected_players.keys()):
                pipe.expire(_K_CONN + s, _TTL)
            for code, room in list(rooms.items()):
                pipe.set(_K_OWNER + code, WORKER_ID, ex=_TTL)
                for pl in room.get('players', []):
                    if pl.get('sid'):
                        pipe.set(_K_SIDROOM + pl['sid'], code, ex=_TTL)
            await pipe.execute()
        except Exception as e:
            print(f"⚠️ [cluster] heartbeat: {e}")
