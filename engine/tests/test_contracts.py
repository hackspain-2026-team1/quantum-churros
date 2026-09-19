"""The frozen interfaces: panel schema, snapshot schema and the glue around them."""

from __future__ import annotations

import random
from dataclasses import fields
from datetime import date

import polars as pl
import pytest
from typer.testing import CliRunner
from xray_engine import artifacts, panel, scoring
from xray_engine.cli import app
from xray_engine.contracts import (
    PANEL_COLUMNS,
    PANEL_KEY,
    PANEL_MONEY_COLUMNS,
    PANEL_UNITS,
    PILLAR_INPUT_KEYS,
    PILLAR_KEYS,
    SNAPSHOT_SCHEMA,
    Anchors,
    ConfidenceParts,
    DeltaParts,
    Driver,
    EntityMonth,
    EntitySnapshot,
    PanelRow,
    PillarResult,
    ScoreParts,
    ScoreSnapshot,
    Trajectory,
)

V1_FIELDS = {
    "entity_id", "month", "score", "observed_score", "predicted_future_score", "forecast_delta",
    "delta", "trend", "persistence_months", "confidence", "drivers", "shap_base_value",
    "explanation_residual", "detected_since", "feature_version", "model_version", "dataset_hash",
}


def test_panel_columns_are_the_panel_row() -> None:
    assert list(PANEL_COLUMNS) == [item.name for item in fields(PanelRow)]
    assert list(PANEL_COLUMNS)[:4] == ["entity_kind", "entity_id", "group_id", "month"]
    assert set(PANEL_KEY) <= set(PANEL_COLUMNS)
    for item in fields(PanelRow):
        assert item.metadata["doc"] and item.metadata["unit"], item.name
    assert set(PANEL_UNITS.values()) <= {
        "-", "date", "months", "count", "flag", "rows", "EUR", "share", "days", "invoices"
    }
    assert {"cash_month_end", "headroom", "op_outflow_median_3m", "lfl_op_inflow_12m"} <= set(
        PANEL_MONEY_COLUMNS
    )


def test_panel_rows_round_trip_through_a_frame(panel_rows) -> None:
    rng = random.Random(3)
    rows = [
        panel_rows.random(rng, entity_id=f"E{index}", month=date(2026, 1, 1)) for index in range(50)
    ]
    frame = panel.rows_to_frame(rows)
    assert dict(frame.schema) == PANEL_COLUMNS
    panel.validate_panel(frame)
    assert list(panel.iter_rows(frame)) == rows
    with pytest.raises(ValueError):
        panel.validate_panel(pl.concat([frame, frame]))
    with pytest.raises(ValueError):
        panel.validate_panel(frame.drop("headroom"))
    with pytest.raises(KeyError):
        PanelRow.from_mapping({"entity_kind": "group"})


def test_anchors_interpolate_and_clamp() -> None:
    table = Anchors(((0.0, 0.0), (13.0, 35.0), (27.0, 60.0)))
    assert table(-5) == 0.0
    assert table(13) == 35.0
    assert table(20) == pytest.approx(47.5)
    assert table(1e9) == 60.0


def test_snapshot_is_a_superset_of_v1() -> None:
    assert V1_FIELDS <= set(EntitySnapshot.model_fields)
    assert set(SNAPSHOT_SCHEMA) == set(EntitySnapshot.model_fields)
    assert ScoreSnapshot is EntitySnapshot
    legacy = EntitySnapshot(
        entity_id="E", month=date(2026, 8, 1), score=61.0, observed_score=60.0,
        predicted_future_score=61.0, forecast_delta=0.0, delta=-1.0, trend="stable",
        persistence_months=0, confidence=0.9, drivers=[], shap_base_value=59.0,
        explanation_residual=0.0, detected_since=None, dataset_hash="h",
    )
    assert legacy.entity_kind == "company" and legacy.model_version == "engine-v2"
    assert set(PILLAR_INPUT_KEYS) == set(PILLAR_KEYS)


