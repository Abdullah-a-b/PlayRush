import os
import time
import asyncio
import socket
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()  # يضمن تحميل .env مهما كان ترتيب الاستيراد
except Exception:
    pass
from app.sockets.state import active_codes, host_chat_ids
import app.sockets.state as state

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BOT_USERNAME = "@p_rushbot"

# قفل على مستوى الجهاز: يضمن أن عملية واحدة فقط تسحب تحديثات البوت.
# ضروري لأن WORKERS>1 (خصوصاً وضع المنافذ المتعددة على ويندوز) يشغّل عدة
# عمليات، ولو سحبت كلها نفس التوكن يحدث 409 Conflict ولا أحد يستقبل الرسائل.
_bot_lock_sock = None

def try_become_bot_leader(port=8399):
    """يحاول حجز منفذ محلي ثابت. أول عملية تنجح تصبح 'القائد' وتسحب التحديثات؛
    بقية العمليات تفشل في الحجز فلا تسحب (تتجنّب 409)."""
    global _bot_lock_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        _bot_lock_sock = s  # نبقيه مفتوحاً طوال عمر العملية
        return True
    except OSError:
        try:
            s.close()
        except Exception:
            pass
        return False


# ---- تخزين الرموز/الروابط: Redis (مشترك بين الـ workers) مع سقوط للذاكرة ----
import json as _json

def _redis():
    try:
        from app.infrastructure.redis_client import redis_enabled, get_redis
        if redis_enabled():
            return get_redis()
    except Exception:
        pass
    return None

async def _store_code(code, sid, party_token):
    active_codes[code] = {"sid": sid, "party_token": party_token, "expires": time.time() + 30}
    r = _redis()
    if r is not None:
        try:
            await r.setex(f"pr:hostcode:{code}", 30, _json.dumps({"sid": sid, "party_token": party_token}))
        except Exception:
            pass

async def _pop_code(code):
    """يرجّع {sid, party_token} ويحذف الرمز — يفحص Redis أولاً ثم الذاكرة."""
    r = _redis()
    if r is not None:
        try:
            raw = await r.get(f"pr:hostcode:{code}")
            if raw:
                await r.delete(f"pr:hostcode:{code}")
                data = _json.loads(raw)
                active_codes.pop(code, None)
                return data
        except Exception:
            pass
    entry = active_codes.pop(code, None)
    if entry:
        return {"sid": entry.get("sid"), "party_token": entry.get("party_token")}
    return None

async def _mark_linked(party_token, chat_id):
    if not party_token:
        return
    state.linked_hosts[party_token] = {"chat_id": chat_id, "ts": time.time()}
    r = _redis()
    if r is not None:
        try:
            await r.setex(f"pr:linked:{party_token}", 300, str(chat_id))
        except Exception:
            pass

async def _is_linked(party_token):
    if not party_token:
        return False
    rec = state.linked_hosts.get(party_token)
    if rec and (time.time() - rec['ts'] < 300):
        return True
    r = _redis()
    if r is not None:
        try:
            return bool(await r.get(f"pr:linked:{party_token}"))
        except Exception:
            pass
    return False

async def _consume_linked(party_token):
    """يحذف الربط بعد تسليمه مرة واحدة — يمنع إعادة توجيه الصفحة عند الرجوع للّوبي."""
    if not party_token:
        return
    state.linked_hosts.pop(party_token, None)
    r = _redis()
    if r is not None:
        try:
            await r.delete(f"pr:linked:{party_token}")
        except Exception:
            pass

