"""V3-F1: running the documented flows inside a git repo leaves no non-ignored run output or ranking word.

A temp git repo gets this repo's .gitignore; the README step-by-step block is run literally, then ``demo``,
``steps`` and ``init`` as documented. Every file git does not ignore is then scanned.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN_OUTPUTS = {
    "forecasts.parquet",
    "leaderboard.csv",
    "metrics.json",
    "run_manifest.json",
    "selection.json",
    "splits.json",
    "report.html",
    "selection-1.json",
}
RANKING = re.compile(r"\b(rank|ranks|ranked|rankable|ranking|recommended)\b", re.IGNORECASE)
_NEXT = Path(sys.executable).parent / ("xferbench.exe" if sys.platform == "win32" else "xferbench")
CLI = str(_NEXT) if _NEXT.exists() else (shutil.which("xferbench") or str(_NEXT))


def _readme_block(heading: str) -> list[list[str]]:
    text = (ROOT / "README.md").read_text(encoding="utf-8").split(heading, 1)[1].split("```bash\n", 1)[1]
    body = text.split("```", 1)[0].replace("\\\n", " ")
    return [shlex.split(line.split("#", 1)[0]) for line in body.splitlines() if line.startswith("xferbench ")]


def _run(repo: Path, argv: list[str]) -> str:
    r = subprocess.run([CLI, *argv[1:]], cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert r.returncode == 0, (argv, r.stdout[-2000:], r.stderr[-2000:])
    return r.stdout + r.stderr


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    repo = tmp_path_factory.mktemp("hyg")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
    out = []
    for argv in _readme_block("## Step-by-step commands"):
        out.append(_run(repo, argv))
    out.append(_run(repo, shlex.split("xferbench demo --out ./xb-demo")))
    out.append(_run(repo, _readme_block("### Methods in order, and your own data")[0]))
    out.append(_run(repo, shlex.split("xferbench init --path ./my-bench")))
    return repo, "\n".join(out)


def test_no_unignored_run_outputs_or_ranking_words(repo: tuple[Path, str]) -> None:
    root, _ = repo
    files = subprocess.run(
        ["git", "ls-files", "-o", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.split("\0")
    files = [f for f in files if f]
    assert ".gitignore" in files and any(f.startswith("my-bench/") for f in files)
    bad = [f for f in files if Path(f).name in RUN_OUTPUTS or Path(f).parts[0] in {"work", "xb-demo", "runs"}]
    words = [f for f in files if RANKING.search((root / f).read_text(encoding="utf-8", errors="replace"))]
    assert bad == [] and words == [], (bad, words)
    for d in ["work/validation-run", "work/test-run", "work/xb-steps", "xb-demo", "validation-run", "a/test-run"]:
        assert subprocess.run(["git", "check-ignore", "-q", d + "/x"], cwd=root).returncode == 0, d


def test_cli_output_never_says_recommended(repo: tuple[Path, str]) -> None:
    _, out = repo
    assert "recommended" not in out.lower()
    assert "frozen selection:" in out


def test_init_readme_points_outputs_to_work(repo: tuple[Path, str]) -> None:
    text = (repo[0] / "my-bench/README.txt").read_text(encoding="utf-8")
    outs = re.findall(r"--out (\./[^\s)]+)", text)
    assert outs and all(o.startswith("./work/") or o == "./metadata.json" for o in outs), outs