def _entity_month(month: date, score: float) -> EntityMonth:
    pillars = {
        key: PillarResult(key=key, score=70.0, raw_score=72.0, gates=("no_debt",) if key == "debt" else ())
        for key in PILLAR_KEYS
    }
    pillars["payments"] = PillarResult(key="payments", score=None, raw_score=None, gates=("stamped_regime",))
    available = [key for key in PILLAR_KEYS if pillars[key].score is not None]
    parts = ScoreParts(
        month=month, months_observed=12, months_since_perimeter_change=None,
        branch="+".join(available), pillar_scores={key: pillars[key].score for key in PILLAR_KEYS},
        weights_effective={key: 0.25 for key in available}, level_weighted=70.0,
        penalty_level=0.0, cap_adjustment_level=0.0, caps_fired=(), level_raw=70.0,
        confidence=0.8, confidence_parts=ConfidenceParts(0.9, 0.95, 0.8 / 0.9 / 0.95),
        base=58.0, contributions={key: 2.0 for key in available}, penalty=0.0,
        cap_adjustment=0.0, score=score, feed_live=True, flags=("debt_snapshot",),
        abstained=False, unlock_hint=None,
    )
    verdict = Trajectory(available=True, reason=None, direction="deteriorating",
                         nature="shock_pending", shock_pending=True, shock_month=month,
                         delta3=-7.0, sigma=2.0, delta3_sigma=-3.5, compared_to=date(2026, 4, 1),
                         pillars_moved=("liquidity",), persistence_months=1, detected_since=month)
    row = PanelRow(entity_kind="group", entity_id="GROUP_X", group_id="GROUP_X", month=month,
                   months_observed=12, cash_month_end=1000.0)
    return EntityMonth(row=row, pillars=pillars, parts=parts, trajectory=verdict)


def test_snapshots_reach_parquet_with_the_frozen_schema(tmp_path, monkeypatch, params) -> None:
    driver = Driver(feature="liquidity", label="Liquidez", direction="positive", contribution=2.0,
                    observed=70.0, baseline=60.0, evidence="Colchón de 45 días")
    monkeypatch.setattr(scoring, "explain", lambda parts, pillars, p: [driver])
    monkeypatch.setattr(
        scoring, "delta_parts",
        lambda current, previous: DeltaParts(score=current.score - previous.score, base=-1.0,
                                             contributions={"liquidity": -1.5}, penalty=0.0,
                                             cap_adjustment=0.0),
    )
    first = _entity_month(date(2026, 7, 1), 68.5)
    second = _entity_month(date(2026, 8, 1), 66.0)
    snapshots = [
        scoring.build_snapshot(first, None, params, "hash"),
        scoring.build_snapshot(second, first, params, "hash"),
    ]
    assert snapshots[0].delta == 0.0 and snapshots[0].delta_parts is None
    assert snapshots[1].delta == pytest.approx(-2.5)
    # deprecated v1 fields keep a meaning
    assert snapshots[1].observed_score == 70.0 and snapshots[1].shap_base_value == 58.0
    assert snapshots[1].predicted_future_score == 66.0 and snapshots[1].forecast_delta == 0.0
    assert snapshots[1].explanation_residual == 0.0 and snapshots[1].params_hash == params.sha256
    assert snapshots[1].trend == "deteriorating" and snapshots[1].persistence_months == 1

    frame = scoring.snapshots_frame(snapshots)
    assert dict(frame.schema) == SNAPSHOT_SCHEMA
    row = frame.row(1, named=True)
    assert row["pillars"]["payments"] is None and row["gates"]["payments"] == ["stamped_regime"]
    assert row["delta_parts"]["contributions"]["activity"] is None
    assert row["series"]["cash_month_end"] == 1000.0

    path = tmp_path / "scores.parquet"
    frame.write_parquet(path)
    history = artifacts.read_entity_scores(path, "GROUP_X")
    assert [item["score"] for item in history] == [68.5, 66.0]
    assert artifacts.read_latest_score(path, "GROUP_X")["month"] == date(2026, 8, 1)
    months, values = artifacts.read_entity_series(path, "GROUP_X", "cash_month_end")
    assert months == ["2026-07-01", "2026-08-01"] and values == [1000.0, 1000.0]
    flat = scoring.flat_scores(frame, "group")
    assert "pillars_liquidity" in flat.columns and flat["caps_fired"].dtype == pl.String
    assert not any(isinstance(dtype, (pl.Struct, pl.List)) for dtype in flat.schema.values())


def test_cli_exposes_the_frozen_commands() -> None:
    runner = CliRunner()
    listing = runner.invoke(app, ["--help"]).output
    for command in ("ingest", "fit-reference", "predict", "validate"):
        assert command in listing
    assert "train" not in listing
    for command in ("predict", "score"):
        output = runner.invoke(app, [command, "--help"]).output
        assert "--export-dir" in output and "--out" in output
