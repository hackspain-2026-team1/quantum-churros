"""Orchestrator: folder with the eight CSVs -> scores, alerts and profile cards.

``io -> cleaning -> panel -> (pillars -> aggregate -> trajectory) per entity
-> alerts -> profile``. Every entity is scored from its own rows (plus the
group row of the same month for the liquidity inheritance) and ``Params``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from . import cleaning, io, panel as panel_module, profile
from .aggregate import aggregate, delta_parts, explain
from .alerts import build_alerts
from .contracts import (
    ENGINE_VERSION,
    FEATURE_VERSION,
    PILLAR_KEYS,
    SERIES_KEYS,
    SNAPSHOT_SCHEMA,
    Alert,
    EntityMonth,
    EntitySnapshot,
    IndustryClassification,
    PanelRow,
    Params,
    ProfileCard,
)
from .params import load_params
from .pillars import compute_pillars, smooth_pillars
from .trajectory import trajectory

# Deprecated alias kept for older readers of the score run metadata.
MODEL_VERSION = ENGINE_VERSION


@dataclass(frozen=True)
class ScoreResult:
    snapshots: pl.DataFrame  # SNAPSHOT_SCHEMA, sorted by (entity_kind, entity_id, month)
    panel: pl.DataFrame  # PANEL_COLUMNS
    months: tuple[EntityMonth, ...]  # same order as snapshots
    alerts: tuple[Alert, ...]
    profiles: Mapping[str, ProfileCard]
    params: Params
    dataset_hash: str
    window: io.Window


def score_entity(
    rows: Sequence[PanelRow],
    params: Params,
    group_rows: Mapping[date, PanelRow] | None = None,
) -> list[EntityMonth]:
    """Scores one entity month by month, past-only.

    ``rows`` belong to a single entity; ``group_rows`` (companies only) maps a
    month to the row of the owning group.
    """
    history = []
    months: list[EntityMonth] = []
    previous: dict[str, float | None] | None = None
    for row in sorted(rows, key=lambda item: item.month):
        group_row = group_rows.get(row.month) if group_rows else None
        pillars = smooth_pillars(compute_pillars(row, params, group_row), previous, params)
        parts = aggregate(pillars, row, params)
        history.append(parts)
        months.append(EntityMonth(row, pillars, parts, trajectory(history, params)))
        previous = {key: pillars[key].score for key in PILLAR_KEYS}
    return months


def score_panel(panel: pl.DataFrame, params: Params) -> list[EntityMonth]:
    """Scores every entity of a ``PANEL_COLUMNS`` frame.

    Output sorted by (entity_kind, entity_id, month). Company rows receive the
    group row of the same month as context for the liquidity inheritance.
    """
    panel_module.validate_panel(panel)
    by_entity: dict[tuple[str, str], list[PanelRow]] = defaultdict(list)
    for row in panel_module.iter_rows(panel):
        by_entity[(row.entity_kind, row.entity_id)].append(row)
    group_rows = {
        entity_id: {row.month: row for row in rows}
        for (kind, entity_id), rows in by_entity.items()
        if kind == "group"
    }
    months: list[EntityMonth] = []
    for (kind, _), rows in sorted(by_entity.items()):
        context = group_rows.get(rows[0].group_id) if kind == "company" else None
        months.extend(score_entity(rows, params, context))
    return months


def _by_pillar(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: values.get(key) for key in PILLAR_KEYS}


def _bounded(value: float) -> float:
    # float noise around the ends of the scale must not fail validation
    return min(100.0, max(0.0, value))


def _series(month: EntityMonth) -> dict[str, float | None]:
    row, pillars = month.row, month.pillars
    values: dict[str, float | None] = {
        "cash_month_end": row.cash_month_end,
        "cash_intra_month_min": row.cash_intra_month_min,
        "headroom": row.headroom,
        "drawn": row.drawn,
        "op_inflow_1m": row.op_inflow_1m,
        "op_outflow_1m": row.op_outflow_1m,
        "buffer_days": pillars["liquidity"].inputs.get("buffer_days_month_end"),
        "ap_days_beyond_terms": pillars["payments"].inputs.get("days_beyond_terms"),
        "ar_days_beyond_terms": pillars["collections"].inputs.get("days_beyond_terms"),
        "activity_ratio": pillars["activity"].inputs.get("ratio"),
        "dscr": pillars["debt"].inputs.get("dscr"),
        "lines_utilisation": pillars["debt"].inputs.get("utilisation"),
    }
    return {key: values[key] for key in SERIES_KEYS}


def build_snapshot(
    month: EntityMonth,
    previous: EntityMonth | None,
    params: Params,
    dataset_hash: str,
) -> EntitySnapshot:
    """``EntityMonth`` -> serialisable snapshot, deprecated v1 fields included.

    ``previous`` is the month before of the same entity (None on the first
    one: ``delta`` 0 and no ``delta_parts``).
    """
    row, parts, verdict = month.row, month.parts, month.trajectory
    change = delta_parts(parts, previous.parts) if previous is not None else None
    return EntitySnapshot(
        entity_kind=row.entity_kind,
        entity_id=row.entity_id,
        group_id=row.group_id,
        month=row.month,
        score=_bounded(parts.score),
        level_raw=parts.level_raw,
        base=parts.base,
        pillars=_by_pillar(parts.pillar_scores),
        pillars_raw={key: month.pillars[key].raw_score for key in PILLAR_KEYS},
        weights_effective=_by_pillar(parts.weights_effective),
        contributions=_by_pillar(parts.contributions),
        penalty=parts.penalty,
        cap_adjustment=parts.cap_adjustment,
        caps_fired=list(parts.caps_fired),
        branch=parts.branch,
        confidence=parts.confidence,
        confidence_parts=parts.confidence_parts,
        delta=change.score if change is not None else 0.0,
        delta_parts=change,
        trend=verdict.direction,
        persistence_months=verdict.persistence_months,
        detected_since=verdict.detected_since,
        trajectory=verdict,
        gates={key: list(month.pillars[key].gates) for key in PILLAR_KEYS},
        flags=list(parts.flags),
        abstained=parts.abstained,
        unlock_hint=parts.unlock_hint,
        months_observed=row.months_observed,
        perimeter_changed=row.perimeter_changed,
        drivers=explain(parts, month.pillars, params),
        series=_series(month),
        observed_score=_bounded(parts.level_raw),
        predicted_future_score=_bounded(parts.score),
        forecast_delta=0.0,
        shap_base_value=parts.base,
        explanation_residual=0.0,
        feature_version=FEATURE_VERSION,
        model_version=ENGINE_VERSION,
        engine_version=ENGINE_VERSION,
        params_hash=params.sha256,
        dataset_hash=dataset_hash,
    )


def snapshots_frame(snapshots: Sequence[EntitySnapshot]) -> pl.DataFrame:
    """Snapshots -> frame with ``SNAPSHOT_SCHEMA``; unrounded floats."""
    records = []
    for snapshot in snapshots:
        record = snapshot.model_dump()
        if record["delta_parts"] is not None:
            record["delta_parts"]["contributions"] = _by_pillar(
                record["delta_parts"]["contributions"]
            )
        record["gates"] = {key: record["gates"].get(key, []) for key in PILLAR_KEYS}
        record["series"] = {key: record["series"].get(key) for key in SERIES_KEYS}
        for name in ("pillars", "pillars_raw", "weights_effective", "contributions"):
            record[name] = _by_pillar(record[name])
        records.append({name: record[name] for name in SNAPSHOT_SCHEMA})
    return pl.DataFrame(records, schema=SNAPSHOT_SCHEMA)


def score_dataset(
    input_dir: Path,
    params: Params | None = None,
    *,
    cache_dir: Path = io.DEFAULT_CACHE_DIR,
    industry_override: Mapping[str, IndustryClassification] | None = None,
) -> ScoreResult:
    """Full run on a folder with the eight CSVs (any number of groups).

    ``params`` defaults to the verified reference file. ``industry_override``
    replaces the classifier output; it only reaches the profile cards.
    """
    params = params if params is not None else load_params()
    tables = io.load_tables(Path(input_dir), cache_dir)
    clean = cleaning.clean(tables, params)
    panel = panel_module.build_panel(clean, params)
    months = score_panel(panel, params)

    snapshots: list[EntitySnapshot] = []
    alerts: list[Alert] = []
    by_entity: dict[tuple[str, str], list[EntityMonth]] = defaultdict(list)
    for month in months:
        by_entity[(month.row.entity_kind, month.row.entity_id)].append(month)
    for _, entity_months in sorted(by_entity.items()):
        previous = None
        for month in entity_months:
            snapshots.append(build_snapshot(month, previous, params, tables.dataset_hash))
            previous = month
        alerts.extend(build_alerts(entity_months, params))

    industry = industry_override
    if industry is None:
        from .industry_classifier import classify_dataset

        industry = {item.entity_id: item for item in classify_dataset(Path(input_dir))[1]}
    return ScoreResult(
        snapshots=snapshots_frame(snapshots),
        panel=panel,
        months=tuple(months),
        alerts=tuple(alerts),
        profiles=profile.build_profiles(clean, panel, params, industry),
        params=params,
        dataset_hash=tables.dataset_hash,
        window=tables.window,
    )


_FLAT_EXCLUDED = ("drivers", "series", "trajectory", "delta_parts", "gates")


def flat_scores(snapshots: pl.DataFrame, entity_kind: str) -> pl.DataFrame:
    """CSV-friendly view of one entity kind: structs unnested with a prefix,
    lists joined with ``|``, nested detail columns dropped."""
    frame = snapshots.filter(pl.col("entity_kind") == entity_kind).drop(_FLAT_EXCLUDED)
    for name, dtype in frame.schema.items():
        if isinstance(dtype, pl.Struct):
            renamed = [
                pl.col(name).struct.field(item.name).alias(f"{name}_{item.name}")
                for item in dtype.fields
            ]
            frame = frame.with_columns(renamed).drop(name)
        elif isinstance(dtype, pl.List):
            frame = frame.with_columns(pl.col(name).list.join("|"))
    return frame


def write_outputs(result: ScoreResult, out_dir: Path) -> dict[str, Path]:
    """Writes ``scores.parquet`` (both kinds, every month), ``scores_groups.csv``,
    ``scores_companies.csv`` and ``alerts.parquet`` under ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scores": out_dir / "scores.parquet",
        "groups": out_dir / "scores_groups.csv",
        "companies": out_dir / "scores_companies.csv",
        "alerts": out_dir / "alerts.parquet",
    }
    result.snapshots.write_parquet(paths["scores"])
    flat_scores(result.snapshots, "group").write_csv(paths["groups"])
    flat_scores(result.snapshots, "company").write_csv(paths["companies"])
    alert_records = [asdict(alert) for alert in result.alerts]
    pl.DataFrame(alert_records, schema=ALERT_SCHEMA).write_parquet(paths["alerts"])
    return paths


ALERT_SCHEMA: dict[str, Any] = {
    "id": pl.String,
    "entity_kind": pl.String,
    "entity_id": pl.String,
    "group_id": pl.String,
    "month": pl.Date,
    "kind": pl.String,
    "state": pl.String,
    "title": pl.String,
    "detail": pl.String,
    "suppressed_by": pl.Struct({"reason": pl.String, "since": pl.Date, "until": pl.Date}),
}

__all__ = [
    "ALERT_SCHEMA",
    "ENGINE_VERSION",
    "FEATURE_VERSION",
    "MODEL_VERSION",
    "ScoreResult",
    "build_snapshot",
    "flat_scores",
    "score_dataset",
    "score_entity",
    "score_panel",
    "snapshots_frame",
    "write_outputs",
]
