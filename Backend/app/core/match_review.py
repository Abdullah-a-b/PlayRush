"""Background-only review of public results. No account enforcement."""
import asyncio
import json
import logging
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from app.core.shadow_network import network_cases
from app.domains.games.models import MatchReview, ShadowOutcome
from app.infrastructure.database import SessionLocal

log = logging.getLogger(__name__)
LABELS = {"ordinary", "insufficient", "review"}


def classify_batch(features):
    from app.infrastructure.gemini_model import load_gemini_model
    model = load_gemini_model()
    if model is None:
        return None
    prompt = ("Classify anonymized quiz match summaries for human fair-play review. "
              "Index corresponds to position in the list. Return only a JSON array of labels "
              "in the same order: ordinary, insufficient, or review. "
              "Missing context or few opponents can explain repetition. A surrender alone is "
              "not collusion. Correlated signals are not independent.\n" + json.dumps(features))
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json",
                                      "temperature": 0}, request_options={"timeout": 12, "retry": None})
    labels = json.loads(response.text)
    if (isinstance(labels, list) and len(labels) == len(features)
            and all(isinstance(label, str) and label in LABELS for label in labels)):
        return labels
    return None


def run_batch():
    with SessionLocal.begin() as db:
        if not db.execute(text("SELECT pg_try_advisory_xact_lock(173280491)")).scalar():
            return
        rows = db.query(MatchReview, ShadowOutcome).join(
            ShadowOutcome, MatchReview.match_id == ShadowOutcome.match_id
        ).filter(MatchReview.status == "pending").order_by(ShadowOutcome.settled_at).limit(100).all()
        if not rows:
            return
        # Anchor to the selected batch so a backlog does not erase its evidence.
        window_end = rows[-1][1].settled_at
        history = db.query(ShadowOutcome).filter(
            ShadowOutcome.settled_at >= rows[0][1].settled_at - timedelta(days=1),
            ShadowOutcome.settled_at <= window_end).order_by(ShadowOutcome.settled_at)
        # Evaluate separate daily windows if the queue spans multiple days.
        outcomes = history.all()
        by_match = defaultdict(set)
        for day in sorted({o.settled_at.date() for _, o in rows}):
            cutoff = max(o.settled_at for _, o in rows if o.settled_at.date() == day)
            for reason, _, ids in network_cases(o for o in outcomes if cutoff-timedelta(days=1) <= o.settled_at <= cutoff):
                for mid in ids:
                    by_match[mid].add(reason)
        features = []
        ids = []
        for review, outcome in rows:
            signals = sorted(set(json.loads(review.signals)) | by_match[review.match_id])
            review.signals = json.dumps(signals)
            # A thin queue explains repeated opponents; retain the signal but lower
            # its priority unless there is independent cross-account evidence.
            if signals and (by_match[review.match_id] or (review.alternatives or 0) > 0):
                review.local_label = "review"
            elif signals or review.alternatives is None:
                review.local_label = "insufficient"
            else:
                review.local_label = "ordinary"
            review.status = "local"
            ids.append(review.match_id)
            features.append(dict(game=outcome.game_mode, alternatives=review.alternatives,
                                 surrender=outcome.surrendered, draw=outcome.winner_id is None, signals=signals))
    # Commit local decisions before any external request. No database locks during inference.
    try:
        labels = classify_batch(features)
    except Exception as exc:
        log.warning("AMACS classifier unavailable (%s)", type(exc).__name__)
        return
    if labels is not None:
        with SessionLocal.begin() as db:
            for mid, label in zip(ids, labels):
                db.query(MatchReview).filter_by(match_id=mid).update(dict(ai_label=label, status="gemini"))


async def review_loop():
    while True:
        await asyncio.sleep(300)
        await asyncio.to_thread(run_batch)
