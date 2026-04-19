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

                    if text in ["/start", "بدء"]:
                        welcome_msg = "👋 أهلاً بك في مدير لعبة PlayRush!\n\n🔑 يرجى إرسال الرمز السري المكون من 4 أرقام الذي يظهر على الشاشة لربط جلستك."
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': welcome_msg})

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

async def send_secret_to_mobile(question, answer):
    CHAT_ID = host_chat_ids.get('admin')
    if not CHAT_ID: return
    msg = f"السؤال: {question}\n🎯 الإجابة: {answer}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        await asyncio.to_thread(requests.post, url, data={'chat_id': CHAT_ID, 'text': msg}, timeout=2)
    except Exception as e:
        print("لم يتم إرسال التليجرام:", e)

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