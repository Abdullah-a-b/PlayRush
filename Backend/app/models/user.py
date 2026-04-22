import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, unique=True, index=True, nullable=True) 
    player_name = Column(String, nullable=True) 
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    avatar = Column(String, nullable=True)      
    country = Column(String, nullable=True)
    verification_code = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    session_token = Column(String, nullable=True) 
    welcome_email_sent = Column(Boolean, default=False)
    auth_provider = Column(String, default="local")
    level = Column(Integer, default=0)
    xp = Column(Integer, default=0)              
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
    is_banned = Column(Boolean, default=False)

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