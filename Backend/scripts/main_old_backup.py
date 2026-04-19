from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from Backend.app.core.database import engine, Base
from Backend.scripts.auth import get_db, router as auth_router
import socketio
import Backend.scripts.game_manager as game_manager
import json
import string
import random
from dotenv import load_dotenv
import requests
import asyncio
from datetime import datetime, timedelta
import time
from Backend.app.core.database import engine, Base, SessionLocal, Question, User, GameStat
import os
import html # 👈 أضف هذا الاستيراد في الأعلى لحماية الدردشة
from jose import jwt, JWTError
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ما قبل الـ yield يعمل فور تشغيل السيرفر (Startup)
    cleanup_task = asyncio.create_task(cleanup_abandoned_accounts())
    
    yield # هنا السيرفر يعمل ويستقبل طلبات المستخدمين
    
    # ما بعد الـ yield يعمل عند إيقاف السيرفر (Shutdown)
    cleanup_task.cancel() # إيقاف المكنسة بأمان

# إنشاء الجداول بقاعدة البيانات
Base.metadata.create_all(bind=engine)

# 2. ربط الـ lifespan بتطبيق FastAPI الخاص بك
app = FastAPI(lifespan=lifespan)

# 2. أضف هذا الكود بعد إنشاء التطبيق (app = FastAPI()) مباشرة
# إنشاء مجلد الصور إذا لم يكن موجوداً
os.makedirs("uploads/avatars", exist_ok=True)

