"""مسارات المشروع المركزية.

كل ملف يحتاج الوصول إلى data/ أو scripts/ أو uploads/ يستورد من هنا
بدل بناء المسار بسلاسل dirname نسبية لموقعه — تلك تنكسر مع أي نقل ملفات.
"""
from pathlib import Path
import os
import time
from app.core.import_support import atomic_json, read_json, import_lock

# هذا الملف في app/core/ — الصعود مستويين يصل لجذر Backend
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

SEED_DATA_DIR = BACKEND_ROOT / "data"
# Azure يفك التطبيق داخل /tmp؛ المحتوى المتولد وحالة الاستيراد يبقيان في /home.
_default_data = Path("/home/playrush/data") if os.environ.get("WEBSITE_INSTANCE_ID") else SEED_DATA_DIR
DATA_DIR = Path(os.environ.get("PLAYRUSH_DATA_DIR", str(_default_data)))
if DATA_DIR != SEED_DATA_DIR:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for seed in SEED_DATA_DIR.glob("*.json"):
        if seed.name.endswith("_import_state.json"):
            continue
        target = DATA_DIR / seed.name
        # تهيئة ذرية تحت قفل؛ لا يستطيع عامل ثان قراءة نصف ملف.
        if target.exists():
            continue
        for attempt in range(300):
            with import_lock(target) as acquired:
                if acquired:
                    if not target.exists():
                        atomic_json(target, read_json(seed))
                    break
            time.sleep(.1)
        else:
            raise RuntimeError("تعذر تهيئة محتوى الألعاب الدائم")
SCRIPTS_DIR = BACKEND_ROOT / "scripts"
UPLOADS_DIR = BACKEND_ROOT / "uploads"
