"""The brief's canonical slow trajectories, proven end to end (Q-05).

45 -> 65 (improvement) and 82 -> 68 (deterioration) over 24 months move 2-3 points a quarter: the three-month verdict keeps reading them as stable and the Theil-Sen drift makes the call at least six months before the last month. A one-month spike stays a bump and never becomes a drift alert.
"""

from __future__ import annotations

from datetime import date

import pytest
from xray_engine.alerts import build_alerts
from xray_engine.contracts import PILLAR_KEYS, EntityMonth, PanelRow, PillarResult
from xray_engine.trajectory import trajectories

TOL = 1e-6
START = date(2025, 1, 1)
MONTHS = 24
LEAD = 6  # the alert must exist at least this many months before the last


def _ramp(first: float, last: float) -> list[float]:
    return [first + (last - first) * index / (MONTHS - 1) for index in range(MONTHS)]


def _entity_months(score_parts, params, scores) -> list[EntityMonth]:
    history = [
        score_parts.live(score_parts.month_add(START, index), float(score), params)
        for index, score in enumerate(scores)
    ]
    verdicts = trajectories(history, params)
    return [
        EntityMonth(
            PanelRow(
                entity_kind="group",
                entity_id="GROUP_X",
                group_id="GROUP_X",
                month=parts.month,
                months_observed=index + 1,
            ),
            {
                key: PillarResult(key=key, score=parts.pillar_scores[key], gates=())
                for key in PILLAR_KEYS
            },
            parts,
            verdicts[index],
        )
        for index, parts in enumerate(history)
    ]


def _canonical_alert(score_parts, params, first: float, last: float, kind: str):
    months = _entity_months(score_parts, params, _ramp(first, last))
    verdicts = [entry.trajectory for entry in months]
    alerts = [alert for alert in build_alerts(months, params) if alert.kind == kind]
    return verdicts, alerts


def test_the_briefs_improvement_case_is_alerted_early_by_the_drift(
    score_parts, params
) -> None:
    verdicts, alerts = _canonical_alert(
        score_parts, params, 45.0, 65.0, "improvement_structural"
    )
    cfg = params.trajectory
    slope = 20.0 / (MONTHS - 1)
    # the three-month verdict keeps its discipline: 2-3 points a quarter is no shock
    assert all(
        abs(item.delta3) < cfg.min_delta_points for item in verdicts if item.available
    )
    # the drift makes the call and holds it to the end of the window
    assert (verdicts[-1].direction, verdicts[-1].horizon, verdicts[-1].nature) == (
        "improving",
        "long",
        "structural",
    )
    assert verdicts[-1].drift_points == pytest.approx(slope * cfg.long_horizon, abs=TOL)
    # the brief's numbers: the alert comes at least LEAD months before month 24
    assert len(alerts) == 1 and alerts[0].state == "fired"
    alert_index = next(
        index
        for index, entry in enumerate(
            _entity_months(score_parts, params, _ramp(45.0, 65.0))
        )
        if entry.row.month == alerts[0].month
    )
    assert (MONTHS - 1) - alert_index >= LEAD
    # the alert tells the slow-erosion story, not the three-month fall story
    assert "lenta y sostenida" in alerts[0].detail
    # and nothing of the opposite kind
    assert not [
        alert
        for alert in build_alerts(
            _entity_months(score_parts, params, _ramp(45.0, 65.0)), params
        )
        if alert.kind == "deterioration_structural"
    ]


def test_the_briefs_erosion_case_reaches_the_bar(score_parts, params) -> None:
    verdicts, alerts = _canonical_alert(
        score_parts, params, 82.0, 68.0, "deterioration_structural"
    )
    assert (verdicts[-1].direction, verdicts[-1].horizon, verdicts[-1].nature) == (
        "deteriorating",
        "long",
        "structural",
    )
    assert len(alerts) == 1 and alerts[0].state == "fired"
    alert_index = next(
        index
        for index, entry in enumerate(
            _entity_months(score_parts, params, _ramp(82.0, 68.0))
        )
        if entry.row.month == alerts[0].month
    )
    assert (MONTHS - 1) - alert_index >= LEAD


def test_a_one_month_spike_is_a_bump_and_never_a_drift_alert(
    score_parts, params
) -> None:
    scores = [60.0] * MONTHS
    spike = 15
    scores[spike] = 70.0
    months = _entity_months(score_parts, params, scores)
    verdicts = [entry.trajectory for entry in months]
    # the spike is a short-horizon event, pending while it lasts
    assert (
        verdicts[spike].direction,
        verdicts[spike].horizon,
        verdicts[spike].nature,
    ) == (
        "improving",
        "short",
        "shock_pending",
    )
    assert verdicts[spike].drift_call is None  # the median slope ignores one month
    # it reverts: a bump, dated on the spike month
    assert verdicts[spike + 1].nature == "bump"
    assert verdicts[spike + 1].shock_month == months[spike].row.month
    # no month ever reaches a structural call, so no alert of either kind fires
    assert all(item.nature != "structural" for item in verdicts)
    assert build_alerts(months, params) == []
