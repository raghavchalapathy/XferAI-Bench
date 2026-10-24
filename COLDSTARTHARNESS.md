# COLDSTARTHARNESS.md

The cold-start harness: what runs, in what order, and which rules apply. Current rules: the highest `harness/BEST_PRACTICES.v<N>.yaml`. Self-improvement loop and guardrails: [harness/README.md](harness/README.md).

Scope: cold-start only. An existing item launches at an FPG where it has never sold. Objective: 0.5*WMAPE(PAIR0-E) + 0.5*WMAPE(PAIR0-N). The evaluator (`src/xferbench/evaluation/`) is protected; do not change its logic or hash.

Flow (same for all three data flavours, configured in [configs/](configs/)):

1. `scripts/data_prep.sh`: generate or ingest data, then validate it
2. `scripts/data_cleaning.sh`: Polars cleaning and export
3. `scripts/model_train.sh`: validation run and frozen selection
4. `scripts/inference.sh`: test run with the frozen selection
5. `scripts/model_eval.sh <experiment>`: experiment report and leaderboard into `eval/`

Self-improvement: log every run (`--log-lesson`), then run `xferbench harness triggers`. Rule changes go only through reviewed proposals (`xferbench harness apply`). See [harness/README.md](harness/README.md).
