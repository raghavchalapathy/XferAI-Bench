from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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
