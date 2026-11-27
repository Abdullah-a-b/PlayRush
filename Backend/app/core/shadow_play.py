"""Observe completed public matches. This module has no enforcement actions."""
from datetime import timedelta

from app.domains.games.models import ShadowOutcome


def review_reason(outcomes):
    # Chronological suffix only. Draws interrupt winner-based patterns.
    recent = outcomes[-5:]
    if len(recent) < 5 or any(winner is None for winner, _ in recent):
        return None
    winners = [winner for winner, _ in recent]
    concessions = sum(surrendered for _, surrendered in recent)
    if concessions >= 3 and len(set(winners)) == 1:
        return "five_same_winner_with_repeated_surrenders"
    if concessions >= 3 and all(a != b for a, b in zip(winners, winners[1:])):
        return "five_alternating_winners_with_repeated_surrenders"
    return None


def observe(db, match_id, low, high, now, winner, surrendered, mode):
    history = db.query(ShadowOutcome.winner_id, ShadowOutcome.surrendered).filter(
        ShadowOutcome.low_id == low, ShadowOutcome.high_id == high,
        ShadowOutcome.settled_at > now - timedelta(hours=6),
    ).order_by(ShadowOutcome.settled_at.desc(), ShadowOutcome.match_id.desc()).limit(4).all()
    reason = review_reason([*reversed(history), (winner, surrendered)])
    db.add(ShadowOutcome(match_id=match_id, low_id=low, high_id=high, settled_at=now,
                         winner_id=winner, surrendered=surrendered, game_mode=mode,
                         review_reason=reason))