async def telegram_bot_listener(sio):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"

    if not TELEGRAM_TOKEN:
        print(" [telegram] TELEGRAM_TOKEN غير مضبوط — البوت لن يستقبل أي رسالة")
        return

    # مهم: نحذف أي webhook مضبوط على البوت، وإلا getUpdates يرجع 409 ولن نستقبل رسائل
    # (الرموز/الدعم /reply /close كلها تعتمد على استقبال الرسائل عبر getUpdates)
    try:
        r = await asyncio.to_thread(requests.get, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5)
        print(f" [telegram] deleteWebhook(drop_pending) -> {r.status_code}")
    except Exception as e:
        print(" [telegram] deleteWebhook فشل:", e)

    while True:
        try:
            current_time = time.time()
            expired = [c for c, data in active_codes.items() if data['expires'] < current_time]
            for c in expired:
                del active_codes[c]
            # تنظيف الروابط الثابتة القديمة (أكثر من 5 دقائق)
            stale = [t for t, rec in state.linked_hosts.items() if current_time - rec['ts'] > 300]
            for t in stale:
                del state.linked_hosts[t]

            response = await asyncio.to_thread(requests.get, f"{url}?offset={state.LAST_UPDATE_ID + 1}&timeout=1", timeout=2)

            if response.status_code != 200:
                # 409 = بوت آخر يسحب التحديثات (سيرفر منشور + محلي معاً) أو webhook باقٍ
                try:
                    print(f" [telegram] getUpdates status {response.status_code}: {response.text[:200]}")
                except Exception:
                    pass

            if response.status_code == 200:
                data = response.json()
                for update in data.get("result", []):
                    state.LAST_UPDATE_ID = update["update_id"]
                    msg = update.get("message", {})
                    text = str(msg.get("text", "")).strip()
                    chat_id = msg.get("chat", {}).get("id")

                    # هل هذا المُرسِل هو الأدمن (المطوّر)؟ — أوامر الدعم له فقط
                    admin_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
                    is_admin = admin_id and str(chat_id) == str(admin_id)

                    # محاولة الربط: الرسالة نفسها (رمز)، أو payload بعد /start (رابط عميق)
                    candidate = None
                    if text.startswith("/start "):
                        candidate = text.split(" ", 1)[1].strip()
                    elif text and not text.startswith("/"):
                        candidate = text

                    link_entry = await _pop_code(candidate) if candidate else None

                    if link_entry:
                        sid = link_entry.get('sid')
                        party_token = link_entry.get('party_token')
                        host_chat_ids['admin'] = chat_id
                        await _mark_linked(party_token, chat_id)

                        if party_token:
                            await sio.emit('host_linked_success', {}, room=f"party:{party_token}")
                        if sid:
                            await sio.emit('host_linked_success', {}, to=sid)

                        success_msg = "🎯 تم ربطك بنجاح كمدير للجلسة! الإجابات ستصلك هنا."
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': success_msg})

                    elif text in ["/start", "بدء"]:
                        # رسالة عامة للاعبين (إدارة الجلسة) + أوامر الدعم تظهر للأدمن فقط
                        welcome_msg = "👋 أهلاً بك في مدير لعبة PlayRush!\n\n🔑 لربط جلسة لعبة: أرسل الرمز السري الذي يظهر على الشاشة."
                        if is_admin:
                            welcome_msg += "\n\n🎧 أوامر الدعم (للأدمن):\n/reply <رقم> <ردك>\n/close <رقم>"
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': welcome_msg})

                    elif text == "/myid":
                        # متاح للجميع — فقط يعرض chat_id الخاص بالمُرسِل (لا يكشف شيئاً حساساً)
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': f"🆔 chat_id الخاص بك:\n{chat_id}\n\n(للمطوّر) ضعه في .env:\nTELEGRAM_ADMIN_CHAT_ID={chat_id}"})

                    elif text.startswith("/reply "):
                        # أوامر الدعم للأدمن فقط
                        if is_admin:
                            await _handle_reply_command(sio, text, chat_id)
                        else:
                            await _send_tg(chat_id, "🔒 هذا الأمر مخصّص لإدارة الدعم فقط.")

                    elif text.startswith("/close "):
                        if is_admin:
                            await _handle_close_command(sio, text, chat_id)
                        else:
                            await _send_tg(chat_id, "🔒 هذا الأمر مخصّص لإدارة الدعم فقط.")
        except Exception:
            pass 
        
        await asyncio.sleep(1)


async def _send_tg(chat_id, text):
    try:
        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': text})
    except Exception:
        pass


async def _notify_player_socket(sio, user_id, message):
    """يُشعر اللاعب حيّاً (لو متصل) برد/إغلاق تذكرته."""
    try:
        from app.domains.notifications.service import add_notification, find_online_sid
        notif = add_notification(user_id, 'support_reply', message)
        online_sid = find_online_sid(user_id)
        if online_sid and notif:
            await sio.emit('new_notification', notif, to=online_sid)
    except Exception:
        pass


async def _handle_reply_command(sio, text, chat_id):
    """/reply <ticket_id> <نص>"""
    parts = text.split(" ", 2)
    if len(parts) < 3:
        await _send_tg(chat_id, "الصيغة: /reply <رقم التذكرة> <نص الرد>")
        return
    try:
        ticket_id = int(parts[1])
    except ValueError:
        await _send_tg(chat_id, "رقم التذكرة غير صالح")
        return
    reply_text = parts[2].strip()

    from app.domains.support.service import admin_reply_ticket
    result = await asyncio.to_thread(admin_reply_ticket, ticket_id, reply_text)
    await _send_tg(chat_id, ("✅ " if result['ok'] else "⚠️ ") + result['msg'])

    # نُشعر اللاعب
    if result.get('ok') and result.get('user_id'):
        await _notify_player_socket(sio, result['user_id'],
                                    f'رد الدعم على تذكرتك #{ticket_id}')


async def _handle_close_command(sio, text, chat_id):
    """/close <ticket_id>"""
    parts = text.split(" ", 1)
    if len(parts) < 2:
        await _send_tg(chat_id, "الصيغة: /close <رقم التذكرة>")
        return
    try:
        ticket_id = int(parts[1].strip())
    except ValueError:
        await _send_tg(chat_id, "رقم التذكرة غير صالح")
        return

    from app.domains.support.service import admin_close_ticket
    result = await asyncio.to_thread(admin_close_ticket, ticket_id)
    await _send_tg(chat_id, ("✅ " if result['ok'] else "⚠️ ") + result['msg'])

    if result.get('ok') and result.get('user_id'):
        await _notify_player_socket(sio, result['user_id'],
                                    f'أُغلقت تذكرتك #{ticket_id}')

