"""Licence-pinned donor-prior composites (FM.chronos2, FM.chronos_bolt, FM.timesfm25, M6.deepar_count).

Real backends need heavy extras and pinned weights; these tests use a small fake backend for the model interface
and check lazy imports, clean not-installed failures and origin-only donor inputs.
"""

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
from xferbench.models.foundation_models.donor_prior import (
    STATUS_LABEL,
    ChronosBackend,
    DeepARCountBackend,
    DonorSeries,
    ExtraMissingError,
    FMChronos2,
    FMChronosBolt,
    FMTimesFM25,
    M6DeepARCount,
    TimesFMBackend,
    _hf_kwargs,
    donor_series,
)
from xferbench.models.registry import assess, get_entry

IDS = ["FM.chronos2", "FM.chronos_bolt", "FM.timesfm25", "M6.deepar_count"]
HEAVY = ["torch", "chronos", "timesfm", "gluonts"]


class FakeBackend:
    """Forecasts the mean of the last 4 donor rates; records what it was shown."""

    def __init__(self) -> None:
        self.seen: list[DonorSeries] = []
        self.fitted: list[DonorSeries] = []

    def fit(self, series: list[DonorSeries], horizon: int) -> None:
        self.fitted = list(series)

    def forecast(self, series: list[DonorSeries], horizon: int) -> list[np.ndarray]:
        self.seen += series
        return [np.full(horizon, float(np.mean(s.rate[-4:]))) for s in series]


def test_registry_import_is_lazy() -> None:
    code = (
        "import sys, xferbench.models.registry as r; r.all_entries(); "
        f"print([m for m in {HEAVY!r} if m in sys.modules])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", errors="replace", check=True
    )
    assert out.stdout.strip() == "[]"


@pytest.mark.parametrize("mid", IDS)
def test_registry_labels_and_pins(mid: str) -> None:
    e = get_entry(mid)
    s = e.spec
    assert STATUS_LABEL in s.display_name and STATUS_LABEL in s.rights.notes
    assert "pins.v2" in s.rights.notes and "PENDING" in s.rights.notes
    assert s.board == "donor_only" and s.identity == "composite" and s.min_own_pair_history_weeks == 0
    assert not e.research_only and "core" not in e.profiles
    assert s.rights.code_revision and "R3 pin" in s.rights.code_revision
    if mid.startswith("FM."):
        assert s.rights.weights_revision


def test_pinned_revisions() -> None:
    assert "1224fafa91e1ecd6674f5204066b159e40b5e4a1" in get_entry("FM.chronos2").spec.rights.code_revision  # type: ignore[operator]
    assert get_entry("FM.chronos2").spec.rights.weights_revision == "29ec3766d36d6f73f0696f85560a422f50e8498c"
    assert "e51928e27119cb17bebc005be2696b75e0a9e688" in get_entry("FM.timesfm25").spec.rights.code_revision  # type: ignore[operator]
    assert get_entry("FM.timesfm25").spec.rights.weights_revision == "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
    assert "5d9f166d69f47aef3401367a7b842e78fe97b121" in get_entry("FM.chronos_bolt").spec.rights.weights_revision  # type: ignore[operator]


@pytest.mark.parametrize("mid", IDS)
def test_not_installed_reported(mid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a, **k: None if n in HEAVY else real(n, *a, **k))
    rep = assess(get_entry(mid))
    assert rep.execution_state == "not_installed"
    assert get_entry(mid).spec.optional_extra in rep.remedy  # type: ignore[operator]


@pytest.mark.parametrize("backend", [lambda: ChronosBackend("amazon/chronos-2"), TimesFMBackend, DeepARCountBackend])
def test_missing_extra_fails_cleanly(backend, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    for m in HEAVY:
        monkeypatch.setitem(sys.modules, m, None)  # forces ImportError
    with pytest.raises(ExtraMissingError, match="install the"):
        backend().fit([], 52)


def test_weights_never_downloaded_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XFERBENCH_ALLOW_WEIGHT_DOWNLOAD", raising=False)
    assert _hf_kwargs("abc") == {"revision": "abc", "local_files_only": True}


def _ctx(ds: Dataset):  # type: ignore[no-untyped-def]
    return ContextBuilder(ds, Exclusions(fpgs=frozenset({"X"}))).at(hm.ORIGIN)


def test_donor_series_origin_only_and_excludes_heldout() -> None:
    ds = hm.build()
    s0 = donor_series(_ctx(ds), "I1")
    assert s0 is not None and s0.weeks.max() <= hm.ORIGIN - pd.Timedelta(days=7)
    fut = {k: v.copy() for k, v in ds.tables.items()}
    obs = fut["observations"]
    future = obs["week_start"] >= hm.ORIGIN - pd.Timedelta(days=7)
    obs.loc[future, "units"] = obs.loc[future, "units"] * 1000 + 5
    obs.loc[obs["fpg_id"] == "X", "units"] = 1e6  # held-out FPG
    obs.loc[obs["fpg_id"] == "T", "units"] = 1e6  # target FPG (never a donor of itself? see below)
    s1 = donor_series(_ctx(Dataset(ds.metadata, ds.base_dir, fut)), "I1")
    assert s1 is not None
    # Target T has no I1 observations in the handmade data, so only future and held-out changes matter.
    np.testing.assert_allclose(s0.units, s1.units)
    np.testing.assert_allclose(s0.households, s1.households)


def test_predict_is_donor_rate_times_households() -> None:
    ds = hm.build()
    ctx = _ctx(ds)
    fake = FakeBackend()
    m = FMChronos2(fake)
    art = m.fit(TrainingContext(hm.request(), pd.DataFrame(), hm.ORIGIN, "h", lambda r: ctx), None, {})
    out = m.predict_batch(hm.request(), ctx, art)
    s = donor_series(ctx, "I1")
    assert s is not None
    hh = float(ctx.locations.set_index("fpg_id")["households"]["T"])
    np.testing.assert_allclose(out["point_units"].to_numpy(), np.mean(s.rate[-4:]) * hh)
    assert all(x.item_id == "I1" for x in fake.seen)
    assert STATUS_LABEL in art.notes


def _training(tiny: Dataset, split_path: Path) -> TrainingContext:
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig, load_split

    split = load_split(split_path)
    r = BenchmarkRunner(RunConfig(Path("m.json"), split_path, "validation", Path("unused")))
    return r._training_context(tiny, split, get_domain("retail"))


@pytest.mark.parametrize("cls", [FMChronos2, FMChronosBolt, FMTimesFM25, M6DeepARCount])
def test_contract_with_fake_backend(cls, tiny: Dataset, tiny_split_path: Path) -> None:  # type: ignore[no-untyped-def]
    from xferbench.orchestration.runner import load_split, validate_batch

    tc = _training(tiny, tiny_split_path)
    fake = FakeBackend()
    m = cls(fake)
    art = m.fit(tc, None, m.variants()[0])
    if cls is M6DeepARCount:
        assert fake.fitted and all(s.weeks.max() < tc.fit_cutoff for s in fake.fitted)
    else:
        assert not fake.fitted
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
    assert all(s.weeks.max() <= ctx.latest_usable_week for s in fake.seen)