# ربط المجلد ليكون متاحاً عبر الرابط كملفات ثابتة (Static Files)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-123")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# 🛡️ دالة جديدة لفك تشفير التوكن والبحث عن المستخدم بالإيميل (وليس بالتوكن نفسه)
def get_user_from_token(db, token: str):
    if not token or token == "null" or token == "undefined":
        print("🚫 [نظام التوكن] لم يتم إرسال توكن من المتصفح أو التوكن فارغ.")
        return None
    try:
        clean_token = token.replace('"', '').replace("'", "").replace("Bearer ", "").strip()
        # محاولة فك التشفير
        payload = jwt.decode(clean_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email = payload.get("sub")
        
        if user_email:
            user = db.query(User).filter(User.email == user_email).first()
            if user:
                print(f"✅ [نظام التوكن] تم التعرف على اللاعب: {user.player_name} (الإيميل: {user.email})")
                return user
            else:
                print(f"⚠️ [نظام التوكن] التوكن سليم، لكن الإيميل ({user_email}) محذوف من الداتابيس.")
        else:
            print("⚠️ [نظام التوكن] التوكن لا يحتوي على إيميل داخله.")
            
    except JWTError as e:
        print(f"❌ [نظام التوكن] التوكن تالف أو قديم جداً (يجب تسجيل الخروج والدخول): {e}")
    except Exception as e:
        print(f"🔥 [نظام التوكن] خطأ برمجي غير متوقع: {e}")
        
    return None

# ==========================================
# 🛡️ دالة التحقق من التوكن واستخراج الهوية
# ==========================================
def verify_token(token: str):
    if not token: return None
    db = SessionLocal()
    try:
        user = get_user_from_token(db, token) # 👈 استخدام الدالة الجديدة
        if user:
            avatar_url = user.avatar if user.avatar else f"https://api.dicebear.com/7.x/bottts/svg?seed={user.player_name}"
            return {
                'username': user.player_name,
                'avatar': avatar_url
            }
        return None
    finally:
        db.close()

# 1. إعداد الـ CORS بشكل دقيق وواضح
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth")

# 2. إعداد السوكيت (بدون وضع CORS هنا لكي لا يتضارب مع FastAPI)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins=[]) # نتركها فارغة هنا
socket_app = socketio.ASGIApp(sio, socketio_path='socket.io')

# 3. دمج السوكيت مع التطبيق الرئيسي
app.mount('/socket.io', socket_app) # 👈 ربط المسار مباشرة

# ==========================================
# 📊 المتغيرات الشاملة للمتصلين والغرف
# ==========================================
connected_players = {}   
global_chat_history = [] 
game_lobby_players = {}  
game_chat_history = {}  

# ==========================================
# 🎉 تتبع أسئلة وضع الحفلة (Party Mode)
# مفتاح الـ session_id يربط كل المستخدمين في نفس الجلسة
# القيمة: set من IDs الأسئلة التي تم استخدامها
# ==========================================
party_session_used_ids: set = set()   # أسئلة مستخدمة في الجلسة الحالية
party_session_sid: str | None = None  # الـ sid للمضيف الحالي (لتحديد انتهاء الجلسة)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") # 🛡️ قراءة آمنة
BOT_USERNAME = "@p_rushbot" # غيره لاسم البوت حقك

# قواميس لتخزين البيانات المؤقتة
active_codes = {}  # لتخزين الرموز المؤقتة { "1234": {"sid": "...", "expires": 1623...} }
host_chat_ids = {} # لتخزين معرف المضيف لكل جلسة
LAST_UPDATE_ID = 0 # لتتبع الرسائل المقروءة في تليجرام

# توحيد الحروف المتشابهة للفلترة الصحيحة
NORMALIZE_LETTER = {
    'ا': 'أ', 'إ': 'أ', 'آ': 'أ',
    'ة': 'ه', 'ى': 'ي', 'ؤ': 'و',
}

TOPICS = ['إسلاميات وسيرة نبوية', 'ألغاز وفوازير ذكية', 'تاريخ', 'جغرافيا', 'علوم', 'ثقافة عامة', 'رياضة']

# ==========================================
# ⚡ نظام التخزين المؤقت (Cache) لتخفيف الضغط
# ==========================================
STATS_CACHE = {}
CACHE_TTL = 15  # الاحتفاظ بالبيانات لـ 15 ثانية فقط

disconnect_timers = {}  # لتخزين مؤقتات الانقطاع لكل غرفة {room_code: asyncio.Task}

async def handle_disconnection_timeout(room_code, old_sid):
    """دالة تعمل في الخلفية لانتظار عودة اللاعب، وتعلن انسحابه إذا لم يعد"""
    await asyncio.sleep(30) # ⏳ فترة السماح (30 ثانية)
    
    room = game_manager.get_room_state(room_code)
    if room and room.get('state') == 'playing':
        # التحقق هل اللاعب ما زال مفقوداً؟ (لم يتم تحديث sid الخاص به)
        missing_player = next((p for p in room['players'] if p.get('old_sid') == old_sid and p.get('sid') is None), None)
        
        if missing_player:
            print(f"⏰ [Timeout] انتهت مهلة عودة اللاعب في الغرفة {room_code}. إعلان فوز الخصم.")
            
            # 1. تحديد الفائز المتبقي
            winner_player = next((p for p in room['players'] if p.get('old_sid') != old_sid), None)
            winner_color = winner_player['color'] if winner_player else 'green'
            
            # 2. تسجيل النتيجة رسمياً (انسحاب/تخطي المهلة)
            record_match_result(winner_player, missing_player, room.get('game_mode', 'huroof'), extra={'reason': 'surrender'})
            
            # 3. إعلان الفوز للطرف المتبقي
            await sio.emit('show_winner', {'color': winner_color, 'reason': 'surrender'}, room=room_code)
            
            # 4. تنظيف الغرفة وإنهائها
            room['state'] = 'finished'
            if room.get('game_state'):
                room['game_state'].state_version += 9999 # إفساد أي مؤقت سؤال يعمل حالياً
            
            await return_players_to_lobby(room)
            
            if room_code in game_manager.rooms:
                del game_manager.rooms[room_code]

def normalize_letter(ch):
    return NORMALIZE_LETTER.get(ch, ch)

def get_answer_letter(answer):
    """استخراج الحرف الأول من الإجابة مع تجاهل ال التعريف"""
    answer = answer.strip()
    if answer.startswith('ال') and len(answer) > 2:
        answer = answer[2:]
    return normalize_letter(answer[0]) if answer else None

# ==========================================
# 🔄 أحداث الدخول والخروج من السيرفر
# ==========================================
@sio.event
async def connect(sid, environ):
    print(f"[+] اتصال جديد بالسيرفر: {sid}")

@sio.event
async def disconnect(sid):
    if sid in connected_players:
        player_name = connected_players[sid]['name']
        del connected_players[sid]
        print(f"[-] غادر {player_name} النظام")
        await sio.emit('update_online_players', list(connected_players.values()))
    
    for game_mode, players in game_lobby_players.items():
        if sid in players:
            player_name = players[sid]['name']
            del players[sid]
            print(f"[-] غادر {player_name} لوبي: {game_mode}")
            
            players_list = list(players.values())
            for p_sid in list(players.keys()):
                await sio.emit('update_game_lobby_players', players_list, to=p_sid)
                
    # خروج اللاعب من الغرفة وإبلاغ الخصم بانسحابه
    room_code, room = game_manager.leave_room(sid)
    if room_code:
        print(f"[-] اللاعب غادر غرفة {room_code}")
        if room and room.get('state') == 'playing':
            print(f"⚠️ [انقطاع] انقطع اتصال لاعب في غرفة {room_code}، تبدأ مهلة 30 ثانية...")
            
            # 1. إبلاغ الخصم ببدء مؤقت الانتظار
            await sio.emit('opponent_disconnected', {'msg': 'انقطع اتصال الخصم، ننتظر عودته...'}, room=room_code)
            
            # 2. إيقاف مؤقتات اللعبة الحالية (تجميد اللعبة)
            if room.get('game_state'):
                room['game_state'].state_version += 1 
            
            # 3. تشغيل مؤقت الـ 30 ثانية في الخلفية
            task = asyncio.create_task(handle_disconnection_timeout(room_code, sid))
            disconnect_timers[room_code] = task

# ==========================================
# 🌍 اللوبي العام (Categories) والدردشة
# ==========================================
@sio.event
async def join_global_lobby(sid, data):
    player_name = data.get('name', 'لاعب')
    avatar = data.get('avatar', '')
    
    connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': 'global'}
    print(f"[+] انضم {player_name} إلى الساحة العامة")
    
    await sio.emit('chat_history', global_chat_history, to=sid)
    await sio.emit('update_online_players', list(connected_players.values()))

@sio.event
async def send_chat_message(sid, data):
    raw_text = str(data.get('text', ''))
    clean_text = html.escape(raw_text) # 🛡️ الجدار الناري: تنظيف النص من أي كود خبيث
    
    msg = {'sender': data.get('sender'), 'text': clean_text, 'isSystem': False}
    global_chat_history.append(msg)
    if len(global_chat_history) > 50: global_chat_history.pop(0)
    await sio.emit('new_chat_message', msg)

# ==========================================
# 🎮 اللوبي المخصص للألعاب (مثل لوبي حروف)
# ==========================================
@sio.event
async def join_game_lobby(sid, data):
    game_mode = data.get('gameMode')
    player_name = data.get('name', 'لاعب')
    avatar = data.get('avatar', '')
    token = data.get('token', None)

    if game_mode not in game_lobby_players:
        game_lobby_players[game_mode] = {}
    if game_mode not in game_chat_history:
        game_chat_history[game_mode] = []
        
    game_lobby_players[game_mode][sid] = {'name': player_name, 'avatar': avatar}
    connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': game_mode, 'token': token}
    print(f"[+] انضم {player_name} إلى لوبي: {game_mode}")
    
    await sio.emit('update_online_players', list(connected_players.values()))
    await sio.emit('game_chat_history', game_chat_history[game_mode], to=sid)
    
    players_list = list(game_lobby_players[game_mode].values())
    for p_sid in list(game_lobby_players[game_mode].keys()):
        await sio.emit('update_game_lobby_players', players_list, to=p_sid)

@sio.event
async def send_game_chat_message(sid, data):
    game_mode = data.get('gameMode')
    raw_text = str(data.get('text', ''))
    clean_text = html.escape(raw_text) # 🛡️ الجدار الناري: تنظيف النص هنا أيضاً
    
    msg = {'sender': data.get('sender'), 'text': clean_text, 'isSystem': False}
    
    if game_mode not in game_chat_history:
        game_chat_history[game_mode] = []
        
    game_chat_history[game_mode].append(msg)
    if len(game_chat_history[game_mode]) > 50: 
        game_chat_history[game_mode].pop(0)
        
    if game_mode in game_lobby_players:
        for p_sid in list(game_lobby_players[game_mode].keys()):
            await sio.emit('new_game_chat_message', msg, to=p_sid)

# ==========================================
# ⚡ اللعب السريع (Matchmaking)
# ==========================================
@sio.event
async def quick_play_search(sid, data):
    game_mode = data.get('game_mode')
    player_name = data.get('player_name')
    avatar = data.get('avatar')
    
    success, msg = game_manager.add_to_queue(sid, player_name, avatar, game_mode)
    
    match_found, room_code, matched_players, rp_data = game_manager.check_queue_for_match(game_mode)
    
    if match_found:
        # 🛡️ تحويل بيانات اللاعبين إلى مصفوفة نظيفة لكي يفهمها الفرونت إند
        players_list = list(rp_data.values())
        
        for p in matched_players:
            # اللاعب الأول هو المضيف، والثاني ضيف
            role = 'host' if p['sid'] == matched_players[0]['sid'] else 'guest'
            
            await sio.emit('match_found', {
                'room_code': room_code,
                'role': role,
                'players': players_list
            }, to=p['sid'])

@sio.event
async def cancel_quick_play(sid):
    if game_manager.remove_from_queue(sid):
        print(f"[Matchmaking] تم إزالة {sid} من طابور البحث")
        await sio.emit('quick_play_cancelled', {}, to=sid)

# ==========================================
# 🚪 الغرف الخاصة (Private Rooms)
# ==========================================
@sio.event
async def create_room(sid, data):
    host_name = data.get('host_name')
    game_mode = data.get('game_mode')
    avatar = data.get('avatar', '')
    
    room_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    room = game_manager.create_room(room_code, sid, host_name, 2, game_mode, "0.0.0.0", avatar, "private")
    
    await sio.emit('room_created', {'room_code': room_code, 'players': room['players']}, to=sid)

@sio.event
async def join_room(sid, data):
    room_code = data.get('room_code')
    token = data.get('token')
    
    user_data = verify_token(token) if token else None
    
    if user_data:
        # 🛡️ إعطاء الأولوية المطلقة لقاعدة البيانات الجديدة وتجاهل ذاكرة المتصفح القديمة
        player_name = user_data.get('username')
        avatar = user_data.get('avatar')
    else:
        player_name = data.get('player_name', 'مجهول')
        avatar = data.get('avatar', '')
        
    print(f"[*] محاولة انضمام {player_name} للغرفة {room_code}...")
    
    success, msg = game_manager.join_room(room_code, sid, player_name, avatar)
    if success:
        # 🛠️ الإصلاح الأول: إضافة await الناقصة
        await sio.enter_room(sid, room_code)
        
        room = game_manager.get_room_state(room_code)
        
        # تحديث حالة اللاعب في اللوبي
        game_mode = room.get('game_mode', 'huroof')
        connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': f'playing_{game_mode}', 'token': token}

        # 🛠️ الإصلاح الثاني والأهم: تنظيف الغرفة من كائن البايثون قبل إرسالها للفرونت إند!
        # 🛠️ تنظيف الغرفة وجلب الإحصائيات من الداتابيس لكل لاعب
        safe_room = {k: v for k, v in room.items() if k != 'game_state'}
        
        fetch_tasks = []
        for p in safe_room['players']:
            if p.get('sid') == sid and token:
                p['token'] = token
            p_token = p.get('token') or (connected_players.get(p['sid'], {}).get('token') if p.get('sid') else None)
            
            # تجهيز مهام البحث للعمل معاً
            fetch_tasks.append(get_player_full_stats(p_token, p['name'], p.get('avatar', '')))

        # 🚀 تنفيذ كل عمليات الداتابيس للاعبين في نفس اللحظة (Parallel) بدون تعليق
        stats_results = await asyncio.gather(*fetch_tasks)
        
        # ربط النتائج بكائنات اللاعبين
        for i, p in enumerate(safe_room['players']):
            p['stats'] = stats_results[i]
            if p['stats']:
                p['avatar'] = p['stats']['avatar']

        # 1. إرسال الغرفة للاعب المنضم للتو
        await sio.emit('room_joined', safe_room, to=sid)
        
        # 🚀 2. [الحل النهائي] إجبار جميع مَن في الغرفة (بما فيهم أنت المنتظر) على استقبال وتحديث بيانات الخصم!
        await sio.emit('update_players_stats', safe_room['players'], room=room_code)
        
        await sio.emit('player_joined', {'player': player_name}, room=room_code)
        
        # 🚀 إرسال اللوحة
        # 🚀 الإرسال المباشر للوحة ومزامنة الشاشة بعد التحديث
        # 🚀 الإرسال المباشر للوحة ومزامنة الشاشة بعد التحديث
        if msg in ["reconnected", "reconnected_ready"]:
            if room_code in disconnect_timers:
                disconnect_timers[room_code].cancel()
                del disconnect_timers[room_code]
                print(f"✅ تم إلغاء مؤقت الانسحاب، عاد اللاعب للغرفة {room_code}")
                # إبلاغ الخصم لاستئناف اللعب
                await sio.emit('opponent_reconnected', {'msg': 'عاد الخصم للعب!'}, room=room_code)

            gs = room.get('game_state')
            if gs and hasattr(gs, 'board'):
                print(f"[+] إرسال اللوحة ومزامنة اللعبة للاعب {player_name}")
                await sio.emit('huroof_board_init', {'board': gs.board}, to=sid)
                
                if room['state'] == 'playing':
                    # 🚀 إرسال الدور الحالي للجميع لكي يبدأ اللعب إذا اكتمل العدد!
                    await sio.emit('huroof_turn_changed', {'turn_sid': gs.turn}, room=room_code)
                    
                    # 🚀 إذا تم تحديث الصفحة أثناء وجود سؤال، نعيد إرساله لك فوراً!
                    if gs.stage != 'selecting' and gs.current_question and gs.active_hex:
                        await sio.emit('huroof_hex_locked', {'hexIndex': gs.active_hex['index'], 'letter': gs.active_hex['letter']}, to=sid)
                        await sio.emit('huroof_new_question', {
                            'questionData': gs.current_question,
                            'round': 'r1',
                            'timer': 40
                        }, to=sid)
    else:
        print(f"[-] رفض انضمام {player_name}: {msg}")
        await sio.emit('error_message', msg, to=sid)

@sio.event
async def start_game(sid, data):
    """حدث بدء اللعبة للغرف الخاصة"""
    room_code = data.get('room_code')
    room = game_manager.get_room_state(room_code)
    if room and room.get('host') == sid:
        room['state'] = 'starting' # نضعها في حالة الانتقال
        print(f"🚀 بدء اللعبة في الغرفة الخاصة: {room_code}")
        await sio.emit('game_started', {'roomCode': room_code}, room=room_code)

@sio.event
async def join_party_mode(sid, data):
    global party_session_sid, party_session_used_ids
    game_mode = data.get('gameMode', 'huroof')
    player_name = data.get('name', 'لاعب')
    avatar = data.get('avatar', 'https://api.dicebear.com/7.x/bottts/svg?seed=Hero')
    
    connected_players[sid] = {'name': player_name, 'avatar': avatar, 'location': f"party_{game_mode}"}
    print(f"[*] {player_name} دخل وضع الجمعات في: {game_mode}")

    if party_session_sid is None:
        party_session_sid = sid
        party_session_used_ids = set()
        print(f"🎉 [Party] جلسة جديدة بدأت - المضيف: {player_name} ({sid})")
    
    await sio.emit('update_online_players', list(connected_players.values()))

# ⚔️ أحداث اللعب الفعلية للأونلاين (المحرك الرئيسي)
# ==========================================

def advance_state(game_state, new_stage):
    """تحديث حالة اللعبة وزيادة رقم النسخة لمنع تداخل المؤقتات"""
    game_state.stage = new_stage
    game_state.state_version += 1
    return game_state.state_version

def clean_text_for_match(t):
    """فلتر تنظيف النصوص للتحكيم اللحظي"""
    t = str(t).strip()
    t = t.replace("ال", "", 1) if t.startswith("ال") else t
    return t.replace(" ", "").replace("ة", "ه").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")

def check_answer_fast_track(player_ans, correct_ans, accepted_list, required_letter):
    """التحكيم اللحظي (0 ملي ثانية) - 3 فلاتر"""
    p_clean = clean_text_for_match(player_ans)
    req_clean = clean_text_for_match(required_letter)
    
    # 1. فلتر الإعدام الفوري (الكلمة لا تبدأ بالحرف المطلوب)
    if not p_clean.startswith(req_clean):
        return False, "wrong_letter"
        
    # 2. فلتر الفوز الفوري (تطابق مع الإجابة الرسمية)
    c_clean = clean_text_for_match(correct_ans)
    if p_clean == c_clean:
        return True, "exact_match"
        
    # 3. فلتر الفوز الفوري (تطابق مع قائمة المرادفات المسموحة)
    for acc in accepted_list:
        if p_clean == clean_text_for_match(acc):
            return True, "accepted_match"
            
    # 4. إذا مرت من كل هذا، نحيلها للمحكمة العليا (الذكاء الاصطناعي)
    return False, "إجابة خاطئة"

async def trigger_new_question(room_code):
    print(f"\n🔄 [السيرفر] طلب سؤال جديد للغرفة: {room_code}")
    room = game_manager.get_room_state(room_code)
    if not room or not room.get('game_state'): return
    gs = room['game_state']
    gs.attempts = 1

    norm_letter = normalize_letter(gs.active_hex['letter'])
    print(f"🎯 [السيرفر] تم الضغط على الحرف: {norm_letter}")

    # ==========================================
    # 📚 تحميل سجلات الأسئلة المشاهَدة لكلا اللاعبَين من قاعدة البيانات
    # ==========================================
    db = SessionLocal()
    combined_seen = set()  # اتحاد ما شاهده اللاعبان معاً
    player_db_ids = {}     # {sid: user_db_id} لتحديث السجل لاحقاً

    try:
        for player in room.get('players', []):
            p_sid = player.get('sid')
            if not p_sid:
                continue
            # نحاول نجيب المستخدم من الداتابيس عبر token الجلسة
            token = connected_players.get(p_sid, {}).get('token')
            user = None
            if token:
                user = db.query(User).filter(User.session_token == token).first()
            if user:
                try:
                    seen_ids = json.loads(user.seen_question_ids or "[]")
                    combined_seen.update(seen_ids)
                    player_db_ids[p_sid] = user.id
                    print(f"📖 [{player.get('name')}] سجله: {len(seen_ids)} سؤال مشاهَد")
                except Exception:
                    pass

        # ==========================================
        # 🔍 اختيار السؤال — استبعاد المشترك + استبعاد نفس المباراة
        # ==========================================
        valid_qs = []
        query = db.query(Question).filter(Question.game_mode == "huroof")
        for q in query.all():
            # استبعاد ما تم لعبه في هذه المباراة
            if hasattr(gs, 'used_questions') and q.id in gs.used_questions:
                continue
            # استبعاد ما شاهده أي من اللاعبَين سابقاً
            if q.id in combined_seen:
                continue
            try:
                ans = q.correct_answer.strip()
                if ans.startswith("ال"):
                    ans = ans[2:]
                extra = json.loads(q.extra_data) if q.extra_data else {}
                letter_from_extra = normalize_letter(extra.get("letter", ""))
                letter_from_ans = normalize_letter(ans[0]) if ans else ""
                if letter_from_extra == norm_letter or letter_from_ans == norm_letter:
                    valid_qs.append(q)
            except:
                pass

        print(f"📊 [السيرفر] أسئلة جديدة لكليهما لهذا الحرف: {len(valid_qs)}")

        if not valid_qs:
            # ❌ لا يوجد سؤال جديد لأي من اللاعبَين — أبلغهما مباشرة
            print(f"⚠️ نفدت الأسئلة الجديدة لحرف '{norm_letter}' بالنسبة لهذين اللاعبَين.")
            fallback = {
                "question": f"نفدت الأسئلة الجديدة لحرف ({norm_letter}) لكلاكما. اختاروا حرفاً آخر.",
                "answer": "لا يوجد",
                "category": "نفدت الأسئلة",
                "letter": norm_letter,
                "accepted_answers": []
            }
            await sio.emit('receive_ai_question', fallback, room=room_code)
            return

        # ==========================================
        # ✅ تم اختيار السؤال — نحفظه ونرسله
        # ==========================================
        chosen = random.choice(valid_qs)

        # حفظ في سجل المباراة الحالية
        if hasattr(gs, 'used_questions'):
            gs.used_questions.append(chosen.id)
            gs.used_answers.append(chosen.correct_answer)

        # ✏️ تحديث سجل كلا اللاعبَين في قاعدة البيانات فوراً
        for p_sid, user_id in player_db_ids.items():
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                try:
                    seen_ids = json.loads(user.seen_question_ids or "[]")
                    if chosen.id not in seen_ids:
                        seen_ids.append(chosen.id)
                        user.seen_question_ids = json.dumps(seen_ids)
                except Exception:
                    user.seen_question_ids = json.dumps([chosen.id])
        db.commit()
        print(f"💾 [سجل] تم حفظ ID={chosen.id} في سجل اللاعبَين")

        extra = json.loads(chosen.extra_data) if chosen.extra_data else {}
        gs.current_question = {
            "question": chosen.question_text,
            "answer": chosen.correct_answer,
            "accepted_answers": extra.get("accepted_answers", []),
            "category": chosen.category,
            "letter": norm_letter
        }

        version = advance_state(gs, 'buzz_r1')
        gs.buzzed_player = None
        gs.skip_votes.clear()

        asyncio.create_task(send_secret_to_mobile(gs.current_question['question'], gs.current_question['answer']))

        print(f"✅ [السيرفر] إرسال السؤال للمتصفح: {gs.current_question['question']}")
        await sio.emit('huroof_new_question', {
            'questionData': gs.current_question,
            'round': 'r1',
            'timer': 40
        }, room=room_code)

        sio.start_background_task(huroof_timer_task, room_code, version, 40, 'timeout_buzz_r1')

    finally:
        db.close()

async def huroof_timer_task(room_code, version, seconds, timeout_type):
    await asyncio.sleep(seconds)
    # 🕵️ رادار: هل الغرفة لا تزال موجودة وبحالة لعب؟
    room = game_manager.get_room_state(room_code)
    if not room or room.get('state') != 'playing' or not room.get('game_state'):
        return 
        
    gs = room['game_state']
    if gs.state_version != version: return
    
    # التحقق أن الحالة لم تتغير
    if gs.state_version == version:
        print(f"⏰ [Timeout] الغرفة {room_code} | النوع: {timeout_type}")
        
        if timeout_type == 'timeout_buzz_r1':
            # 0️⃣ لم يضغط أحد الجرس في الـ 40 ثانية -> فرصة أخيرة مباشرة
            gs.attempts = 2
            version = advance_state(gs, 'question')
            gs.buzzed_player = None
            await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')

        elif timeout_type == 'timeout_answer_r1':
            # 1️⃣ اللاعب الأول أضاع الـ 15 ثانية -> ينتقل للخصم بـ 20 ثانية (المحاولة الأولى)
            version = advance_state(gs, 'answer_r2')
            gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
            await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 20, 'round': 'r2'}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
            
        elif timeout_type == 'timeout_answer_r2':
            # 2️⃣ الخصم أضاع الـ 20 ثانية -> فشل الكل في الأولى، نفتح المحاولة الثانية
            # نضبط attempts لكي يعرف حدث huroof_buzz أن القادم هو 12 ثانية
            gs.attempts = 2 
            version = advance_state(gs, 'question') # نعيدها لحالة السؤال ليضغطوا مجدداً
            gs.buzzed_player = None
            # نرسل إشعار "فرصة ثانية" (يمكنك وضع تايمر 15 ثانية للضغط)
            await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, version, 30, 'timeout_buzz_r3')
            
        elif timeout_type == 'timeout_answer_r3':
            # 3️⃣ اللاعب أضاع الـ 12 ثانية (في المحاولة الثانية) -> ينتقل للخصم بـ 12 ثانية
            version = advance_state(gs, 'answer_r4')
            gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
            await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 12, 'round': 'r4'}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')

        elif timeout_type == 'timeout_answer_r4' or timeout_type == 'timeout_buzz_r3':
            # 4️⃣ انتهت كل الفرص أو لم يضغط أحد في الفرصة الثانية -> تغيير السؤال
            advance_state(gs, 'selecting')
            gs.attempts = 1 # تصفير للسؤال القادم
            gs.turn = gs.p2 if gs.turn == gs.p1 else gs.p1
            await sio.emit('huroof_timeout_info', {'msg': 'انتهى الوقت! نعود لاختيار الحروف.'}, room=room_code)
            await asyncio.sleep(2)
            await sio.emit('huroof_turn_changed', {'turn_sid': gs.turn}, room=room_code)

