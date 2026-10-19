from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from xferbench.cli.main import app

runner = CliRunner()


def test_help_lists_commands() -> None:
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    for cmd in (
        "synth",
        "validate",
        "split",
        "run",
        "select",
        "report",
        "compare",
        "list-methods",
        "doctor",
        "demo",
        "init",
        "schemas",
    ):
        assert cmd in res.output


def test_validate_and_list_methods(tiny_dir: Path) -> None:
    res = runner.invoke(app, ["validate", "--metadata", str(tiny_dir / "metadata.csv.json")])
    assert res.exit_code == 0, res.output
    res = runner.invoke(app, ["list-methods", "--all", "--format", "json"])
    assert res.exit_code == 0
    payload = json.loads(res.output)
    rows = payload["entries"] if isinstance(payload, dict) else payload
    ids = {r["method_id"] for r in rows}
    assert {"B0", "B1", "B2", "M1", "M2", "M3", "B3", "FM.chronos2"} <= ids
    assert "SVC.timegpt" not in ids and "B2.raw_units" not in ids


def test_doctor(tiny_dir: Path) -> None:
    res = runner.invoke(app, ["doctor", "--profile", "core"])
    assert res.exit_code == 0, res.output


def test_init_and_schemas(tmp_path: Path) -> None:
    res = runner.invoke(app, ["init", "--path", str(tmp_path / "proj")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "proj" / "metadata.json").exists()
    res = runner.invoke(app, ["schemas", "--out", str(tmp_path / "schemas")])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "schemas" / "metadata.schema.json").exists()


def test_import_has_no_side_effects() -> None:
    code = (
        "import socket, sys\n"
        "def refuse(*a, **k): raise SystemExit('network on import')\n"
        "socket.socket.connect = refuse\n"
        "import xferbench, xferbench.cli.main, xferbench.methods.registry\n"
        "heavy = [m for m in ('torch', 'lightgbm', 'xgboost', 'catboost', 'requests') if m in sys.modules]\n"
        "assert not heavy, heavy\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_run_selection_directory_is_a_clear_user_error(tmp_path: Path) -> None:
    from xferbench.orchestration.runner import RunError, load_selection_file

    d = tmp_path / "sel"
    d.mkdir()
    (d / "selection.json").write_text("{}", encoding="utf-8")
    with pytest.raises(RunError, match="not a directory") as ei:
        load_selection_file(d)
    assert ei.value.exit_code == 2 and "did you mean" in str(ei.value)
    with pytest.raises(RunError, match="not found") as ei:
        load_selection_file(tmp_path / "missing.json")
    assert ei.value.exit_code == 2
    with pytest.raises(RunError, match=r"not a valid selection\.json") as ei:
        load_selection_file(d / "selection.json")
    assert ei.value.exit_code == 2


def test_cli_run_selection_dir_exits_2_without_traceback(tiny_dir: Path, tiny_split_path: Path, tmp_path: Path) -> None:
    d = tmp_path / "seldir"
    d.mkdir()
    res = runner.invoke(
        app,
        [
            "run",
            "--metadata",
            str(tiny_dir / "metadata.json"),
            "--splits",
            str(tiny_split_path),
            "--stage",
            "test",
            "--selection",
            str(d),
            "--out",
            str(tmp_path / "out"),
        ],
    )
    assert res.exit_code == 2, res.output
    assert "not a directory" in res.output and "Traceback" not in res.output
