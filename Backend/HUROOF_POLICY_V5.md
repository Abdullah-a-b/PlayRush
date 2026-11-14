# Huroof policy v5 — 2026-11-14

Huroof solo now runs a small learned cell-selection policy and a learned reaction
profile for each of the four difficulties. These run in-process with Python's
standard library. They do not require the developer's computer, a GPU, a new
Azure service, or a paid model endpoint. Optional external answer inference is
unchanged; cell selection no longer waits for that endpoint.

## Behavior

- Beginner remains almost uniform in cell choice. Medium favors short connections
  with substantial variation. Hard and expert account for both their own route and
  the damage if the opponent wins the chosen cell, including useful distant cells.
- The exported distribution is sampled. Taking its maximum for every difficulty
  would inadvertently strengthen the easier levels. The old strategy gate is not
  applied a second time. Expert retains immediate-win and immediate-block guards.
- Thinking time depends on question difficulty and length, with a separate learned
  hesitation profile for each level. Recent human results adjust timing only within
  the selected level's bounds; they do not secretly increase knowledge.
- Knowledge, hesitation draw, and timing quantile are stored once per question.
  A transfer/retry cannot turn an unknown answer into a known one by rerolling.
  A new question or round resets the private memory; server-state JSON preserves it.
- Missing or invalid artifacts fall back to the existing algorithm. Knowledge caps
  remain enforced separately: beginner hard 2.5%, beginner rare 0.5%, expert rare 24%
  before hesitation. Board skill is deliberately separate from factual knowledge.

## Training evidence

These models distill **synthetic design policies**, not human-video labels. Video
notes motivated scenarios, but the chooser and precise buzz timing were not
verified; no uncertain clip was relabelled as a measured human decision. No private
player records, production accounts, or answer keys were used as model inputs.

Each cell policy uses a 20 → 32 tanh → 1 network trained on 16,000 synthetic boards,
with 2,500 validation and 4,000 test boards. Train/validation/test groups exclude
duplicates and valid top-bottom reflections of each other. Both player colors are
represented. A naive 180-degree rotation is invalid for this offset-row board and
was not used as augmentation. Checkpoints were selected on validation loss.

The deployed policy was compared with the previous `f17a52d` algorithm in 960
synthetic rounds, swapping colors for paired seeds and using shared capture
probabilities of 0.5, 0.65 and 0.8. This isolates board decisions, not answering skill:

| Level | Wins against previous algorithm | Rounds |
|---|---:|---:|
| Beginner | 118 | 240 |
| Medium | 114 | 240 |
| Hard | 131 | 240 |
| Expert | 118 | 240 |

These small samples show approximate parity, not proven overall superiority.
On 1,156 test positions with a non-tactical safe distant option, the deployed
policy assigned such options an average 72.3% probability on hard and 96.1% on
expert. This is a deliberately engineered policy target, not a human benchmark.
All evaluated move probability is on legal cells. Medium and hard approximate
their target distributions less closely than expert; real matches remain needed.

Each reaction network uses 6 → 12 tanh → 2 sigmoid outputs (timing center and
hesitation). Four initializations per level were compared on validation loss.
There are 232 training, 48 validation, and 48 diagnostic test input combinations
per level, separated by word counts. The diagnostic test was inspected while
tuning convergence; it is not an untouched external benchmark. Its 0.009–0.013 s
mean timing-center error measures fit to the synthetic reference only.

Export/runtime checks covered 1,312 reaction inputs against Torch and 5,760 timing
and window cases. Strategy features match the saved 4,000 test-board tensors within
2.87e-8. Four concurrent local CPU decisions had median 4.53 ms and p95 9.63 ms.
These are local measurements, not an Azure capacity/load test.

The non-generative answer path still answers correctly when it elects to buzz;
this work does not establish human-like wrong-answer generation or empirical
human realism. The important improvement is stable knowledge, distinct level
behavior, conditional timing, and server-local model inference.

## Reproduce and verify

Runtime adds no dependencies. For **offline training only**, use a separate
environment with NumPy and PyTorch (the recorded run used Torch 2.7.1, two CPU
threads). From `Backend`, write outputs to a local work directory:

```powershell
python scripts/training/train_huroof_strategy.py --output-dir C:/Temp/huroof-v5-strategy
python scripts/training/train_huroof_reaction.py --output-dir C:/Temp/huroof-v5-reaction
python -m unittest discover -s tests -v
```

Training never copies output into the running app or deploys anything. Review
metrics before replacing `app/domains/games/huroof/strategy_policy_v5.json` and
`reaction_policy_v5.json`. Board caches are invalidated when the teacher source
changes. Detailed calibration and runtime evidence is committed in
`data/huroof_policy_v5_evaluation.json`, `data/huroof_policy_v5_runtime_evaluation.json`
and `data/huroof_reaction_v5_runtime_evaluation.json`.

Local pre-change backup: `work/backups/huroof_training_20261113` in the Codex
workspace. Unrelated unfinished Knowledge-game changes are outside this update.
