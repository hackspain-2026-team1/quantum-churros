"""Alert inbox: spells, abstention, the perimeter month and the stale feed."""

from __future__ import annotations

import random
import re
from dataclasses import replace
from datetime import date

import pytest
from xray_engine.alerts import TITLES, build_alerts
from xray_engine.contracts import (
    CAP_TEXTS,
    PILLAR_KEYS,
    EntityMonth,
    PanelRow,
    PillarResult,
    SuppressedBy,
    Trajectory,
)
from xray_engine.scoring import score_entity

START = date(2025, 1, 1)


def _month(score_parts, params, index, level=70.0, *, verdict=None, perimeter=False, stale=False,
           **overrides) -> EntityMonth:
    """``level`` is the own level of the month; a carried month overrides ``score``."""
    month = score_parts.month_add(START, index)
    make = score_parts.stale if stale else score_parts.live
    parts = replace(make(month, level, params), **overrides)
    row = PanelRow(entity_kind="group", entity_id="GROUP_X", group_id="GROUP_X", month=month,
                   months_observed=index + 1, perimeter_changed=perimeter)
    pillars = {key: PillarResult(key=key, score=parts.pillar_scores[key], gates=("no_base",))
               for key in PILLAR_KEYS}
    reason = "stale_feed" if stale else None
    return EntityMonth(row, pillars, parts, verdict or Trajectory(available=not stale, reason=reason))


def _structural(direction: str, run: int, since: date) -> Trajectory:
    return Trajectory(available=True, reason=None, direction=direction, nature="structural",
                      delta3=-9.0, sigma=2.0, delta3_sigma=-4.5, persistence_months=run,
                      detected_since=since)


def _summary(alerts):
    return [(alert.month.strftime("%Y-%m"), alert.kind, alert.state) for alert in alerts]


def test_quiet_entity_has_no_alerts(score_parts, params) -> None:
    assert build_alerts([_month(score_parts, params, index) for index in range(8)], params) == []


def test_one_alert_per_spell(score_parts, params) -> None:
    scores = [70, 34.9, 30, 35.0, 70, 20, 20]
    alerts = build_alerts(
        [_month(score_parts, params, index, score) for index, score in enumerate(scores)], params
    )
    assert _summary(alerts) == [("2025-02", "level_critical", "fired"), ("2025-06", "level_critical", "fired")]
    first = alerts[0]
    assert first.id == "GROUP_X:2025-02:level_critical" and first.suppressed_by is None
    assert (first.entity_kind, first.entity_id, first.group_id) == ("group", "GROUP_X", "GROUP_X")
    assert first.title and first.detail


def test_structural_calls_alert_once_and_shocks_never(score_parts, params) -> None:
    since = score_parts.month_add(START, 2)
    shock = Trajectory(available=True, reason=None, direction="deteriorating", nature="shock_pending",
                       shock_pending=True, shock_month=since, delta3=-9.0, sigma=2.0,
                       delta3_sigma=-4.5, persistence_months=1, detected_since=since)
    shifted = Trajectory(available=True, reason=None, direction="perimeter_shift", delta3=-30.0,
                         sigma=2.0, delta3_sigma=-15.0)
    months = [
        _month(score_parts, params, 0),
        _month(score_parts, params, 1, verdict=shifted),
        _month(score_parts, params, 2, verdict=shock),
        _month(score_parts, params, 3, verdict=_structural("deteriorating", 2, since)),
        _month(score_parts, params, 4, verdict=_structural("deteriorating", 3, since)),
        _month(score_parts, params, 5),
        _month(score_parts, params, 6, verdict=_structural("improving", 2, since)),
    ]
    assert _summary(build_alerts(months, params)) == [
        ("2025-04", "deterioration_structural", "fired"),
        ("2025-07", "improvement_structural", "fired"),
    ]


