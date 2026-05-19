#!/usr/bin/env python3
"""
🆘 سكريبت استعادة DB من backup.

⚠️ خطر: هذا السكريبت يستبدل DB موجودة. استخدمه بحذر شديد.

الاستخدام:
    # عرض قائمة الـ backups المتاحة
    python -m scripts.restore_db --list

    # استعادة من backup محدد
    python -m scripts.restore_db --file backups/playrush_hourly_20251231_140000.sql.gz

    # استعادة لـ DB مختلفة (اختبار قبل الإنتاج)
    python -m scripts.restore_db --file ... --to-db postgresql://user:pass@host/test_db
"""
import os
import sys
import subprocess
import gzip
import argparse
import io
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

BACKUP_DIR = BACKEND_DIR / "backups"


def parse_database_url(url: str) -> dict:
    if "://" not in url:
        raise ValueError("DATABASE_URL ليس بالصيغة الصحيحة")
    _, rest = url.split("://", 1)
    auth, host_db = rest.split("@", 1)
    user, password = auth.split(":", 1) if ":" in auth else (auth, "")
    host_port, dbname = host_db.split("/", 1) if "/" in host_db else (host_db, "")
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")
    if "?" in dbname:
        dbname = dbname.split("?")[0]
    return {"user": user, "password": password, "host": host, "port": port, "dbname": dbname}


def list_backups():
    """يعرض الـ backups المتاحة مرتبة بالأحدث."""
    files = sorted(BACKUP_DIR.glob("playrush_*.sql.gz"), key=os.path.getmtime, reverse=True)
    if not files:
        print("📂 لا توجد backups في:", BACKUP_DIR)
        return

    print(f"📂 backups متاحة في {BACKUP_DIR}:")
    print(f"{'الاسم':<55} {'الحجم':<10} {'التاريخ':<20}")
    print("-" * 90)
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{f.name:<55} {size_mb:>6.2f} MB  {mtime}")


def restore(file_path: Path, db_url: str, force: bool = False):
    """يستعيد backup إلى DB."""
    if not file_path.exists():
        raise FileNotFoundError(f"❌ الملف غير موجود: {file_path}")

    parts = parse_database_url(db_url)

    # ⚠️ تحذير الإنتاج
    if not force:
        print(f"⚠️  ستُستبدل بيانات DB: {parts['host']}/{parts['dbname']}")
        print(f"📂 الـ backup: {file_path.name}")
        confirm = input("اكتب 'yes' للمتابعة: ").strip().lower()
        if confirm != "yes":
            print("🛑 ألغيت العملية")
            return

    cmd = [
        "psql",
        "-h", parts["host"],
        "-p", parts["port"],
        "-U", parts["user"],
        "-d", parts["dbname"],
        "--no-password",
        "-v", "ON_ERROR_STOP=1",  # يوقف عند أول خطأ
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]

    print(f"🔄 جاري الاستعادة...")

    try:
        # نفك الضغط ونمرّر للـ psql
        with gzip.open(file_path, "rb") as f_in:
            proc = subprocess.run(
                cmd,
                stdin=f_in,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )
        print(f"✅ الاستعادة مكتملة")
        if proc.stderr:
            stderr = proc.stderr.decode("utf-8", errors="replace")
            if stderr.strip():
                print(f"📝 ملاحظات psql:\n{stderr[:500]}")
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode("utf-8", errors="replace")[:1000] if e.stderr else ""
        raise RuntimeError(f"❌ فشلت الاستعادة:\n{err_msg}")
    except FileNotFoundError:
        raise RuntimeError(
            "❌ psql غير موجود في PATH.\n"
            "Linux: apt install postgresql-client\n"
            "Windows: ضِف C:\\Program Files\\PostgreSQL\\<version>\\bin إلى PATH"
        )


def main():
    parser = argparse.ArgumentParser(description="PostgreSQL restore tool")
    parser.add_argument("--list", action="store_true", help="عرض الـ backups المتاحة")
    parser.add_argument("--file", help="مسار ملف الـ backup للاستعادة")
    parser.add_argument("--to-db", help="DATABASE_URL هدف (default: من .env)")
    parser.add_argument("--force", action="store_true", help="تخطي تأكيد المستخدم (خطر!)")
    args = parser.parse_args()

    if args.list:
        list_backups()
        return

    if not args.file:
        parser.error("--file مطلوب (أو --list)")

    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = BACKEND_DIR / file_path

    db_url = args.to_db or os.environ.get("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL غير مضبوط ولا --to-db مذكور", file=sys.stderr)
        sys.exit(1)

    try:
        restore(file_path, db_url, force=args.force)
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
