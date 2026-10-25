"""Benchmark the Polars as-of slice attach against the pandas reference loop.

Synthetic frames (timing only, not results). Reports the median of --repeats runs plus machine specs.
Usage: python scripts/bench_polars_swaps.py --requests 2000 --repeats 5 [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import time

import numpy as np
import pandas as pd
import polars as pl

import xferbench
from xferbench.domains.retail.plugin import RetailDomain


def _frames(n_req: int, n_items: int, seed: int) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2024-01-01")

    def versions(key: str, attr: str, n: int) -> pd.DataFrame:
        k = 3 * n
        d = base + pd.to_timedelta(rng.integers(0, 300, k), unit="D")
        return pd.DataFrame(
            {key: [f"{key[0]}{i}" for i in rng.integers(0, n, k)], "known_at": d,
             "effective_from": d - pd.to_timedelta(rng.integers(0, 10, k), unit="D"),
             attr: rng.choice(["a", "b", "c"], k).astype(object)}
        ).drop_duplicates([key, "effective_from"])  # fmt: skip

    ds = {"items": versions("item_id", "category", n_items), "locations": versions("fpg_id", "region", 50)}
    req = pd.DataFrame(
        {"item_id": [f"i{i}" for i in rng.integers(0, n_items, n_req)],
         "fpg_id": [f"f{i}" for i in rng.integers(0, 50, n_req)],
         "origin": base + pd.to_timedelta(rng.integers(0, 330, n_req), unit="D")}
    )  # fmt: skip
    return ds, req


def _time(fn, repeats: int) -> list[float]:  # type: ignore[no-untyped-def]
    out = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t)
    return out


def specs() -> dict[str, object]:
    mem = None
    try:
        with open("/proc/meminfo") as f:
            mem = int(f.readline().split()[1]) // 1024
    except OSError:
        pass
    return {"platform": platform.platform(), "processor": platform.processor() or platform.machine(),
            "cpu_count": os.cpu_count(), "ram_mib": mem, "python": platform.python_version(),
            "pandas": pd.__version__, "polars": pl.__version__, "numpy": np.__version__,
            "xferbench": xferbench.__version__}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--items", type=int, default=500)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    a = ap.parse_args()
    ds, req = _frames(a.requests, a.items, a.seed)
    d = RetailDomain()
    new = d._attach_slices(ds, req)  # type: ignore[arg-type]
    ref = d._attach_slices_reference(ds, req)  # type: ignore[arg-type]
    pd.testing.assert_frame_equal(new.reset_index(drop=True), ref.reset_index(drop=True))
    tp = _time(lambda: d._attach_slices(ds, req), a.repeats)  # type: ignore[arg-type]
    tr = _time(lambda: d._attach_slices_reference(ds, req), a.repeats)  # type: ignore[arg-type]
    res = {"synthetic": True, "requests": a.requests, "items": a.items, "repeats": a.repeats, "parity": True,
           "median_s_polars": statistics.median(tp), "median_s_reference": statistics.median(tr),
           "speedup": statistics.median(tr) / statistics.median(tp), "specs": specs()}  # fmt: skip
    print(json.dumps(res, indent=2))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