def test_a_slow_drift_alerts_on_its_first_month_with_its_own_words(score_parts, params) -> None:
    since = score_parts.month_add(START, 7)
    drift = Trajectory(available=True, reason=None, direction="deteriorating", nature="structural",
                       delta3=-2.4, sigma=2.0, delta3_sigma=-1.2, persistence_months=1,
                       detected_since=since, horizon="long", drift_points=-9.64, drift_months=12,
                       pillars_moved=("liquidity",))
    months = [_month(score_parts, params, index) for index in range(7)]
    months.append(_month(score_parts, params, 7, verdict=drift))
    months.append(_month(score_parts, params, 8, verdict=replace(drift, persistence_months=2)))
    alerts = build_alerts(months, params)
    assert _summary(alerts) == [("2025-08", "deterioration_structural", "fired")]
    assert alerts[0].detail == (
        "El score acumula una caída de 9,6 puntos en 12 meses: una deriva lenta y sostenida; "
        "se mueven: liquidez."
    )
    up = replace(drift, direction="improving", drift_points=11.0, horizon="both", pillars_moved=())
    rising = build_alerts([*months[:7], _month(score_parts, params, 7, verdict=up)], params)
    assert rising[0].kind == "improvement_structural"
    assert rising[0].detail == "El score acumula una subida de 11,0 puntos en 12 meses: una mejora lenta y sostenida."


def test_cap_alert_follows_the_binding_rule(score_parts, params) -> None:
    capped = dict(cap_adjustment=5.0, caps_fired=("negative_liquidity", "weak_payments"))
    other = dict(cap_adjustment=3.0, caps_fired=("weak_payments",))
    idle = dict(cap_adjustment=0.0, caps_fired=("negative_liquidity",))  # holds but does not bind
    months = [
        _month(score_parts, params, 0, **idle),
        _month(score_parts, params, 1, **capped),
        _month(score_parts, params, 2, **capped),
        _month(score_parts, params, 3, **other),
        _month(score_parts, params, 4),
    ]
    assert _summary(build_alerts(months, params)) == [
        ("2025-02", "cap_fired", "fired"), ("2025-04", "cap_fired", "fired"),
    ]


def test_abstained_and_perimeter_months_do_not_fire(score_parts, params) -> None:
    muted = dict(abstained=True, abstain_reason="short_history", unlock_hint="Faltan meses.")
    months = [
        _month(score_parts, params, 0, 20.0, **muted),
        _month(score_parts, params, 1, 20.0, **muted),
        _month(score_parts, params, 2, 20.0),  # the spell can fire now
        _month(score_parts, params, 3, 20.0),
        _month(score_parts, params, 4, 70.0),
        _month(score_parts, params, 5, 20.0, perimeter=True),
        _month(score_parts, params, 6, 20.0),  # the change month only
        _month(score_parts, params, 7, 20.0, perimeter=True),
    ]
    alerts = build_alerts(months, params)
    assert _summary(alerts) == [
        ("2025-01", "level_critical", "abstained"),
        ("2025-03", "level_critical", "fired"),
        ("2025-06", "level_critical", "suppressed"),
        ("2025-07", "level_critical", "fired"),
    ]
    assert alerts[0].suppressed_by == SuppressedBy("abstention", date(2025, 1, 1), None)
    assert alerts[2].suppressed_by == SuppressedBy("perimeter_change", date(2025, 6, 1), date(2025, 6, 1))
    # abstention wins over the perimeter month
    both = build_alerts([_month(score_parts, params, 0, 20.0, perimeter=True, **muted)], params)
    assert both[0].state == "abstained"


def test_a_stale_month_only_emits_stale_feed(score_parts, params) -> None:
    frozen = dict(score=20.0, cap_adjustment=4.0, caps_fired=("negative_liquidity",))
    months = [
        _month(score_parts, params, 0, 20.0, cap_adjustment=4.0, caps_fired=("negative_liquidity",)),
        _month(score_parts, params, 1, 90.0, stale=True, **frozen),
        _month(score_parts, params, 2, 90.0, stale=True, **frozen),
        _month(score_parts, params, 3, 20.0, cap_adjustment=4.0, caps_fired=("negative_liquidity",)),
        _month(score_parts, params, 4, 70.0),
        _month(score_parts, params, 5, 70.0, stale=True),
    ]
    alerts = build_alerts(months, params)
    assert _summary(alerts) == [
        ("2025-01", "cap_fired", "fired"),
        ("2025-01", "level_critical", "fired"),
        ("2025-02", "stale_feed", "fired"),  # never abstained, although the month is
        ("2025-06", "stale_feed", "fired"),
    ]
    assert months[1].parts.abstained and alerts[2].suppressed_by is None
    # the carried spell went on through the stale months: nothing fires again in April
    assert alerts == sorted(alerts, key=lambda alert: (alert.month, alert.kind))
    perimeter = replace(months[1], row=replace(months[1].row, perimeter_changed=True))
    assert build_alerts([months[0], perimeter], params)[-1].state == "fired"


