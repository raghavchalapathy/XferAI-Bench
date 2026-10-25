"""Parity: each Polars swap equals the original pandas code, and evaluator + scalable_eval outputs are unchanged."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from xferbench.cli.main import app
from xferbench.domains.retail import plugin
from xferbench.domains.retail.plugin import RetailDomain, _as_of_attr


def _demo(out: Path) -> Path:
    r = CliRunner().invoke(app, ["demo", "--out", str(out)])
    assert r.exit_code == 0, r.output
    return out


@pytest.fixture(scope="module")
def runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    swapped = _demo(tmp_path_factory.mktemp("swap") / "d")
    mp = pytest.MonkeyPatch()
    mp.setattr(RetailDomain, "_attach_slices", RetailDomain._attach_slices_reference)
    try:
        reference = _demo(tmp_path_factory.mktemp("ref") / "d")
    finally:
        mp.undo()
    return swapped, reference


def test_random_as_of_matches_reference_loop() -> None:
    rng = np.random.default_rng(0)
    days = pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 60, 400), unit="D")
    versions = pd.DataFrame(
        {
            "item_id": rng.choice([f"i{k}" for k in range(30)], 400).astype(object),
            "known_at": days,
            "effective_from": days - pd.to_timedelta(rng.integers(0, 10, 400), unit="D"),
            "category": rng.choice(["a", "b", "c", None], 400).astype(object),
        }
    ).drop_duplicates(["item_id", "effective_from"])  # reference order on ties is unspecified (unstable sort)
    req = pd.DataFrame(
        {
            "item_id": rng.choice([f"i{k}" for k in range(35)], 300).astype(object),
            "origin": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 70, 300), unit="D"),
        }
    )
    ref = []
    for r in req.itertuples(index=False):
        it = versions[
            (versions["item_id"] == r.item_id) & (versions["known_at"] <= r.origin)
            & (versions["effective_from"] <= r.origin)
        ].sort_values("effective_from")  # fmt: skip
        ref.append(it["category"].iloc[-1] if len(it) and pd.notna(it["category"].iloc[-1]) else "unknown")
    assert _as_of_attr(req, versions, "item_id", "category") == ref


def test_requests_identical(runs: tuple[Path, Path]) -> None:
    from xferbench.contracts.metadata import load_metadata
    from xferbench.data.io import load_dataset
    from xferbench.orchestration.runner import load_split

    swapped, _ = runs
    meta = load_metadata(swapped / "data/metadata.json")
    ds = load_dataset(meta, (swapped / "data/metadata.json").parent)
    split = load_split(swapped / "splits.json")
    d = RetailDomain()
    for stage in ("validation", "test"):
        req = d.requests(ds, split, stage)
        base = req.drop(columns=["category", "region"])
        pd.testing.assert_frame_equal(req, d._attach_slices_reference(ds, base))
        pd.testing.assert_frame_equal(
            d.training_requests(ds, split, stage),
            d._attach_slices_reference(ds, d.training_requests(ds, split, stage).drop(columns=["category", "region"])),
        )


@pytest.mark.parametrize("stage", ["validation-run", "test-run"])
def test_evaluator_outputs_unchanged(runs: tuple[Path, Path], stage: str) -> None:
    swapped, reference = runs
    for f in ("slices.csv", "failures.csv"):
        assert (swapped / stage / f).read_bytes() == (reference / stage / f).read_bytes(), f
    timing = ["fit_seconds", "predict_seconds", "peak_python_mib"]  # wall-clock / memory, not results
    pd.testing.assert_frame_equal(
        pd.read_csv(swapped / stage / "leaderboard.csv").drop(columns=timing),
        pd.read_csv(reference / stage / "leaderboard.csv").drop(columns=timing),
        check_exact=True,
    )
    m1 = json.loads((swapped / stage / "metrics.json").read_text(encoding="utf-8"))["boards"]
    m2 = json.loads((reference / stage / "metrics.json").read_text(encoding="utf-8"))["boards"]
    strip = lambda b: {k: [{x: y for x, y in r.items() if x not in timing} for r in v] for k, v in b.items()}  # noqa: E731
    assert strip(m1) == strip(m2)
    pd.testing.assert_frame_equal(
        pd.read_parquet(swapped / stage / "forecasts.parquet").drop(columns=["run_id"]),
        pd.read_parquet(reference / stage / "forecasts.parquet").drop(columns=["run_id"]),
        check_exact=True,
    )


def test_scalable_eval_unchanged(runs: tuple[Path, Path]) -> None:
    from xferbench.contracts.metadata import load_metadata
    from xferbench.data.io import load_dataset
    from xferbench.experiments.runner import _scalable_parity
    from xferbench.orchestration.runner import load_split

    out = []
    for root in runs:
        ds = load_dataset(load_metadata(root / "data/metadata.json"), root / "data")
        out.append(_scalable_parity(ds, load_split(root / "splits.json"), root / "test-run"))
    assert out[0]["engine"] == out[1]["engine"] and out[0]["match"] is True and out[1]["match"] is True
    assert abs(out[0]["max_abs_diff"] - out[1]["max_abs_diff"]) < 1e-12  # float round-off only
    assert plugin._as_of_attr is _as_of_attr
