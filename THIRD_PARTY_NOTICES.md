# Third-party notices

Xfer Benchmark's newly authored code is licensed under Apache-2.0 (see `LICENSE`). That license does not
relicense dependencies, model weights, datasets or services. Code, weights, data and services are separate
rights and are tracked per method in the registry (`xferbench list-methods --all`).

## Runtime dependencies of the core package

The core wheel depends on these packages, installed separately from PyPI under their own licenses. No
third-party source code is copied into this package.

| Package | License (as published by the project) |
|---|---|
| numpy | BSD-3-Clause |
| pandas | BSD-3-Clause |
| pyarrow (Apache Arrow) | Apache-2.0 |
| pydantic / pydantic-core | MIT |
| typer (and its dependencies click, rich, shellingham) | MIT / BSD-3-Clause |
| jinja2 (and markupsafe) | BSD-3-Clause |

Verify exact licenses of the versions you install; this table is a convenience summary.

## Optional extras (declared, not yet tested or used)

`boosting`, `neural`, `foundation`, `intermittent`, `services`, `distributed` reference LightGBM (MIT),
XGBoost (Apache-2.0), CatBoost (Apache-2.0), PyTorch (BSD-3-Clause), GluonTS (Apache-2.0), NeuralForecast
(Apache-2.0), pytorch-forecasting (MIT), chronos-forecasting (Apache-2.0), StatsForecast (Apache-2.0), the
Nixtla SDK (Apache-2.0) and PySpark (Apache-2.0). Pretrained weights have their own licenses; several reviewed
checkpoints (TimesFM 3, Moirai 2.0, TabPFN 3.5) carry non-commercial terms and are blocked by default.
TimeGPT is a proprietary paid service and is never called by default.

## Reference material

`reference/` holds the build prompt and research context supplied by the user. It is not part of the
distributed package and is kept unchanged.

## Referenced, not included: reproduction targets (research only)

| Project | Licence (verified from public pages) | How it is used |
|---|---|---|
| GTM-Transformer, <https://github.com/HumaticsLAB/GTM-Transformer> | MIT License, "Copyright (c) 2021 HumaticsLAB" (repo `LICENSE` and GitHub licence API, accessed 2026-10-24) | **Not vendored, not installed, not run here.** `experiments/exp03_visuelle_gtm` drives the user's own local install by path. |

The VISUELLE dataset is **not** listed as a dependency: no licence text was found (audit 2026-10-24,
`not_found`), so its use is blocked; nothing from it is included.