def test_texts_are_spanish_sentences_with_the_numbers(score_parts, params) -> None:
    since = score_parts.month_add(START, 1)
    verdict = Trajectory(available=True, reason=None, direction="deteriorating", nature="structural",
                         delta3=-12.34, sigma=2.0, delta3_sigma=-6.17, compared_to=date(2024, 12, 1),
                         pillars_moved=("liquidity", "payments"), persistence_months=2, detected_since=since)
    capped = dict(cap_adjustment=7.3, caps_fired=("negative_liquidity",))
    months = [
        _month(score_parts, params, 0),
        _month(score_parts, params, 1),
        _month(score_parts, params, 2, 31.26, verdict=verdict, **capped),
        _month(score_parts, params, 3, 31.26, stale=True, score=31.26, carried_from=score_parts.month_add(START, 2)),
    ]
    alerts = {alert.kind: alert for alert in build_alerts(months, params)}
    assert set(alerts) == {"cap_fired", "deterioration_structural", "level_critical", "stale_feed"}
    assert alerts["deterioration_structural"].detail == (
        "El score cae 12,3 puntos frente a 2024-12 y la caída se mantiene 2 meses seguidos; "
        "se mueven: liquidez, pagos a proveedores."
    )
    assert alerts["level_critical"].detail == "El score (31,3) baja de 35 puntos con el feed bancario activo."
    assert alerts["cap_fired"].detail == f"{CAP_TEXTS['negative_liquidity']} Resta 7,3 puntos."
    assert alerts["stale_feed"].detail == (
        "No llegan movimientos bancarios recientes: se mantiene el score de 2025-03."
    )
    up = replace(verdict, direction="improving", delta3=9.0, pillars_moved=())
    better = build_alerts([_month(score_parts, params, 5, verdict=up)], params)
    assert better[0].detail == "El score sube 9,0 puntos frente a 2024-12 y la mejora se mantiene 2 meses seguidos."
    first_stale = build_alerts([_month(score_parts, params, 0, stale=True)], params)
    assert "no hay un mes anterior" in first_stale[0].detail  # nothing to carry from
    for alert in [*alerts.values(), *better, *first_stale]:
        assert alert.title == TITLES[alert.kind]
        assert 1 <= len(alert.detail) <= 400 and alert.detail.endswith(".") and "None" not in alert.detail
        assert re.fullmatch(r"GROUP_X:\d{4}-\d{2}:[a-z_]+", alert.id)


def test_inbox_is_deterministic_unique_and_order_free(score_parts, params) -> None:
    rng = random.Random(71)
    since = score_parts.month_add(START, 0)
    months = []
    for index in range(36):
        extra = {}
        if rng.random() < 0.3:
            extra = dict(cap_adjustment=2.0, caps_fired=(rng.choice(["negative_liquidity", "weak_payments"]),))
        if rng.random() < 0.2:
            extra |= dict(abstained=True, abstain_reason="no_bank_pillar", unlock_hint="Conectar cuentas.")
        verdict = _structural(rng.choice(["improving", "deteriorating"]), 2, since) if rng.random() < 0.3 else None
        months.append(_month(score_parts, params, index, rng.choice([20.0, 70.0]), verdict=verdict,
                             perimeter=rng.random() < 0.2, stale=rng.random() < 0.15, **extra))
    alerts = build_alerts(months, params)
    assert alerts == build_alerts(months, params) == build_alerts(months[::-1], params)
    assert len({alert.id for alert in alerts}) == len(alerts) > 10
    assert {alert.state for alert in alerts} == {"fired", "suppressed", "abstained"}
    for alert in alerts:
        assert (alert.suppressed_by is None) == (alert.state == "fired")
        if alert.kind == "stale_feed":
            assert alert.state == "fired"
    by_month = {item.row.month: item for item in months}
    for alert in alerts:  # a stale month only says that the feed is stale
        assert by_month[alert.month].parts.feed_live != (alert.kind == "stale_feed")


