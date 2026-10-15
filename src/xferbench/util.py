"""Small shared helpers: strict JSON, hashing and atomic file writes."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCHEMA_VERSION = "1.0"


def to_jsonable(value: Any) -> Any:
    """Convert values to strict-JSON-safe Python objects.

    NaN, +/-Infinity and pandas/NumPy missing markers become ``None``; dates become ISO strings.
    """
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        if value == value.normalize() and value.tzinfo is None:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump(mode="json"))
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def dumps_strict(obj: Any, *, indent: int | None = 2) -> str:
    """Serialize to JSON, refusing NaN/Infinity after normalization."""
    return json.dumps(to_jsonable(obj), indent=indent, sort_keys=False, allow_nan=False, ensure_ascii=False)


def canonical_json(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_obj(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def hash_frame(df: pd.DataFrame, sort_by: Iterable[str] | None = None) -> str:
    """Deterministic content hash of a table, independent of row order and source format."""
    frame = df.copy()
    cols = sorted(frame.columns)
    frame = frame[cols]
    keys = [c for c in (sort_by or cols) if c in frame.columns]
    if keys and len(frame):
        frame = frame.sort_values(keys, kind="mergesort").reset_index(drop=True)
    for c in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[c]):
            frame[c] = frame[c].dt.strftime("%Y-%m-%d")
    text = frame.to_csv(index=False, float_format="%.10g", na_rep="<NA>", lineterminator="\n")
    return sha256_text(text)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, dumps_strict(obj) + "\n")


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def atomic_write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_csv(path: Path, df: pd.DataFrame, float_format: str | None = None) -> None:
    """Write CSV with ISO dates; floats keep full precision unless ``float_format`` is given."""
    frame = df.copy()
    for c in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[c]):
            frame[c] = frame[c].dt.strftime("%Y-%m-%d")
    atomic_write_text(path, frame.to_csv(index=False, lineterminator="\n", float_format=float_format))


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
