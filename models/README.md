# models/

Index layer. The code lives in `src/xferbench/models/`. Old `xferbench.methods.*` imports still work through shims.

| family | package module | registry ids |
|---|---|---|
| stats | `xferbench.models.stats` | B0, B1, M1, M2 |
| affinity_propensity | `xferbench.models.affinity_propensity` | propensity recipes |
| analogs | `xferbench.models.analogs` | B2, B3 |
| machine_learning | `xferbench.models.machine_learning` | M4.lightgbm (extra `lightgbm`; SynapseML on Spark for complete data) |
| deep_learning | `xferbench.models.deep_learning` | M6.deepar_count (experimental) |
| graph_models | `xferbench.models.graph_models` | placeholder |
| foundation_models | `xferbench.models.foundation_models` | FM.chronos2, FM.chronos_bolt, FM.timesfm25 (adapters, config_required offline) |

To add a model, see `docs/EXTENDING.md`.
