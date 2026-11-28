"""Neutral cancellation and aid reimbursement for public matches with expired owners."""
import asyncio
import os
from datetime import timedelta

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from app.core.cluster import WORKER_ID
from app.domains.games.models import MatchHelpDebit, MatchSettlement, PublicMatchLease
from app.infrastructure.database import SessionLocal

GRACE = max(60, int(os.environ.get("MATCH_OWNER_GRACE_SEC", "150")))


def owns_live_lease(db, row, states=("active",)):
    if row.owner != WORKER_ID or row.status not in states:
        return False
    now = db.query(func.timezone("UTC", func.clock_timestamp())).scalar()
    return row.heartbeat > now - timedelta(seconds=GRACE)


def register(room, mid, reserved=False):
    a, b = room["players"]
    with SessionLocal.begin() as db:
        db.execute(insert(PublicMatchLease).values(
            match_id=mid, room_code=room["code"], first_uid=a["user_id"], second_uid=b["user_id"],
            owner=WORKER_ID, status="reserved" if reserved else "active", heartbeat=func.timezone("UTC", func.now())
        ).on_conflict_do_nothing(index_elements=["match_id"]))
        row = db.get(PublicMatchLease, mid, with_for_update=True)
        if not owns_live_lease(db, row, ("reserved", "active")):
            raise RuntimeError("match owner expired")
        if not reserved:
            row.status = "active"
            row.heartbeat = func.timezone("UTC", func.now())


def maintain(active_ids):
    cancelled = []
    with SessionLocal.begin() as db:
        now = db.query(func.timezone("UTC", func.now())).scalar()
        cutoff = now - timedelta(seconds=GRACE)
        if active_ids:
            db.query(PublicMatchLease).filter(PublicMatchLease.owner == WORKER_ID,
                PublicMatchLease.match_id.in_(active_ids), PublicMatchLease.status == "active",
                PublicMatchLease.heartbeat > cutoff).update({"heartbeat": now}, synchronize_session=False)
        stale = db.query(PublicMatchLease).filter(PublicMatchLease.status.in_(("reserved","active")),
            PublicMatchLease.heartbeat <= cutoff).order_by(PublicMatchLease.heartbeat).limit(50).with_for_update(skip_locked=True)
        for row in stale:
            if db.get(MatchSettlement, row.match_id):
                row.status = "settled"
                continue
            row.status = "cancelled"
            for debit in db.query(MatchHelpDebit).filter_by(match_id=row.match_id).order_by(
                    MatchHelpDebit.user_id, MatchHelpDebit.help_id):
                db.execute(text("""INSERT INTO player_help_inventory(user_id,help_id,quantity)
                    VALUES(:uid,:hid,1) ON CONFLICT(user_id,help_id) DO UPDATE SET
                    quantity=player_help_inventory.quantity+1"""), {"uid":debit.user_id,"hid":debit.help_id})
            cancelled.append((row.room_code, row.first_uid, row.second_uid))
    return cancelled


def last_result(code, uid):
    with SessionLocal() as db:
        row = db.query(PublicMatchLease).filter(PublicMatchLease.room_code == code,
            (PublicMatchLease.first_uid == uid) | (PublicMatchLease.second_uid == uid)
        ).order_by(PublicMatchLease.heartbeat.desc()).first()
        if not row or row.status in ("active","reserved"):
            return {}
        if row.status == "cancelled":
            return {"status": "cancelled"}
        return {"status": "settled", "result": "draw" if row.winner_id is None else
                "win" if row.winner_id == uid else "loss"}


async def recovery_loop(sio):
    from app.domains.games.core_manager import rooms
    from app.infrastructure.redis_client import get_redis
    while True:
        await asyncio.sleep(20)
        mids = [r["settlement_id"] for r in list(rooms.values()) if r.get("settlement_id")
                and r.get("type") == "public" and r.get("state") != "finished"]
        for code, a, b in await asyncio.to_thread(maintain, mids):
            await sio.emit("match_unavailable", {"status":"cancelled"}, room=code)
            client = get_redis()
            if client is not None:
                for uid in (a,b):
                    await client.eval("if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end",
                                      1, "pr:mm_active:"+str(uid), code)
