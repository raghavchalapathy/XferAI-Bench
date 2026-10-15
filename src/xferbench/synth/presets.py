"""Bounded, deterministic synthetic presets. ``stress`` is never a default."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace


@dataclass(frozen=True)
class SynthConfig:
    preset: str
    seed: int
    n_items: int
    n_established_fpgs: int
    new_fpgs: dict[str, int]
    items_per_new_fpg: int
    e_launches: dict[str, int]
    origins_per_stage: dict[str, int]
    households_median: float = 3000.0
    history_start: str = "2019-01-07"
    last_week: str = "2026-03-23"
    stage_windows: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {
            "train": ("2021-01-04", "2021-12-27"),
            "validation": ("2023-01-09", "2023-12-25"),
            "test": ("2025-01-06", "2025-03-31"),
        }
    )
    reporting_delay_days: int = 7
    donor_offer_prob: float = 0.55
    min_donor_fpgs_per_item: int = 3
    target_zero_fraction: float = 0.8
    nb_shape: float = 1.2
    stockout_prob: float = 0.03
    missing_prob: float = 0.01
    late_report_prob: float = 0.02
    dead_pair_fraction: float = 0.06
    burst_prob: float = 0.01
    propensity_noise_sigma: float = 0.2
    include_edge_fixtures: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, SynthConfig] = {
    "tiny": SynthConfig(
        preset="tiny",
        seed=42,
        n_items=12,
        n_established_fpgs=10,
        new_fpgs={"train": 3, "validation": 2, "test": 2},
        items_per_new_fpg=4,
        e_launches={"train": 10, "validation": 8, "test": 8},
        origins_per_stage={"train": 8, "validation": 6, "test": 4},
    ),
    "small": SynthConfig(
        preset="small",
        seed=42,
        n_items=40,
        n_established_fpgs=30,
        new_fpgs={"train": 6, "validation": 4, "test": 4},
        items_per_new_fpg=8,
        e_launches={"train": 40, "validation": 30, "test": 30},
        origins_per_stage={"train": 26, "validation": 26, "test": 13},
    ),
    "stress": SynthConfig(
        preset="stress",
        seed=42,
        n_items=200,
        n_established_fpgs=120,
        new_fpgs={"train": 20, "validation": 15, "test": 15},
        items_per_new_fpg=20,
        e_launches={"train": 300, "validation": 200, "test": 200},
        origins_per_stage={"train": 52, "validation": 51, "test": 13},
    ),
}


def get_preset(name: str, seed: int | None = None) -> SynthConfig:
    if name not in PRESETS:
        raise KeyError(f"unknown preset '{name}'; choose one of {sorted(PRESETS)}")
    cfg = PRESETS[name]
    return replace(cfg, seed=seed) if seed is not None else cfg
