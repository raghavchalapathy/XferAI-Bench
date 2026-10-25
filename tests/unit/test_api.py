"""Production path: fit -> save -> forecast on new launches, reproducibility, and refusal of mismatches."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from xferbench import api
from xferbench.cli.main import app


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo") / "d"
    r = CliRunner().invoke(app, ["demo", "--out", str(out)])
    assert r.exit_code == 0, r.output
    return out


def _fit(demo: Path, seed: int = 7) -> api.FittedModel:
    return api.fit(
        demo / "data/metadata.json", demo / "splits.json", "B3", selection_path=demo / "selection.json", seed=seed
    )


def test_fit_save_forecast_matches_benchmark(demo: Path, tmp_path: Path) -> None:
    m = _fit(demo)
    api.save(m, tmp_path / "model")
    man = json.loads((tmp_path / "model/manifest.json").read_text(encoding="utf-8"))
    for k in (
        "method_id",
        "method_version",
        "config_hash",
        "code",
        "data_schema_hash",
        "seed",
        "libraries",
        "artifact_sha256",
    ):
        assert k in man
    assert set(man["code"]) == {"git_commit", "git_dirty"}
    fc = api.predict(api.load(tmp_path / "model"), demo / "data/metadata.json", demo / "splits.json")
    bench = pd.read_parquet(demo / "test-run/forecasts.parquet")
    bench = bench[bench["variant_id"] == m.artifact.variant_id]
    j = fc.merge(bench, on=["request_id", "horizon_week"], suffixes=("", "_b"))
    assert len(j) == len(bench) == len(fc) > 0
    assert np.allclose(j["point_units"], j["point_units_b"], equal_nan=True)  # benchmarked == production


def test_predict_never_reads_actuals_or_calls_evaluator(demo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from xferbench.domains.retail import plugin
    from xferbench.evaluation import evaluator, metrics

    m = _fit(demo)

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("forecast must not touch actuals or the evaluator")

    monkeypatch.setattr(plugin.RetailDomain, "targets", boom)
    monkeypatch.setattr(evaluator, "evaluate", boom)
    monkeypatch.setattr(evaluator, "population", boom)
    monkeypatch.setattr(metrics, "wmape", boom)
    assert len(api.predict(m, demo / "data/metadata.json", demo / "splits.json")) > 0


def test_same_seed_reproducible(demo: Path, tmp_path: Path) -> None:
    a, b = _fit(demo, 11), _fit(demo, 11)
    assert a.artifact.model_dump() == b.artifact.model_dump()
    assert a.manifest["config_hash"] == b.manifest["config_hash"]
    fa = api.predict(a, demo / "data/metadata.json", demo / "splits.json")
    fb = api.predict(b, demo / "data/metadata.json", demo / "splits.json")
    pd.testing.assert_frame_equal(fa, fb)


def test_schema_mismatch_refused(demo: Path, tmp_path: Path) -> None:
    m = _fit(demo)
    m.manifest["data_schema_hash"] = "0" * 64
    with pytest.raises(api.ApiError) as e:
        api.predict(m, demo / "data/metadata.json", demo / "splits.json")
    assert e.value.exit_code == api.EXIT_SCHEMA


def test_tampered_or_mismatched_artifact_refused(demo: Path, tmp_path: Path) -> None:
    d = api.save(_fit(demo), tmp_path / "m")
    art = json.loads((d / "artifact.json").read_text(encoding="utf-8"))
    art["notes"] = art["notes"] + " tampered"
    (d / "artifact.json").write_text(json.dumps(art), encoding="utf-8")
    with pytest.raises(api.ApiError) as e:
        api.load(d)
    assert e.value.exit_code == api.EXIT_ARTIFACT
    d2 = api.save(_fit(demo), tmp_path / "m2")
    art2 = json.loads((d2 / "artifact.json").read_text(encoding="utf-8"))
    art2["method_version"] = "0.0.0-old"
    (d2 / "artifact.json").write_bytes(json.dumps(art2).encode())
    man = json.loads((d2 / "manifest.json").read_text(encoding="utf-8"))
    import hashlib

    man["artifact_sha256"] = hashlib.sha256((d2 / "artifact.json").read_bytes()).hexdigest()
    (d2 / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    with pytest.raises(api.ApiError, match="version mismatch") as e2:
        api.load(d2)
    assert e2.value.exit_code == api.EXIT_ARTIFACT


def test_save_refuses_overwrite(demo: Path, tmp_path: Path) -> None:
    m = _fit(demo)
    api.save(m, tmp_path / "m")
    with pytest.raises(api.ApiError):
        api.save(m, tmp_path / "m")


def test_cli_fit_forecast_exit_codes(demo: Path, tmp_path: Path) -> None:
    r = CliRunner()
    base = ["--metadata", str(demo / "data/metadata.json"), "--splits", str(demo / "splits.json")]
    res = r.invoke(
        app, ["fit", *base, "--method", "B3", "--selection", str(demo / "selection.json"), "--out", str(tmp_path / "m")]
    )
    assert res.exit_code == 0, res.output
    res = r.invoke(app, ["forecast", "--model", str(tmp_path / "m"), *base, "--out", str(tmp_path / "f.parquet")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "f.manifest.json").exists()
    assert r.invoke(app, ["fit", *base, "--method", "NOPE", "--out", str(tmp_path / "x")]).exit_code == 3
    assert (
        r.invoke(
            app, ["forecast", "--model", str(tmp_path / "nope"), *base, "--out", str(tmp_path / "g.parquet")]
        ).exit_code
        == 2
    )
