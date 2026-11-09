"""نشر المسيرات المراجعة للفردي والأونلاين من المصدر نفسه."""
import json

from sqlalchemy import text

from app.core.import_support import content_backup
from app.domains.games.career.pilot import ROSTER_BY_QID, normalize_name
from app.domains.games.models import CareerPlayer
from app.infrastructure.database import SessionLocal


def sync_reviewed_roster():
    with SessionLocal() as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(:namespace, :key)"),
                   {"namespace": 81242, "key": 1})
        rows = db.query(CareerPlayer).order_by(CareerPlayer.id).all()
        by_qid = {}
        manual = {}
        for row in rows:
            if row.wikidata_id:
                by_qid.setdefault(row.wikidata_id, []).append(row)
            else:
                manual.setdefault(normalize_name(row.name), []).append(row)

        changes = []
        for qid, player in ROSTER_BY_QID.items():
            payload = {key: player[key] for key in ("name", "status", "nationality", "era", "position")}
            payload.update(
                wikidata_id=qid, active=True, difficulty=player["recognition"],
                clubs=json.dumps(player["clubs"], ensure_ascii=False),
                accepted_answers=json.dumps(player["accepted_answers"], ensure_ascii=False),
            )
            candidates = by_qid.get(qid, []) + manual.get(normalize_name(player["name"]), [])
            row = min(candidates, key=lambda item: item.id, default=None)
            if row is None or any(getattr(row, key) != value for key, value in payload.items()):
                changes.append((row, payload))
            for duplicate in candidates:
                if duplicate is not row and (duplicate.active or duplicate.wikidata_id != qid):
                    changes.append((duplicate, {"active": False, "wikidata_id": qid}))

        if changes:
            fields = ("id", "wikidata_id", "name", "status", "clubs", "accepted_answers",
                      "difficulty", "active", "era", "position", "nationality")
            content_backup("career_reviewed_roster", [
                {key: getattr(row, key) for key in fields} for row in rows
            ])
            for row, payload in changes:
                if row is None:
                    db.add(CareerPlayer(**payload))
                else:
                    for key, value in payload.items():
                        setattr(row, key, value)
        return {"reviewed": len(ROSTER_BY_QID), "changed": len(changes)}
