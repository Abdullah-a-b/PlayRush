"""Run from Backend with python -m scripts.review_shadow_play (read only)."""
from app.domains.games.models import ShadowOutcome
from app.infrastructure.database import SessionLocal, register_models


def main():
    register_models()
    with SessionLocal() as db:
        cases = db.query(ShadowOutcome).filter(ShadowOutcome.review_reason.isnot(None)).order_by(
            ShadowOutcome.settled_at.desc()).limit(100)
        for case in cases:
            print(case.settled_at, case.match_id, case.low_id, case.high_id, case.review_reason)


if __name__ == "__main__":
    main()
