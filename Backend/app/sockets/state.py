# ==========================================
# 📊 المتغيرات الشاملة للمتصلين والغرف (Central State)
# ==========================================

connected_players = {}   
global_chat_history = [] 
game_lobby_players = {}  
game_chat_history = {}  

party_session_used_ids: set = set()   
party_session_sid: str | None = None  

active_codes = {}  
host_chat_ids = {} 
LAST_UPDATE_ID = 0 

disconnect_timers = {}

# أضف هذه السطور في ملف state.py
STATS_CACHE = {}
CACHE_TTL = 15
TOPICS = ['إسلاميات وسيرة نبوية', 'ألغاز وفوازير ذكية', 'تاريخ', 'جغرافيا', 'علوم', 'ثقافة عامة', 'رياضة']