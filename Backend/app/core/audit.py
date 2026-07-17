"""
 Audit Logger — يسجّل كل الأحداث الأمنية الحرجة لمراجعة لاحقة.

يكتب في ملف منفصل (audit.log) مع تنسيق صارم.
يستخدم rotating file handler (لا ينفجر حجمه).
"""
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os

LOG_DIR = Path(os.environ.get("LOG_DIR", "logs"))
LOG_DIR.mkdir(exist_ok=True)

# ============================================================
# Audit logger — يسجّل في ملف منفصل
# ============================================================

audit_logger = logging.getLogger("playrush.audit")
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False  # لا ينسخ لـ root logger

if not audit_logger.handlers:
    handler = RotatingFileHandler(
        LOG_DIR / "audit.log",
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,             # احتفظ بـ 10 ملفات (500 MB total)
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        '%(asctime)s|%(levelname)s|%(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S'
    )
    handler.setFormatter(formatter)
    audit_logger.addHandler(handler)


# ============================================================
# الـ events اللي نسجلها
# ============================================================

def log_login(email: str, ip: str, success: bool, reason: str = ""):
    status = "SUCCESS" if success else "FAILED"
    audit_logger.info(f"LOGIN|{status}|email={email}|ip={ip}|reason={reason}")


def log_register(email: str, ip: str):
    audit_logger.info(f"REGISTER|email={email}|ip={ip}")


def log_password_change(email: str, ip: str):
    audit_logger.info(f"PASSWORD_CHANGE|email={email}|ip={ip}")


def log_email_change(old_email: str, new_email: str, ip: str):
    audit_logger.info(f"EMAIL_CHANGE|old={old_email}|new={new_email}|ip={ip}")


def log_account_deletion(email: str, ip: str):
    audit_logger.warning(f"ACCOUNT_DELETED|email={email}|ip={ip}")


def log_ban(email: str, ip: str, reason: str, ban_type: str = "permanent"):
    audit_logger.warning(f"BAN|type={ban_type}|email={email}|ip={ip}|reason={reason}")


def log_anticheat_violation(email: str, ip: str, reason: str, severity: int):
    audit_logger.warning(f"ANTICHEAT|email={email}|ip={ip}|severity={severity}|reason={reason}")


def log_rate_limit_hit(endpoint: str, ip: str, email: str = ""):
    audit_logger.info(f"RATE_LIMIT|endpoint={endpoint}|ip={ip}|email={email}")


def log_suspicious(category: str, details: str, ip: str = "", email: str = ""):
    """عام — لأي شيء غير عادي."""
    audit_logger.warning(f"SUSPICIOUS|category={category}|email={email}|ip={ip}|details={details}")
