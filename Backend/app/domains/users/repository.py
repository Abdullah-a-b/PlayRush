import string
import secrets

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
        self.db.delete(user)
        self.db.commit()

    def commit(self):
        self.db.commit()
