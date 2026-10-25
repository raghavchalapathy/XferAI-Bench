# Experiments (synthetic data only)

**Synthetic interface test, not rankings.** These experiments check that the pipeline runs end to end. They do not show which method is better.
Outputs list methods alphabetically, with no order, rank or "recommended" field. exp02 (zero-shot TSFM; chronos-t5 ruling
pending in pins.v5) is marked `day_zero_result: false` and carries a NOT A DAY-ZERO RESULT banner; it must never
be presented as a day-zero result.

| id | paper | default path | optional |
|---|---|---|---|
| exp01_m5_lightgbm_analogs | Makridakis et al. 2022, M5 ([doi](https://doi.org/10.1016/j.ijforecast.2021.11.013)); Ke et al. 2017, LightGBM | B0-B3 analogs, M1, M2 (no download) | `M4.lightgbm` with `pip install -e ".[lightgbm]"` |
| repro_visuelle_gtm | Skenderi et al. 2021, GTM-Transformer ([arXiv](https://arxiv.org/abs/2109.09824)) | research only, licence-gated: blocked until the user supplies VISUELLE and a GTM install; reproduced WAPE pending | `--allow-research-only` |
| exp02_chronos_zero_shot | Ansari et al. 2024, Chronos ([arXiv](https://arxiv.org/abs/2403.07815)) | B0, B2, B3 | `FM.chronos2`: foundation extra plus reviewed weights; otherwise `config_required` |

Run:

```bash
xferbench experiment list
xferbench experiment run exp01_m5_lightgbm_analogs   # -> experiments/<id>/runs/<UTC timestamp>/
xferbench experiment run-all                          # research-only entries show as "blocked"
xferbench experiment --config experiments/exp01_m5_lightgbm_analogs/config.yaml --out eval/exp01
# or: scripts/model_eval.sh exp01_m5_lightgbm_analogs
```

Each run writes `leaderboard.html`, `report.html`, `results.json` and `SUMMARY.md`. Methods without their extras are listed as `config_required`. Nothing is downloaded.

Synthetic runs carry no Rank column, no `rank`/`rankable` CSV columns and no "Ranked by" text. The frozen
validation selection used to drive the test run is written only to the private, git-ignored `_work/selection.json`
(labelled `data_class: synthetic`, `not_a_ranking: true`, `publish: false`); never copy `_work/` into results or the site.
