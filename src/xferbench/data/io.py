"""Read CSV or Parquet sources into the canonical Arrow schemas, then to pandas."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from xferbench.contracts.metadata import Metadata, TableSource
from xferbench.contracts.tables import TABLES, TableSpec
from xferbench.data.issues import DataError, Issue
from xferbench.util import hash_frame, hash_obj

ID_COLUMNS = {"item_id", "fpg_id", "launch_id", "pair_id", "scope_id", "donor_scope_id", "cohort_id"}


@dataclass
class Dataset:
    metadata: Metadata
    base_dir: Path
    tables: dict[str, pd.DataFrame]
    table_hashes: dict[str, str] = field(default_factory=dict)
    load_issues: list[Issue] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        return hash_obj(dict(sorted(self.table_hashes.items())))

    def has(self, name: str) -> bool:
        return name in self.tables

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]


def resolve_path(base_dir: Path, path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else (base_dir / p)


def read_header(path: Path, fmt: str) -> list[str]:
    if fmt == "parquet":
        return list(pq.read_schema(path).names)
    with open(path, newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh), [])


def _read_raw(path: Path, fmt: str) -> pa.Table:
    if fmt == "parquet":
        return pq.read_table(path)
    names = read_header(path, fmt)
    return pacsv.read_csv(
        path,
        convert_options=pacsv.ConvertOptions(
            column_types={n: pa.string() for n in names},
            strings_can_be_null=True,
            null_values=[""],
        ),
    )


def _cast(arr: pa.ChunkedArray, target: pa.DataType, table: str, col: str, issues: list[Issue]) -> pa.ChunkedArray:
    src = arr.type
    if src.equals(target):
        return arr
    try:
        if pa.types.is_string(target) or pa.types.is_large_string(target):
            if pa.types.is_integer(src) or pa.types.is_floating(src):
                issues.append(
                    Issue(
                        "warning",
                        "id_stored_as_number",
                        f"column stored as {src}; converted to string. Leading zeros cannot be recovered.",
                        table,
                        col,
                        suggestion="Store identifiers as strings in the source files.",
                    )
                )
                if pa.types.is_floating(src):
                    arr = pc.cast(arr, pa.int64())
            return pc.cast(arr, target)
        if pa.types.is_date32(target):
            if pa.types.is_string(src) or pa.types.is_large_string(src):
                arr = pc.cast(pc.strptime(arr, format="%Y-%m-%d", unit="s", error_is_null=False), pa.date32())
                return arr
            if pa.types.is_timestamp(src):
                return pc.cast(arr, pa.date32())
        if pa.types.is_integer(target) and (pa.types.is_string(src) or pa.types.is_floating(src)):
            as_float = pc.cast(arr, pa.float64())
            rounded = pc.round(as_float)
            bad = pc.sum(pc.cast(pc.not_equal(as_float, rounded), pa.int64())).as_py() or 0
            if bad:
                raise pa.ArrowInvalid(f"{bad} non-integer values")
            return pc.cast(rounded, target)
        return pc.cast(arr, target)
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError) as exc:
        issues.append(
            Issue(
                "error",
                "type_cast_failed",
                f"cannot convert {src} to {target}: {exc}",
                table,
                col,
                suggestion="Fix the values or the column mapping; dates must be ISO YYYY-MM-DD.",
            )
        )
        return pa.chunked_array([pa.nulls(len(arr), type=target)])


def _to_pandas(table: pa.Table) -> pd.DataFrame:
    df = table.to_pandas(date_as_object=False)
    for f in table.schema:
        if pa.types.is_date32(f.type) or pa.types.is_timestamp(f.type):
            df[f.name] = pd.to_datetime(df[f.name]).astype("datetime64[ns]")
        elif pa.types.is_string(f.type):
            df[f.name] = df[f.name].astype(object).where(df[f.name].notna(), None)
    return df


def load_table(
    spec: TableSpec, src: TableSource, base_dir: Path, metadata: Metadata, issues: list[Issue]
) -> pd.DataFrame | None:
    path = resolve_path(base_dir, src.path)
    if not path.exists():
        issues.append(
            Issue(
                "error",
                "file_not_found",
                f"{path} does not exist",
                spec.name,
                suggestion="Fix tables.<name>.path in metadata (relative paths resolve from the metadata file).",
            )
        )
        return None
    if (src.format == "parquet" and path.suffix.lower() == ".csv") or (
        src.format == "csv" and path.suffix.lower() == ".parquet"
    ):
        issues.append(
            Issue("warning", "format_suffix_mismatch", f"declared {src.format} but file is {path.suffix}", spec.name)
        )
    try:
        raw = _read_raw(path, src.format)
    except Exception as exc:
        issues.append(Issue("error", "read_failed", f"could not read {path}: {exc}", spec.name))
        return None
    present = set(raw.column_names)
    arrays: dict[str, pa.ChunkedArray] = {}
    for col in spec.columns:
        source_col = src.columns.get(col.name, col.name)
        if source_col not in present:
            if col.required:
                issues.append(
                    Issue(
                        "error",
                        "missing_column",
                        f"required column '{col.name}' (source '{source_col}') not found; available: {sorted(present)}",
                        spec.name,
                        col.name,
                        suggestion=f"Map it with tables.{spec.name}.columns.{col.name} = '<your column>'.",
                    )
                )
            arrays[col.name] = pa.chunked_array([pa.nulls(raw.num_rows, type=col.type)])
            continue
        arrays[col.name] = _cast(raw.column(source_col), col.type, spec.name, col.name, issues)
    extras = list(src.extra_columns)
    if spec.name == "locations":
        extras += [c for c in metadata.features.demographic_share_columns if c not in extras]
    for extra in extras:
        if extra not in present:
            issues.append(
                Issue("error", "missing_declared_column", f"declared column '{extra}' not found", spec.name, extra)
            )
            continue
        arrays[extra] = _cast(raw.column(extra), pa.float64(), spec.name, extra, issues)
    table = pa.table(arrays)
    return _to_pandas(table)


def load_dataset(metadata: Metadata, base_dir: Path, *, verify_hash: bool = True) -> Dataset:
    issues: list[Issue] = []
    tables: dict[str, pd.DataFrame] = {}
    for name, src in metadata.tables.items():
        df = load_table(TABLES[name], src, base_dir, metadata, issues)
        if df is not None:
            tables[name] = df
    if any(i.severity == "error" for i in issues):
        raise DataError(issues)
    ds = Dataset(metadata=metadata, base_dir=base_dir, tables=tables, load_issues=issues)
    ds.table_hashes = {n: hash_frame(df, TABLES[n].key) for n, df in tables.items()}
    if verify_hash and metadata.dataset.expected_hash and metadata.dataset.expected_hash != ds.content_hash:
        raise DataError(
            [
                Issue(
                    "error",
                    "dataset_hash_mismatch",
                    f"expected {metadata.dataset.expected_hash}, found {ds.content_hash}",
                    None,
                    suggestion="Data changed since metadata was written; review changes, then update dataset.expected_hash.",
                )
            ]
        )
    return ds


def load_from_metadata_path(metadata_path: Path, *, verify_hash: bool = True) -> Dataset:
    from xferbench.contracts.metadata import load_metadata

    md = load_metadata(metadata_path)
    return load_dataset(md, metadata_path.resolve().parent, verify_hash=verify_hash)
