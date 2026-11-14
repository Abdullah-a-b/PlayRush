"""سياسات صغيرة مدرّبة محلياً؛ الاستدلال على السيرفر بلا Torch أو خدمة خارجية."""
from functools import lru_cache
import json
import logging
import math
from pathlib import Path


@lru_cache(maxsize=4)
def load_policy(name):
    try:
        data = json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("unsupported policy schema")
        return data
    except (OSError, ValueError, TypeError):
        logging.getLogger(__name__).warning("Huroof policy %s unavailable; using fallback", name)
        return None


def network(features, weights):
    """طبقتان صغيرتان بأوزان JSON؛ أي ملف غير صالح يعيدنا للخوارزمية."""
    w1, b1, w2, b2 = weights
    if (len(w1) != len(b1) or len(w2) != len(b2)
            or any(len(row) != len(features) for row in w1)
            or any(len(row) != len(b1) for row in w2)):
        raise ValueError("policy shape mismatch")
    hidden = [math.tanh(b + sum(w * x for w, x in zip(row, features)))
              for row, b in zip(w1, b1)]
    outputs = [b + sum(w * x for w, x in zip(row, hidden)) for row, b in zip(w2, b2)]
    if not all(math.isfinite(x) for x in outputs):
        raise ValueError("non-finite policy output")
    return outputs


def reaction_parameters(level, difficulty, words, attempt):
    data = load_policy("reaction_policy_v5.json")
    if data is None:
        return None
    try:
        features = [float(difficulty == label) for label in ("easy", "medium", "hard", "rare")]
        features += [max(0, min(40, words)) / 40, float(attempt >= 2)]
        logits = network(features, data["levels"][level]["weights"])
        if len(logits) != 2:
            return None
        return tuple(1 / (1 + math.exp(-max(-40, min(40, x)))) for x in logits)
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
