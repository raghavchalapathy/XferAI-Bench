# data_preparation/

Index layer. The code lives in the installable package `src/xferbench/data_preparation/` so `pip install` works. Shared by all three data flavours. Polars is the default engine; PySpark is the optional `distributed` extra.

| step | package module |
|---|---|
| data_cleaning | `xferbench.data_preparation.data_cleaning` (`clean_observations`) and `xferbench.data_preparation.spark` |
| feature_engineering | `xferbench.data_preparation.feature_engineering` (context, aggregates, hierarchy) |
| export_data | `xferbench.data_preparation.export_data` (`export_table`) |

Runbooks: `scripts/data_prep.sh`, `scripts/data_cleaning.sh`.
