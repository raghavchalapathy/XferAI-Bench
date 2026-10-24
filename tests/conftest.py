from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from xferbench.data.io import Dataset, load_from_metadata_path
from xferbench.domains.registry import get_domain
from xferbench.synth.generator import generate
from xferbench.synth.presets import get_preset
from xferbench.util import write_json


@pytest.fixture(scope="session", autouse=True)
def no_network() -> Iterator[None]:
    """The whole session (including shared data and run fixtures) runs with outbound connections disabled."""

    real_connect, real_create = socket.socket.connect, socket.create_connection
    loopback = ("127.0.0.1", "localhost", "::1")  # local-only IPC (Spark-local py4j gateway); never outbound

    def _host(addr: object) -> object:
        return addr[0] if isinstance(addr, tuple) and addr else addr

    def connect(self: socket.socket, addr: object) -> None:
        if _host(addr) not in loopback:
            raise AssertionError("network access attempted during a test")
        real_connect(self, addr)  # type: ignore[arg-type]

    def create(addr: object, *args: object, **kwargs: object) -> socket.socket:
        if _host(addr) not in loopback:
            raise AssertionError("network access attempted during a test")
        return real_create(addr, *args, **kwargs)  # type: ignore[arg-type]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", connect)
        mp.setattr(socket, "create_connection", create)
        yield


@pytest.fixture(scope="session")
def tiny_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("tiny") / "data"
    generate(get_preset("tiny", seed=42), out, formats=("parquet", "csv"))
    return out


@pytest.fixture(scope="session")
def tiny(tiny_dir: Path) -> Dataset:
    return load_from_metadata_path(tiny_dir / "metadata.json")


@pytest.fixture(scope="session")
def tiny_split_path(tiny: Dataset, tmp_path_factory: pytest.TempPathFactory) -> Path:
    split = get_domain("retail").build_splits(tiny)
    path = tmp_path_factory.mktemp("split") / "splits.json"
    write_json(path, split.model_dump(mode="json"))
    return path


@pytest.fixture(scope="session")
def tiny_split(tiny_split_path: Path):  # type: ignore[no-untyped-def]
    from xferbench.orchestration.runner import load_split

    return load_split(tiny_split_path)


@pytest.fixture(scope="session")
def tiny_runs(tiny_dir: Path, tiny_split_path: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One validation run, a frozen selection and one test run, shared by integration tests."""
    from xferbench.contracts.selection import SelectionPolicy
    from xferbench.evaluation.selection import select
    from xferbench.orchestration.runner import BenchmarkRunner, RunConfig

    root = tmp_path_factory.mktemp("runs")
    md = tiny_dir / "metadata.json"
    val = BenchmarkRunner(RunConfig(md, tiny_split_path, "validation", root / "validation")).run()
    assert val.exit_code == 0
    sel = select(val.out, SelectionPolicy())
    sel_path = root / "selection.json"
    sel_path.write_text(json.dumps(sel.model_dump(mode="json"), indent=2), encoding="utf-8")
    test = BenchmarkRunner(RunConfig(md, tiny_split_path, "test", root / "test", selection_path=sel_path)).run()
    assert test.exit_code == 0
    return {
        "validation": val.out,
        "test": test.out,
        "selection": sel_path,
        "metadata": md,
        "splits": tiny_split_path,
        "root": root,
    }


# ---------------------------------------------------------------- V2-6: strict skips
_SKIPPED: list[tuple[str, str]] = []


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped and not hasattr(report, "wasxfail"):
        _SKIPPED.append((report.nodeid, str(report.longrepr)))


def unexpected_skips(profile: str, skipped: list[str], spec: str) -> list[str]:
    """Node ids in ``skipped`` that are not allowed for ``profile`` by the ``expected_skips.txt`` text ``spec``."""
    import fnmatch

    allowed = [
        line.split(None, 1)[1].strip()
        for line in spec.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and line.split(None, 1)[0] == profile
    ]
    return [n for n in skipped if not any(fnmatch.fnmatchcase(n, pat) for pat in allowed)]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    import os

    profile = os.environ.get("XFERBENCH_STRICT_SKIPS", "").strip()
    if not profile:
        return
    spec = (Path(__file__).parent / "expected_skips.txt").read_text(encoding="utf-8")
    bad = unexpected_skips(profile, [n for n, _ in _SKIPPED], spec)
    if bad:
        reasons = dict(_SKIPPED)
        msg = "\n".join(f"  {n}: {reasons[n]}" for n in bad)
        print(f"\nXFERBENCH_STRICT_SKIPS={profile}: unexpected skips:\n{msg}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
