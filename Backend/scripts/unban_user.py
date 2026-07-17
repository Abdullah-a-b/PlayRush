"""
 سكريبت فك الحظر — للمطوّر

الاستخدام:
    python scripts/unban_user.py --list           # يعرض كل الحسابات وحالتها
    python scripts/unban_user.py --all             # يفك الحظر عن الجميع
    python scripts/unban_user.py <البريد أو الاسم>  # يفك حساباً محدداً
"""
import sys
import os

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)

# نحمّل .env صراحةً (السكريبت المستقل لا يحمّله تلقائياً)
try:
    from dotenv import load_dotenv
    env_path = os.path.join(_BASE, '.env')
    load_dotenv(env_path)
    print(f" حُمّل .env من: {env_path}")
except Exception as e:
    print(f" تعذّر تحميل .env: {e}")

_db_url = os.environ.get("DATABASE_URL", "غير مضبوط")
if "@" in _db_url:
    print(f" قاعدة البيانات: ...@{_db_url.split('@')[-1]}")
else:
    print(f" قاعدة البيانات: {_db_url}")

from app.infrastructure.database import SessionLocal
from app.domains.users.models import User
from sqlalchemy import text


def list_all():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("\n لا يوجد أي حسابات في قاعدة البيانات!")
            return
        print(f"\n كل الحسابات ({len(users)}):")
        for u in users:
            mark = "🚫 محظور" if u.is_banned else "✅ نشط"
            score = getattr(u, 'anticheat_score', 0) or 0
            print(f"  {mark} | {u.player_name} | {u.email} | score={score}")
    finally:
        db.close()


def unban(identifier):
    db = SessionLocal()
    try:
        user = db.query(User).filter(
            (User.email == identifier) | (User.player_name == identifier)
        ).first()
        if not user:
            print(f"\n لم أجد حساباً بـ: '{identifier}'")
            print("   جرّب --list لرؤية كل الحسابات")
            return
        was = user.is_banned
        user.is_banned = False
        user.anticheat_score = 0
        try:
            db.execute(text("UPDATE player_penalties SET expires_at = NOW() WHERE user_id = :uid AND (expires_at IS NULL OR expires_at > NOW())"), {"uid": user.id})
        except Exception:
            pass
        db.commit()
        print(f"\n تم فك الحظر: {user.player_name} ({user.email})")
        print(f"   {'كان محظوراً  الآن نشط' if was else 'لم يكن محظوراً (صُفّر score)'}")
    finally:
        db.close()


def unban_all():
    db = SessionLocal()
    try:
        banned = db.query(User).filter(User.is_banned == True).all()
        for u in db.query(User).all():
            u.is_banned = False
            u.anticheat_score = 0
        try:
            db.execute(text("UPDATE player_penalties SET expires_at = NOW() WHERE expires_at IS NULL OR expires_at > NOW()"))
        except Exception:
            pass
        db.commit()
        print(f"\n فُك الحظر عن {len(banned)} حساب + صُفّر score للكل")
        for u in banned:
            print(f"   • {u.player_name} ({u.email})")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nالاستخدام:")
        print("  python scripts/unban_user.py --list")
        print("  python scripts/unban_user.py --all")
        print("  python scripts/unban_user.py <البريد>")
        sys.exit(1)
    arg = sys.argv[1]
    if arg == "--list":
        list_all()
    elif arg == "--all":
        unban_all()
    else:
        unban(arg)
