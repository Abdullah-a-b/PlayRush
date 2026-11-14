"""Offline, four-policy distillation; synthetic boards, never human-labelled videos.

No application/database import. Two CPU threads. Reproducible group holdouts.
"""
import argparse
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).resolve().parent
LEVELS = ("beginner", "medium", "hard", "expert")
COLORS = ("green", "orange")
FULL = (1 << 25) - 1
SOURCE = Path(__file__).resolve().parents[2] / "app/domains/games/huroof/solo_bot.py"
sys.path.insert(0, str(SOURCE.parents[4]))
from app.domains.games.huroof import solo_bot as baseline
N = tuple(tuple(baseline._hex_neighbors(*divmod(i, 5))) for i in range(25))
NB = tuple(sum(1 << j for j in row) for row in N)
AX = (tuple(i // 5 for i in range(25)), tuple(i % 5 for i in range(25)))
EDGES = tuple(tuple(sum(1 << i for i in range(25) if axis[i] == a) for a in (0, 4)) for axis in AX)
REFLECT = tuple((4 - i // 5) * 5 + i % 5 for i in range(25))
assert all({REFLECT[j] for j in N[i]} == set(N[REFLECT[i]]) for i in range(25))
FEATURES = ["own_distance", "opponent_distance", "own_progress", "blocking_gain", "opponent_gain_if_lost", "own_loss_if_lost", "own_neighbors", "opponent_neighbors", "immediate_win", "immediate_block", "goal_score", "opponent_goal_score", "medium_score", "advanced_score", "safe_remote", "axis_center_distance", "cross_axis_center_distance", "occupied_fraction", "own_fraction", "opponent_fraction"]

def cells(bits):
    while bits:
        bit = bits & -bits
        yield bit.bit_length() - 1
        bits ^= bit

def distance(mine, enemy, side):
    distances = [26] * 25
    queue = deque()
    for i in cells(EDGES[side][0] & ~enemy):
        cost = int(not (mine & (1 << i)))
        distances[i] = cost
        (queue.append if cost else queue.appendleft)(i)
    while queue:
        i = queue.popleft()
        cost = distances[i]
        if AX[side][i] == 4:
            return cost
        for j in N[i]:
            if enemy & (1 << j):
                continue
            extra = int(not (mine & (1 << j)))
            if cost + extra < distances[j]:
                distances[j] = cost + extra
                (queue.append if extra else queue.appendleft)(j)
    return 26

def board_for(g, o):
    return [{"color": "green" if g & (1 << i) else "orange" if o & (1 << i) else None} for i in range(25)]

def reflect(bits):
    return sum(1 << REFLECT[i] for i in cells(bits))

def key(g, o):
    return min((g, o), (reflect(g), reflect(o)))

def encode(g, o, side):
    mine, enemy = (g, o) if side == 0 else (o, g)
    a, b = distance(mine, enemy, side), distance(enemy, mine, 1-side)
    free = list(cells(FULL ^ (g | o)))
    rows = []
    board = board_for(g, o)
    wins, blocks, remote = [], [], []
    medium, advanced = [], []
    for i in free:
        bit = 1 << i
        after, block = distance(mine | bit, enemy, side), distance(enemy, mine | bit, 1-side)
        lost, risk = distance(mine, enemy | bit, side), distance(enemy | bit, mine, 1-side)
        progress, blocked = max(0, a-after), min(3, block-b)
        risk, loss = b-risk, min(3, lost-a)
        own_n, opp_n = (mine & NB[i]).bit_count(), (enemy & NB[i]).bit_count()
        win, threat = after == 0, distance(enemy | bit, mine, 1-side) == 0
        safe = progress > 0 and risk == 0 and loss == 0 and opp_n == 0
        goal = baseline._goal_distance(i, COLORS[side], board)
        other = baseline._goal_distance(i, COLORS[1-side], board)
        med = goal + 8 * (own_n >= 2) + .5 * other
        adv = 4*progress + blocked - 3*risk - loss + int(own_n > 0) + .65*safe
        rows.append([a/26, b/26, progress, blocked/3, risk, loss/3, own_n/6, opp_n/6, float(win), float(threat), goal/30, other/30, med/40, adv/10, float(safe), abs(AX[side][i]-2)/2, abs(AX[1-side][i]-2)/2, (g|o).bit_count()/25, mine.bit_count()/25, enemy.bit_count()/25])
        wins.append(win); blocks.append(threat); remote.append(safe)
        medium.append(med); advanced.append(adv)
    meta = np.array([wins, blocks, remote], dtype=np.bool_)
    targets = []
    for level in LEVELS:
        gate = baseline.get_difficulty(level)["strategy"]
        target = np.full(len(free), (1-gate)/len(free), dtype=np.float32)
        if any(wins):
            top = np.flatnonzero(wins)
        elif level in ("hard", "expert") and any(blocks):
            top = np.flatnonzero(blocks)
        else:
            scores = np.array(advanced if level in ("hard", "expert") else medium)
            top = np.flatnonzero(scores >= scores.max() - (0.49 if level == "medium" else 1e-5))
        target[top] += gate / len(top)
        targets.append(target)
    return np.asarray(rows, np.float32), np.asarray(targets), meta, free

def dataset(count, seed, used):
    rng = random.Random(seed)
    x = np.zeros((count, 25, len(FEATURES)), dtype=np.float32)
    y = np.zeros((count, 4, 25), dtype=np.float32)
    m = np.zeros((count, 25), dtype=np.bool_)
    meta = np.zeros((count, 3, 25), dtype=np.bool_)
    states = []
    while len(states) < count:
        # Random legal play histories, cut off before a terminal connection.
        g = o = 0
        order = rng.sample(range(25), rng.randint(2, 23))
        for i in order:
            ng, no = (g | (1 << i), o) if rng.getrandbits(1) else (g, o | (1 << i))
            if distance(ng, no, 0) == 0 or distance(no, ng, 1) == 0:
                break
            g, o = ng, no
        k = key(g, o)
        if k in used:
            continue
        used.add(k)
        side = rng.randrange(2)
        if rng.getrandbits(1):
            g, o = reflect(g), reflect(o)
        features, targets, tags, free = encode(g, o, side)
        j = len(states)
        x[j, :len(free)], y[j, :, :len(free)], meta[j, :, :len(free)] = features, targets, tags
        m[j, :len(free)] = True
        states.append((g, o, side))
        if len(states) % 2000 == 0:
            print("dataset", seed, len(states), flush=True)
    return x, y, m, meta, np.asarray(states, dtype=np.int64)

def measure(probs, target, masks, tags):
    win, block, remote = tags[:, 0], tags[:, 1], tags[:, 2]
    can_win = win.any(1)
    must_block = block.any(1) & ~can_win
    safe = remote.any(1) & ~can_win & ~block.any(1)
    output = {"mean_total_variation_from_design": float(np.abs(probs-target).sum(1).mean()/2), "illegal_mass": float(probs[~masks].sum()), "normalized_entropy": float((-(probs*np.log(np.maximum(probs, 1e-12))).sum(1) / np.log(masks.sum(1))).mean())}
    for name, subset, action in (("immediate_win", can_win, win), ("immediate_block", must_block, block), ("safe_remote", safe, remote)):
        output[name] = {"boards": int(subset.sum()), "candidate_probability": float((probs*action).sum(1)[subset].mean()), "design_probability": float((target*action).sum(1)[subset].mean())}
    return output

def main():
    started = time.monotonic()
    torch.set_num_threads(2)
    torch.manual_seed(357041)
    cache = HERE / "huroof_strategy_v5_dataset.npz"
    identity = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    cache_id = cache.with_suffix(".sha256")
    if not cache.exists() or not cache_id.exists() or cache_id.read_text() != identity:
        used = set()
        sets = {name: dataset(n, seed, used) for name, n, seed in (("train", 16000, 760211), ("validation", 2500, 17593), ("test", 4000, 830099))}
        np.savez_compressed(cache, **{f"{name}_{i}": a for name, ds in sets.items() for i, a in enumerate(ds)})
        cache_id.write_text(identity)
    else:
        raw = np.load(cache)
        sets = {name: tuple(raw[f"{name}_{i}"] for i in range(5)) for name in ("train", "validation", "test")}
    keys = [{key(int(g), int(o)) for g, o, _ in sets[name][4]} for name in ("train", "validation", "test")]
    assert not (keys[0]&keys[1] or keys[0]&keys[2] or keys[1]&keys[2])
    tx, ty, tm = (torch.from_numpy(a) for a in sets["train"][:3])
    vx, vy, vm = (torch.from_numpy(a) for a in sets["validation"][:3])
    ex, ey, em = (torch.from_numpy(a) for a in sets["test"][:3])
    report = {"version": 5, "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "data_source": "synthetic legal histories, distribution distillation; no video-derived decision or latency labels", "counts": {k: len(v[0]) for k,v in sets.items()}, "split": "board + valid top-bottom reflection canonical groups, globally disjoint", "architecture": [len(FEATURES), 32, 1], "features": FEATURES, "levels": {}}
    for index, level in enumerate(LEVELS):
        torch.manual_seed(23419+index)
        model = nn.Sequential(nn.Linear(len(FEATURES), 32), nn.Tanh(), nn.Linear(32, 1))
        optimizer = torch.optim.AdamW(model.parameters(), lr=.003, weight_decay=.0001)
        best = float("inf")
        best_weights = None
        for epoch in range(60):
            for batch in torch.randperm(len(tx)).split(256):
                logits = model(tx[batch]).squeeze(-1).masked_fill(~tm[batch], -1e9)
                loss = -(ty[batch, index] * logits.log_softmax(1)).sum(1).mean()
                optimizer.zero_grad(); loss.backward(); optimizer.step()
            with torch.no_grad():
                logits = model(vx).squeeze(-1).masked_fill(~vm, -1e9)
                val = float(-(vy[:, index] * logits.log_softmax(1)).sum(1).mean())
            if val < best:
                best = val
                best_weights = [p.detach().clone() for p in model.parameters()]
            if epoch % 20 == 0:
                print(level, "epoch", epoch, "validation_cross_entropy", round(val, 5), flush=True)
        with torch.no_grad():
            for parameter, weights in zip(model.parameters(), best_weights): parameter.copy_(weights)
            probs = model(ex).squeeze(-1).masked_fill(~em, -1e9).softmax(1).numpy()
        metrics = measure(probs, sets["test"][1][:, index], sets["test"][2], sets["test"][3])
        print(level, json.dumps(metrics), flush=True)
        report["levels"][level] = {"validation_cross_entropy": best, "evaluation": metrics, "weights": [p.tolist() for p in best_weights]}
    report["seconds"] = round(time.monotonic()-started, 2)
    path = HERE / "huroof_strategy_v5_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    artifact = {"schema_version": 1, "kind": "huroof_strategy_policy", "architecture": report["architecture"],
                "features": FEATURES, "provenance": report["data_source"],
                "levels": {level: {"weights": item["weights"]} for level, item in report["levels"].items()}}
    (HERE / "strategy_policy_v5.json").write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")
    print("wrote", path, "seconds", report["seconds"], flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="Local directory for training artifacts; never deploys")
    args = parser.parse_args()
    HERE = args.output_dir.resolve()
    HERE.mkdir(parents=True, exist_ok=True)
    main()
