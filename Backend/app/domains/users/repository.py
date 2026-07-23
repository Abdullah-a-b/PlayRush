import string
import secrets

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.users.models import User


class UserRepository:
    """نقطة الوصول الوحيدة لجدول المستخدمين.

    كل استعلامات وكتابات users تمر من هنا — لا يصل أي Controller
    أو Service إلى SQLAlchemy مباشرة في هذا النطاق.
    """

    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def email_exists(self, email: str) -> bool:
        return self.get_by_email(email) is not None

    def get_by_player_name(self, player_name: str) -> User | None:
        return self.db.query(User).filter(User.player_name == player_name).first()

    def player_id_exists(self, player_id: str) -> bool:
        return self.db.query(User).filter(User.player_id == player_id).first() is not None

    def generate_unique_player_id(self) -> str:
        """توليد معرف لاعب فريد بصيغة PR-XXXXX عبر secrets."""
        while True:
            new_id = "PR-" + ''.join(secrets.choice(string.digits) for _ in range(5))
            if not self.player_id_exists(new_id):
                return new_id

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User):
        """يحذف المستخدم بعد تنظيف كل السجلات المرتبطة به.

        الجداول التابعة تشير إلى users.id بلا ON DELETE CASCADE، فحذف
        مستخدم له بيانات (إشعارات/تقدّم/صداقات) كان يفشل بخطأ قيد مرجعي.
        ننظّفها هنا أولاً حتى يتم الحذف بنجاح ولا تبقى بيانات يتيمة.
        """
        uid = user.id

        # (اسم الجدول, شرط الحذف) — نستخدم SQL خاماً ليشمل الجداول
        # المُنشأة يدوياً (player_reports/‏player_penalties) وجداول الـseen.
        cleanup = [
            ("notifications",  "user_id = :uid"),
            ("friendships",    "user_id = :uid OR friend_id = :uid"),
            ("game_stats",     "user_id = :uid"),
            ("player_ranks",   "user_id = :uid"),
            ("player_quests",  "user_id = :uid"),
            ("player_pass",    "user_id = :uid"),
            ("bank_seen",      "user_id = :uid"),
            ("career_seen",    "user_id = :uid"),
            ("knowledge_seen", "user_id = :uid"),
            ("player_reports", "reporter_id = :uid OR target_id = :uid"),
            ("player_penalties", "user_id = :uid"),
        ]

        for table, where in cleanup:
            # نقطة حفظ لكل جدول: لو فشل واحد (جدول غير موجود مثلاً)
            # نتراجع عنه وحده دون إلغاء ما نجح قبله.
            try:
                with self.db.begin_nested():
                    self.db.execute(text(f"DELETE FROM {table} WHERE {where}"), {"uid": uid})
            except Exception:
                pass

        self.db.delete(user)
        self.db.commit()

    def commit(self):
        self.db.commit()