@sio.event
async def huroof_select_hex(sid, data):
    """حدث اختيار حرف من اللوحة"""
    room_code = data.get('roomCode')
    hex_index = data.get('hexIndex')
    
    room = game_manager.get_room_state(room_code)
    if not room: return
    gs = room['game_state']
    
    if gs.stage != 'selecting' or gs.turn != sid:
        return # ليس دوره أو اللوحة مقفلة
        
    gs.active_hex = gs.board[hex_index]
    await sio.emit('huroof_hex_locked', {'hexIndex': hex_index, 'letter': gs.active_hex['letter']}, room=room_code)
    
    # جلب السؤال الأول لهذا الحرف
    await trigger_new_question(room_code)

@sio.event
async def huroof_buzz(sid, data):
    room_code = data.get('roomCode')
    room = game_manager.get_room_state(room_code)
    
    # 🕵️ الفحص الذهبي: التأكد من أن الغرفة موجودة وأننا في مرحلة تسمح بالضغط
    if not room or not room.get('game_state'): return
    gs = room['game_state']
    
    # السماح بالضغط إذا كانت المرحلة 'question' (للمرة الأولى) 
    # أو إذا كانت المرحلة مهيأة للمحاولة الثانية
    # واستبدله بهذا (أضفنا buzz_r1):
    allowed_stages = ['question', 'buzz_r1', 'buzz_r3']
    if gs.stage not in allowed_stages:
        print(f"⚠️ تجاهل الضغطة: المرحلة الحالية هي {gs.stage}")
        return
    
    gs.buzzed_player = sid
    if not hasattr(gs, 'attempts'): gs.attempts = 1

    # ضبط الوقت والمرحلة بناءً على رقم المحاولة
    if gs.attempts == 1:
        current_time = 15
        version = advance_state(gs, 'answer_r1')
        timeout_type = 'timeout_answer_r1'
    else:
        current_time = 12
        version = advance_state(gs, 'answer_r3')
        timeout_type = 'timeout_answer_r3'
    
    print(f"🔔 {sid} ضغط الجرس - محاولة رقم: {gs.attempts} - وقت: {current_time}ث")
    
    await sio.emit('huroof_buzzed', {'sid': sid, 'time': current_time}, room=room_code)
    sio.start_background_task(huroof_timer_task, room_code, version, current_time, timeout_type)

