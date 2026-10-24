"""Experiments run offline on synthetic data and label outputs as interface tests, not rankings."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from xferbench.experiments.runner import LABEL, ExperimentConfig, ExperimentError, run_experiment
from xferbench.util import read_json

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = sorted((ROOT / "experiments").glob("*/config.yaml"))


def test_configs_exist_and_load() -> None:
    assert len(CONFIGS) >= 2
    for c in CONFIGS:
        cfg = ExperimentConfig.load(c)
        assert cfg.papers and all(p["url"].startswith("https://") for p in cfg.papers)
        excluded = {"POP", "VISUELLE", "TimeGPT", "Moirai", "TimesFM3"}
        assert not excluded & {m.split(".")[-1] for m in cfg.methods + cfg.optional_methods}


def test_non_synthetic_rejected(tmp_path: Path) -> None:
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump({"id": "x", "methods": ["B0"], "data": {"flavour": "complete_data"}}), encoding="utf-8")
    with pytest.raises(ExperimentError):
        ExperimentConfig.load(p)


@pytest.mark.slow
def test_exp02_runs_offline_and_marks_chronos(tmp_path: Path) -> None:
    out = tmp_path / "exp02"
    res = run_experiment(ROOT / "experiments/exp02_chronos_zero_shot/config.yaml", out, progress=lambda _m: None)
    for f in ("leaderboard.html", "report.html", "results.json", "SUMMARY.md"):
        assert (out / f).exists()
    assert LABEL in (out / "leaderboard.html").read_text(encoding="utf-8")
    assert read_json(out / "results.json")["label"] == LABEL
    if importlib.util.find_spec("chronos") is None:
        assert [s["method_id"] for s in res["not_run"]] == ["FM.chronos2"]
        assert res["not_run"][0]["status"] == "config_required"
    assert {r["method_id"] for r in res["test_rows"]} <= {"B0", "B2", "B3"}
