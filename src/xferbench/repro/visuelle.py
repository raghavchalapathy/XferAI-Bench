"""VISUELLE / GTM-Transformer reproduction helpers (research only, licence-gated).

Nothing here downloads data or vendors third-party code:

* :func:`adapt_visuelle` turns a VISUELLE folder the *user* obtained from the official source
  (train.csv / test.csv, as read by the official GTM-Transformer ``forecast.py``) into
  ``data/<flavour>/{input,metadata}/`` with Polars.
* :class:`GtmWrapper` drives the user's *own local install* of GTM-Transformer (path from config);
  it never clones, installs or copies that code.
* :func:`wape` is the paper's metric, WAPE = 100 * sum|y - yhat| / sum y over the first ``horizon`` weeks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl

HORIZON_WEEKS = 6
SALES_WEEKS = 12  # VISUELLE stores 12 weekly sales columns named "0".."11"
STATIC_COLUMNS = ["external_code", "season", "category", "color", "fabric", "release_date", "image_path"]
PAPER = {
    "citation": "Skenderi, G., Joppi, C., Denitto, M., Cristani, M. (2021). Well Googled is Half Done: "
    "Multimodal Forecasting of New Fashion Product Sales with Image-based Google Trends. arXiv:2109.09824 (v6); "
    "journal version linked from arXiv: doi:10.1002/for.3104",
    "url": "https://arxiv.org/abs/2109.09824",
    "table": "p.11, Table 1 (VISUELLE), row GTM-Transformer [T+I+G], column group '6 Weeks, G.Trends: 52 weeks', WAPE",
    "wape_reported": 55.2,
    "quote": "row text (p.11, Table 1; pdftotext -layout, spaces collapsed): GTM-Transformer [T+I+G] 55,2 30,2(15;36) 0,41 0,33",
    "reviewer_record": (
        "citation-checked: factory/inbox/reviewer/usability-v4-v2-review-20261024/review.md sha256 "
        "fd0d8ceacf2bcf7ca500376cf51169214084c0c79cb0fa42f23aa9867df95911 "
        "(citation check only; paper-reported; reproduction pending)"
    ),
    "reproduction": "pending",
    "accessed": "2026-10-24",
}


class ReproError(RuntimeError):
    """Raised when the reproduction is blocked (licence gate, missing data, missing local install)."""


def _validate(df: pl.DataFrame, name: str) -> None:
    need = STATIC_COLUMNS + [str(i) for i in range(SALES_WEEKS)]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ReproError(f"{name}: missing VISUELLE columns {missing}")


def adapt_visuelle(src: Path, data_root: Path, flavour: str = "visuelle", synthetic: bool = False) -> dict[str, Any]:
    """Convert ``src/{train,test}.csv`` into ``data_root/<flavour>/{input,metadata}``. Returns the metadata dict."""
    frames = []
    for split in ("train", "test"):
        p = src / f"{split}.csv"
        if not p.is_file():
            raise ReproError(f"{p} not found: obtain VISUELLE from the official source first (see README)")
        df = pl.read_csv(p, infer_schema_length=10000)
        _validate(df, p.name)
        frames.append(df.with_columns(pl.lit(split).alias("split")))
    allp = pl.concat(frames, how="diagonal_relaxed")
    weeks = [str(i) for i in range(SALES_WEEKS)]
    products = allp.select([*STATIC_COLUMNS, "split"]).with_columns(pl.col("external_code").cast(pl.Utf8))
    sales = (
        allp.select(["external_code", *weeks])
        .with_columns(pl.col("external_code").cast(pl.Utf8))
        .unpivot(index="external_code", on=weeks, variable_name="week", value_name="sales")
        .with_columns(pl.col("week").cast(pl.Int32), pl.col("sales").cast(pl.Float64))
        .sort(["external_code", "week"])
    )
    inp, meta_dir = data_root / flavour / "input", data_root / flavour / "metadata"
    inp.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    products.write_parquet(inp / "products.parquet")
    sales.write_parquet(inp / "sales.parquet")
    counts = {s: int(n) for s, n in products.group_by("split").len().iter_rows()}
    meta = {
        "flavour": flavour,
        "source": "SYNTHETIC FIXTURE (interface test only)" if synthetic else "VISUELLE (user-obtained, licence-gated)",
        "usage_tag": "research_only",
        "synthetic": synthetic,
        "horizon_weeks": HORIZON_WEEKS,
        "sales_weeks": SALES_WEEKS,
        "products": counts,
        "files": {"products": "input/products.parquet", "sales": "input/sales.parquet"},
    }
    (meta_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def wape(actual: pl.DataFrame, forecast: pl.DataFrame, horizon: int = HORIZON_WEEKS) -> float:
    """WAPE (percent) over weeks < horizon. Frames: external_code, week, sales / forecast."""
    j = actual.filter(pl.col("week") < horizon).join(
        forecast.filter(pl.col("week") < horizon), on=["external_code", "week"], how="inner"
    )
    if j.height != actual.filter(pl.col("week") < horizon).height:
        raise ReproError("forecast does not cover every (product, week) of the actuals")
    num = j.select((pl.col("sales") - pl.col("forecast")).abs().sum()).item()
    den = j.select(pl.col("sales").sum()).item()
    return float(100.0 * num / den)


@dataclass(frozen=True)
class GtmWrapper:
    """Runs the user's own local GTM-Transformer install (never cloned, installed or vendored here)."""

    install_path: Path
    python: str = sys.executable

    def check(self) -> None:
        if not self.install_path.is_dir():
            raise ReproError(
                f"GTM-Transformer local install not found at {self.install_path!s}; set gtm.install_path in config.yaml"
            )
        for f in ("forecast.py", "train.py", "LICENSE"):
            if not (self.install_path / f).is_file():
                raise ReproError(f"{self.install_path / f} missing: not an official GTM-Transformer checkout")

    def forecast_command(self, data_folder: Path, ckpt: Path, trend_len: int = 52, seed: int = 21) -> list[str]:
        folder = str(data_folder).rstrip("/") + "/"  # official script concatenates strings
        return [
            self.python, "forecast.py", "--data_folder", folder, "--ckpt_path", str(ckpt),
            "--trend_len", str(trend_len), "--seed", str(seed),
        ]  # fmt: skip

    def run_forecast(self, data_folder: Path, ckpt: Path, trend_len: int = 52, seed: int = 21) -> None:
        self.check()
        subprocess.run(self.forecast_command(data_folder, ckpt, trend_len, seed), cwd=self.install_path, check=True)


