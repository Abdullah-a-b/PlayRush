"""Inference for the level-specific synthetic recall models."""
import json
import math
from pathlib import Path

_WEIGHTS = json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf8'))


def calibrated(game, level, prior):
    if prior <= 0 or prior >= 1:
        return prior
    weights = _WEIGHTS[game]
    bias, slope = weights.get(level, weights['medium'])
    return 1 / (1 + math.exp(-bias - slope * math.log(prior / (1-prior))))
