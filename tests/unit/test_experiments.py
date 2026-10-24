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
    assert res["scalable_eval_parity"]["match"] is True
    if importlib.util.find_spec("chronos") is None:
        assert [s["method_id"] for s in res["not_run"]] == ["FM.chronos2"]
        assert res["not_run"][0]["status"] == "config_required"
    assert {r["method_id"] for r in res["test_rows"]} <= {"B0", "B2", "B3"}


def test_exp02_is_never_day_zero_and_never_ranked(tmp_path: Path) -> None:
    out = tmp_path / "exp02"
    run_experiment(ROOT / "experiments/exp02_chronos_zero_shot/config.yaml", out, progress=lambda _m: None)
    res = read_json(out / "results.json")
    assert res["day_zero_result"] is False
    assert res["not_day_zero"]
    assert "recommended_on_validation" not in res
    for f in ("leaderboard.html", "SUMMARY.md"):
        text = (out / f).read_text(encoding="utf-8")
        assert "NOT A DAY-ZERO RESULT" in text.upper()
        assert "recommended on validation" not in text.lower()
    assert all("order" not in r and "rank" not in r for r in res["test_rows"])


def test_v2_synthetic_outputs_carry_no_ranking_and_private_selection(tmp_path: Path) -> None:
    """V2-1 + V2-2: synthetic outputs have no Rank column / "Ranked by" text, selection.json is private."""
    import json
    import re
    import subprocess
    import urllib.parse

    from xferbench.experiments.runner import SELECTION_LABEL, WORK_DIR

    out = tmp_path / "exp02"
    run_experiment(ROOT / "experiments/exp02_chronos_zero_shot/config.yaml", out, progress=lambda _m: None)

    # V2-2: no published selection.json anywhere outside the private working dir
    published = [p for p in out.rglob("*") if p.is_file() and WORK_DIR not in p.relative_to(out).parts]
    assert not [p for p in published if p.name == "selection.json"], published
    sel = json.loads((out / WORK_DIR / "selection.json").read_text(encoding="utf-8"))
    assert sel["data_class"] == "synthetic" and sel["not_a_ranking"] is True and sel["publish"] is False
    assert sel["label"] == SELECTION_LABEL

    # V2-1: no rank column or ranking prose in what we publish
    rank_re = re.compile(r"\bRank\b|\brank,|Ranked by", re.IGNORECASE)
    targets = [out / "report.html", out / "SUMMARY.md", out / "leaderboard.html"]
    targets += [p for p in published if p.name in {"report.html", "leaderboard.csv", "summary.md"}]
    for f in targets:
        # decode embedded CSV data-URIs too, so their headers are checked
        text = urllib.parse.unquote(f.read_text(encoding="utf-8"))
        assert not rank_re.search(text), f"ranking text in {f}"
        if f.parent == out:
            # "not reviewer-recommended" is a catalogue disclaimer, not a recommendation
            assert not re.search(r"(?<!not reviewer-)recommended", text, re.IGNORECASE), f
    for csv in [p for p in published if p.name == "leaderboard.csv"]:
        header = csv.read_text(encoding="utf-8").splitlines()[0].split(",")
        assert "rank" not in header and "rankable" not in header

    # never committed and ignored by git
    assert "_work/" in (ROOT / ".gitignore").read_text(encoding="utf-8").split()
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False
    ).stdout
    assert not [t for t in tracked.splitlines() if t.endswith("selection.json") and t.startswith("results")]
