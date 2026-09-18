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
