# ==========================================
# المتغيرات الشاملة للمتصلين والغرف (Central State)
# ==========================================

connected_players = {}   
global_chat_history = [] 
game_lobby_players = {}  
game_chat_history = {}  

party_session_used_ids: set = set()   
party_session_sid: str | None = None  

active_codes = {}  
host_chat_ids = {} 
linked_hosts = {}   # party_token -> {chat_id, ts} : ربط ثابت ينجو من إعادة اتصال السوكت
LAST_UPDATE_ID = 0 

disconnect_timers = {}

# خريطة sid  IP (لمنع اللعب ضد النفس أو ضد نفس المنطقة/الشبكة)
sid_ip_map = {}

# أضف هذه السطور في ملف state.py
STATS_CACHE = {}
CACHE_TTL = 15
TOPICS = ['إسلاميات وسيرة نبوية', 'ألغاز وفوازير ذكية', 'تاريخ', 'جغرافيا', 'علوم', 'ثقافة عامة', 'رياضة']