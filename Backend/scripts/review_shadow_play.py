"""From Backend run python -m scripts.review_shadow_play. Read-only, UTC, last 24 hours."""
from datetime import datetime, timedelta, timezone

from app.core.shadow_network import network_cases
from app.domains.games.models import ShadowOutcome
from app.infrastructure.database import SessionLocal, register_models


def main():
    register_models()
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        cases = db.query(ShadowOutcome).filter(ShadowOutcome.review_reason.isnot(None)).order_by(
            ShadowOutcome.settled_at.desc()).limit(100)
        for case in cases:
            print(case.settled_at, case.match_id, case.low_id, case.high_id, case.review_reason)
        rows = db.query(ShadowOutcome).filter(
            ShadowOutcome.settled_at >= end - timedelta(days=1), ShadowOutcome.settled_at < end
        ).yield_per(500)
        for reason, accounts, matches in network_cases(rows):
            print(reason, "accounts", accounts, "matches", matches)


if __name__ == "__main__":
    main()
