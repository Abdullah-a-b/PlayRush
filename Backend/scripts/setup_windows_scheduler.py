"""
🪟 إعداد Windows Task Scheduler تلقائياً للـ backups.

الاستخدام:
    cd Backend
    python -m scripts.setup_windows_scheduler           # تثبيت الـ tasks
    python -m scripts.setup_windows_scheduler --remove  # إزالة الـ tasks
    python -m scripts.setup_windows_scheduler --status  # فحص الحالة

ينشئ مهمتين في Task Scheduler:
    1. PlayRush_Backup_Hourly  — كل ساعة
    2. PlayRush_Backup_Daily   — كل يوم 3 صباحاً
"""
import sys
import os
import subprocess
import argparse
from pathlib import Path

# نتأكد إننا على Windows
if sys.platform != "win32":
    print("❌ هذا السكريبت لـ Windows فقط.")
    print("   على Linux، استخدم cron أو systemd timers.")
    sys.exit(1)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable  # نستخدم نفس Python الحالي

# ✅ نستخدم pythonw.exe (بدون نافذة console) لو موجود
PYTHON_NO_WINDOW = Path(PYTHON_EXE).parent / "pythonw.exe"
if PYTHON_NO_WINDOW.exists():
    PYTHON_FOR_TASK = str(PYTHON_NO_WINDOW)
else:
    PYTHON_FOR_TASK = PYTHON_EXE

TASKS = [
    {
        "name": "PlayRush_Backup_Hourly",
        "schedule": "HOURLY",
        "modifier": "1",       # كل ساعة
        "start_time": "00:05", # دقيقة 5 من كل ساعة
        "tag": "hourly",
        "description": "PlayRush DB hourly backup",
    },
    {
        "name": "PlayRush_Backup_Daily",
        "schedule": "DAILY",
        "modifier": "1",       # كل يوم
        "start_time": "03:00", # الساعة 3 صباحاً
        "tag": "daily",
        "description": "PlayRush DB daily snapshot",
    },
]


