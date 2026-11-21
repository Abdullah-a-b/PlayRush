"""Difficulty policy for the list-game opponent."""
import random
import math
import json
from pathlib import Path

WEIGHTS = json.loads(Path(__file__).with_name("recall_weights.json").read_text("utf8"))

# Accuracy before the commonly recalled answers have been used, and response times.
LEVELS = {
    'beginner': (0.50, 4.8, 8.5),
    'medium': (0.69, 3.8, 7.7),
    'hard': (0.85, 2.9, 6.9),
    'expert': (0.95, 2.2, 5.9),
}


def recall_probability(difficulty, pressure):
    base, linear, quadratic = WEIGHTS[difficulty]
    return 1 / (1 + math.exp(-(base + linear * pressure + quadratic * pressure ** 2)))


def plan_turn(pool, used, difficulty, rng=random, *, distractors=()):
    _, earliest, latest = LEVELS[difficulty]
    remaining = [item['display'] for i, item in enumerate(pool) if i not in used]
    pressure = len(used) / max(1, len(pool))
    if remaining and rng.random() < recall_probability(difficulty, pressure):
        answer = rng.choice(remaining)
    else:
        roll = rng.random()
        if used and roll < .25 + .20 * pressure:
            answer = pool[rng.choice(sorted(used))]['display']
        elif distractors and roll < .75:
            answer = rng.choice(distractors)
        else:
            return 10, None
    return rng.uniform(earliest, latest), answer
