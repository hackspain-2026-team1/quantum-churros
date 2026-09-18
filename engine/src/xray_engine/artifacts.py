from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl


def read_entity_scores(path: Path, entity_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return (
        pl.scan_parquet(path)
        .filter(pl.col("entity_id") == entity_id)
        .sort("month")
        .collect()
        .to_dicts()
    )


def read_latest_score(path: Path, entity_id: str) -> dict[str, Any] | None:
    records = read_entity_scores(path, entity_id)
    return records[-1] if records else None


def read_entity_series(
    path: Path, entity_id: str, key: str
) -> tuple[list[str], list[float]]:
    if not path.exists():
        return [], []
    schema = pl.scan_parquet(path).collect_schema()
    if "series" not in schema.names():
        return [], []
    frame = (
        pl.scan_parquet(path)
        .filter(pl.col("entity_id") == entity_id)
        .sort("month")
        .select("month", pl.col("series").struct.field(key).alias("value"))
        .collect()
    )
    if frame.is_empty():
        return [], []
    months = [str(month) for month in frame["month"].to_list()]
    values = [float(value) if value is not None else 0.0 for value in frame["value"].to_list()]
    return months, values
