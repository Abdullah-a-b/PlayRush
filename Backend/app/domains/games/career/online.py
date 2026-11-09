"""اختيار لاعب أونلاين وتسجيل آخر ظهور لكل طرف في معاملة واحدة."""
from collections import defaultdict
from datetime import datetime, timezone
import random

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.domains.games.models import CareerPlayer, CareerSeen
from app.domains.games.career.pilot import normalize_name


def pick_player_id(available_ids, histories):
    if not available_ids:
        return None

    def priority(pid):
        seen = histories.get(pid, ())
        return (bool(seen), max(seen, default=datetime.min), len(seen))

    best = min(map(priority, available_ids))
    return random.choice([pid for pid in available_ids if priority(pid) == best])


def reserve_player(db, used_ids, user_ids):
    user_ids = sorted(set(user_ids or ()) - {None})
    for uid in user_ids:
        db.execute(text("SELECT pg_advisory_xact_lock(:namespace, :uid)"),
                   {"namespace": 81241, "uid": uid})

    rows = db.query(CareerPlayer.id, CareerPlayer.wikidata_id, CareerPlayer.name,
                    CareerPlayer.active).order_by(CareerPlayer.id).all()
    identities = {row.id: row.wikidata_id or normalize_name(row.name) for row in rows}
    used = {identities.get(pid, pid) for pid in used_ids}
    available = {}
    for row in rows:
        identity = identities[row.id]
        if row.active and identity not in used:
            available.setdefault(identity, row.id)

    histories = defaultdict(dict)
    if available and user_ids:
        for pid, uid, seen_at in (db.query(CareerSeen.player_id, CareerSeen.user_id, CareerSeen.seen_at)
                                  .filter(CareerSeen.user_id.in_(user_ids)).all()):
            canonical = available.get(identities.get(pid))
            if canonical is not None and seen_at is not None:
                history = histories[canonical]
                history[uid] = max(history.get(uid, seen_at), seen_at)
    chosen = pick_player_id(list(available.values()), {pid: list(seen.values()) for pid, seen in histories.items()})
    if chosen is None:
        return None

    row = db.get(CareerPlayer, chosen)
    if user_ids:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        statement = insert(CareerSeen).values([
            {"user_id": uid, "player_id": chosen, "seen_at": now} for uid in user_ids
        ])
        db.execute(statement.on_conflict_do_update(
            index_elements=["user_id", "player_id"], set_={"seen_at": statement.excluded.seen_at}
        ))
    return row
