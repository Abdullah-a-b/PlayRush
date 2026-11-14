"""اختيار خلايا من أربع سياسات صغيرة مدرّبة، بلا خدمة أو مكتبة تعلم آلي."""
import math
import random
from collections import deque

from .learned_policy import load_policy, network

_NEIGHBORS = tuple(tuple(
    rr * 5 + cc
    for dr, dc in ([(-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1)]
                   if (i // 5) % 2 == 0 else
                   [(-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0)])
    for rr, cc in [(i // 5 + dr, i % 5 + dc)]
    if 0 <= rr < 5 and 0 <= cc < 5
) for i in range(25))
_BITS = tuple(sum(1 << j for j in row) for row in _NEIGHBORS)
_AXIS = (tuple(i // 5 for i in range(25)), tuple(i % 5 for i in range(25)))
_STARTS = tuple(tuple(i for i in range(25) if axis[i] == 0) for axis in _AXIS)


def _distance(mine, enemy, side):
    """أقصر مسار بكلفة صفر لخليتنا وواحد للخالية؛ الجيران محسوبون مرة واحدة."""
    distances = [26] * 25
    queue = deque()
    for idx in _STARTS[side]:
        if enemy & (1 << idx):
            continue
        cost = int(not mine & (1 << idx))
        distances[idx] = cost
        (queue.append if cost else queue.appendleft)(idx)
    while queue:
        idx = queue.popleft()
        cost = distances[idx]
        if _AXIS[side][idx] == 4:
            return cost
        for neighbor in _NEIGHBORS[idx]:
            if enemy & (1 << neighbor):
                continue
            extra = int(not mine & (1 << neighbor))
            if cost + extra < distances[neighbor]:
                distances[neighbor] = cost + extra
                (queue.append if extra else queue.appendleft)(neighbor)
    return 26


def candidates(board, color):
    """خصائص اللوحة الظاهرة فقط؛ لا أسئلة ولا إجابات مخفية ضمن التدريب."""
    # الاستيراد مؤجل لتجنب دورة الاستيراد مع المسار الاحتياطي.
    from . import solo_bot as bot
    if len(board) != 25 or color not in ("green", "orange"):
        return [], [], []
    free = bot._empty_cells(board)
    colors = [None if i in free else h["color"] for i, h in enumerate(board)]
    other = "orange" if color == "green" else "green"
    clean_board = [{"color": owner} for owner in colors]
    side = int(color == "orange")
    mine = sum(1 << i for i, owner in enumerate(colors) if owner == color)
    enemy = sum(1 << i for i, owner in enumerate(colors) if owner == other)
    own_before = _distance(mine, enemy, side)
    opp_before = _distance(enemy, mine, 1-side)
    own_count, opp_count = colors.count(color), colors.count(other)
    rows, tags = [], []
    for idx in free:
        bit = 1 << idx
        own_after = _distance(mine | bit, enemy, side)
        blocked = _distance(enemy, mine | bit, 1-side)
        own_lost = _distance(mine, enemy | bit, side)
        opp_after = _distance(enemy | bit, mine, 1-side)
        progress = max(0, own_before - own_after)
        block = min(3, blocked - opp_before)
        risk = opp_before - opp_after
        loss = min(3, own_lost - own_before)
        own_n = (mine & _BITS[idx]).bit_count()
        opp_n = (enemy & _BITS[idx]).bit_count()
        win, threat = own_after == 0, opp_after == 0
        safe = progress > 0 and risk == 0 and loss == 0 and opp_n == 0
        goal = bot._goal_distance(idx, color, clean_board)
        opponent_goal = bot._goal_distance(idx, other, clean_board)
        medium = goal + 8 * (own_n >= 2) + .5 * opponent_goal
        advanced = 4 * progress + block - 3 * risk - loss + int(own_n > 0) + .65 * safe
        axis, cross = divmod(idx, 5) if color == "green" else divmod(idx, 5)[::-1]
        rows.append([
            own_before/26, opp_before/26, progress, block/3, risk, loss/3,
            own_n/6, opp_n/6, float(win), float(threat), goal/30,
            opponent_goal/30, medium/40, advanced/10, float(safe),
            abs(axis-2)/2, abs(cross-2)/2, (own_count+opp_count)/25,
            own_count/25, opp_count/25,
        ])
        tags.append({"win": win, "block": threat, "safe_remote": safe, "score": advanced})
    return free, rows, tags


def probabilities(board, color, level):
    """توزيع كامل للمستوى؛ لا يُضرب مجددًا في احتمال استراتيجية الخوارزمية."""
    data = load_policy("strategy_policy_v5.json")
    if data is None:
        return None
    try:
        if data.get("architecture") != [20, 32, 1]:
            return None
        weights = data["levels"][level]["weights"]
        free, rows, tags = candidates(board, color)
        if not free:
            return None
        logits = [network(row, weights)[0] for row in rows]
        support = list(range(len(free)))
        if level == "expert":
            # لا يضيع فوزًا مباشرًا أو صدًا لازمًا بسبب تقريب الشبكة.
            wins = [i for i, tag in enumerate(tags) if tag["win"]]
            blocks = [i for i, tag in enumerate(tags) if tag["block"]]
            if wins or blocks:
                support = wins or blocks
            else:
                # هامش ضيق يحمي من الخطأ الكبير دون تحويل التوزيع إلى argmax.
                best = max(tag["score"] for tag in tags)
                support = [i for i, tag in enumerate(tags) if tag["score"] >= best - .5]
        peak = max(logits[i] for i in support)
        scores = [math.exp(logits[i] - peak) if i in support else 0.0 for i in range(len(free))]
        total = sum(scores)
        if total <= 0 or not math.isfinite(total):
            return None
        return [(idx, score / total) for idx, score in zip(free, scores)]
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, AttributeError):
        return None


def choose(board, color, level, preferred=None):
    """الاقتراح الخارجي لا يرفع قوة المستوى؛ السياسة الكاملة هي صاحبة القرار."""
    distribution = probabilities(board, color, level)
    if not distribution:
        return None
    indices, weights = zip(*distribution)
    return random.choices(indices, weights=weights, k=1)[0]
