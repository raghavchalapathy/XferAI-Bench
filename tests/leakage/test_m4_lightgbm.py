"""M4.lightgbm: lazy optional extra, origin-only features, no post-cutoff labels."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests import handmade as hm
from xferbench.data.io import Dataset
from xferbench.data_preparation.feature_engineering.context import ContextBuilder, Exclusions
from xferbench.domains.registry import get_domain
from xferbench.models.base import TrainingContext
from xferbench.models.machine_learning.lightgbm_pairs import M4LightGBM, pair_features
from xferbench.models.registry import assess, get_entry


def test_registry_import_does_not_import_lightgbm() -> None:
    code = "import sys, xferbench.models.registry as r; r.all_entries(); print('lightgbm' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", errors="replace", check=True
    )
    assert out.stdout.strip() == "False"


def test_not_installed_is_reported_not_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a, **k: None if name == "lightgbm" else real(name, *a, **k)
    )
    rep = assess(get_entry("M4.lightgbm"))
    assert rep.execution_state == "not_installed"
    assert "--with-lightgbm" in rep.remedy and "--extra lightgbm" in rep.remedy and "boosting" not in rep.remedy


def test_features_ignore_future_data() -> None:
    def feats(ds: Dataset) -> pd.DataFrame:
        ctx = ContextBuilder(ds, Exclusions(fpgs=frozenset({"X"}))).at(hm.ORIGIN)
        req = next(hm.request().itertuples(index=False))
        f = pair_features(ctx, req, ctx.metadata.time.horizon_weeks)
        assert f is not None
        return f

    ds = hm.build()
    f0 = feats(ds)
    fut = {k: v.copy() for k, v in ds.tables.items()}
    obs = fut["observations"]
    future = obs["week_start"] >= hm.ORIGIN - pd.Timedelta(days=7)
    obs.loc[future, "units"] = obs.loc[future, "units"] * 1000 + 5
    f1 = feats(Dataset(ds.metadata, ds.base_dir, fut))
    pd.testing.assert_frame_equal(f0, f1)
    assert len(f0) == ds.metadata.time.horizon_weeks
    assert np.isfinite(f0[["season", "horizon_week", "week_of_year", "log_h"]].to_numpy()).all()


def _training(tiny: Dataset, split_path: Path) -> TrainingContext:
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, load_split

    split = load_split(split_path)
    r = BenchmarkRunner(RunConfig(Path("m.json"), split_path, "validation", Path("unused")))
    return r._training_context(tiny, split, get_domain("retail"))


def test_post_cutoff_labels_are_ignored(tiny: Dataset, tiny_split_path: Path) -> None:
    pytest.importorskip("lightgbm")
    tc = _training(tiny, tiny_split_path)
    leak = tc.labels.head(200).copy()
    leak["forecast_week"] = tc.fit_cutoff + pd.Timedelta(days=7)
    leak["actual"] = 1e6
    leak["measured"] = True
    tc_leak = TrainingContext(
        tc.requests, pd.concat([tc.labels, leak], ignore_index=True), tc.fit_cutoff, tc.data_hash, tc.context_for
    )
    a, b = M4LightGBM(), M4LightGBM()
    a.fit(tc, None, {})
    b.fit(tc_leak, None, {})
    rid = tc.requests["request_id"].iloc[0]
    req = next(tc.requests[tc.requests["request_id"] == rid].itertuples(index=False))
    f = pair_features(tc.context_for(rid), req, 52)
    assert f is not None
    np.testing.assert_allclose(a._booster.predict(a._matrix([f])), b._booster.predict(b._matrix([f])))


def test_fit_predict_contract(tiny: Dataset, tiny_split_path: Path) -> None:
    pytest.importorskip("lightgbm")
    from xferbench.orchestration.runner import load_split, validate_batch

    tc = _training(tiny, tiny_split_path)
    m = M4LightGBM()
    art = m.fit(tc, None, {})
    assert art.params["n_rows"] > 0 and art.fit_cutoff == tc.fit_cutoff.date().isoformat()
    split = load_split(tiny_split_path)
    dom = get_domain("retail")
    reqs = dom.requests(tiny, split, "validation")
    origin = sorted(reqs["origin"].unique())[0]
    batch = reqs[reqs["origin"] == origin]
    ctx = dom.context_builder(tiny, split, "validation").at(origin)
    out, problems = validate_batch(m.predict_batch(batch, ctx, art), batch, 52)
    assert not problems
    ok = out[out["status"] == "success"]["point_units"]
    assert len(ok) and (ok >= 0).all()
