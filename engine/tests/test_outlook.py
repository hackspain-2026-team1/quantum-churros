"""Scenarios best / common / worst: drift projection, flat gate, own-volatility fan."""

from __future__ import annotations

import random
import statistics
from dataclasses import replace
from datetime import date

import pytest
from xray_engine.outlook import GATE_TEXTS, outlook, outlooks
from xray_engine.trajectory import own_sigma

TOL = 1e-9
START = date(2025, 1, 1)


def _history(score_parts, params, scores, **overrides):
    return [
        score_parts.live(score_parts.month_add(START, index), float(score), params, **overrides)
        for index, score in enumerate(scores)
    ]


def _ramp(first: float, last: float, count: int = 24) -> list[float]:
    return [first + (last - first) * index / (count - 1) for index in range(count)]


def test_flat_without_a_measurable_drift(score_parts, params) -> None:
    # fewer than long_min_months comparable live months: the score is held, with a gate
    young = outlook(_history(score_parts, params, [60.0] * 5), params)
    assert young.available and young.reason is None
    assert (young.basis, young.gates) == ("flat", ("no_drift",))
    assert young.common == pytest.approx(60.0)
    assert young.horizon_months == params.trajectory.horizon_months == 3
    assert young.best == pytest.approx(66.0) and young.worst == pytest.approx(54.0)

    # a flat year does measure a fit: a zero slope projects the score, without gates
    calm = outlook(_history(score_parts, params, [60.0] * 12), params)
    assert (calm.basis, calm.gates) == ("drift", ())
    assert calm.common == pytest.approx(60.0) and calm.drift_points == pytest.approx(0.0, abs=TOL)
    assert calm.drift_months == params.trajectory.long_horizon


def test_common_projects_the_measured_drift(score_parts, params) -> None:
    fan = outlook(_history(score_parts, params, _ramp(45.0, 65.0)), params)
    slope = 20.0 / 23
    assert fan.basis == "drift" and fan.gates == ()
    assert fan.drift_months == params.trajectory.long_horizon
    assert fan.drift_points == pytest.approx(slope * params.trajectory.long_horizon, abs=1e-6)
    assert fan.common == pytest.approx(65.0 + slope * fan.horizon_months, abs=1e-6)
    # a calm ramp has no noise of its own: the fan is the six-point floor
    assert fan.best == pytest.approx(fan.common + params.trajectory.min_delta_points, abs=1e-6)
    assert fan.worst == pytest.approx(fan.common - params.trajectory.min_delta_points, abs=1e-6)


def test_the_fan_is_the_own_volatility_of_the_business(score_parts, params) -> None:
    noisy = [60.0]
    for _ in range(11):
        noisy.append(noisy[-1] + 9.0 * (1 if len(noisy) % 2 else -1))
    history = _history(score_parts, params, noisy)
    fan = outlook(history, params)
    assert fan.basis == "drift"  # a sawtooth measures no drift: the fit is flat
    assert fan.common == pytest.approx(noisy[-1], abs=1e-6)
    sigma = own_sigma(history, params)
    assert sigma == pytest.approx(statistics.stdev([9.0, -9.0] * 4), abs=TOL)
    band = max(params.trajectory.min_delta_points, params.trajectory.long_sigma_mult * sigma)
    assert band > params.trajectory.min_delta_points
    assert fan.best == pytest.approx(fan.common + band, abs=1e-6)
    assert fan.worst == pytest.approx(fan.common - band, abs=1e-6)


def test_the_fan_is_clamped_to_the_score_range(score_parts, params) -> None:
    top = outlook(_history(score_parts, params, _ramp(80.0, 99.0)), params)
    assert top.common == 100.0 and top.best == 100.0
    assert top.worst == pytest.approx(100.0 - params.trajectory.min_delta_points, abs=1e-6)
    bottom = outlook(_history(score_parts, params, _ramp(20.0, 1.0)), params)
    assert bottom.common == 0.0 and bottom.worst == 0.0
    assert bottom.best == pytest.approx(params.trajectory.min_delta_points, abs=1e-6)


def test_not_available_without_a_live_score(score_parts, params) -> None:
    assert outlook([], params).reason == "short_history"
    history = _history(score_parts, params, [60.0] * 9)
    stale = score_parts.stale(score_parts.month_add(START, 9), 60.0, params)
    assert outlook([*history, stale], params).reason == "stale_feed"
    abstained = score_parts.live(
        score_parts.month_add(START, 9), 60.0, params, abstained=True, abstain_reason="short_history"
    )
    assert outlook([*history, abstained], params).reason == "abstention"
    for fan in (outlook([], params), outlook([*history, stale], params)):
        assert not fan.available and fan.common is None and fan.best is None and fan.worst is None


def test_a_perimeter_shift_month_holds_the_score(score_parts, params) -> None:
    history = _history(score_parts, params, [70.0] * 9)
    shifted = history[:-1] + [replace(history[-1], flags=("perimeter_changed", "perimeter_shift"))]
    fan = outlook(shifted, params)
    assert (fan.basis, fan.gates) == ("flat", ("perimeter_shift",))
    assert fan.common == pytest.approx(70.0)
    assert fan.best == pytest.approx(76.0) and fan.worst == pytest.approx(64.0)
    # the same history without the shift measures a fit instead
    assert outlook(history, params).basis == "drift"


def test_every_flat_projection_travels_with_a_known_gate(score_parts, params) -> None:
    for scores in ([60.0] * 4, [70.0] * 5, [55.0] * 6):
        fan = outlook(_history(score_parts, params, scores), params)
        assert fan.available and (fan.basis == "flat") == (fan.gates != ())
    assert set(GATE_TEXTS) >= {"no_drift", "perimeter_shift"}
    assert all(GATE_TEXTS.values())


def test_forward_pass_equals_every_prefix_and_is_past_only(score_parts, params) -> None:
    rng = random.Random(63)
    seen: set[tuple] = set()
    for _ in range(30):
        history, score = [], rng.uniform(20.0, 90.0)
        for index in range(24):
            month = score_parts.month_add(START, index)
            score = min(100.0, max(0.0, score + rng.choice([0.0, 0.0, 2.0, -2.0, 8.0, -8.0, 15.0, -15.0])))
            if rng.random() < 0.1:
                history.append(score_parts.stale(month, score, params, score=60.0, carried_from=month))
                continue
            flags = ("perimeter_shift",) if rng.random() < 0.06 else ()
            history.append(score_parts.live(month, score, params, flags=flags))
        fans = outlooks(history, params)
        assert len(fans) == len(history)
        for size, fan in enumerate(fans, start=1):
            assert fan == outlook(history[:size], params)
            if not fan.available:
                assert fan.basis == "flat" and fan.gates == ()
                continue
            seen.add((fan.basis, *fan.gates))
            assert 0.0 <= fan.worst <= fan.common <= fan.best <= 100.0
            assert fan.horizon_months == params.trajectory.horizon_months
            assert (fan.gates != ()) == (fan.basis == "flat")
        assert outlooks(history, params) == fans  # deterministic
    assert seen == {("drift",), ("flat", "no_drift"), ("flat", "perimeter_shift")}