@sio.event
async def huroof_submit_answer(sid, data):
    """حدث تسليم الإجابة والتحكيم (محلي فقط)"""
    room_code = data.get('roomCode')
    player_ans = html.escape(str(data.get('answer', '')).strip())
    
    room = game_manager.get_room_state(room_code)
    if not room: return
    gs = room['game_state']
    
    # منع تسليم الإجابة إذا لم نكن في إحدى مراحل الإجابة الأربعة
    if gs.stage not in ['answer_r1', 'answer_r2', 'answer_r3', 'answer_r4']: return
    if sid != gs.buzzed_player: return 
    
    correct_ans = gs.current_question['answer']
    accepted_list = gs.current_question['accepted_answers']
    req_letter = gs.current_question['letter']
    
    # 1. التحكيم اللحظي المحلي المباشر
    is_correct, reason = check_answer_fast_track(player_ans, correct_ans, accepted_list, req_letter)
    
    # 2. تنفيذ النتيجة فوراً (لا يوجد ذكاء اصطناعي للانتظار)
    await process_answer_result(room_code, is_correct, player_ans)

async def process_answer_result(room_code, is_correct, player_ans):
    room = game_manager.get_room_state(room_code)
    if not room or not room.get('game_state'): return
    gs = room['game_state']
    sid = gs.buzzed_player
    player_color = 'green' if sid == gs.p1 else 'orange'
    
    if is_correct:
        # ✅ إجابة صحيحة
        gs.active_hex['color'] = player_color
        await sio.emit('huroof_answer_result', {'correct': True, 'answer': player_ans, 'hexIndex': gs.active_hex['index'], 'color': player_color}, room=room_code)
        
        if gs.check_win(player_color):
            await asyncio.sleep(1.5) # مهلة للاحتفال بالخلية قبل إعلان الفوز
            room = game_manager.get_room_state(room_code)
            
            if room:
                # 1. تسجيل نقطة الجولة للاعب
                gs.points[player_color] += 1
                
                # 2. التحقق مما إذا كان قد فاز بنقطتين (انتهت المباراة)
                if gs.points[player_color] >= gs.points_to_win_match:
                    winner_player = next((p for p in room['players'] if p['color'] == player_color), None)
                    loser_player = next((p for p in room['players'] if p['color'] != player_color), None)
                    loser_color = 'orange' if player_color == 'green' else 'green'
                    # حفظ النتيجة في الداتابيس مع بيانات الجولات
                    record_match_result(winner_player, loser_player, room.get('game_mode', 'huroof'), extra={
                        'winner_rounds': gs.points[player_color],
                        'loser_rounds':  gs.points[loser_color]
                    })

                    # إعلان الفوز النهائي
                    await sio.emit('huroof_match_over', {
                        'winner': player_color,
                        'points': gs.points,
                        'reason': 'normal'
                    }, room=room_code)

                    # 🧹 تنظيف الغرفة بعد انتهاء المباراة
                    await asyncio.sleep(2)  # مهلة قصيرة لكي تصل الرسالة للعميل
                    room['state'] = 'finished'
                    if room.get('game_state'):
                        room['game_state'].state_version += 9999  # إيقاف جميع المؤقتات
                    await return_players_to_lobby(room)
                    if room_code in game_manager.rooms:
                        del game_manager.rooms[room_code]
                        print(f"🗑️ تم حذف الغرفة {room_code} بعد انتهاء المباراة.")
                
                else:
                    # 3. فاز بجولة واحدة فقط (ننتقل للجولة التالية)
                    gs.round_number += 1
                    
                    # إشعار اللاعبين بانتهاء الجولة وتحديث النقاط
                    await sio.emit('huroof_round_over', {
                        'winner': player_color,
                        'points': gs.points,
                        'next_round': gs.round_number
                    }, room=room_code)
                    
                    # إعطاء اللاعبين فرصة 3 ثواني لرؤية شاشة الفوز المؤقتة
                    await asyncio.sleep(3)
                    
                    # إعادة تهيئة اللوحة (الخاسر يبدأ الجولة الجديدة)
                    gs.reset_round_state(starting_turn=player_color)  # الفائز يبدأ الجولة التالية
                    
                    # إرسال اللوحة الجديدة وبدء الجولة
                    await sio.emit('huroof_board_init', {'board': gs.board}, room=room_code)
                    await sio.emit('huroof_new_round_started', {
                        'turn': gs.turn
                    }, room=room_code)
        else:
            advance_state(gs, 'selecting')
            gs.turn = sid
            await asyncio.sleep(2) # 🚀 مهلة لكي يقرأ اللاعبون "إجابة صحيحة"
            await sio.emit('huroof_turn_changed', {'turn_sid': sid}, room=room_code)
            
    else:
        # ❌ إجابة خاطئة
        await sio.emit('huroof_answer_result', {'correct': False, 'answer': player_ans, 'hexIndex': gs.active_hex['index']}, room=room_code)
        await asyncio.sleep(1.5)
        
        if gs.stage == 'answer_r1':
            # المحاولة 1، اللاعب 1 أخطأ -> ينتقل للخصم بـ 20 ثانية
            version = advance_state(gs, 'answer_r2')
            gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
            await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 20, 'round': 'r2'}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, version, 20, 'timeout_answer_r2')
            
        elif gs.stage == 'answer_r2':
            # المحاولة 1، الخصم أيضاً أخطأ -> نفتح المحاولة الثانية (الفرصة الأخيرة)
            gs.attempts = 2
            version = advance_state(gs, 'question') # نعود لحالة السؤال للسماح بالضغط
            gs.buzzed_player = None
            await sio.emit('huroof_last_chance', {'timer': 30}, room=room_code) # مهلة للضغط
            
        elif gs.stage == 'answer_r3':
            # المحاولة 2، اللاعب 1 أخطأ -> ينتقل للخصم بـ 12 ثانية
            version = advance_state(gs, 'answer_r4')
            gs.buzzed_player = gs.p2 if gs.buzzed_player == gs.p1 else gs.p1
            await sio.emit('huroof_chance_transfer', {'to_sid': gs.buzzed_player, 'timer': 12, 'round': 'r4'}, room=room_code)
            sio.start_background_task(huroof_timer_task, room_code, version, 12, 'timeout_answer_r4')
            
        elif gs.stage == 'answer_r4':
            # الجميع أخطأ في كل الفرص -> إنهاء السؤال
            advance_state(gs, 'selecting')
            gs.attempts = 1
            gs.turn = gs.p2 if gs.turn == gs.p1 else gs.p1
            await sio.emit('huroof_timeout_info', {'msg': 'كلاكما أخطأ! نعود للاختيار.'}, room=room_code)
            await asyncio.sleep(2)
            await sio.emit('huroof_turn_changed', {'turn_sid': gs.turn}, room=room_code)