def _bank_rows(score_parts, cash, recent_inflow=lambda index: 300_000.0, count=24) -> list[PanelRow]:
    """A group seen from its first month: bank pillars only, flat flows of 300k a month."""
    rows, negative = [], []
    for index in range(count):
        negative.append(cash(index) < 0)
        seen = index + 1
        rows.append(PanelRow(
            entity_kind="group", entity_id="GROUP_X", group_id="GROUP_X",
            month=score_parts.month_add(START, index), months_observed=seen, size_band="small",
            rows_month=100, rows_3m=100 * min(3, seen), rows_base_median=100.0 if index >= 6 else None,
            rows_base_months=max(0, min(9, index - 3)), cash_month_end=cash(index),
            cash_intra_month_min=cash(index) - 50_000.0, n_cash_products=1, no_cash_anchor_share=0.0,
            neg_liquidity_months_6m=sum(negative[-6:]), outflow_median_3m=300_000.0,
            outflow_median_12m=300_000.0, op_in_sum_6m_w=300_000.0 * min(6, seen),
            outflow_sum_6m_w=300_000.0 * min(6, seen), months_in_6m_window=min(6, seen),
            op_in_sum_12m_w=300_000.0 * min(12, seen), months_in_12m_window=min(12, seen),
            op_in_lfl_recent_mean=recent_inflow(index), op_in_lfl_prior_mean=300_000.0,
            lfl_prior_months=max(0, min(6, index - 2)), dash_share=0.05, fx_excluded_share=0.0,
            orphan_product_share=0.0,
        ))
    return rows


def test_a_draining_group_from_rows_to_inbox(score_parts, params) -> None:
    """Pillars, aggregate, trajectory and alerts chained by ``score_entity``."""
    rows = _bank_rows(score_parts, lambda index: 900_000.0 - max(0, index - 11) * 120_000.0)
    months = score_entity(rows, params)
    assert [item.parts.abstained for item in months[:4]] == [True, True, True, False]
    for item in months:
        parts = item.parts
        explained = parts.base + sum(parts.contributions.values()) - parts.penalty - parts.cap_adjustment
        assert parts.score == pytest.approx(explained, abs=1e-9) and parts.feed_live
    natures = [item.trajectory.nature for item in months]
    first = natures.index("shock_pending")
    assert natures[first + 1] == "structural" and "structural" not in natures[:first]
    assert all(item.trajectory.direction == "stable" for item in months[:first])  # momentum onset included
    assert months[first].trajectory.pillars_moved == ("liquidity",)
    scores = [item.parts.score for item in months]
    assert scores[first - 3] > 75 and scores[-1] < 10 and months[-1].parts.band == "critical"

    alerts = build_alerts(months, params)
    assert _summary(alerts) == [
        (f"{months[first + 1].row.month:%Y-%m}", "deterioration_structural", "fired"),
        (f"{next(item.row.month for item in months if item.parts.score < 35):%Y-%m}", "level_critical", "fired"),
    ]
    assert "se mueven: liquidez" in alerts[0].detail
    # past-only end to end: the same months and the same inbox when the series stops earlier
    cut = first + 3
    assert score_entity(rows[:cut], params) == months[:cut]
    assert build_alerts(months[:cut], params) == [alert for alert in alerts if alert.month <= rows[cut - 1].month]


def test_a_young_group_whose_momentum_comes_online_raises_nothing(score_parts, params) -> None:
    rows = _bank_rows(score_parts, lambda index: 900_000.0, recent_inflow=lambda index: 450_000.0, count=14)
    months = score_entity(rows, params)
    onset = params.activity.min_months_observed - 1
    jump = months[onset].parts.score - months[onset - 1].parts.score
    assert jump > 6 and months[onset].parts.branch == months[onset - 1].parts.branch
    assert months[onset].trajectory.delta3 == pytest.approx(jump)  # reported, not called
    assert [item.trajectory.direction for item in months] == ["stable"] * 14
    assert build_alerts(months, params) == []
