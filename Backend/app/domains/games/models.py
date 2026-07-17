import datetime
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, UniqueConstraint
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
    difficulty = Column(String, default="medium") # easy | medium | hard (للتوازن لاحقاً)
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
