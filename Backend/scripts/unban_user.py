"""
🔓 سكريبت فك حظر مستخدم.

الاستخدام:
    cd Backend
    python -m scripts.unban_user <email>

أو لعرض كل المحظورين:
    python -m scripts.unban_user --list

أو لفك حظر الكل (احذر!):
    python -m scripts.unban_user --all
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from app.models.user import User


def list_banned():
    db = SessionLocal()
    try:
        banned = db.query(User).filter(User.is_banned == True).all()
        if not banned:
            print("✅ لا يوجد مستخدمين محظورين")
            return
        print(f"📋 المستخدمون المحظورون ({len(banned)}):\n")
        for u in banned:
            score = getattr(u, 'anticheat_score', 0) or 0
            print(f"   • {u.email:<40} | name={u.player_name or '—':<15} | score={score}")
    finally:
        db.close()


def unban(email: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ المستخدم {email} غير موجود")
            return False

        if not user.is_banned and (getattr(user, 'anticheat_score', 0) or 0) == 0:
            print(f"ℹ️  المستخدم {email} غير محظور أصلاً")
            return True

        user.is_banned = False
        if hasattr(user, 'anticheat_score'):
            user.anticheat_score = 0
        db.commit()
        print(f"✅ تم فك حظر {email} (player={user.player_name})")
        print("⚠️  ملاحظة: امسح localStorage في المتصفح أو استخدم incognito")
        print("   وإلا الـ anti_cheat.js سيحظره مجدداً (cb=1 في localStorage)")
        return True
    finally:
        db.close()


def unban_all():
    db = SessionLocal()
    try:
        banned = db.query(User).filter(User.is_banned == True).all()
        count = len(banned)
        if count == 0:
            print("✅ لا يوجد محظورين")
            return
        confirm = input(f"⚠️  ستفك حظر {count} مستخدم. اكتب 'yes' للتأكيد: ")
        if confirm.lower() != 'yes':
            print("🛑 ألغيت")
            return
        for u in banned:
            u.is_banned = False
            if hasattr(u, 'anticheat_score'):
                u.anticheat_score = 0
        db.commit()
        print(f"✅ تم فك حظر {count} مستخدم")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]
    if arg == "--list":
        list_banned()
    elif arg == "--all":
        unban_all()
    elif "@" in arg:
        unban(arg)
    else:
        print(f"❌ {arg} ليس بإيميل صالح")
        print(__doc__)
        sys.exit(1)