@sio.event
async def huroof_vote_skip(sid, data):
    room_code = data.get('roomCode')
    room = game_manager.get_room_state(room_code)
    if not room or room.get('state') != 'playing': return
    gs = room['game_state']
    
    # يسمح بالتصويت فقط في مرحلة انتظار الجرس (buzz_r1 أو buzz_r3)
    if gs.stage in ['buzz_r1', 'buzz_r3', 'question']:
        gs.skip_votes.add(sid)
        await sio.emit('huroof_skip_voted', {'sid': sid}, room=room_code)
        
        # إذا وافق اللاعبان (2)
        if len(gs.skip_votes) >= 2:
            print(f"🔄 [Skipping] اتفاق على تغيير السؤال في الغرفة {room_code}")
            await sio.emit('huroof_timeout_info', {'msg': 'تم الاتفاق! جاري جلب سؤال جديد...'}, room=room_code)
            gs.state_version += 1 # إيقاف المؤقت الحالي
            await trigger_new_question(room_code)

async def return_players_to_lobby(room):
    """إعادة بيانات اللاعبَين للوبي فوراً بعد انتهاء المباراة (فوز أو انسحاب)
    يحل مشكلة ظهور بيانات الخصم مجهولة حتى يرجع هو للوبي بنفسه"""
    game_mode = room.get('game_mode', 'huroof')
    
    if game_mode not in game_lobby_players:
        game_lobby_players[game_mode] = {}
    
    for player in room.get('players', []):
        p_sid = player.get('sid')
        p_name = player.get('name', 'لاعب')
        p_avatar = player.get('avatar', '')
        
        if not p_sid:
            continue
        
        # تحديث حالة اللاعب في القاموس العام كأنه عاد للوبي
        connected_players[p_sid] = {'name': p_name, 'avatar': p_avatar, 'location': game_mode}
        game_lobby_players[game_mode][p_sid] = {'name': p_name, 'avatar': p_avatar}
    
    # إرسال تحديث فوري لكل من في اللوبي
    players_list = list(game_lobby_players[game_mode].values())
    for p_sid in list(game_lobby_players[game_mode].keys()):
        await sio.emit('update_game_lobby_players', players_list, to=p_sid)
    
    await sio.emit('update_online_players', list(connected_players.values()))
    print(f"✅ [Lobby] تم إعادة لاعبي الغرفة للوبي {game_mode} مسبقاً.")

