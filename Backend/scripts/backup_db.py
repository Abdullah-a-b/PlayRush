#!/usr/bin/env python3
"""
🔄 PostgreSQL Backup Tool — يعمل على Windows + Linux

الاستخدام البسيط:
    cd Backend
    python -m scripts.backup_db                        # backup hourly عادي
    python -m scripts.backup_db --tag daily            # daily snapshot
    python -m scripts.backup_db --tag manual           # نسخة يدوية (تبقى للأبد)

Windows Task Scheduler:
    استخدم setup_windows_scheduler.py لإعداد الجدولة تلقائياً

ينتج: backups/playrush_<tag>_YYYYMMDD_HHMMSS.sql.gz
"""
import os
import sys
import subprocess
import gzip
import argparse
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

# ==========================================
# إعدادات
# ==========================================
BACKUP_DIR = BACKEND_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

# سياسة الاستبقاء (كم نسخة نحتفظ لكل tag)
RETENTION = {
    "hourly":  24,    # آخر 24 ساعة
    "daily":   14,    # أسبوعين
    "weekly":  12,    # 3 أشهر
    "manual":  999,   # لا تُحذف تلقائياً
}


def parse_database_url(url: str) -> dict:
    """تحلل DATABASE_URL إلى مكوناتها."""
    if "://" not in url:
        raise ValueError("DATABASE_URL ليس بالصيغة الصحيحة")
    _, rest = url.split("://", 1)
    if "@" not in rest:
        raise ValueError("DATABASE_URL لا يحوي auth")

    auth, host_db = rest.split("@", 1)
    user, password = auth.split(":", 1) if ":" in auth else (auth, "")
    host_port, dbname = host_db.split("/", 1) if "/" in host_db else (host_db, "")
    host, port = host_port.split(":", 1) if ":" in host_port else (host_port, "5432")

    if "?" in dbname:
        dbname = dbname.split("?")[0]

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "dbname": dbname,
    }


def find_pg_dump() -> str:
    """يلقى pg_dump في PATH أو في مسارات Windows الشائعة."""
    # 1. جرب من PATH
    for cmd in ["pg_dump", "pg_dump.exe"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, check=True, timeout=5)
            return cmd
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # 2. جرب مسارات Windows الشائعة
    if sys.platform == "win32":
        for version in ["17", "16", "15", "14", "13"]:
            candidate = Path(f"C:/Program Files/PostgreSQL/{version}/bin/pg_dump.exe")
            if candidate.exists():
                return str(candidate)

    raise RuntimeError(
        "❌ pg_dump غير موجود.\n"
        "Windows: أضف C:\\Program Files\\PostgreSQL\\<version>\\bin إلى PATH\n"
        "Linux: sudo apt install postgresql-client"
    )


def make_backup(tag: str, custom_db_url: str = None) -> Path:
    """ينشئ backup ويرجع المسار."""
    db_url = custom_db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL غير مضبوط في .env")

    parts = parse_database_url(db_url)
    pg_dump = find_pg_dump()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = BACKUP_DIR / f"playrush_{tag}_{timestamp}.sql.gz"

    cmd = [
        pg_dump,
        "-h", parts["host"],
        "-p", parts["port"],
        "-U", parts["user"],
        "-d", parts["dbname"],
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "-F", "p",
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]

    print(f"[backup] DB: {parts['host']}:{parts['port']}/{parts['dbname']}")
    print(f"[backup] target: {output_file.name}")

    try:
        with gzip.open(output_file, "wb") as f_out:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
                timeout=600,  # 10 دقائق timeout
            )
            f_out.write(proc.stdout)
    except subprocess.TimeoutExpired:
        output_file.unlink(missing_ok=True)
        raise RuntimeError("❌ pg_dump تجاوز 10 دقائق")
    except subprocess.CalledProcessError as e:
        output_file.unlink(missing_ok=True)
        err = e.stderr.decode("utf-8", errors="replace")[:500] if e.stderr else "(لا توجد رسالة خطأ)"
        raise RuntimeError(f"❌ فشل pg_dump:\n{err}")

    size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"[backup] ✅ تم: {size_mb:.2f} MB")
    return output_file


def cleanup_old(tag: str):
    """يحذف backups أقدم من الحد المسموح."""
    keep = RETENTION.get(tag, 24)
    files = sorted(
        BACKUP_DIR.glob(f"playrush_{tag}_*.sql.gz"),
        key=os.path.getmtime,
        reverse=True
    )

    if len(files) <= keep:
        return

    deleted = 0
    for f in files[keep:]:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            print(f"[cleanup] ⚠️ فشل حذف {f.name}: {e}")

    if deleted:
        print(f"[cleanup] 🗑️  حذفت {deleted} نسخة قديمة (احتفظت بـ {keep})")


def verify_backup(path: Path) -> bool:
    """يتأكد إن الـ backup يحتوي على CREATE TABLE — تأكيد سلامة."""
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            content_start = f.read(20000)  # أول 20KB
            if "CREATE TABLE" in content_start.upper():
                print(f"[verify] ✅ صالح (يحتوي CREATE TABLE)")
                return True
            print(f"[verify] ⚠️  لا يحتوي CREATE TABLE — قد يكون فاضي!")
            return False
    except Exception as e:
        print(f"[verify] ❌ فشل: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="PostgreSQL backup tool")
    parser.add_argument("--tag", default="hourly",
                        choices=list(RETENTION.keys()),
                        help="نوع الـ backup (يحدد retention)")
    parser.add_argument("--db-url", help="DATABASE_URL مخصص (override)")
    parser.add_argument("--no-verify", action="store_true",
                        help="تخطي التحقق من الـ backup")
    args = parser.parse_args()

    print(f"[backup] === Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"[backup] tag: {args.tag}")

    try:
        path = make_backup(tag=args.tag, custom_db_url=args.db_url)
        if not args.no_verify:
            verify_backup(path)
        cleanup_old(args.tag)
        print(f"[backup] === Completed successfully ===")
    except Exception as e:
        print(f"[backup] ❌ FAILED: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
