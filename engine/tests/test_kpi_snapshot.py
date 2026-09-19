"""Tests for KPI history snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from xray_engine.kpi_snapshot import append_kpi_history, format_snapshot_row


def test_format_snapshot_row_includes_stage_kpis() -> None:
    row = format_snapshot_row({
        "dataset_hash": "abc123",
        "params_hash": "def456",
        "engine_version": "2.1.0",
        "runtime_seconds": 12.3,
        "kpis": {
            "by_stage": {
                "reconcile": {"netting_placebo_pass": True},
                "normalize": {"truncation_pass": True, "scale_pass": True, "coverage_scored_pct": 0.91},
                "score": {
                    "holdout_n_groups": 60,
                    "level_autocorr_lag3": 0.79,
                    "slope_autocorr_lag3": 0.02,
                    "rolling_min_spearman": 1.0,
                    "p_structural_given_spike": 0.05,
                },
            },
        },
    })
    assert "`abc123`" in row and "60" in row and "0.79" in row


def test_append_kpi_history_creates_and_appends(tmp_path: Path) -> None:
    validation = tmp_path / "validation.json"
    history = tmp_path / "KPI_HISTORY.md"
    validation.write_text(json.dumps({"dataset_hash": "x", "params_hash": "y", "engine_version": "z", "kpis": {"by_stage": {}}}), encoding="utf-8")
    row = append_kpi_history(validation, history)
    text = history.read_text(encoding="utf-8")
    assert "Historial de evaluación" in text and "Qué mide cada columna" in text and row in text
    append_kpi_history(validation, history)
    assert text.count(row) == 1