@sio.event
async def huroof_surrender(sid, data):
    room_code = data.get('roomCode')
    room = game_manager.get_room_state(room_code)
    
    if room:
        # 1. إعلان الفائز للطرفين قبل الحذف
        winner_color = 'orange' if room['players'][0]['sid'] == sid else 'green'
        
        # 🚀 تسجيل نتيجة الانسحاب (المنسحب خاسر، والآخر فائز)
        loser_player = next((p for p in room['players'] if p['sid'] == sid), None)
        winner_player = next((p for p in room['players'] if p['sid'] != sid), None)
        record_match_result(winner_player, loser_player, room.get('game_mode', 'huroof'), extra={'reason': 'surrender'})

        await sio.emit('show_winner', {'color': winner_color, 'reason': 'surrender'}, room=room_code)
        
        # 2. تغيير الحالة فوراً لإيقاف المؤقتات
        room['state'] = 'finished'
        if room.get('game_state'):
            room['game_state'].state_version += 9999 # إفساد أي نسخة مؤقت تعمل حالياً
        
        # 3. 🛠️ إعادة كلا اللاعبَين للوبي فوراً قبل حذف الغرفة
        await return_players_to_lobby(room)
        
        # 4. حذف الغرفة من القائمة العالمية (مهم جداً)
        if room_code in game_manager.rooms:
            del game_manager.rooms[room_code]
            print(f"🗑️ تم حذف الغرفة {room_code} نهائياً من الذاكرة.")

# ==========================================
# 🤖 أحداث الذكاء الاصطناعي (توليد أسئلة وتحقق)
# ==========================================

@sio.event
async def request_ai_question(sid, data):
    global party_session_used_ids
    letter = data.get('letter', 'أ').strip()
    requested_category = data.get('category', 'عام')
    norm_letter = normalize_letter(letter)

    db = SessionLocal()
    try:
        query = db.query(Question).filter(Question.game_mode == "huroof")
        if requested_category != 'عام':
            query = query.filter(Question.category == requested_category)

        all_qs = query.all()

        # ✅ نبني قائمة الأسئلة المتاحة بعد استبعاد المستخدمة في هذه الجلسة
        valid = []
        for q in all_qs:
            if q.id in party_session_used_ids:
                continue
            try:
                ans = q.correct_answer.strip()
                if ans.startswith("ال"):
                    ans = ans[2:]
                extra = json.loads(q.extra_data) if q.extra_data else {}
                letter_from_extra = normalize_letter(extra.get("letter", ""))
                letter_from_ans = normalize_letter(ans[0]) if ans else ""
                if letter_from_extra == norm_letter or letter_from_ans == norm_letter:
                    valid.append(q)
            except:
                pass

        if valid:
            chosen = random.choice(valid)
            # ✅ نحجز السؤال فوراً في سجل الجلسة قبل الإرسال
            party_session_used_ids.add(chosen.id)
            print(f"⚡ [Party] سؤال جديد ID={chosen.id} | إجمالي المستخدمة: {len(party_session_used_ids)}")
            qa_data = {
                "question": chosen.question_text,
                "answer": chosen.correct_answer,
                "category": chosen.category,
                "letter": norm_letter
            }
            asyncio.create_task(send_secret_to_mobile(qa_data['question'], qa_data['answer']))
            await sio.emit('receive_ai_question', qa_data, to=sid)
        else:
            # ♻️ نفدت كل أسئلة هذا الحرف في هذا التصنيف — نرسل رسالة للمستخدم
            print(f"⚠️ [Party] نفدت أسئلة حرف '{norm_letter}' بتصنيف '{requested_category}'.")
            fallback = {
                "question": f"عذراً، نفدت أسئلة حرف ({norm_letter}) في هذا التصنيف. جرب تصنيفاً آخر.",
                "answer": "لا يوجد",
                "category": "نفدت الأسئلة",
                "letter": norm_letter,
                "accepted_answers": []
            }
            await sio.emit('receive_ai_question', fallback, to=sid)

    finally:
        db.close()

