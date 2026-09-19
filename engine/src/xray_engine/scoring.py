"""Orchestrator: folder with the eight CSVs -> scores, alerts and profile cards.

``io -> cleaning (-> invoices) -> panel -> (pillars -> aggregate -> carry
forward -> trajectory) per entity -> alerts -> profile``. Every entity is
scored from its own rows (plus the group row of the same month for the
liquidity inheritance) and ``Params``.

Stale months. ``aggregate`` decides per month whether the bank feed is live.
A month that is not live is first scored on its own, with penalty and caps
off, and is abstained with reason ``stale_feed``. If the entity has an earlier
live month, ``carry_forward`` then replaces the explanation block with the one
of the LAST LIVE month L, verbatim:

  copied from L : branch, pillar_scores, weights_effective, level_weighted,
                  penalty, cap_adjustment, caps_fired, base, contributions,
                  score, band, size_band
  kept from t   : month, months_observed, months_since_perimeter_change,
                  level (own level, penalty and caps off), feed_live = False,
                  confidence, confidence_parts, confidence_label, flags
                  (``stale_feed`` among them), abstained, abstain_reason,
                  unlock_hint
  set           : carried_from = L.month

The pillar results of a carried month are those of L with the gate
``carried_forward`` appended, so scores, notes and drivers describe the same
month as the number. The source is always a live month, never another carried
one: a long stale spell repeats L. Both identities of ``ScoreParts`` hold on a
carried month because the block is copied whole, and its month-on-month delta
is 0 term by term. Without an earlier live month nothing is copied and the
own arithmetic stands. The first live month after the spell is scored normally.
A carried month has no trajectory (reason ``stale_feed``) and can only emit
the ``stale_feed`` alert.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from . import cleaning, invoices as invoice_module, io, panel as panel_module, profile
from .aggregate import aggregate, delta_parts, explain
from .alerts import build_alerts
from .contracts import (
    CARRIED_GATE,
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
    PillarResult,
    ProfileCard,
    ScoreParts,
)
from .params import load_params
from .pillars import compute_pillars
from .trajectory import trajectories

# Deprecated alias kept for older readers of the score run metadata.
MODEL_VERSION = ENGINE_VERSION

# Fields of ScoreParts a carried month copies from the last live month.
CARRIED_FIELDS: tuple[str, ...] = (
    "branch",
    "pillar_scores",
    "weights_effective",
    "level_weighted",
    "penalty",
    "cap_adjustment",
    "caps_fired",
    "base",
    "contributions",
    "score",
    "band",
    "size_band",
)


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
    due_ar: pl.DataFrame  # open overdue AR invoices as of the window end


def carry_forward(own: ScoreParts, last_live: ScoreParts) -> ScoreParts:
    """Stale month: the explanation block of the last live month, verbatim.

    ``own`` is the stale month as ``aggregate`` scored it; ``last_live`` is the
    most recent earlier month with ``feed_live``. See the module docstring.
    """
    if own.feed_live or not last_live.feed_live:
        raise ValueError("carry_forward copies a live month into a stale one")
    copied = {name: getattr(last_live, name) for name in CARRIED_FIELDS}
    return replace(own, carried_from=last_live.month, **copied)


def carried_pillars(pillars: Mapping[str, PillarResult]) -> dict[str, PillarResult]:
    """Pillar results of the last live month, marked with ``CARRIED_GATE``."""
    return {
        key: replace(pillars[key], gates=(*pillars[key].gates, CARRIED_GATE))
        for key in PILLAR_KEYS
    }


def score_entity(
    rows: Sequence[PanelRow],
    params: Params,
    group_rows: Mapping[date, PanelRow] | None = None,
) -> list[EntityMonth]:
    """Scores one entity month by month, past-only.

    ``rows`` belong to a single entity; ``group_rows`` (companies only) maps a
    month to the row of the owning group. Stale months are carried forward from
    the last live month (module docstring); the trajectory reads the final
    parts, carried months included, in one forward pass: the verdict of a
    month never depends on later ones.
    """
    ordered = sorted(rows, key=lambda item: item.month)
    history: list[ScoreParts] = []
    shown: list[Mapping[str, PillarResult]] = []
    last_live: int | None = None
    for row in ordered:
        group_row = group_rows.get(row.month) if group_rows else None
        pillars = compute_pillars(row, params, group_row)
        parts = aggregate(pillars, row, params, group_row)
        if not parts.feed_live and last_live is not None:
            parts = carry_forward(parts, history[last_live])
            pillars = carried_pillars(shown[last_live])
        elif parts.feed_live:
            last_live = len(history)
        history.append(parts)
        shown.append(pillars)
    verdicts = trajectories(history, params)
    return [
        EntityMonth(row, pillars, parts, verdict)
        for row, pillars, parts, verdict in zip(ordered, shown, history, verdicts)
    ]


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
    # facts come from the row of the month; pillar inputs follow the pillars
    # shown for it (those of the last live month when carried)
    row, pillars = month.row, month.pillars
    values: dict[str, float | None] = {
        "cash_month_end": row.cash_month_end,
        "cash_intra_month_min": row.cash_intra_month_min,
        "headroom": row.headroom,
        "drawn": row.drawn,
        "op_inflow_1m": row.op_inflow_1m,
        "op_outflow_1m": row.op_outflow_1m,
        "debt_service_1m": row.debt_service_1m,
        "buffer_days": pillars["liquidity"].inputs.get("buffer_days_month_end"),
        "ap_days_beyond_terms": pillars["payments"].inputs.get("days_beyond_terms"),
        "ar_days_beyond_terms": pillars["collections"].inputs.get("days_beyond_terms"),
        "activity_coverage": pillars["activity"].inputs.get("coverage"),
        "activity_momentum": pillars["activity"].inputs.get("momentum"),
        "debt_burden": pillars["debt"].inputs.get("burden"),
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
    one: ``delta`` 0 and no ``delta_parts``). ``score`` is the number on screen
    (carried on a stale month) and ``level`` the own level of the month.
    """
    row, parts, verdict = month.row, month.parts, month.trajectory
    change = delta_parts(parts, previous.parts) if previous is not None else None
    return EntitySnapshot(
        entity_kind=row.entity_kind,
        entity_id=row.entity_id,
        group_id=row.group_id,
        month=row.month,
        score=_bounded(parts.score),
        band=parts.band,
        size_band=parts.size_band,
        level=parts.level,
        base=parts.base,
        pillars=_by_pillar(parts.pillar_scores),
        weights_effective=_by_pillar(parts.weights_effective),
        contributions=_by_pillar(parts.contributions),
        penalty=parts.penalty,
        cap_adjustment=parts.cap_adjustment,
        caps_fired=list(parts.caps_fired),
        branch=parts.branch,
        feed_live=parts.feed_live,
        carried_from=parts.carried_from,
        confidence=parts.confidence,
        confidence_label=parts.confidence_label,
        confidence_parts=parts.confidence_parts,
        delta=change.score if change is not None else 0.0,
        delta_parts=change,
        trend="stable" if verdict.direction == "perimeter_shift" else verdict.direction,
        persistence_months=verdict.persistence_months,
        detected_since=verdict.detected_since,
        trajectory=verdict,
        gates={key: list(month.pillars[key].gates) for key in PILLAR_KEYS},
        flags=list(parts.flags),
        abstained=parts.abstained,
        abstain_reason=parts.abstain_reason,
        unlock_hint=parts.unlock_hint,
        months_observed=row.months_observed,
        perimeter_changed=row.perimeter_changed,
        drivers=explain(parts, month.pillars, params),
        series=_series(month),
        observed_score=_bounded(parts.level),
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
        for name in ("pillars", "weights_effective", "contributions"):
            record[name] = _by_pillar(record[name])
        records.append({name: record[name] for name in SNAPSHOT_SCHEMA})
    return pl.DataFrame(records, schema=SNAPSHOT_SCHEMA)


def _by_entity(months: Sequence[EntityMonth]) -> list[list[EntityMonth]]:
    """Months of each entity, entities sorted by (entity_kind, entity_id)."""
    found: dict[tuple[str, str], list[EntityMonth]] = defaultdict(list)
    for month in months:
        found[(month.row.entity_kind, month.row.entity_id)].append(month)
    return [found[key] for key in sorted(found)]


def score_frame(months: Sequence[EntityMonth], params: Params, dataset_hash: str) -> pl.DataFrame:
    """``score_panel`` output -> ``SNAPSHOT_SCHEMA`` frame, month-on-month deltas included."""
    snapshots: list[EntitySnapshot] = []
    for entity_months in _by_entity(months):
        previous = None
        for month in entity_months:
            snapshots.append(build_snapshot(month, previous, params, dataset_hash))
            previous = month
    return snapshots_frame(snapshots)


def classify_industry(source: Path | io.Tables) -> dict[str, IndustryClassification]:
    """Industry archetype per company, for the profile cards.

    ``source`` is the ``io.Tables`` already in memory (no second parse of the
    CSVs) or a folder. Context only: when the classifier fails the cards lose
    the attribute and every score is still produced.
    """
    try:
        from .industry_classifier import classify_dataset, classify_tables

        if isinstance(source, io.Tables):
            return classify_tables(source)
        return {item.entity_id: item for item in classify_dataset(Path(source))[1]}
    except Exception:  # noqa: BLE001 - nothing in the number depends on this reader
        return {}


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
    tables = io.load_source(input_dir, cache_dir)
    return score_tables(tables, params, industry_override=industry_override)


def score_tables(
    tables: io.Tables,
    params: Params,
    *,
    industry_override: Mapping[str, IndustryClassification] | None = None,
) -> ScoreResult:
    """``score_dataset`` from tables already in memory: clean -> panel ->
    pillars -> aggregate -> carry forward -> trajectory -> alerts -> profiles,
    for groups and companies, every month of the window."""
    clean = cleaning.clean(tables, params)
    panel = panel_module.build_panel(clean, params)
    months = score_panel(panel, params)

    alerts: list[Alert] = []
    for entity_months in _by_entity(months):
        alerts.extend(build_alerts(entity_months, params))

    industry = industry_override if industry_override is not None else classify_industry(tables)
    return ScoreResult(
        snapshots=score_frame(months, params, tables.dataset_hash),
        panel=panel,
        months=tuple(months),
        alerts=tuple(alerts),
        profiles=profile.build_profiles(clean, panel, params, industry),
        params=params,
        dataset_hash=tables.dataset_hash,
        window=tables.window,
        due_ar=invoice_module.open_overdue_ar(clean.invoices, tables.window.last_month),
    )


_FLAT_EXCLUDED = ("drivers", "series", "trajectory", "delta_parts", "gates")
# First columns of the CSV views: the answer, then how it was reached.
FLAT_LEADING: tuple[str, ...] = (
    "entity_id",
    "month",
    "score",
    "band",
    "direction",
    "nature",
    "confidence",
    "abstained",
    *(f"pillars_{key}" for key in PILLAR_KEYS),
)


def flat_scores(snapshots: pl.DataFrame, entity_kind: str) -> pl.DataFrame:
    """CSV-friendly view of one entity kind: ``FLAT_LEADING`` first, structs
    unnested with a prefix, lists joined with ``|``, nested detail columns
    dropped but for the trajectory call (``direction``, ``nature``,
    ``horizon``, ``delta3``, ``drift_points``)."""
    verdict = pl.col("trajectory").struct
    frame = (
        snapshots.filter(pl.col("entity_kind") == entity_kind)
        .with_columns(
            verdict.field("direction").alias("direction"),
            verdict.field("nature").alias("nature"),
            verdict.field("horizon").alias("horizon"),
            verdict.field("delta3").alias("delta3"),
            verdict.field("drift_points").alias("drift_points"),
        )
        .drop(_FLAT_EXCLUDED)
    )
    frame = _unnest(frame)
    return frame.select(*FLAT_LEADING, pl.exclude(FLAT_LEADING))


def _unnest(frame: pl.DataFrame) -> pl.DataFrame:
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
    ``scores_companies.csv``, ``alerts.parquet`` and ``panel.parquet`` (the
    facts behind the scores) under ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scores": out_dir / "scores.parquet",
        "groups": out_dir / "scores_groups.csv",
        "companies": out_dir / "scores_companies.csv",
        "alerts": out_dir / "alerts.parquet",
        "panel": out_dir / "panel.parquet",
    }
    result.snapshots.write_parquet(paths["scores"])
    result.panel.write_parquet(paths["panel"])
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
    "CARRIED_FIELDS",
    "FLAT_LEADING",
    "ENGINE_VERSION",
    "FEATURE_VERSION",
    "MODEL_VERSION",
    "ScoreResult",
    "build_snapshot",
    "carried_pillars",
    "carry_forward",
    "classify_industry",
    "flat_scores",
    "score_dataset",
    "score_frame",
    "score_entity",
    "score_panel",
    "score_tables",
    "snapshots_frame",
    "write_outputs",
]
