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
    ABSTAIN_REASONS,
    BAND_KEYS,
    BAND_LABELS,
    CAP_KEYS,
    CAP_TEXTS,
    CARRIED_GATE,
    CONFIDENCE_LABEL_KEYS,
    CONFIDENCE_LABELS,
    FLAG_TEXTS,
    GATE_TEXTS,
    PANEL_COLUMNS,
    PANEL_KEY,
    PANEL_MONEY_COLUMNS,
    PANEL_UNITS,
    PILLAR_GATES,
    PILLAR_INPUT_KEYS,
    PILLAR_KEYS,
    REASON_TEXTS,
    SCORE_FLAGS,
    SERIES_KEYS,
    SIZE_BAND_LABELS,
    SIZE_BANDS,
    SNAPSHOT_SCHEMA,
    SUPPRESSION_REASONS,
    TRAJECTORY_REASONS,
    UNLOCK_HINTS,
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
    band_of,
    size_band_of,
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
    assert {
        "cash_month_end", "cash_intra_month_min", "headroom", "headroom_at_min", "outflow_median_3m",
        "outflow_median_12m", "op_in_sum_6m_w", "outflow_sum_6m_w", "op_in_sum_12m_w",
        "debt_service_sum_12m_w", "op_in_lfl_recent_mean", "op_in_lfl_prior_mean", "ap_amount",
    } <= set(PANEL_MONEY_COLUMNS)


def test_panel_row_holds_pre_aggregated_facts_only() -> None:
    # the pure core never reads history arrays: every column is a scalar
    assert not [name for name, dtype in PANEL_COLUMNS.items() if isinstance(dtype, (pl.List, pl.Struct))]
    needed = {
        "size_band", "months_in_6m_window", "months_in_12m_window", "lfl_prior_months",
        "has_debt_products", "no_external_revenue", "swept_subsidiary", "months_observed",
        "rows_3m", "rows_base_median", "rows_base_months", "zero_row_month", "perimeter_changed",
        "new_perimeter_inflow_share_3m", "neg_liquidity_months_6m", "no_cash_anchor_share",
        "limit_assumed_constant", "dash_share", "fx_excluded_share", "orphan_product_share",
    }
    for side in ("ap", "ar"):
        needed |= {f"{side}_n", f"{side}_neff", f"{side}_days_beyond_terms", f"{side}_stamped_share"}
    assert needed <= set(PANEL_COLUMNS)
    dropped = {"lfl_op_inflow_12m", "op_outflow_median_3m", "interest_12m", "debt_service_12m",
               "ap_cohort_n", "ap_settlements_6m", "ap_unpaid30_share", "uncategorised_share"}
    assert not dropped & set(PANEL_COLUMNS)


def test_vocabularies_have_spanish_text() -> None:
    assert set(GATE_TEXTS) == set(PILLAR_GATES) and CARRIED_GATE in PILLAR_GATES
    assert set(FLAG_TEXTS) == set(SCORE_FLAGS)
    assert set(CAP_TEXTS) == set(CAP_KEYS) == {"negative_liquidity", "weak_payments"}
    assert set(REASON_TEXTS) == set(ABSTAIN_REASONS) | set(SUPPRESSION_REASONS) | set(TRAJECTORY_REASONS)
    assert set(UNLOCK_HINTS) == set(ABSTAIN_REASONS)
    assert ABSTAIN_REASONS == ("stale_feed", "short_history", "no_bank_pillar")
    assert set(BAND_LABELS) == set(BAND_KEYS) and set(SIZE_BAND_LABELS) == set(SIZE_BANDS)
    assert set(CONFIDENCE_LABELS) == set(CONFIDENCE_LABEL_KEYS)
    assert "concentration" not in " ".join(SCORE_FLAGS + PILLAR_GATES + CAP_KEYS)
    assert not [key for key in SERIES_KEYS if "dscr" in key or "utilisation" in key]


def test_bands_and_size_bands(params) -> None:
    assert [band_of(score, params.bands) for score in (0.0, 39.94, 39.96, 40.0, 59.9, 60.0, 79.94, 80.0, 100.0)] == [
        "critical", "critical", "watch", "watch", "watch", "stable", "stable", "solid", "solid",
    ]
    bounds = params.size_bands.upper_bounds_eur
    assert [size_band_of(value, bounds) for value in (0.0, 1_999_999.0, 2e6, 9.9e6, 1e7, 4.9e7, 5e7, 1e9)] == [
        "micro", "micro", "small", "small", "medium", "medium", "large", "large",
    ]


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
    pillars = {key: PillarResult(key=key, score=70.0) for key in PILLAR_KEYS}
    pillars["payments"] = PillarResult(key="payments", score=None, gates=("stamped_regime",))
    available = [key for key in PILLAR_KEYS if pillars[key].score is not None]
    parts = ScoreParts(
        month=month, months_observed=12, months_since_perimeter_change=None,
        branch="+".join(available), pillar_scores={key: pillars[key].score for key in PILLAR_KEYS},
        weights_effective={key: 0.25 for key in available}, level_weighted=70.0,
        penalty=0.0, cap_adjustment=0.0, caps_fired=(), base=score - 8.0,
        contributions={key: 2.0 for key in available}, score=score, band="stable", level=score,
        feed_live=True, carried_from=None, confidence=0.8,
        confidence_parts=ConfidenceParts(0.9, 0.95, 0.8 / 0.9 / 0.95), confidence_label="high",
        flags=("debt_snapshot",), abstained=False, abstain_reason=None, unlock_hint=None,
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
    assert snapshots[1].observed_score == 66.0 and snapshots[1].shap_base_value == 58.0
    assert snapshots[1].predicted_future_score == 66.0 and snapshots[1].forecast_delta == 0.0
    assert snapshots[1].band == "stable" and snapshots[1].confidence_label == "high"
    assert snapshots[1].level == 66.0 and snapshots[1].carried_from is None and snapshots[1].feed_live
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