async def send_secret_to_mobile(question, answer):
    CHAT_ID = host_chat_ids.get('admin')
    if not CHAT_ID: return
    msg = f"السؤال: {question}\n🎯 الإجابة: {answer}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        await asyncio.to_thread(requests.post, url, data={'chat_id': CHAT_ID, 'text': msg}, timeout=2)
    except Exception as e:
        print("لم يتم إرسال التليجرام:", e)


def _get_admin_chat_id():
    """
    يجلب chat_id الأدمن للإشعارات.
    الأولوية: TELEGRAM_ADMIN_CHAT_ID في .env (ثابت، لا يضيع)
    ثم host_chat_ids المؤقت (لو ربطت جلسة).
    """
    fixed = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if fixed:
        return fixed
    return host_chat_ids.get('admin')


def notify_new_ticket_sync(ticket_id, player_name, category_label, subject, message):
    """
    إشعار تيليجرام بتذكرة دعم جديدة (نسخة متزامنة).
     يُرسَل فقط لـ TELEGRAM_ADMIN_CHAT_ID الثابت — لا يُرسَل أبداً لجلسة لاعب مربوطة
    (لأن البوت علني ويستخدمه اللاعبون لإدارة الجلسات).
    """
    CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not CHAT_ID or not TELEGRAM_TOKEN:
        print(f" [support] تذكرة #{ticket_id} لم يُرسل إشعارها — اضبط TELEGRAM_ADMIN_CHAT_ID في .env")
        return
    body = (message or '')[:300]
    msg = (
        f"🎧 تذكرة دعم جديدة #{ticket_id}\n"
        f"👤 اللاعب: {player_name}\n"
        f"📂 الفئة: {category_label}\n"
        f"📝 الموضوع: {subject or '—'}\n"
        f"💬 الرسالة:\n{body}\n\n"
        f"↩️ للرد: أرسل\n/reply {ticket_id} نص ردك\n"
        f"🔒 للإغلاق: أرسل\n/close {ticket_id}"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={'chat_id': CHAT_ID, 'text': msg}, timeout=3)
    except Exception as e:
        print("لم يتم إرسال إشعار التذكرة:", e)

def register_telegram_events(sio):
    import random
    @sio.event
    async def generate_host_code(sid, data):
        party_token = (data or {}).get('party_token')
        code = str(random.randint(1000, 9999))
        await _store_code(code, sid, party_token)
        if party_token:
            await sio.enter_room(sid, f"party:{party_token}")
        await sio.emit('receive_host_code', {"code": code, "bot": BOT_USERNAME}, to=sid)

    @sio.event
    async def report_party_question(sid, data):
        """إبلاغ عن سؤال في وضع الجمعات — يُرسل لتيليجرام المطوّر (الأدمن) بضغطة، بلا كتابة."""
        data = data or {}
        question = str(data.get('question', '')).strip()[:400]
        answer   = str(data.get('answer', '')).strip()[:200]
        letter   = str(data.get('letter', '')).strip()[:8]

        admin_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
        if not admin_id:
            await sio.emit('party_report_ack', {'ok': False, 'msg': 'لم يتم ضبط قناة الإبلاغ.'}, to=sid)
            return

        msg = (
            "🚩 بلاغ عن سؤال (وضع الجمعات)\n"
            f"— الحرف: {letter or '—'}\n"
            f"— السؤال: {question or '—'}\n"
            f"— الإجابة المسجّلة: {answer or '—'}"
        )
        await _send_tg(admin_id, msg)
        await sio.emit('party_report_ack', {'ok': True, 'msg': 'تم إرسال البلاغ للمطوّر. شكراً!'}, to=sid)

    @sio.event
    async def register_party_token(sid, data):
        # عند كل اتصال/إعادة اتصال: نعيد إدخال السوكت للغرفة الثابتة + نسلّم الربط لو تم أثناء الانقطاع
        party_token = (data or {}).get('party_token')
        if not party_token:
            return
        await sio.enter_room(sid, f"party:{party_token}")
        if await _is_linked(party_token):
            await sio.emit('host_linked_success', {}, to=sid)
            await _consume_linked(party_token)

    @sio.event
    async def check_host_link(sid, data):
        party_token = (data or {}).get('party_token')
        if not party_token:
            return
        if await _is_linked(party_token):
            await sio.emit('host_linked_success', {}, to=sid)
            await _consume_linked(party_token)

    @sio.event
    async def close_host_session(sid, data):
        state.party_session_sid = None
        state.party_session_used_ids = set()
        print(" [Party] تم تصفير جلسة الحفلة عند الإغلاق")
        chat_id = host_chat_ids.get('admin')
        if chat_id:
            msg = "🛑 انتهت اللعبة! تم إغلاق الجلسة وإيقاف إرسال الإجابات."
            await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': msg})
            host_chat_ids.pop('admin', None)

    @sio.event
    async def change_host_session(sid, data):
        chat_id = host_chat_ids.get('admin') 
        if chat_id:
            msg = "🔄 تم تسليم الإدارة لشخص آخر! تم سحب صلاحياتك ولن تصلك الإجابات بعد الآن."
            await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': msg})
            host_chat_ids.pop('admin', None)