"""Pin migrated quiz content to its exact wording until individually reviewed."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("ranked_content_v1.json")


def fingerprint(row):
    fields = ("id", "q", "a", "accepted", "answers", "diff", "cat")
    payload = json.dumps([row.get(k) for k in fields], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


@lru_cache(maxsize=1)
def _manifest(stamp):
    return json.loads(FILE.read_text(encoding="utf8"))


def eligible(row, mode):
    if row.get("active") is False or row.get("ranked_approved") is False:
        return False
    digest = fingerprint(row)
    if (row.get("ranked_approved") is True and row.get("reviewed_hash") == digest
            and row.get("reviewed_at") and row.get("source")):
        return True
    return _manifest(FILE.stat().st_mtime_ns)[mode].get(row["id"]) == digest
