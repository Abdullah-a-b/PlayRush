"""مسارات المشروع المركزية.

كل ملف يحتاج الوصول إلى data/ أو scripts/ أو uploads/ يستورد من هنا
بدل بناء المسار بسلاسل dirname نسبية لموقعه — تلك تنكسر مع أي نقل ملفات.
"""
from pathlib import Path

# هذا الملف في app/core/ — الصعود مستويين يصل لجذر Backend
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BACKEND_ROOT / "data"
SCRIPTS_DIR = BACKEND_ROOT / "scripts"
UPLOADS_DIR = BACKEND_ROOT / "uploads"
