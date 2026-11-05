"""حفظ آمن، هوية ثابتة، ومراقبة مشتركة لاستيراد محتوى الألعاب فقط."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import unicodedata


def canonical(text):
    text = unicodedata.normalize("NFKC", str(text or "")).strip()
    text = re.sub(r"[\u064b-\u065f\u0670\u0640]", "", text)
    text = text.translate(str.maketrans("أإآٱى", "ااااي"))
    return " ".join(text.casefold().split())


def stable_id(kind, *parts):
    raw = "|".join(str(p) for p in parts)
    return "wd_" + kind + "_" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default if default is not None else {}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # تحقق من قابلية التسلسل قبل لمس الملف الحالي.
    encoded = json.dumps(data, ensure_ascii=False, indent=2)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        if path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".previous"))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def import_lock(path):
    """قفل نظام التشغيل؛ يتحرر تلقائياً عند توقف العامل ولا يعتمد مهلة تخمينية."""
    path = Path(str(path) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            if f.tell() == 0:
                f.write(b"0"); f.flush()
            f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1); locked = True
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB); locked = True
            except BlockingIOError:
                pass
        yield locked
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def positive_days(name, default=7):
    try:
        return max(.5, float(os.getenv(name, str(default)))) * 86400
    except (TypeError, ValueError):
        return default * 86400


def record_result(state, result, now=None):
    now = time.time() if now is None else now
    state["schema_version"] = 2
    state["last_attempt"] = now
    state["last_result"] = result
    if result.get("status", "success") == "success":
        state["last_run"] = now
        state.pop("retry_after", None)
    else:
        pending = [s["retry_after"] for s in state.get("sources", {}).values() if s.get("retry_after")]
        state["retry_after"] = min(pending) if pending else now + 3600
    return state


def due(state, interval, now=None):
    now = time.time() if now is None else now
    if state.get("retry_after"):
        return now >= state["retry_after"]
    return now - state.get("last_run", 0) >= interval


def sparql_rows(query, headers=None, timeout=45):
    import requests
    for attempt in range(3):
        try:
            response = requests.get("https://query.wikidata.org/sparql", params={"query": query, "format": "json"}, headers=headers, timeout=timeout)
            if response.status_code in (429, 500, 502, 503, 504):
                if attempt == 2:
                    response.raise_for_status()
                wait = response.headers.get("Retry-After", "")
                time.sleep(min(30, float(wait) if wait.isdigit() else 2 ** attempt * 3))
                continue
            response.raise_for_status()
            rows = response.json()["results"]["bindings"]
            if not isinstance(rows, list):
                raise ValueError("صيغة نتائج المصدر غير صالحة")
            return rows
        except (requests.RequestException, ValueError, KeyError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("تعذر جلب المصدر")


def content_backup(name, rows):
    """نسخة محتوى اللعبة فقط؛ لا مستخدمين أو جلسات أو مفاتيح."""
    from app.core.paths import DATA_DIR
    import datetime
    import uuid
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = DATA_DIR / "backups" / f"{name}_{stamp}_{uuid.uuid4().hex[:8]}.json"
    atomic_json(path, {"kind": name, "created_at": stamp, "rows": rows})
    return path


def unambiguous_questions(questions, text_key="q", answer_key="a"):
    """السؤال النصي نفسه لا يحمل إجابتين متعارضتين، حتى بين كيانين مختلفين."""
    groups = {}
    for q in questions:
        groups.setdefault(canonical(q[text_key]), []).append(q)
    out = []
    for key, rows in sorted(groups.items()):
        if len({canonical(q[answer_key]) for q in rows}) == 1:
            out.append(sorted(rows, key=lambda q: q.get("source_id", q.get("id", "")))[0])
    return out
