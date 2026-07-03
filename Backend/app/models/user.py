import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, unique=True, index=True, nullable=True)
    player_name = Column(String, index=True, nullable=True)  # ⚡ index للبحث في reward_service
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    avatar = Column(String, nullable=True)
    country = Column(String, nullable=True)
    verification_code = Column(String, nullable=True)
    verification_code_expires_at = Column(DateTime, nullable=True)  # 🛡️ ينتهي بعد 15 دقيقة (يمنع OTP أبدي)
    is_verified = Column(Boolean, default=False, index=True)  # ⚡ index لـ cleanup cron
    is_banned = Column(Boolean, default=False, index=True)  # 🛡️ للحظر — index لفلترة الحسابات النشطة
    anticheat_score = Column(Integer, default=0)  # 🛡️ يتراكم مع كل تقرير، 5+ = ban تلقائي
    session_token = Column(String, nullable=True)
    welcome_email_sent = Column(Boolean, default=False)
    auth_provider = Column(String, default="local")
    level = Column(Integer, default=0)
    xp = Column(Integer, default=0, index=True)  # ⚡ index لـ leaderboard
    coins = Column(Integer, default=100)
    gems = Column(Integer, default=3)
    win_streak = Column(Integer, default=0)
    last_win_date = Column(String, nullable=True)
    first_win_claimed = Column(Boolean, default=False)
    daily_games = Column(String, default="{}")
    last_daily_reset = Column(String, nullable=True)
    total_matches = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    seen_question_ids = Column(Text, default="[]")
    game_stats = relationship("GameStat", back_populates="user")

class GameStat(Base):
    __tablename__ = "game_stats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    game_mode = Column(String, index=True)
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    highest_score = Column(Integer, default=0)
    user = relationship("User", back_populates="game_stats")

class Friendship(Base):
    __tablename__ = "friendships"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)       
    friend_id = Column(Integer, ForeignKey("users.id"), index=True)     
    status = Column(String, default="pending")                                          
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)       
    type = Column(String)                                                               
    message = Column(String)                                                            
    is_read = Column(Boolean, default=False)                                            
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    game_mode = Column(String, index=True)      
    question_text = Column(String)              
    correct_answer = Column(String)             
    category = Column(String)                   
    extra_data = Column(String, nullable=True)


class CareerPlayer(Base):
    """لاعب كرة قدم للعبة 'مسيرة لاعب'.
    clubs = JSON list مرتّبة من الأول للأخير:
      [{"name": "سبورتنغ لشبونة", "logo": "sporting.png"}, ...]
    accepted_answers = JSON list بصيغ الاسم المقبولة (للتحكيم المرن).
    """
    __tablename__ = "career_players"
    id = Column(Integer, primary_key=True, index=True)
    wikidata_id = Column(String, nullable=True, index=True)  # QID للتحديث الدوري بلا تكرار
    name = Column(String, index=True)            # الاسم الرسمي (الإجابة الصحيحة)
    status = Column(String, default="retired")   # "current" (حالي) | "retired" (معتزل)
    clubs = Column(Text)                          # JSON list [{name, logo}, ...] بالترتيب
    accepted_answers = Column(Text, nullable=True)  # JSON list صيغ مقبولة
    difficulty = Column(String, default="medium") # easy | medium | hard (للتوازن لاحقاً)
    nationality = Column(String, nullable=True)   # اختياري (تلميح مستقبلي)
    active = Column(Boolean, default=True)        # هل يُستخدم في اللعب


class CareerSeen(Base):
    """شخصيات "مسيرة لاعب" التي شاهدها كل مستخدم (لمنع التكرار عبر المباريات).
    الاختيار يستبعد ما شاهده أيّ من طرفَي المباراة (عدالة)."""
    __tablename__ = "career_seen"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    player_id = Column(Integer, index=True)   # CareerPlayer.id
    seen_at = Column(DateTime, default=datetime.datetime.utcnow)