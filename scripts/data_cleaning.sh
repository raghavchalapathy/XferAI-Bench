#!/usr/bin/env bash
# Clean observations with Polars. Usage: scripts/data_cleaning.sh [flavour]
set -euo pipefail
F="${1:-synthetic_data}"
python - "$F" <<'PY'
import sys
from pathlib import Path
from xferbench.data_preparation.data_cleaning import clean_observations
from xferbench.data_preparation.export_data import export_table
f = sys.argv[1]
src = next(Path(f"data/{f}/input").rglob("observations.parquet"))
df, rep = clean_observations(src)
export_table(df, Path(f"data/{f}/output/observations_clean.parquet"), sort_by=["item_id", "fpg_id", "week_start"])
print(rep)
PY
