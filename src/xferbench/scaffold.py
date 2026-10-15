"""Project templates and JSON-schema export."""

from __future__ import annotations

from pathlib import Path

from xferbench.contracts.metadata import (
    CohortSpec,
    DatasetInfo,
    FeatureSpec,
    Metadata,
    Rights,
    StageWindow,
    TableSource,
    metadata_json_schema,
)
from xferbench.contracts.selection import SelectionPolicy
from xferbench.contracts.splits import SplitManifest
from xferbench.contracts.tables import TABLES, field_dictionary_markdown, table_json_schemas
from xferbench.util import atomic_write_text, write_json

DEFAULT_STAGES = {
    "train": ("2021-01-04", "2021-12-27"),
    "validation": ("2023-01-09", "2023-12-25"),
    "test": ("2025-01-06", "2025-03-31"),
}


def metadata_template(fmt: str = "parquet", shares: list[str] | None = None) -> dict:
    md = Metadata(
        dataset=DatasetInfo(id="my_retail_dataset", version="v1", description="Replace with your description."),
        tables={n: TableSource(path=f"data/{n}.{fmt}", format=fmt) for n in TABLES},  # type: ignore[arg-type]
        features=FeatureSpec(demographic_share_columns=shares or []),
        cohorts=CohortSpec(
            stages={s: StageWindow(origin_start=a, origin_end=b) for s, (a, b) in DEFAULT_STAGES.items()}
        ),
        rights=Rights(data_owner="REPLACE: data owner", permitted_use="REPLACE: permitted use"),
    )
    return md.model_dump(mode="json")


def export_schemas(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, schema in (
        ("metadata.schema.json", metadata_json_schema()),
        ("selection-policy.schema.json", SelectionPolicy.model_json_schema()),
        ("splits.schema.json", SplitManifest.model_json_schema()),
    ):
        write_json(out / name, schema)
        paths.append(out / name)
    tables = out / "tables"
    for name, schema in table_json_schemas().items():
        write_json(tables / f"{name}.schema.json", schema)
        paths.append(tables / f"{name}.schema.json")
    atomic_write_text(out / "FIELD_DICTIONARY.md", field_dictionary_markdown())
    paths.append(out / "FIELD_DICTIONARY.md")
    return paths
