"""Train four tiny reaction profiles from an explicit synthetic reference.

This is policy distillation, not human-video supervised learning. The supplied
video annotations do not establish exact buzz times, so none are used as labels.
No user data, questions, answers, production services or GPU are accessed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import time

import torch
from torch import nn

HERE = Path(__file__).resolve().parent
LEVELS = ("beginner", "medium", "hard", "expert")
DIFFICULTIES = ("easy", "medium", "hard", "rare")
BOUNDS = {"beginner": (8., 16.), "medium": (6., 12.),
          "hard": (4., 9.), "expert": (3., 7.)}
HESITATE = {"beginner": .20, "medium": .12, "hard": .06, "expert": .03}
FEATURES = ["easy", "medium", "hard", "rare", "word_count/40", "retry"]


def features(difficulty: int, words: int, retry: int):
    return [float(difficulty == i) for i in range(4)] + [min(40, max(0, words)) / 40., float(retry)]


def reference(level, difficulty, words, retry):
    # A design target rather than an empirical estimate of human reaction time:
    # longer/rarer prompts require more time; another look saves some reading.
    length = min(40, words) / 40.
    load = (0., .35, .72, 1.)[difficulty]
    center = .22 + .38 * load + .20 * length - .065 * retry
    center += .035 * load * length
    hesitation = HESITATE[level] + .065 * load + .02 * length - .012 * retry
    return [max(.10, min(.90, center)), max(.015, min(.40, hesitation))]


def forward(weights, x):
    w1, b1, w2, b2 = weights
    hidden = [math.tanh(b + sum(a * z for a, z in zip(row, x)))
              for row, b in zip(w1, b1)]
    return [1 / (1 + math.exp(-max(-40, min(40, b + sum(a*z for a,z in zip(row,hidden))))))
            for row, b in zip(w2, b2)]


def evaluate(weights, rows, level):
    errors = []
    for difficulty, words, retry in rows:
        observed = forward(weights, features(difficulty, words, retry))
        target = reference(level, difficulty, words, retry)
        errors.append([abs(a-b) for a,b in zip(observed,target)])
    delay_range = BOUNDS[level][1] - BOUNDS[level][0]
    return {"cases": len(rows),
            "timing_center_mae_seconds": sum(v[0] for v in errors)/len(errors)*delay_range,
            "timing_center_max_error_seconds": max(v[0] for v in errors)*delay_range,
            "hesitation_mae_percentage_points": sum(v[1] for v in errors)/len(errors)*100,
            "hesitation_max_error_percentage_points": max(v[1] for v in errors)*100}


def sample_delay(center, bounds, rng):
    lo, hi = bounds
    value = lo + (hi-lo)*center
    halfwidth = (hi-lo)*.18
    return rng.triangular(max(lo,value-halfwidth),min(hi,value+halfwidth),value)


def main():
    started = time.perf_counter()
    torch.set_num_threads(2)
    word_counts = list(range(41))
    random.Random(515131).shuffle(word_counts)
    splits = {"train": sorted(word_counts[:29]), "validation": sorted(word_counts[29:35]),
              "test": sorted(word_counts[35:])}
    cases = {name: [(d,n,r) for d in range(4) for n in words for r in (0,1)]
             for name,words in splits.items()}
    assert all(not(set(cases[a]) & set(cases[b])) for a,b in
               (("train","validation"),("train","test"),("validation","test")))
    report = {"provenance": "synthetic reference policy; no human timing labels",
              "holdout": "disjoint integer word counts, same four difficulty classes",
              "word_counts": splits, "cases_per_level": {k:len(v) for k,v in cases.items()},
              "train_seeds": [18301,27019,41777,66319], "levels": {}}
    artifact = {"schema_version": 1, "kind": "huroof_reaction_policy",
                "features": FEATURES, "architecture": "6 -> 12 tanh -> 2 sigmoid",
                "outputs": ["timing_fraction", "hesitation_probability"],
                "provenance": report["provenance"], "levels": {}}
    tx = torch.tensor([features(*row) for row in cases["train"]])
    vx = torch.tensor([features(*row) for row in cases["validation"]])
    for level in LEVELS:
        ty = torch.tensor([reference(level,*row) for row in cases["train"]])
        vy = torch.tensor([reference(level,*row) for row in cases["validation"]])
        best = None
        trials = []
        for seed in report["train_seeds"]:
            torch.manual_seed(seed)
            model = nn.Sequential(nn.Linear(6,12),nn.Tanh(),nn.Linear(12,2))
            optimizer = torch.optim.Adam(model.parameters(),lr=.018)
            best_trial_loss = float("inf")
            checkpoint = None
            for epoch in range(2400):
                if epoch == 1200:
                    for group in optimizer.param_groups:
                        group['lr'] = .004
                prediction = model(tx)
                loss = ((prediction-torch.logit(ty))**2).mean()
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                if epoch % 20 == 19:
                    with torch.no_grad():
                        validation = float((((model(vx).sigmoid()-vy)**2)*torch.tensor([1.,10.])).mean())
                    if validation < best_trial_loss:
                        best_trial_loss = validation
                        checkpoint = copy.deepcopy(model.state_dict())
            model.load_state_dict(checkpoint)
            weights = [p.detach().tolist() for p in model.parameters()]
            trials.append({"seed":seed,"validation_loss":best_trial_loss})
            if best is None or best_trial_loss < best[0]:
                best = best_trial_loss, seed, weights
        _,seed,weights=best
        artifact["levels"][level] = {"weights":weights,"delay_bounds":list(BOUNDS[level]),
                                     "jitter_halfwidth_fraction":.18}
        level_report={"selected_seed":seed,"validation_trials":trials,
                      "heldout":evaluate(weights,cases["test"],level)}
        # Quantify sample behavior, independently of reference-fit metrics.
        profiles={}
        for difficulty,name in enumerate(DIFFICULTIES):
            center,hesitation=forward(weights,features(difficulty,12,0))
            rng=random.Random(98761)
            samples=sorted(sample_delay(center,BOUNDS[level],rng) for _ in range(5000))
            profiles[name]={"center_seconds":BOUNDS[level][0]+(BOUNDS[level][1]-BOUNDS[level][0])*center,
                            "hesitation_probability":hesitation,
                            "delay_p10_seconds":samples[500],"delay_p90_seconds":samples[4500]}
        level_report["twelve_word_first_attempt_profiles"]=profiles
        # Guard generalization over ALL valid feature tuples, not just heldout fit.
        all_rows=cases["train"]+cases["validation"]+cases["test"]
        for difficulty,words,retry in all_rows:
            center,hesitation=forward(weights,features(difficulty,words,retry))
            assert .08<=center<=.92 and .01<=hesitation<=.42
            if difficulty<3:
                assert forward(weights,features(difficulty+1,words,retry))[0]>center
            if words<40:
                assert forward(weights,features(difficulty,words+1,retry))[0]>center
            if not retry:
                assert forward(weights,features(difficulty,words,1))[0]<center
        print(level,json.dumps(level_report["heldout"]),flush=True)
        assert level_report["heldout"]["timing_center_max_error_seconds"] < .15
        assert level_report["heldout"]["hesitation_max_error_percentage_points"] < .6
        report["levels"][level]=level_report
    target=HERE/"huroof_reaction_v5_weights.json"
    target.write_text(json.dumps(artifact,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    report["artifact_bytes"]=target.stat().st_size
    report["artifact_sha256"]=hashlib.sha256(target.read_bytes()).hexdigest()
    report["training_seconds"]=time.perf_counter()-started
    # Pure Python runtime benchmark; cold file read excluded, cached model expected.
    start=time.perf_counter()
    for i in range(10000):
        forward(artifact["levels"][LEVELS[i%4]]["weights"],features(i%4,i%41,i%2))
    report["cached_python_mean_inference_us"]=(time.perf_counter()-start)*100
    (HERE/"huroof_reaction_v5_report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("finished",report["artifact_bytes"],"bytes",round(report["training_seconds"],2),"seconds",flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="Local directory for training artifacts; never deploys")
    args = parser.parse_args()
    HERE = args.output_dir.resolve()
    HERE.mkdir(parents=True, exist_ok=True)
    main()
