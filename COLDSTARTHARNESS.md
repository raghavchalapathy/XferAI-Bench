# COLDSTARTHARNESS.md

The cold-start harness: what runs, in what order, and which rules apply. The rules are in [harness/RULES.md](harness/RULES.md) and the improvement log is in [harness/LESSONS.md](harness/LESSONS.md).

Scope: cold-start only. An existing item launches at an FPG where it has never sold. Objective: 0.5*WMAPE(PAIR0-E) + 0.5*WMAPE(PAIR0-N). The evaluator (`src/xferbench/evaluation/`) is protected; do not change its logic or hash.

Flow (same for all three data flavours, configured in [configs/](configs/)):

1. `scripts/data_prep.sh`: generate or ingest data, then validate it
2. `scripts/data_cleaning.sh`: Polars cleaning and export
3. `scripts/model_train.sh`: validation run and frozen selection
4. `scripts/inference.sh`: test run with the frozen selection
5. `scripts/model_eval.sh <experiment>`: experiment report and leaderboard into `eval/`

Self-improvement: every run that teaches something adds a dated lesson with evidence. Rule changes go through review before `harness/RULES.md` changes.