async def telegram_bot_listener():
    global LAST_UPDATE_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    
    while True:
        try:
            current_time = time.time()
            expired = [c for c, data in active_codes.items() if data['expires'] < current_time]
            for c in expired:
                del active_codes[c]

            # جلب الرسائل "في الخلفية" لكي لا يعلق سيرفر اللعبة
            response = await asyncio.to_thread(requests.get, f"{url}?offset={LAST_UPDATE_ID + 1}&timeout=1", timeout=2)
            
            if response.status_code == 200:
                data = response.json()
                for update in data.get("result", []):
                    LAST_UPDATE_ID = update["update_id"]
                    msg = update.get("message", {})
                    text = str(msg.get("text", "")).strip()
                    chat_id = msg.get("chat", {}).get("id")

                    # الرد الفوري على كلمة بدء أو /start
                    if text in ["/start", "بدء"]:
                        welcome_msg = "👋 أهلاً بك في مدير لعبة PlayRush!\n\n🔑 يرجى إرسال الرمز السري المكون من 4 أرقام الذي يظهر على الشاشة لربط جلستك."
                        # إرسال الرسالة في الخلفية ليظل السيرفر سريعاً
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': welcome_msg})

                    # ربط الجلسة بالمدير
                    elif text in active_codes:
                        sid = active_codes[text]['sid']
                        
                        # السر هنا: حفظ الجلسة باسم ثابت 'admin' لكي لا تضيع عند الرجوع للوبي
                        host_chat_ids['admin'] = chat_id 
                        del active_codes[text] 
                        
                        await sio.emit('host_linked_success', {}, to=sid)
                        
                        success_msg = "🎯 تم ربطك بنجاح كمدير للجلسة! الإجابات ستصلك هنا."
                        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': success_msg})
        except Exception:
            pass 
        
        # استجابة سريعة جداً كل ثانية
        await asyncio.sleep(1)

# تشغيل المراقب بمجرد فتح السيرفر
sio.start_background_task(telegram_bot_listener)

# 2. أمر إنشاء الرمز من الشاشة
@sio.event
async def generate_host_code(sid, data):
    code = str(random.randint(1000, 9999))
    active_codes[code] = {"sid": sid, "expires": time.time() + 20}
    await sio.emit('receive_host_code', {"code": code, "bot": BOT_USERNAME}, to=sid)

# 3. إغلاق الجلسة بثقة عند العودة للوبي
@sio.event
async def close_host_session(sid, data):
    global party_session_sid, party_session_used_ids
    # 🧹 تصفير جلسة الحفلة عند الإغلاق — يسمح للمستخدم القادم ببداية نظيفة
    party_session_sid = None
    party_session_used_ids = set()
    print("🧹 [Party] تم تصفير جلسة الحفلة عند الإغلاق")
    # نبحث عن الجلسة الثابتة 'admin' وليس الـ sid المتغير
    chat_id = host_chat_ids.get('admin')
    if chat_id:
        msg = "🛑 انتهت اللعبة! تم إغلاق الجلسة وإيقاف إرسال الإجابات."
        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': msg})
        host_chat_ids.pop('admin', None)

# إغلاق جلسة المدير الحالي وتسليمها لغيره
@sio.event
async def change_host_session(sid, data):
    chat_id = host_chat_ids.get('admin') 
    if chat_id:
        msg = "🔄 تم تسليم الإدارة لشخص آخر! تم سحب صلاحياتك ولن تصلك الإجابات بعد الآن."
        await asyncio.to_thread(requests.post, f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data={'chat_id': chat_id, 'text': msg})
        host_chat_ids.pop('admin', None) # مسح المدير القديم من الذاكرة

# 4. التعديل الأخير: تأكد أن دالة إرسال الإجابات السرية تقرأ من 'admin'
# 👈 جعلنا الدالة async واستخدمنا to_thread عشان ما تعلق السيرفر
async def send_secret_to_mobile(question, answer):
    CHAT_ID = host_chat_ids.get('admin')
    if not CHAT_ID:
        return
    msg = f"السؤال: {question}\n🎯 الإجابة: {answer}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        await asyncio.to_thread(requests.post, url, data={'chat_id': CHAT_ID, 'text': msg}, timeout=2)
    except Exception as e:
        print("لم يتم إرسال التليجرام:", e)

def get_clean_avatar(avatar_val, fallback_name="Player"):
    if not avatar_val or str(avatar_val).strip() == "":
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={fallback_name}"
    
    avatar_str = str(avatar_val).strip()
    if avatar_str.startswith("http") or avatar_str.startswith("data:"):
        return avatar_str
        
    # استخراج اسم الصورة فقط وتنظيفه من أي شوائب في الداتابيس
    clean_name = avatar_str.split('/')[-1]
    if not clean_name.endswith('.svg') and not clean_name.endswith('.png'):
        clean_name += '.svg'
        
    return f"../../assets/avatars/{clean_name}"

# ==========================================
# ⚡ 2. نظام جلب البيانات الموازي (بدون تعليق)
# ==========================================
def fetch_stats_from_db(token: str, fallback_name: str, fallback_avatar: str):
    default_stats = {
        "name": fallback_name or "لاعب",
        "avatar": get_clean_avatar(fallback_avatar, fallback_name),
        "flag": "../../assets/flags/SA.svg", "rank": "--",
        "huroof": {"wins": 0, "losses": 0, "total": 0}, "global": {"wins": 0, "losses": 0, "total": 0}
    }
    
    db = SessionLocal()
    try:
        user = get_user_from_token(db, token)
        if not user and fallback_name and fallback_name not in ["لاعب", "مجهول", "أنت"]:
            user = db.query(User).filter(User.player_name.ilike(f"%{fallback_name.strip()}%")).first()
            
        if not user: return default_stats
            
        huroof_stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == "huroof").first()
        user_xp = user.xp if user.xp is not None else 0
        rank = db.query(User).filter(User.xp > user_xp).count() + 1
        flag_path = f"../../assets/flags/{user.country}.svg" if user.country else default_stats["flag"]
        
        return {
            "name": user.player_name, 
            "avatar": get_clean_avatar(user.avatar, user.player_name), # 🚀 إجبار السيرفر على تجهيز رابط سليم 100%
            "flag": flag_path, "rank": rank,
            "huroof": {"wins": huroof_stat.wins if huroof_stat else 0, "losses": huroof_stat.losses if huroof_stat else 0, "total": huroof_stat.matches_played if huroof_stat else 0},
            "global": {"wins": user.wins or 0, "losses": user.losses or 0, "total": user.total_matches or 0}
        }
    except Exception as e:
        print(f"🔥 خطأ DB: {e}")
        return default_stats
    finally:
        db.close()

async def get_player_full_stats(token: str, fallback_name: str, fallback_avatar: str):
    # تشغيل أوامر الداتابيس في Thread خلفي تماماً لكي لا يعلق السيرفر أبداً!
    return await asyncio.to_thread(fetch_stats_from_db, token, fallback_name, fallback_avatar)

# ==========================================
# ⚡ 3. نظام حفظ النتائج الصاروخي (Fire and Forget)
# ==========================================
# ==========================================
# 🏆 حساب مستوى اللاعب بناءً على XP
# ==========================================
def get_level_from_xp(xp: int) -> int:
    """كل مستوى يحتاج 2000 * (level) نقطة XP"""
    level = 0
    xp_needed = 2000
    total = 0
    while xp >= total + xp_needed:
        total += xp_needed
        level += 1
        xp_needed = xp_needed * 2
    return level

# ==========================================
# 🎁 نظام المكافآت الكامل
# ==========================================
GAME_MODES_ALL = ['huroof', 'bank', 'career', 'whoami', 'whatdo']  # الأطوار الخمسة

