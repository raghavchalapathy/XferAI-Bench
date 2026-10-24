# Experiments (synthetic data only)

**Synthetic interface test, not rankings.** These experiments check that the pipeline runs end to end. They do not show which method is better.

| id | paper | default path | optional |
|---|---|---|---|
| exp01_m5_lightgbm_analogs | Makridakis et al. 2022, M5 ([doi](https://doi.org/10.1016/j.ijforecast.2021.11.013)); Ke et al. 2017, LightGBM | B0-B3 analogs, M1, M2 (no download) | `M4.lightgbm` with `pip install -e ".[lightgbm]"` |
| exp02_chronos_zero_shot | Ansari et al. 2024, Chronos ([arXiv](https://arxiv.org/abs/2403.07815)) | B0, B2, B3 | `FM.chronos2`: foundation extra plus reviewed weights; otherwise `config_required` |

Run:

```bash
xferbench experiment --config experiments/exp01_m5_lightgbm_analogs/config.yaml --out eval/exp01
# or: scripts/model_eval.sh exp01_m5_lightgbm_analogs
```

Each run writes `leaderboard.html`, `report.html`, `results.json` and `SUMMARY.md`. Methods without their extras are listed as `config_required`. Nothing is downloaded.
