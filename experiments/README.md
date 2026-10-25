# Experiments (synthetic data only)

**Synthetic interface test, not rankings.** These experiments check that the pipeline runs end to end. They do not show which method is better.
Outputs list methods alphabetically, with no order, rank or "recommended" field. exp02 (zero-shot TSFM; chronos-t5 weights
licence review still pending) is marked `day_zero_result: false` and carries a NOT A DAY-ZERO RESULT banner; it must never
be presented as a day-zero result.

**Naming.** Folders are named `exp<NN>_<dataset>_<method>` (lowercase letters, digits and `_`), where `<dataset>` equals
`data.flavour`. `xferbench experiment new` refuses other names (exit 2) and `xferbench experiment list` flags them.
Renamed 2026-10-24: `exp01_m5_lightgbm_analogs` → `exp01_synthetic_lightgbm_analogs` (its data is M5-*style* synthetic,
not M5), `exp02_chronos_zero_shot` → `exp02_synthetic_chronos_zero_shot`, `repro_visuelle_gtm` → `exp03_visuelle_gtm`.
The old ids still work for `run`/`--from`, with a deprecation warning.

| id | paper | default path | optional |
|---|---|---|---|
| exp01_synthetic_lightgbm_analogs | Makridakis et al. 2022, M5 ([doi](https://doi.org/10.1016/j.ijforecast.2021.11.013)); Ke et al. 2017, LightGBM | B0-B3 analogs, M1, M2 (no download) | `M4.lightgbm` with `pip install -e ".[lightgbm]"` |
| exp03_visuelle_gtm | Skenderi et al. 2021, GTM-Transformer ([arXiv](https://arxiv.org/abs/2109.09824)) | research only, licence-gated: blocked until the user supplies VISUELLE and a GTM install; reproduced WAPE pending | `--allow-research-only` |
| exp02_synthetic_chronos_zero_shot | Ansari et al. 2024, Chronos ([arXiv](https://arxiv.org/abs/2403.07815)) | B0, B2, B3 | `FM.chronos2`: foundation extra plus reviewed weights; otherwise `config_required` |

Run:

```bash
xferbench experiment list
xferbench experiment run exp01_synthetic_lightgbm_analogs   # -> eval/exp01_synthetic_lightgbm_analogs__synthetic/
xferbench experiment run-all                          # with --allow-research-only, research-only entries show as "blocked"
xferbench experiment --config experiments/exp01_synthetic_lightgbm_analogs/config.yaml --out eval/exp01_synthetic_lightgbm_analogs__synthetic
xferbench experiment run exp01_synthetic_lightgbm_analogs --tier sample   # after setting data.metadata in configs/sample.yaml
# or: scripts/model_eval.sh exp01_synthetic_lightgbm_analogs
```

**Data tiers.** Every run is `synthetic`, `sample` or `complete`; the tier is printed and written to every output
(see [Data tiers](../GETTING_STARTED.md#data-tiers-synthetic-sample-complete)). The tier is a config-only switch:
`configs/sample.yaml` and `configs/complete.yaml` in each experiment folder point `data.metadata` at your own data.
Runs of different tiers are never compared or summarised together (exit 2).

Each run writes `leaderboard.html`, `report.html`, `results.json` and `SUMMARY.md`. Methods without their extras are listed as `config_required`. Nothing is downloaded.

Synthetic runs carry no Rank column, no `rank`/`rankable` CSV columns and no "Ranked by" text. The frozen
validation selection used to drive the test run is written only to the private, git-ignored `_work/selection.json`
(labelled `data_class: synthetic`, `not_a_ranking: true`, `publish: false`); never copy `_work/` into results or the site.
