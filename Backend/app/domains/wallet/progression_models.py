import datetime
from sqlalchemy import (Column, Integer, String, Boolean, ForeignKey,
                        DateTime, Text, UniqueConstraint, Float)
from app.infrastructure.database import Base


class PlayerRank(Base):
    """تصنيف Elo لكل لاعب في كل لعبة، موسمي (يُعاد ضبطه كل موسم مع الـPass).

    مفتاح فريد (user, game, season): كل موسم صف جديد، فتُحفظ رتب المواسم
    السابقة للأرشيف. جواهر عبور الرتب تُمنح مرة لكل موسم عبر highest_tier
    (لا أبدياً) — فتتجدد كمصدر موسمي.
    """
    __tablename__ = "player_ranks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    game_mode = Column(String, index=True)
    season_key = Column(String, index=True, default="")   # موسم هذا الصف
    elo = Column(Integer, default=1000, index=True)   # index لـleaderboard
    peak_elo = Column(Integer, default=1000)
    highest_tier = Column(String, default="bronze")    # أعلى مجموعة بُلغت هذا الموسم
    matches = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "game_mode", "season_key",
                         name="uq_rank_user_game_season"),
    )


class PlayerQuest(Base):
    """مهمة نشطة للاعب (يومية/أسبوعية/موسمية) مع تقدّمها."""
    __tablename__ = "player_quests"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    quest_key = Column(String, index=True)      # معرّف القالب في quests_catalog
    scope = Column(String, index=True)          # daily | weekly | seasonal
    period_key = Column(String, index=True)     # 2026-07-15 / 2026-W29 / 2026-S07
    target = Column(Integer, default=1)
    progress = Column(Integer, default=0)
    claimed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "quest_key", "period_key",
                         name="uq_quest_user_key_period"),
    )


class PlayerPass(Base):
    """تقدّم الـPass الموسمي للاعب (Pass XP + المحطات المستلمة)."""
    __tablename__ = "player_pass"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    season_key = Column(String, index=True)     # 2026-S07
    pass_xp = Column(Integer, default=0)
    is_premium = Column(Boolean, default=False)
    claimed_free = Column(Text, default="[]")   # قائمة أرقام المحطات المستلمة (مجاني)
    claimed_premium = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "season_key", name="uq_pass_user_season"),
    )
