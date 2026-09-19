"""Publish the engine outputs (panel, scores, alerts) to the ``xray`` schema.

One row per entity-month and one column per attribute, so every number the
engine measured can be queried with SQL. Idempotent per ``dataset_hash``: a
re-publish replaces that dataset's rows inside one transaction.
"""

import io
import json
from pathlib import Path

import polars as pl
import psycopg
from psycopg import sql

from .engine_tables import (
    ALERTS_COLUMNS,
    ALERTS_TABLE,
    PANEL_COLUMNS,
    PANEL_TABLE,
    SCORES_COLUMNS,
    SCORES_TABLE,
    Column,
)
from .ingest import postgres_dsn

SCHEMA = "xray"
RUN_COLUMNS = ("dataset_hash", "params_hash")


def _json(value: object) -> str | None:
    if isinstance(value, pl.Series):  # polars hands list cells over as Series
        value = value.to_list()
    return None if value is None else json.dumps(value, default=str, ensure_ascii=False)


def _flatten(frame: pl.DataFrame, spec: tuple[Column, ...], run: dict[str, str]) -> pl.DataFrame:
    expected = {source for _, _, source, _ in spec}
    if expected != set(frame.columns):
        drift = sorted(expected ^ set(frame.columns))
        raise ValueError(f"Engine output drifted from backend/app/engine_tables.py: {drift}")
    names = [name for name, *_ in spec]
    columns = [pl.lit(run[name]).alias(name) for name in RUN_COLUMNS if name not in names]
    for name, kind, source, field in spec:
        if field is not None:
            columns.append(pl.col(source).struct.field(field).alias(name))
        elif kind == "jsonb":
            columns.append(pl.col(source).map_elements(_json, return_dtype=pl.String, skip_nulls=False).alias(name))
        else:
            columns.append(pl.col(source).alias(name))
    return frame.select(columns)


def _copy(cursor: psycopg.Cursor, table: str, frame: pl.DataFrame, dataset_hash: str) -> int:
    target = sql.SQL("{}.{}").format(sql.Identifier(SCHEMA), sql.Identifier(table))
    cursor.execute(sql.SQL("DELETE FROM {} WHERE dataset_hash = %s").format(target), (dataset_hash,))
    buffer = io.BytesIO()
    frame.write_csv(buffer)
    statement = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
        target, sql.SQL(", ").join(map(sql.Identifier, frame.columns))
    )
    with cursor.copy(statement) as copy:
        copy.write(buffer.getvalue())
    return frame.height


def publish_outputs(out_dir: Path, database_url: str) -> tuple[str, dict[str, int]]:
    """Load ``panel.parquet``, ``scores.parquet`` and ``alerts.parquet`` of an engine run."""
    scores = pl.read_parquet(out_dir / "scores.parquet")
    run = {name: scores[name][0] for name in RUN_COLUMNS}
    tables = (
        (PANEL_TABLE, pl.read_parquet(out_dir / "panel.parquet"), PANEL_COLUMNS),
        (SCORES_TABLE, scores, SCORES_COLUMNS),
        (ALERTS_TABLE, pl.read_parquet(out_dir / "alerts.parquet"), ALERTS_COLUMNS),
    )
    counts: dict[str, int] = {}
    with psycopg.connect(postgres_dsn(database_url)) as connection, connection.cursor() as cursor:
        for table, frame, spec in tables:
            counts[table] = _copy(cursor, table, _flatten(frame, spec, run), run["dataset_hash"])
    return run["dataset_hash"], counts
