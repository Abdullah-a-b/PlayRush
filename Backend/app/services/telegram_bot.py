import os
import time
import asyncio
import requests
from app.sockets.state import active_codes, host_chat_ids
import app.sockets.state as state

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BOT_USERNAME = "@p_rushbot"

async def telegram_bot_listener(sio):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    
    while True:
        try:
            current_time = time.time()
            expired = [c for c, data in active_codes.items() if data['expires'] < current_time]
            for c in expired:
                del active_codes[c]

            response = await asyncio.to_thread(requests.get, f"{url}?offset={state.LAST_UPDATE_ID + 1}&timeout=1", timeout=2)
            
            if response.status_code == 200:
                data = response.json()
                for update in data.get("result", []):
                    state.LAST_UPDATE_ID = update["update_id"]
                    msg = update.get("message", {})
                    text = str(msg.get("text", "")).strip()
                    chat_id = msg.get("chat", {}).get("id")

                    # 🔑 هل هذا المُرسِل هو الأدمن (المطوّر)؟ — أوامر الدعم له فقط
                    admin_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
                    is_admin = admin_id and str(chat_id) == str(admin_id)

                    if text in ["/start", "بدء"]:
                        # رسالة عامة للاعبين (إدارة الجلسة) + أوامر الدعم تظهر للأدمن فقط
                        welcome_msg = "👋 أهلاً بك في مدير لعبة PlayRush!\n\n🔑 لربط جلسة لعبة: أرسل الرمز السري الذي يظهر على الشاشة."
                        if is_admin:
                            welcome_msg += "\n\n🎧 أوامر الدعم (للأدمن):\n/reply <رقم> <ردك>\n/close <رقم>"
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': welcome_msg})

                    elif text == "/myid":
                        # متاح للجميع — فقط يعرض chat_id الخاص بالمُرسِل (لا يكشف شيئاً حساساً)
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': f"🆔 chat_id الخاص بك:\n{chat_id}\n\n(للمطوّر) ضعه في .env:\nTELEGRAM_ADMIN_CHAT_ID={chat_id}"})

                    elif text.startswith("/reply "):
                        # 🔒 أوامر الدعم للأدمن فقط
                        if is_admin:
                            await _handle_reply_command(sio, text, chat_id)
                        else:
                            await _send_tg(chat_id, "🔒 هذا الأمر مخصّص لإدارة الدعم فقط.")

                    elif text.startswith("/close "):
                        if is_admin:
                            await _handle_close_command(sio, text, chat_id)
                        else:
                            await _send_tg(chat_id, "🔒 هذا الأمر مخصّص لإدارة الدعم فقط.")

                    elif text in active_codes:
                        sid = active_codes[text]['sid']
                        host_chat_ids['admin'] = chat_id 
                        del active_codes[text] 
                        
                        await sio.emit('host_linked_success', {}, to=sid)
                        
                        success_msg = "🎯 تم ربطك بنجاح كمدير للجلسة! الإجابات ستصلك هنا."
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': success_msg})
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
        from app.services.notifications import add_notification, find_online_sid
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

    from app.services.support import admin_reply_ticket
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

    from app.services.support import admin_close_ticket
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
    🔒 يُرسَل فقط لـ TELEGRAM_ADMIN_CHAT_ID الثابت — لا يُرسَل أبداً لجلسة لاعب مربوطة
    (لأن البوت علني ويستخدمه اللاعبون لإدارة الجلسات).
    """
    CHAT_ID = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not CHAT_ID or not TELEGRAM_TOKEN:
        print(f"⚠️ [support] تذكرة #{ticket_id} لم يُرسل إشعارها — اضبط TELEGRAM_ADMIN_CHAT_ID في .env")
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
        code = str(random.randint(1000, 9999))
        active_codes[code] = {"sid": sid, "expires": time.time() + 20}
        await sio.emit('receive_host_code', {"code": code, "bot": BOT_USERNAME}, to=sid)

    @sio.event
    async def close_host_session(sid, data):
        state.party_session_sid = None
        state.party_session_used_ids = set()
        print("🧹 [Party] تم تصفير جلسة الحفلة عند الإغلاق")
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