def run_schtasks(args: list, capture: bool = True) -> tuple:
    """يشغّل schtasks ويرجع (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["schtasks"] + args,
            capture_output=capture,
            text=True,
            encoding="cp1256",  # Windows Arabic encoding
            errors="replace",
            timeout=30,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except FileNotFoundError:
        return 1, "", "❌ schtasks غير موجود (هل Windows فعلاً؟)"
    except Exception as e:
        return 1, "", str(e)


def task_exists(name: str) -> bool:
    rc, _, _ = run_schtasks(["/Query", "/TN", name])
    return rc == 0


def create_task(task: dict):
    name = task["name"]
    tag = task["tag"]

    # الأمر اللي يُشغَّل
    # نستخدم pythonw.exe (بدون nafidha console) ونوجه stdout لـ log file
    log_file = BACKEND_DIR / "backups" / f"{tag}_log.txt"
    log_file.parent.mkdir(exist_ok=True)

    # cmd.exe مع redirect لـ log
    # ملاحظة: نستخدم cmd /c بدل ما نشغّل python مباشرة عشان نقدر نعمل redirect
    command = (
        f'cmd /c '
        f'""{PYTHON_EXE}" -m scripts.backup_db --tag {tag} '
        f'>> "{log_file}" 2>&1"'
    )

    # نُحذف القديمة إن وُجدت
    if task_exists(name):
        print(f"  ⏭️  {name} موجودة — أحذفها وأعيد إنشاءها")
        run_schtasks(["/Delete", "/TN", name, "/F"])

    args = [
        "/Create",
        "/TN", name,
        "/TR", command,
        "/SC", task["schedule"],
        "/MO", task["modifier"],
        "/ST", task["start_time"],
        "/RL", "LIMITED",  # يجري بصلاحيات user عادي
        "/F",  # force overwrite
        "/SD", "01/01/2024",  # start date (في الماضي للتشغيل الفوري)
    ]

    # working directory — نستخدم /XML بدلاً لكن schtasks /Create لا يدعم cwd مباشرة
    # نخلي cmd /c "cd /d ... && python ..."
    full_command = (
        f'cmd /c "cd /d "{BACKEND_DIR}" && '
        f'"{PYTHON_EXE}" -m scripts.backup_db --tag {tag} '
        f'>> "{log_file}" 2>&1"'
    )
    args = [
        "/Create",
        "/TN", name,
        "/TR", full_command,
        "/SC", task["schedule"],
        "/MO", task["modifier"],
        "/ST", task["start_time"],
        "/RL", "LIMITED",
        "/F",
    ]

    rc, stdout, stderr = run_schtasks(args)
    if rc == 0:
        print(f"  ✅ {name} — أُنشئت")
        print(f"     • Schedule: {task['schedule']} (every {task['modifier']})")
        print(f"     • Start: {task['start_time']}")
        print(f"     • Log: {log_file}")
    else:
        print(f"  ❌ {name} — فشل")
        print(f"     {stderr or stdout}")


def remove_task(name: str):
    if not task_exists(name):
        print(f"  ⏭️  {name} غير موجودة")
        return
    rc, _, stderr = run_schtasks(["/Delete", "/TN", name, "/F"])
    if rc == 0:
        print(f"  ✅ {name} — حُذفت")
    else:
        print(f"  ❌ فشل حذف {name}: {stderr}")


def show_status():
    print("\n📋 حالة المهام:\n")
    for task in TASKS:
        name = task["name"]
        if task_exists(name):
            rc, stdout, _ = run_schtasks(["/Query", "/TN", name, "/V", "/FO", "LIST"])
            if rc == 0:
                # نطبع المعلومات المهمة فقط
                print(f"✅ {name}")
                for line in stdout.split("\n"):
                    line_lower = line.lower().strip()
                    if any(k in line_lower for k in ["next run", "last run", "status", "last result"]):
                        print(f"   {line.strip()}")
                print()
            else:
                print(f"⚠️  {name} موجودة لكن فشل الفحص\n")
        else:
            print(f"❌ {name} — غير مثبتة\n")

    # عرض الـ logs الأخيرة
    print("\n📜 آخر backups:\n")
    log_dir = BACKEND_DIR / "backups"
    if log_dir.exists():
        backups = sorted(log_dir.glob("playrush_*.sql.gz"),
                        key=os.path.getmtime, reverse=True)[:5]
        if backups:
            for b in backups:
                from datetime import datetime
                mtime = datetime.fromtimestamp(b.stat().st_mtime)
                size_mb = b.stat().st_size / (1024 * 1024)
                print(f"   • {b.name:<50} {size_mb:>6.2f} MB  ({mtime.strftime('%Y-%m-%d %H:%M')})")
        else:
            print("   (لا يوجد backups بعد)")


def main():
    parser = argparse.ArgumentParser(description="إدارة Windows Task Scheduler للـ backups")
    parser.add_argument("--remove", action="store_true",
                       help="إزالة كل المهام")
    parser.add_argument("--status", action="store_true",
                       help="عرض حالة المهام")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.remove:
        print("🗑️  إزالة مهام Backup من Task Scheduler...\n")
        for task in TASKS:
            remove_task(task["name"])
        print("\n✅ تم")
        return

    # تثبيت
    print("🪟 إعداد Windows Task Scheduler...\n")
    print(f"📁 Backend: {BACKEND_DIR}")
    print(f"🐍 Python: {PYTHON_EXE}\n")

    # نتأكد من backup_db.py موجود
    backup_script = BACKEND_DIR / "scripts" / "backup_db.py"
    if not backup_script.exists():
        print(f"❌ {backup_script} غير موجود!")
        sys.exit(1)

    print("📋 إنشاء المهام:\n")
    for task in TASKS:
        create_task(task)

    print("\n🎉 تم!")
    print("\n📝 خطوات تالية:")
    print("   1. اختبر backup يدوياً:")
    print("      python -m scripts.backup_db --tag manual")
    print("   2. تأكد من نجاح الـ tasks بعد ساعة:")
    print("      python -m scripts.setup_windows_scheduler --status")
    print("   3. الـ backups راح تظهر في:")
    print(f"      {BACKEND_DIR}/backups/")


if __name__ == "__main__":
    main()