def report_markdown(reproduced: float | None, cfg: dict[str, Any], blocked: list[str]) -> str:
    rep = "PENDING (not run)" if reproduced is None else f"{reproduced:.1f}"
    lines = [
        "# VISUELLE / GTM-Transformer reproduction report (RESEARCH ONLY)",
        "",
        "| quantity | WAPE (%) | source |",
        "|---|---|---|",
        f"| **Paper-reported** | {PAPER['wape_reported']} | {PAPER['table']}; {PAPER['url']} (accessed {PAPER['accessed']}) |",
        f"| **Reproduced by us** | {rep} | eval/{cfg.get('id', 'exp03_visuelle_gtm')}__complete/ |",
        "",
        "The two numbers are labelled separately; the reproduced number is never substituted by the paper number.",
        "",
        "## Blocked items",
        *([f"- {b}" for b in blocked] or ["- none"]),
    ]
    return "\n".join(lines) + "\n"


def blocked_reasons(cfg: dict[str, Any], repo_root: Path) -> list[str]:
    """Everything that currently prevents a real reproduction run (empty list = can run)."""
    out = []
    data = cfg.get("data", {})
    if data.get("licence_status") != "verified":
        out.append(
            f"data: VISUELLE licence status is {data.get('licence_status')!r} (no licence text found); "
            "data use is blocked until the terms are verified"
        )
    acc = repo_root / "data" / data.get("flavour", "visuelle") / "metadata" / "licence_acceptance.json"
    if not acc.is_file():
        out.append(f"data: no interactive licence acceptance recorded ({acc.relative_to(repo_root)})")
    raw = repo_root / data.get("raw_dir", "data/visuelle/input/raw")
    if not any(raw.rglob("test.csv")) if raw.is_dir() else True:
        out.append(f"data: VISUELLE train.csv/test.csv not present under {raw.relative_to(repo_root)}")
    gtm = cfg.get("gtm", {})
    if not gtm.get("install_path"):
        out.append("model: GTM-Transformer local install not found (gtm.install_path is empty); not cloned here")
    else:
        try:
            GtmWrapper(Path(gtm["install_path"]), gtm.get("python") or sys.executable).check()
        except ReproError as exc:
            out.append(f"model: {exc}")
    if not gtm.get("ckpt_path") or not Path(gtm["ckpt_path"]).is_file():
        out.append("model: gtm.ckpt_path (your trained checkpoint) not set or missing")
    return out


def run_reproduction(cfg_path: Path, out: Path) -> dict[str, Any]:
    """Write ``out/report.md``. Raises :class:`ReproError` (after writing the report) when blocked."""
    import yaml

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    repo_root = cfg_path.resolve().parents[2]
    blocked = blocked_reasons(cfg, repo_root)
    out.mkdir(parents=True, exist_ok=False)
    reproduced: float | None = None
    if not blocked:  # pragma: no cover - needs the user's licensed data and local GTM install
        data = cfg["data"]
        raw = next((repo_root / data["raw_dir"]).rglob("test.csv")).parent
        adapt_visuelle(raw, repo_root / "data", data.get("flavour", "visuelle"))
        gtm = cfg["gtm"]
        w = GtmWrapper(Path(gtm["install_path"]), gtm.get("python") or sys.executable)
        p = cfg["protocol"]
        w.run_forecast(raw, Path(gtm["ckpt_path"]), p["trend_len_weeks"], p["seed"])
        blocked.append("reproduced WAPE extraction from GTM results/*.pth must be checked by a Scientist first")
    (out / "report.md").write_text(report_markdown(reproduced, cfg, blocked), encoding="utf-8")
    res = {"experiment": cfg.get("id"), "usage_tag": "research_only", "blocked": blocked, "reproduced_wape": reproduced}
    (out / "results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    if blocked:
        raise ReproError("BLOCKED: " + "; ".join(blocked))
    return res  # pragma: no cover