def save_match_sync(winner_player: dict, loser_player: dict, game_mode: str, extra: dict=None):
    """
    extra (للـ huroof فقط): {
        'winner_rounds': int,  # جولات فاز بها الفائز (1 أو 2)
        'loser_rounds':  int,  # جولات فاز بها الخاسر  (0 أو 1)
        'reason': str,         # 'surrender' أو 'normal'
    }
    """
    db = SessionLocal()
    today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    extra = extra or {}
    try:
        for (is_winner, player) in [(True, winner_player), (False, loser_player)]:
            if not player: continue
            token = player.get('token')
            name = player.get('name')
            user = get_user_from_token(db, token)
            if not user and name and (name not in ['لاعب', 'مجهول', 'أنت']):
                user = db.query(User).filter(User.player_name.ilike(f'%{name.strip()}%')).first()
            if not user: continue
            
            import json
            last_reset = user.last_daily_reset or ''
            if last_reset != today:
                user.daily_games = '{}'
                user.last_daily_reset = today
                user.first_win_claimed = False
            daily_games = json.loads(user.daily_games or '{}')
            user.total_matches = (user.total_matches or 0) + 1
            if is_winner: user.wins = (user.wins or 0) + 1
            else: user.losses = (user.losses or 0) + 1
            
            xp_gain = 0
            coins_gain = 0
            gems_gain = 0
            rewards_log = []
            
            # === 🚀 التوزيع الصارم الجديد لمسابقة "حروف" ===
            if game_mode == 'huroof':
                reason = extra.get('reason', 'normal')
                winner_rounds = extra.get('winner_rounds', 2)
                loser_rounds = extra.get('loser_rounds', 0)
                
                if reason == 'surrender':
                    if is_winner:
                        xp_gain = 150
                        coins_gain = 100
                        rewards_log.append(f'فوز بالانسحاب (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        xp_gain = 0
                        coins_gain = 0
                        rewards_log.append(f'انسحاب من اللعبة (0XP 0🪙)')
                else:
                    if is_winner:
                        if winner_rounds == 2 and loser_rounds == 0:
                            xp_gain = 300
                            coins_gain = 160  # 120 للفوز + 40 لجولتين
                        elif winner_rounds == 2 and loser_rounds == 1:
                            xp_gain = 250
                            coins_gain = 160
                        else:
                            xp_gain = 250
                            coins_gain = 160
                        rewards_log.append(f'فوز حروف (+{xp_gain}XP +{coins_gain}🪙)')
                    else:
                        if winner_rounds == 2 and loser_rounds == 0:
                            xp_gain = 40
                            coins_gain = 15
                        elif winner_rounds == 2 and loser_rounds == 1:
                            xp_gain = 50
                            coins_gain = 35  # 15 للخسارة + 20 نقطة ترضية للجولة
                        else:
                            xp_gain = 40
                            coins_gain = 15
                        rewards_log.append(f'خسارة حروف (+{xp_gain}XP +{coins_gain}🪙)')
            
            # === التوزيع لباقي الألعاب السريعة ===
            else:
                if is_winner:
                    xp_gain = 100
                    coins_gain = 50
                    rewards_log.append(f'فوز {game_mode} (+100XP +50🪙)')
                else:
                    xp_gain = 25
                    coins_gain = 10
                    rewards_log.append(f'خسارة {game_mode} (+25XP +10🪙)')
                    
            # ... استكمال باقي مكافآت اليومية (First win, Streaks) ...
            if is_winner and (not user.first_win_claimed):
                user.first_win_claimed = True
                coins_gain += 100
                gems_gain += 2
                rewards_log.append('🥇 أول فوز اليوم! (+100🪙 +2💎)')
            
            if is_winner:
                last_win = user.last_win_date or ''
                yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
                if last_win == today or last_win == yesterday:
                    user.win_streak = (user.win_streak or 0) + 1
                else:
                    user.win_streak = 1
                user.last_win_date = today
                if user.win_streak % 3 == 0:
                    gems_gain += 1
                    rewards_log.append(f'🔥 سلسلة {user.win_streak} انتصار! (+1💎)')
            else:
                user.win_streak = 0
                
            daily_games[game_mode] = True
            user.daily_games = json.dumps(daily_games)
            completed_modes = [m for m in ['huroof', 'what', 'whoami', 'career', 'bank'] if daily_games.get(m)]
            if len(completed_modes) == 5:
                if 'daily_completionist' not in daily_games:
                    daily_games['daily_completionist'] = True
                    user.daily_games = json.dumps(daily_games)
                    gems_gain += 5
                    rewards_log.append('🏅 مكافأة الخماسي اليومية! (+5💎)')
            
            old_level = get_level_from_xp(user.xp or 0)
            user.xp = (user.xp or 0) + xp_gain
            user.coins = (user.coins or 0) + coins_gain
            user.gems = (user.gems or 0) + gems_gain
            new_level = get_level_from_xp(user.xp)
            user.level = new_level
            
            if new_level > old_level:
                user.gems += 3
                user.coins += 200
                rewards_log.append(f'🆙 Level Up! مستوى {new_level} (+3💎 +200🪙)')
                
            stat = db.query(GameStat).filter(GameStat.user_id == user.id, GameStat.game_mode == game_mode).first()
            if not stat:
                stat = GameStat(user_id=user.id, game_mode=game_mode, matches_played=0, wins=0, losses=0)
                db.add(stat)
            stat.matches_played += 1
            if is_winner: stat.wins += 1
            else: stat.losses += 1
                
            print(f"💾 [{name}] مكافآت: {' | '.join(rewards_log)}")
            
        db.commit()
    except Exception as e:
        print('⚠️ خطأ في حفظ النتيجة:', e)
        db.rollback()
    finally:
        db.close()


# ==========================================
# 🛒 متجر الاستبدال: كوينز ← جواهر
# ==========================================
@app.post("/shop/exchange")
async def exchange_coins_for_gems(token: str, db: requests.Session = Depends(get_db)):
    """1000 كوين = 5 جواهر"""
    user = get_user_from_token(db, token)
    if not user:
        raise HTTPException(status_code=401, detail="غير مصرح")
    COST    = 1000
    REWARD  = 5
    if (user.coins or 0) < COST:
        raise HTTPException(status_code=400, detail=f"تحتاج {COST} كوين للاستبدال")
    user.coins -= COST
    user.gems   = (user.gems or 0) + REWARD
    db.commit()
    return {"success": True, "coins": user.coins, "gems": user.gems,
            "message": f"تم الاستبدال! حصلت على {REWARD} جواهر 💎"}

def record_match_result(winner_player: dict, loser_player: dict, game_mode: str, extra: dict=None):
    try:
        loop = asyncio.get_running_loop()
        # نمرر الـ extra الذي يحتوي على (سبب الفوز، وعدد الجولات)
        loop.run_in_executor(None, save_match_sync, winner_player, loser_player, game_mode, extra)
    except Exception as e:
        print("⚠️ خطأ في تشغيل الحفظ الخلفي:", e)

# دالة المكنسة الآلية
async def cleanup_abandoned_accounts():
    while True:
        try:
            db = SessionLocal()
            # نحدد الوقت: أي حساب أقدم من 24 ساعة
            cutoff_time = datetime.now(datetime.timezone.utc) - timedelta(hours=24)
            
            # نبحث عن الحسابات التي لم تكمل الإعداد (مثلاً لا يوجد لها اسم لاعب)
            abandoned_users = db.query(User).filter(
                User.player_name == None, # لم يكمل الإعداد
                User.created_at < cutoff_time # مر عليها أكثر من 24 ساعة
            ).all()

            for user in abandoned_users:
                # يمكنك هنا أيضاً إضافة كود لحذف صورهم الافتراضية إذا كنت تنشئها لهم
                db.delete(user)
            
            db.commit()
            db.close()
            print(f"تم تنظيف {len(abandoned_users)} حسابات مهجورة.")
        except Exception as e:
            print(f"خطأ في التنظيف الآلي: {e}")
        
        # نجعل الدالة تنام وتعمل مرة كل 12 ساعة (بالثواني)
        await asyncio.sleep(12 * 60 * 60)