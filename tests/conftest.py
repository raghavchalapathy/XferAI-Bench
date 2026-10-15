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

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access attempted during a test")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(socket.socket, "connect", refuse)
        mp.setattr(socket, "create_connection", refuse)
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
    sel_path.write_text(json.dumps(sel.model_dump(mode="json"), indent=2))
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
