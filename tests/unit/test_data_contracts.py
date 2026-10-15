from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from xferbench.contracts.metadata import Metadata, load_metadata
from xferbench.data.io import Dataset, load_from_metadata_path
from xferbench.data.issues import DataError
from xferbench.domains.retail.validation import validate_retail
from xferbench.scaffold import export_schemas, metadata_template


def _codes(ds: Dataset) -> set[str]:
    return {i.code for i in validate_retail(ds) if i.severity == "error"}


def _mutated(ds: Dataset, table: str, fn) -> Dataset:  # type: ignore[no-untyped-def]
    tables = {k: v.copy() for k, v in ds.tables.items()}
    tables[table] = fn(tables[table])
    return Dataset(ds.metadata, ds.base_dir, tables)


def test_regeneration_is_deterministic(tiny: Dataset, tmp_path: Path) -> None:
    from xferbench.synth.generator import generate
    from xferbench.synth.presets import get_preset

    generate(get_preset("tiny", seed=42), tmp_path / "a", formats=("parquet",))
    again = load_from_metadata_path(tmp_path / "a" / "metadata.json")
    assert again.content_hash == tiny.content_hash
    generate(get_preset("tiny", seed=7), tmp_path / "b", formats=("parquet",))
    assert load_from_metadata_path(tmp_path / "b" / "metadata.json").content_hash != tiny.content_hash


def test_generated_data_validates_cleanly(tiny: Dataset) -> None:
    issues = validate_retail(tiny)
    assert not [i for i in issues if i.severity == "error"]


def test_csv_and_parquet_load_identically(tiny_dir: Path, tiny: Dataset) -> None:
    csv = load_from_metadata_path(tiny_dir / "metadata.csv.json")
    assert csv.content_hash == tiny.content_hash
    for name, df in tiny.tables.items():
        pd.testing.assert_frame_equal(
            df.reset_index(drop=True), csv.tables[name].reset_index(drop=True), check_dtype=False, obj=name
        )


def test_identifiers_keep_leading_zeros(tiny: Dataset) -> None:
    assert tiny["items"]["item_id"].str.startswith("0").any()


def test_hash_mismatch_is_rejected(tiny_dir: Path, tmp_path: Path) -> None:
    md = json.loads((tiny_dir / "metadata.json").read_text())
    md["dataset"]["expected_hash"] = "0" * 64
    for t in md["tables"].values():
        t["path"] = str(tiny_dir / t["path"])
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(md))
    with pytest.raises(DataError, match="dataset_hash_mismatch"):
        load_from_metadata_path(p)


def test_metadata_is_strict_and_declarative() -> None:
    base = metadata_template()
    Metadata.model_validate(base)
    bad = copy.deepcopy(base)
    bad["features"]["propensity"]["formula"] = "__import__('os').system('x')"
    with pytest.raises(ValidationError):
        Metadata.model_validate(bad)
    truth = copy.deepcopy(base)
    truth["tables"]["observations"]["path"] = "_synthetic_truth/observations.parquet"
    with pytest.raises(ValidationError, match="hidden synthetic truth"):
        Metadata.model_validate(truth)
    missing = copy.deepcopy(base)
    del missing["tables"]["launches"]
    with pytest.raises(ValidationError):
        Metadata.model_validate(missing)


def test_propensity_must_be_a_rate_not_probability() -> None:
    base = metadata_template()
    base["features"]["propensity"]["unit"] = "probability"
    with pytest.raises(ValidationError):
        Metadata.model_validate(base)


def test_column_mapping(tiny_dir: Path, tmp_path: Path) -> None:
    df = pd.read_csv(tiny_dir / "data" / "items.csv", dtype=str).rename(columns={"category": "dept"})
    df.to_csv(tmp_path / "items.csv", index=False)
    md = load_metadata(tiny_dir / "metadata.csv.json").model_dump(mode="json")
    for t in md["tables"].values():
        t["path"] = str(tiny_dir / t["path"])
    md["tables"]["items"] = {"path": str(tmp_path / "items.csv"), "format": "csv", "columns": {"category": "dept"}}
    md["dataset"]["expected_hash"] = None
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(md))
    ds = load_from_metadata_path(p)
    assert ds["items"]["category"].notna().all()


@pytest.mark.parametrize(
    "table,mutate,code",
    [
        ("observations", lambda d: pd.concat([d, d.head(1)]), "duplicate_key"),
        ("observations", lambda d: d.assign(units=d["units"].where(d.index != d.index[0], -1.0)), "negative_units"),
        (
            "observations",
            lambda d: d.assign(
                week_start=d["week_start"].where(d.index != d.index[0], d["week_start"] + pd.Timedelta(days=1))
            ),
            "week_boundary",
        ),
        ("observations", lambda d: d.assign(known_at=d["week_start"]), "known_before_interval_end"),
        ("offers", lambda d: d.iloc[1:], "observation_without_offer"),
        ("locations", lambda d: d.assign(households=0.0), "nonpositive_households"),
        ("launches", lambda d: d.assign(origin=d["origin"] + pd.Timedelta(days=7)), "origin_rule"),
    ],
)
def test_validation_catches_errors(tiny: Dataset, table: str, mutate, code: str) -> None:  # type: ignore[no-untyped-def]
    assert code in _codes(_mutated(tiny, table, mutate))


def test_share_sum_validation(tiny: Dataset) -> None:
    col = tiny.metadata.features.demographic_share_columns[0]
    assert "share_sum" in _codes(_mutated(tiny, "locations", lambda d: d.assign(**{col: d[col] + 0.3})))


def test_c0_violation_detected(tiny: Dataset) -> None:
    la = tiny["launches"].iloc[0]

    def add_history(obs: pd.DataFrame) -> pd.DataFrame:
        wk = la["origin"] - pd.Timedelta(days=70)
        row = {
            "item_id": la["item_id"],
            "fpg_id": la["fpg_id"],
            "week_start": wk,
            "week_end": wk + pd.Timedelta(days=7),
            "units": 0.0,
            "observation_state": "observed",
            "known_at": wk + pd.Timedelta(days=14),
        }
        return pd.concat([obs, pd.DataFrame([row])], ignore_index=True)

    assert "c0_violation" in _codes(_mutated(tiny, "observations", add_history))


def test_export_schemas(tmp_path: Path) -> None:
    paths = export_schemas(tmp_path)
    names = {p.name for p in paths}
    assert {"metadata.schema.json", "selection-policy.schema.json", "observations.schema.json"} <= names
    json.loads((tmp_path / "metadata.schema.json").read_text())
