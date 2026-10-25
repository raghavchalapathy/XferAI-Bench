"""Data tiers: every run says whether it used synthetic data, a sample of real data, or the complete dataset.

The tier is recorded in run_manifest.json, metrics.json, leaderboard.csv, report.html, summary.md and experiment
results. Runs from different tiers are never mixed in one comparison or summary table (exit 2).
"""

from __future__ import annotations

from collections.abc import Iterable

TIERS = ("synthetic", "sample", "complete")
TIER_TEXT = {
    "synthetic": "synthetic data (interface test only)",
    "sample": "a sample of real data (not the complete dataset)",
    "complete": "the complete dataset",
}


class TierError(ValueError):
    """Invalid or inconsistent data tier."""


class TierMixError(TierError):
    """Runs from different data tiers were combined."""


def resolve_tier(requested: str | None, synthetic: bool) -> str:
    """Tier for a run. Default: 'synthetic' for synthetic data, 'complete' otherwise."""
    tier = requested or ("synthetic" if synthetic else "complete")
    if tier not in TIERS:
        raise TierError(f"data tier must be one of {list(TIERS)}, got {tier!r}")
    if synthetic and tier != "synthetic":
        raise TierError(
            f"this dataset is synthetic (metadata dataset.synthetic: true); its tier must be 'synthetic', not {tier!r}"
        )
    if not synthetic and tier == "synthetic":
        raise TierError("tier 'synthetic' is only for generated data; use 'sample' or 'complete' for real data")
    return tier


def require_single_tier(tiers: Iterable[tuple[str, str | None]], what: str = "runs") -> str:
    """Refuse to combine items from different tiers. ``tiers`` yields (label, tier); a missing tier is 'unlabeled'."""
    seen: dict[str, list[str]] = {}
    for label, tier in tiers:
        seen.setdefault(tier or "unlabeled", []).append(label)
    if len(seen) > 1:
        detail = "; ".join(f"{t}: {', '.join(v)}" for t, v in sorted(seen.items()))
        raise TierMixError(f"refusing to mix data tiers in one view of {what} ({detail}). Compare runs of one tier.")
    return next(iter(seen), "unlabeled")
