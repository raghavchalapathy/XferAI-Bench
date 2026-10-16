"""Benchmark data vs local data (docs/DATA_CLASSES.md).

* benchmark: shared synthetic/public data resolved from a versioned BENCHMARK.json and verified by dataset hash.
* local: the user's own data, loaded only from an explicit path; outputs are labeled local, must not be written
  to a non-ignored path inside a git work tree, and reports contain aggregates only.
"""

from __future__ import annotations

import json
import subprocess
import warnings
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Literal

DataClass = Literal["benchmark", "local"]


class DataClassError(Exception):
    """Refused data-class operation (CLI exit code 2)."""


@dataclass(frozen=True)
class DataSource:
    data_class: DataClass
    metadata_path: Path
    benchmark_id: str | None = None
    benchmark_version: str | None = None
    expected_hash: str | None = None
    kind: str | None = None

    def label(self) -> dict[str, Any]:
        return {
            "data_class": self.data_class,
            "benchmark_id": self.benchmark_id,
            "benchmark_version": self.benchmark_version,
            "benchmark_kind": self.kind,
        }


def _builtin_root() -> Path:
    return Path(str(resources.files("xferbench").joinpath("benchmarks")))


def list_benchmarks() -> list[str]:
    root = _builtin_root()
    return sorted(f"{p.parent.parent.name}@{p.parent.name}" for p in root.glob("*/*/BENCHMARK.json"))


def load_benchmark_manifest(ref: str) -> tuple[dict[str, Any], Path]:
    """`ref` is `id@version` (built-in) or a path to a BENCHMARK.json."""
    p = Path(ref)
    if p.suffix == ".json" and p.exists():
        path = p
    else:
        if "@" not in ref:
            raise DataClassError(f"benchmark reference '{ref}' must be id@version or a BENCHMARK.json path")
        bid, ver = ref.split("@", 1)
        path = _builtin_root() / bid / ver / "BENCHMARK.json"
        if not path.exists():
            raise DataClassError(f"unknown benchmark '{ref}'; known: {list_benchmarks()}")
    man = json.loads(path.read_text())
    for k in ("benchmark_id", "version", "kind", "licence", "source", "dataset_hash"):
        if k not in man:
            raise DataClassError(f"{path}: BENCHMARK.json missing '{k}'")
    if man["kind"] not in ("synthetic", "public"):
        raise DataClassError(f"{path}: kind must be synthetic or public")
    return man, path


def materialize_benchmark(ref: str, data_dir: Path) -> DataSource:
    """Generate (synthetic) or locate (public) benchmark data and verify its dataset hash."""
    from xferbench.data.io import load_from_metadata_path

    man, path = load_benchmark_manifest(ref)
    src = man["source"]
    if man["kind"] == "synthetic" and src.get("generator") == "xferbench.synth":
        from xferbench.synth.generator import generate
        from xferbench.synth.presets import get_preset

        if not (data_dir / "metadata.json").exists():
            generate(get_preset(src["preset"], int(src["seed"])), data_dir, ("parquet",))
        md = data_dir / "metadata.json"
    else:
        md = (path.parent / src.get("metadata", "metadata.json")).resolve()
        if not md.exists():
            raise DataClassError(f"benchmark metadata not found at {md}; fetch the data as described in {path}")
    actual = load_from_metadata_path(md, verify_hash=False).content_hash
    if man["dataset_hash"] and actual != man["dataset_hash"]:
        raise DataClassError(
            f"benchmark {man['benchmark_id']}@{man['version']} hash mismatch: expected {man['dataset_hash']}, "
            f"found {actual}; the data was modified or regenerated differently"
        )
    return DataSource("benchmark", md, man["benchmark_id"], man["version"], man["dataset_hash"], man["kind"])


def _inside_benchmarks_dir(p: Path) -> bool:
    rp = p.resolve()
    return any(part == "benchmarks" for part in rp.parts[:-1]) or str(rp).startswith(str(_builtin_root().resolve()))


def resolve_source(
    *, benchmark: str | None, local_data: Path | None, metadata: Path | None, data_dir: Path | None = None
) -> DataSource:
    given = [x for x in (benchmark, local_data, metadata) if x is not None]
    if len(given) != 1:
        raise DataClassError("give exactly one of --benchmark, --local-data or --metadata")
    if benchmark is not None:
        if data_dir is None:
            raise DataClassError("a benchmark run needs a data directory")
        return materialize_benchmark(benchmark, data_dir)
    if local_data is not None:
        return DataSource("local", local_data)
    assert metadata is not None
    if _inside_benchmarks_dir(metadata):
        return DataSource("benchmark", metadata, kind="unverified (legacy --metadata inside benchmarks/)")
    warnings.warn(
        f"--metadata {metadata} is outside benchmarks/; treating it as LOCAL data (use --local-data explicitly)",
        UserWarning,
        stacklevel=2,
    )
    return DataSource("local", metadata)


def git_toplevel(p: Path) -> Path | None:
    d = p if p.is_dir() else p.parent
    while not d.exists():
        d = d.parent
    try:
        r = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def check_local_output(out: Path) -> None:
    """Refuse a local-data output path inside a git work tree unless git ignores it."""
    top = git_toplevel(out)
    if top is None:
        return
    rel = out.resolve().relative_to(top.resolve()) if out.resolve().is_relative_to(top.resolve()) else out
    probe = str(rel).rstrip("/") + "/probe.local-check"
    r = subprocess.run(["git", "-C", str(top), "check-ignore", "-q", probe], capture_output=True, timeout=10)
    if r.returncode != 0:
        raise DataClassError(
            f"local-data output {out} is inside the git work tree {top} and is not ignored by git; "
            "choose an --out outside the repository or under runs/local/ (gitignored)"
        )


LOCAL_REDACTED_FILES = (
    "report.html",
    "summary.md",
    "leaderboard.csv",
    "slices.csv",
    "failures.csv",
    "metrics.json",
    "data_quality.json",
    "method_support.json",
    "run_manifest.json",
    "methods_in_order.json",
)


def _token(value: str, salt: str) -> str:
    import hashlib

    return "id:" + hashlib.sha256((salt + value).encode()).hexdigest()[:10]


def redact_ids(text: str, ids: set[str], salt: str) -> str:
    import re

    ids = {i for i in ids if i}
    if not ids:
        return text
    pat = re.compile(
        r"(?<![A-Za-z0-9_.-])("
        + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True))
        + r")(?![A-Za-z0-9_-])"
    )
    return pat.sub(lambda m: _token(m.group(1), salt), text)


def redact_local_outputs(run_dir: Path, ids: set[str], salt: str) -> list[str]:
    """Replace entity identifiers in human-facing local-run outputs with salted hashes."""
    done = []
    for name in LOCAL_REDACTED_FILES:
        p = run_dir / name
        if p.exists():
            p.write_text(redact_ids(p.read_text(), ids, salt))
            done.append(name)
    return done
