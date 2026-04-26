import json
from app.core.redis_client import redis_db
import uuid

# ==========================================
# 🧠 العقل المركزي (Distributed State Manager)
# ==========================================

# --- 1. إدارة كل المتصلين (Global Players) ---
async def add_connected_player(sid, data):
    await redis_db.hset("global:connected_players", sid, json.dumps(data))

async def get_connected_player(sid):
    data = await redis_db.hget("global:connected_players", sid)
    return json.loads(data) if data else None

async def remove_connected_player(sid):
    await redis_db.hdel("global:connected_players", sid)

async def get_all_online_players():
    players = await redis_db.hgetall("global:connected_players")
    return [json.loads(p) for p in players.values()]

# --- 2. إدارة لوبي الألعاب المخصصة (Game Lobbies) ---
async def add_game_lobby_player(game_mode, sid, data):
    await redis_db.hset(f"lobby:{game_mode}", sid, json.dumps(data))

async def remove_game_lobby_player(game_mode, sid):
    await redis_db.hdel(f"lobby:{game_mode}", sid)

async def get_game_lobby_players(game_mode):
    players = await redis_db.hgetall(f"lobby:{game_mode}")
    return [json.loads(p) for p in players.values()]

# --- 3. إدارة الشات المركزي (Distributed Chat) ---
async def add_chat_message(room_name, msg_data):
    key = f"chat:{room_name}"
    await redis_db.lpush(key, json.dumps(msg_data))
    await redis_db.ltrim(key, 0, 49) # الاحتفاظ بآخر 50 رسالة فقط لمنع انفجار الذاكرة

async def get_chat_history(room_name):
    key = f"chat:{room_name}"
    messages = await redis_db.lrange(key, 0, -1)
    return [json.loads(m) for m in messages[::-1]] # عكس الترتيب ليظهر الأقدم فالأحدث

# --- 4. إدارة الماتش ميكنج (Matchmaking) ---
async def join_matchmaking(game_mode, player_data):
    # إضافة اللاعب للطابور الخاص باللعبة
    await redis_db.rpush(f"queue:{game_mode}", json.dumps(player_data))

async def leave_matchmaking(game_mode, sid):
    # إزالة اللاعب من الطابور (يحتاج لبعض المعالجة لأنها قائمة)
    queue_key = f"queue:{game_mode}"
    players = await redis_db.lrange(queue_key, 0, -1)
    for p_str in players:
        p_data = json.loads(p_str)
        if p_data.get('sid') == sid:
            await redis_db.lrem(queue_key, 1, p_str)
            break

async def check_matchmaking(game_mode):
    # التحقق هل يوجد لاعبين في الطابور
    queue_key = f"queue:{game_mode}"
    queue_len = await redis_db.llen(queue_key)
    
    if queue_len >= 2:
        # سحب أول لاعبين من الطابور
        p1_str = await redis_db.lpop(queue_key)
        p2_str = await redis_db.lpop(queue_key)
        
        if p1_str and p2_str:
            p1 = json.loads(p1_str)
            p2 = json.loads(p2_str)
            return p1, p2
    return None, None

# --- 5. إدارة الغرف النشطة (Active Rooms) ---
async def create_active_room(game_mode, p1, p2):
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    room_data = {
        "id": room_id,
        "mode": game_mode,
        "players": [p1, p2],
        "state": "playing"
    }
    await redis_db.hset("active_rooms", room_id, json.dumps(room_data))
    return room_id, room_data

async def get_active_room(room_id):
    data = await redis_db.hget("active_rooms", room_id)
    return json.loads(data) if data else None

async def delete_active_room(room_id):
    await redis_db.hdel("active_rooms", room_id)

# ==========================================
# 🎮 القواميس المحلية (Local Memory)
# ==========================================
active_rooms = {} 
matchmaking_queues = {}
cheat_strikes = {}
disconnect_timers = {} # 👈 تأكد من إضافة هذا السطر

# 🤖 متغيرات بوت التليجرام
active_codes = {}
host_chat_ids = {}

# 🛑 متغيرات وهمية مؤقتة (لكي لا تنهار الملفات التي لم نحدثها بعد)
connected_players = {}
game_lobby_players = {}
global_chat_history = []
game_chat_history = {}