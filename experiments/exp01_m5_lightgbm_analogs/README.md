# exp01_m5_lightgbm_analogs

**Synthetic interface test, not a ranking.** Outputs check the software end to end, not which method is better.

- **Paper(s):** Makridakis, Spiliotis & Assimakopoulos (2022). *M5 accuracy competition: Results, findings, and
  conclusions.* International Journal of Forecasting 38(4):1346-1364. <https://doi.org/10.1016/j.ijforecast.2021.11.013>.
  Ke et al. (2017). *LightGBM: A Highly Efficient Gradient Boosting Decision Tree.* NeurIPS 30.
- **Data:** synthetic preset `tiny`, seed 42 (`data.flavour: synthetic`), generated on the fly; nothing downloaded.
- **Models:** B0, B1, B2, B3 (hierarchical analogs/baselines), M1, M2. Optional: `M4.lightgbm` (global LightGBM)
  with `pip install -e ".[lightgbm]"` or `uv sync --extra lightgbm`; without it, it is listed as `config_required`.
- **Runtime:** `runtime.backend: polars` (default) or `spark` (needs the `distributed` extra + Java).
- **Run:** `xferbench experiment run exp01_m5_lightgbm_analogs` -> `experiments/exp01_m5_lightgbm_analogs/runs/<UTC timestamp>/`
  (`leaderboard.html`, `report.html`, `results.json`, `SUMMARY.md`; git-ignored).
