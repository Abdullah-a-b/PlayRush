"""Difficulty policy for the list-game opponent."""
import random

# Accuracy before the commonly recalled answers have been used, and response times.
LEVELS = {
    'beginner': (0.50, 4.8, 8.5),
    'medium': (0.69, 3.8, 7.7),
    'hard': (0.85, 2.9, 6.9),
    'expert': (0.95, 2.2, 5.9),
}


def plan_turn(pool, used, difficulty, rng=random):
    accuracy, earliest, latest = LEVELS[difficulty]
    remaining = [index for index in range(len(pool)) if index not in used]
    recall_pressure = len(used) / max(1, len(pool))
    chance = accuracy * (1 - recall_pressure * (1 - accuracy))
    if not remaining or rng.random() >= chance:
        return 10, None
    delay = rng.uniform(earliest, latest)
    return delay, rng.choice(remaining)
