# DATASCIENTIST.md

For data scientists using XferAI-Bench.

- Quick start: `xferbench demo --out runs/demo`, then `xferbench experiment run exp01_synthetic_lightgbm_analogs` (-> `eval/exp01_synthetic_lightgbm_analogs__synthetic/`). Experiment names: `exp<NN>_<dataset>_<method>`; every run carries a data tier (`synthetic`, `sample`, `complete`).
- Your own data: follow [GETTING_STARTED.md Step 2](GETTING_STARTED.md#step-2-run-on-your-own-data). Put files under `data/complete_data/input/` or `data/sample_data/input/`; these folders are gitignored.
- Metric: WMAPE per scenario (PAIR0-E, PAIR0-N), combined 0.5/0.5. Select on validation only, then run test once with the frozen selection.
- Synthetic numbers never show that one method is better than another.
