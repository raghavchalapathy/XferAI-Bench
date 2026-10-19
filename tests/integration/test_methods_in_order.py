"""Methods in order, each adding one idea (B0, B1, B2, M1, M2, M3, M4.lightgbm; B3 extra row)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from xferbench.cli.main import app
from xferbench.reports.progression import build, to_markdown

runner = CliRunner()
SC = ("PAIR0-E", "PAIR0-N")


def _e(mid: str, w: float, b: float, obj: float | None = 1.0) -> dict:
    return {
        "method_id": mid,
        "variant_id": mid,
        "objective": obj,
        "scenarios": {s: {"WMAPE": w, "Bias": b} for s in SC},
    }


def test_build_deltas_and_na() -> None:
    order = (("B0", "a"), ("M1", "b"), ("M3", "c"))
    comps = (("M1", "B0", "x"), ("M3", "M1", "y"))
    sup = [{"method_id": "M3", "implementation_state": "config_required", "reason": "M3 formula unspecified"}]
    p = build([_e("B0", 1.0, 0.2), _e("M1", 0.8, 0.1)], sup, SC, order, comps)
    assert p is not None
    assert p["comparisons"][0]["delta"]["PAIR0-E"]["WMAPE"] == pytest.approx(-0.2)
    assert p["comparisons"][1]["status"] == "N/A"
    m3 = p["steps"][2]
    assert not m3["ran"] and m3["state"] == "config_required" and "unspecified" in m3["reason"]
    assert "N/A" in to_markdown(p)


def test_no_order_no_section() -> None:
    assert build([], [], SC, (), ()) is None


def test_m3_explicit_request_exits_3(tiny_runs: dict[str, Path], tmp_path: Path) -> None:
    res = runner.invoke(
        app,
        [
            "run",
            "--local-data",
            str(tiny_runs["metadata"]),
            "--splits",
            str(tiny_runs["splits"]),
            "--stage",
            "validation",
            "--out",
            str(tmp_path / "m3"),
            "--methods",
            "M3",
        ],
    )
    assert res.exit_code == 3
    assert "M3 formula unspecified" in res.output


def test_steps_command_on_tiny_benchmark(tmp_path: Path) -> None:
    out = tmp_path / "steps"
    res = runner.invoke(app, ["steps", "--benchmark", "synthetic-tiny@1.1.0", "--out", str(out)])
    assert res.exit_code == 0, res.output
    p = json.loads((out / "test-run" / "methods_in_order.json").read_text(encoding="utf-8"))
    ran = {s["method_id"] for s in p["steps"] if s["ran"]}
    assert {"B0", "B1", "B2", "B3", "M1", "M2"} <= ran
    b3 = next(s for s in p["steps"] if s["method_id"] == "B3")
    assert b3["extra"] and not next(s for s in p["steps"] if s["method_id"] == "B2")["extra"]
    m3 = next(s for s in p["steps"] if s["method_id"] == "M3")
    assert not m3["ran"] and m3["state"] == "config_required"
    variants = {
        e["variant_id"]
        for e in json.loads((out / "test-run" / "metrics.json").read_text(encoding="utf-8"))["boards"]["cold_c0"]
    }
    assert any(v.startswith("B3[") for v in variants) and any(v.startswith("B2[") for v in variants)
    assert not any("raw_units" in v for v in variants), "the raw-unit ablation is not displayed"
    comp = {(c["candidate"], c["reference"]): c for c in p["comparisons"]}
    assert comp[("M3", "M2")]["status"] == "N/A"
    assert comp[("B3", "B2")]["status"] == "ok" and "shrinkage" in comp[("B3", "B2")]["note"]
    assert "M3 pending recipe" in comp[("M4.lightgbm", "M2")]["note"]
    assert "Methods in order, each adding one idea" in (out / "test-run" / "report.html").read_text(encoding="utf-8")
    man = json.loads((out / "test-run" / "run_manifest.json").read_text(encoding="utf-8"))
    assert man["data"]["data_class"] == "benchmark"
