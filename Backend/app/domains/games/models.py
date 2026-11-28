import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, UniqueConstraint, Index
from app.infrastructure.database import Base

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    game_mode = Column(String, index=True)
    question_text = Column(String)
    correct_answer = Column(String)
    category = Column(String)
    extra_data = Column(String, nullable=True)
    # منع التكرار على مستوى DB (طبقة ثانية بعد dedup الكود)
    __table_args__ = (
        UniqueConstraint("game_mode", "question_text",
                         name="uq_question_game_text"),
    )


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
    difficulty = Column(String, default="medium") # easy | medium | hard: شهرة مراجعة للبوت، وليست سهولة مسيرة الأندية
    nationality = Column(String, nullable=True)   # للمساعدة "كاشف الجنسية"
    era = Column(String, nullable=True)           # فترة المسيرة "1995-2010" (كاشف الجيل)
    position = Column(String, nullable=True)      # المركز بالعربية (كاشف المركز)
    active = Column(Boolean, default=True)        # هل يُستخدم في اللعب


class BankSeen(Base):
    """أسئلة البنك التي شاهدها كل مستخدم (لمنع التكرار عبر المباريات).
    الفلترة شخصية: سؤال شفته أنا لا يظهر لي، لكن يظهر لخصمي إن لم يره."""
    __tablename__ = "bank_seen"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String, index=True)   # id السؤال (q001...)
    seen_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_bank_seen_user_q"),
    )


class CareerSeen(Base):
    """شخصيات "مسيرة لاعب" التي شاهدها كل مستخدم (لمنع التكرار عبر المباريات).
    الاختيار يستبعد ما شاهده أيّ من طرفَي المباراة (عدالة)."""
    __tablename__ = "career_seen"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    player_id = Column(Integer, index=True)   # CareerPlayer.id
    seen_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "player_id", name="uq_career_seen_user_p"),
    )


class KnowledgeSeen(Base):
    """أسئلة "ماذا تعرف" التي شاهدها كل مستخدم (لمنع التكرار عبر المباريات).
    الفلترة شخصية: سؤال شفته أنا لا يظهر لي، لكن يظهر لخصمي إن لم يره."""
    __tablename__ = "knowledge_seen"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String, index=True)   # id سؤال القائمة
    seen_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_knowledge_seen_user_q"),
    )


class WhoamiSeen(Base):
    """شخصيات من أنا التي عُرضت للمستخدم، دون بيانات شخصية إضافية."""
    __tablename__ = 'whoami_seen'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    character_id = Column(String, index=True)
    seen_at = Column(DateTime, default=datetime.datetime.utcnow)
    __table_args__ = (UniqueConstraint('user_id', 'character_id', name='uq_whoami_seen_user_char'),)


class MatchSettlement(Base):
    """حاجز ذري ضد صرف مكافأة نتيجة المباراة مرتين."""
    __tablename__ = 'match_settlements'
    match_id = Column(String(64), primary_key=True)
    settled_at = Column(DateTime, default=datetime.datetime.utcnow)


class PairSettlement(Base):
    __tablename__ = "pair_settlements"
    match_id = Column(String(64), ForeignKey("match_settlements.match_id"), primary_key=True)
    low_id = Column(Integer, nullable=False)
    high_id = Column(Integer, nullable=False)
    settled_at = Column(DateTime, nullable=False)
    __table_args__ = (Index("ix_pair_settlement_window", "low_id", "high_id", "settled_at"),)

class FairPlayAccount(Base):
    __tablename__ = "fair_play_accounts"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    score = Column(Integer, nullable=False, default=0)
    updated = Column(DateTime, nullable=False)
    suspended_until = Column(DateTime)
    permanent_reason = Column(String(200))

class ShadowOutcome(Base):
    """Server-observed results for retrospective fair-play review."""
    __tablename__ = "shadow_outcomes"
    match_id = Column(String(64), ForeignKey("match_settlements.match_id"), primary_key=True)
    low_id = Column(Integer, nullable=False)
    high_id = Column(Integer, nullable=False)
    settled_at = Column(DateTime, nullable=False)
    winner_id = Column(Integer)
    surrendered = Column(Boolean, nullable=False)
    game_mode = Column(String(24), nullable=False)
    review_reason = Column(String(160))
    __table_args__ = (Index("ix_shadow_pair_time", "low_id", "high_id", "settled_at"),)


class MatchReview(Base):
    __tablename__ = "match_reviews"
    match_id = Column(String(64), ForeignKey("shadow_outcomes.match_id"), primary_key=True)
    alternatives = Column(Integer)
    local_label = Column(String(24), nullable=False)
    ai_label = Column(String(24))
    status = Column(String(24), nullable=False, index=True)
    signals = Column(Text, nullable=False, default="[]")


class StoreReceipt(Base):
    __tablename__ = "store_receipts"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    request_id = Column(String(36), primary_key=True)
    item_id = Column(String(128), nullable=False)
    coins = Column(Integer, nullable=False)
    gems = Column(Integer, nullable=False)


class PublicMatchLease(Base):
    __tablename__ = "public_match_leases"
    match_id = Column(String(64), primary_key=True)
    room_code = Column(String(16), nullable=False, index=True)
    owner = Column(String(96), nullable=False)
    first_uid = Column(Integer, nullable=False)
    second_uid = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False)
    heartbeat = Column(DateTime, nullable=False)
    winner_id = Column(Integer)
    __table_args__ = (Index("ix_public_lease_expiry", "status", "heartbeat"),)


class MatchHelpDebit(Base):
    __tablename__ = "match_help_debits"
    id = Column(Integer, primary_key=True)
    match_id = Column(String(64), ForeignKey("public_match_leases.match_id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=False)
    help_id = Column(String(40), nullable=False)
