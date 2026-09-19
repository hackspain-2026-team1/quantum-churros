"""Direction and nature: own-noise threshold, shock then structural, bump, perimeter shift."""

from __future__ import annotations

import random
import statistics
from dataclasses import replace
from datetime import date

import pytest
from xray_engine.aggregate import aggregate
from xray_engine.contracts import PILLAR_KEYS, PanelRow, PillarResult
from xray_engine.trajectory import own_sigma, trajectories, trajectory

TOL = 1e-9
START = date(2025, 1, 1)


def _history(score_parts, params, scores, **overrides):
    return [
        score_parts.live(score_parts.month_add(START, index), float(score), params, **overrides)
        for index, score in enumerate(scores)
    ]


def _verdicts(history, params):
    return [trajectory(history[: size + 1], params) for size in range(len(history))]


def test_needs_six_scored_months_and_a_live_feed(score_parts, params) -> None:
    history = _history(score_parts, params, [70, 70, 70, 50, 50, 50, 50])
    verdicts = _verdicts(history, params)
    for verdict in verdicts[:5]:
        assert (verdict.available, verdict.reason, verdict.direction) == (False, "short_history", "stable")
        assert verdict.nature is None and verdict.delta3 is None and not verdict.shock_pending
    assert verdicts[5].available and verdicts[5].reason is None
    assert verdicts[5].delta3 == pytest.approx(-20.0) and verdicts[5].compared_to == date(2025, 3, 1)

    stale = score_parts.stale(score_parts.month_add(START, 7), 50.0, params)
    verdict = trajectory([*history, stale], params)
    assert (verdict.available, verdict.reason, verdict.direction) == (False, "stale_feed", "stable")
    # a hole where month t-3 should be: not comparable
    gap = history[:3] + _history(score_parts, params, [0] * 4 + [50, 50, 50, 50])[4:]
    assert trajectory(gap[:-1] + [replace(gap[-1], month=date(2025, 12, 1))], params).reason == "short_history"


def test_direction_fires_at_the_larger_of_six_points_and_own_noise(score_parts, params) -> None:
    calm = [60.0] * 9
    for delta, expected in ((5.9, "stable"), (6.0, "improving"), (-6.0, "deteriorating"), (-5.9, "stable")):
        verdict = trajectory(_history(score_parts, params, [*calm, 60.0 + delta]), params)
        assert verdict.direction == expected, delta
        assert verdict.sigma == params.trajectory.sigma_floor
        assert verdict.delta3_sigma == pytest.approx(delta / 2.0)

    rng = random.Random(61)
    noisy = [60.0]
    for _ in range(14):
        noisy.append(noisy[-1] + rng.choice([-7.0, 7.0, -5.0, 5.0]))
    changes = [b - a for a, b in zip(noisy, noisy[1:])]
    sigma = statistics.stdev(changes)  # every change is at or before t - 3
    assert sigma > 4.0
    base = _history(score_parts, params, noisy)
    for delta in (1.5 * sigma - 0.01, 1.5 * sigma + 0.01, -(1.5 * sigma + 0.01)):
        tail = [noisy[-1], noisy[-1], noisy[-1] + delta]
        history = base + [
            score_parts.live(score_parts.month_add(START, len(noisy) + index), value, params)
            for index, value in enumerate(tail)
        ]
        verdict = trajectory(history, params)
        assert verdict.sigma == pytest.approx(sigma, abs=TOL)  # the window under test is left out
        assert verdict.delta3 == pytest.approx(delta, abs=TOL)
        expected = "stable" if abs(delta) < 1.5 * sigma else ("improving" if delta > 0 else "deteriorating")
        assert verdict.direction == expected
    assert own_sigma(base, params) == pytest.approx(statistics.stdev(changes[:-3]), abs=TOL)
    assert own_sigma(base[:5], params) == params.trajectory.sigma_floor  # fewer than three changes


def test_first_month_is_a_pending_shock_then_structural(score_parts, params) -> None:
    history = _history(score_parts, params, [70] * 8 + [56] * 5)
    verdicts = _verdicts(history, params)
    step = verdicts[8]
    assert (step.direction, step.nature, step.shock_pending) == ("deteriorating", "shock_pending", True)
    assert step.shock_month == history[8].month and step.persistence_months == 1
    assert step.detected_since == history[8].month
    for index in (9, 10):
        verdict = verdicts[index]
        assert (verdict.direction, verdict.nature, verdict.shock_pending) == (
            "deteriorating", "structural", False,
        )
        assert verdict.persistence_months == index - 7 and verdict.detected_since == history[8].month
    settled = verdicts[11]  # the step left the three-month window: a new level, not a bump
    assert (settled.direction, settled.nature, settled.persistence_months) == ("stable", None, 0)
    assert settled.detected_since is None
    # past-only: a verdict never changes when later months arrive
    assert verdicts[8] == trajectory(history[:9], params)


def test_a_spike_that_reverts_is_a_bump(score_parts, params) -> None:
    history = _history(score_parts, params, [70] * 8 + [55, 69, 70, 70, 70])
    verdicts = _verdicts(history, params)
    assert verdicts[8].nature == "shock_pending"
    back = verdicts[9]
    assert (back.direction, back.nature, back.shock_month) == ("stable", "bump", history[8].month)
    assert not back.shock_pending and back.persistence_months == 0
    assert verdicts[10].nature == "bump"  # still inside the two-month look-back
    # three months later the spike is the comparison month: no echo in the other direction
    echo = verdicts[11]
    assert echo.delta3 == pytest.approx(15.0) and echo.compared_to == history[8].month
    assert (echo.direction, echo.nature, echo.persistence_months) == ("stable", None, 0)
    assert all(verdict.nature != "structural" for verdict in verdicts)
    assert [verdict.direction for verdict in verdicts[9:]] == ["stable"] * 4

    # an improvement spike behaves the same way
    up = _verdicts(_history(score_parts, params, [50] * 8 + [64, 51, 50]), params)
    assert [item.nature for item in up[8:]] == ["shock_pending", "bump", "bump"]
    assert up[8].direction == "improving"
    # half undone is the bar
    partial = _verdicts(_history(score_parts, params, [70] * 8 + [56, 62.9, 62.9]), params)
    assert partial[9].direction == "deteriorating" and partial[9].nature == "structural"


def test_perimeter_shift_replaces_the_direction_call(score_parts, params) -> None:
    history = _history(score_parts, params, [70] * 8 + [50])
    assert trajectory(history, params).direction == "deteriorating"
    shifted = history[:-1] + [replace(history[-1], flags=("perimeter_changed", "perimeter_shift"))]
    verdict = trajectory(shifted, params)
    assert (verdict.available, verdict.direction, verdict.nature) == (True, "perimeter_shift", None)
    assert verdict.delta3 == pytest.approx(-20.0) and not verdict.shock_pending
    assert verdict.persistence_months == 0 and verdict.detected_since is None
    # a perimeter change alone (no shift of the inflow) keeps the call
    changed = history[:-1] + [replace(history[-1], flags=("perimeter_changed",))]
    assert trajectory(changed, params).direction == "deteriorating"
    # a shifted month breaks a run: the month after starts again as a pending shock
    later = shifted + _history(score_parts, params, [0] * 9 + [50])[9:]
    assert trajectory(later, params).nature == "shock_pending"


def test_pillars_moved_is_descriptive(score_parts, params) -> None:
    def scores(liquidity, activity, payments=None):
        return {"liquidity": liquidity, "payments": payments, "collections": None,
                "activity": activity, "debt": None}

    history = _history(score_parts, params, [70] * 8 + [56])
    history[5] = replace(history[5], pillar_scores=scores(80.0, 60.0, 90.0))
    history[8] = replace(history[8], pillar_scores=scores(50.0, 64.0))
    verdict = trajectory(history, params)
    assert verdict.pillars_moved == ("liquidity",)  # activity rose, payments is gone at t
    assert verdict.nature == "shock_pending"  # pillars no longer decide the nature


def test_stale_months_are_flat_and_do_not_feed_the_noise(score_parts, params) -> None:
    live = _history(score_parts, params, [60, 66, 60, 66, 60, 66, 60, 66])
    frozen = [
        score_parts.stale(score_parts.month_add(START, 8 + index), 20.0, params, score=66.0,
                          carried_from=live[-1].month)
        for index in range(4)
    ]
    back = [score_parts.live(score_parts.month_add(START, 12 + index), 66.0, params) for index in range(4)]
    history = live + frozen + back
    verdict = trajectory(history, params)
    assert verdict.available and verdict.delta3 == 0.0 and verdict.direction == "stable"
    expected = statistics.stdev([6.0, -6.0] * 3 + [6.0])  # live-to-live changes only
    assert verdict.sigma == pytest.approx(expected, abs=TOL)


def _scored(score_parts, params, index, months_observed=12, **scores):
    """A live month aggregated from pillar scores: the branch is whatever is given."""
    row = PanelRow(entity_kind="group", entity_id="GROUP_X", group_id="GROUP_X",
                   month=score_parts.month_add(START, index), months_observed=months_observed,
                   rows_month=100, rows_3m=300, rows_base_median=100.0, rows_base_months=9)
    pillars = {
        key: PillarResult(key=key, score=scores.get(key), gates=() if key in scores else ("no_base",))
        for key in PILLAR_KEYS
    }
    return aggregate(pillars, row, params)


def test_a_pillar_that_drops_out_is_not_a_trajectory(score_parts, params) -> None:
    def history(after: dict[str, float], before: dict[str, float] | None = None):
        before = before or dict(liquidity=80.0, payments=32.0, activity=80.0)
        return [_scored(score_parts, params, index, **(before if index < 8 else after)) for index in range(11)]

    # the weak payments pillar stops being observable: the level jumps, the entity did not change
    gone = history(dict(liquidity=80.0, activity=80.0))
    assert gone[8].score - gone[7].score > 15 and gone[8].branch != gone[7].branch
    verdicts = _verdicts(gone, params)
    assert [verdict.direction for verdict in verdicts[8:]] == ["stable"] * 3
    assert verdicts[8].delta3 == pytest.approx(gone[8].score - gone[5].score, abs=TOL)  # still reported
    assert all(verdict.nature is None and verdict.pillars_moved == () for verdict in verdicts[8:])
    # with the same branch at both ends the same jump is a call
    same_branch = _history(score_parts, params, [gone[0].score] * 8 + [gone[8].score])
    assert trajectory(same_branch, params).direction == "improving"

    # the pillars present at both ends confirm the move: the call stands
    better = _verdicts(history(dict(liquidity=100.0, activity=95.0)), params)
    assert [(item.direction, item.nature) for item in better[8:10]] == [
        ("improving", "shock_pending"), ("improving", "structural"),
    ]
    assert better[8].pillars_moved == ("liquidity", "activity")
    # they move the other way: no call in either direction
    worse = _verdicts(history(dict(liquidity=70.0, activity=75.0)), params)
    assert worse[8].delta3 > 6 and [item.direction for item in worse[8:]] == ["stable"] * 3

    # a pillar that comes online (debt after six months in its window) is no call either
    arrived = history(dict(liquidity=60.0, activity=60.0, debt=100.0), dict(liquidity=60.0, activity=60.0))
    assert arrived[8].score - arrived[7].score > 6
    assert [item.direction for item in _verdicts(arrived, params)[8:]] == ["stable"] * 3
    # nothing comparable at both ends
    swapped = history(dict(payments=20.0, debt=30.0), dict(liquidity=90.0, activity=90.0))
    assert [item.direction for item in _verdicts(swapped, params)[8:]] == ["stable"] * 3

    # a pillar that flickers in and out does not pass for the noise of the entity
    flicker = [
        _scored(score_parts, params, index, liquidity=80.0, activity=80.0,
                **(dict(payments=32.0) if index % 2 else {}))
        for index in range(14)
    ]
    assert max(abs(b.score - a.score) for a, b in zip(flicker, flicker[1:])) > 15
    assert own_sigma(flicker, params) == params.trajectory.sigma_floor
    assert [item.direction for item in _verdicts(flicker, params)] == ["stable"] * 14


def test_momentum_coming_online_is_not_a_trajectory(score_parts, params) -> None:
    onset = params.activity.min_months_observed

    def history(first_observed: int, liquidity_after: float = 60.0):
        # activity jumps on the seventh month of the series
        return [
            _scored(score_parts, params, index, months_observed=first_observed + index,
                    liquidity=liquidity_after if index >= onset - 1 else 60.0,
                    activity=95.0 if index >= onset - 1 else 50.0)
            for index in range(10)
        ]

    young = history(1)  # the jump lands on the month the momentum sub-score appears
    jump = young[onset - 1].score - young[onset - 2].score
    assert jump > 6 and young[onset - 1].branch == young[onset - 2].branch
    assert [item.direction for item in _verdicts(young, params)] == ["stable"] * 10
    confirmed = _verdicts(history(1, liquidity_after=85.0), params)  # liquidity moves too
    assert [item.direction for item in confirmed[onset - 1: onset + 2]] == ["improving"] * 3
    mature = _verdicts(history(10), params)  # same jump, momentum present at both ends
    assert [item.direction for item in mature[onset - 1: onset + 2]] == ["improving"] * 3


def test_switching_to_the_cash_of_the_group_is_not_a_trajectory(score_parts, params) -> None:
    def history(liquidity_after: float, activity_after: float):
        months = [_scored(score_parts, params, index, liquidity=20.0, activity=70.0) for index in range(8)]
        for index in range(8, 11):  # from here on the liquidity shown is the one of the group
            parts = _scored(score_parts, params, index, liquidity=liquidity_after, activity=activity_after)
            months.append(replace(parts, flags=(*parts.flags, "inherited_from_group")))
        return months

    swept = history(85.0, 70.0)
    assert swept[8].score - swept[7].score > 30 and swept[8].branch == swept[7].branch
    assert [item.direction for item in _verdicts(swept, params)[8:]] == ["stable"] * 3
    confirmed = _verdicts(history(85.0, 90.0), params)  # activity, comparable, moves as well
    assert [item.direction for item in confirmed[8:10]] == ["improving"] * 2
    later = swept + [
        replace(_scored(score_parts, params, index, liquidity=60.0, activity=70.0),
                flags=("inherited_from_group",))
        for index in range(11, 14)
    ]  # inherited at both ends: the usual rule, and the switch is not part of the own noise
    verdict = trajectory(later, params)
    assert verdict.sigma == params.trajectory.sigma_floor and verdict.direction == "deteriorating"


def test_forward_pass_equals_every_prefix_and_is_past_only(score_parts, params) -> None:
    rng = random.Random(62)
    seen, horizons = set(), set()
    for _ in range(40):
        history, score, last_live = [], rng.uniform(30, 80), None
        for index in range(30):
            if rng.random() < 0.05:
                continue  # a month without a row
            month = score_parts.month_add(START, index)
            score = min(100.0, max(0.0, score + rng.choice([0.0, 0.0, 1.5, -1.5, 9.0, -9.0, 16.0, -16.0])))
            if last_live is not None and rng.random() < 0.12:
                history.append(score_parts.stale(month, score, params, score=last_live.score,
                                                 carried_from=last_live.month))
                continue
            flags = ("perimeter_shift",) if rng.random() < 0.06 else ()
            last_live = score_parts.live(month, score, params, flags=flags)
            history.append(last_live)
        verdicts = trajectories(history, params)
        assert len(verdicts) == len(history)
        for size, verdict in enumerate(verdicts, start=1):
            assert verdict == trajectory(history[:size], params)
            seen.add((verdict.reason, verdict.direction, verdict.nature))
            if verdict.nature == "structural" and verdict.horizon == "short":
                assert verdict.persistence_months >= params.trajectory.structural_consecutive_months
            if verdict.nature == "shock_pending":
                assert verdict.horizon == "short"
            if verdict.direction in ("stable", "perimeter_shift"):
                assert verdict.persistence_months == 0 and verdict.detected_since is None
                assert verdict.horizon is None
            else:
                assert verdict.horizon in ("short", "long", "both") and verdict.persistence_months >= 1
            horizons.add(verdict.horizon)
        assert trajectories(history, params) == verdicts  # deterministic
    assert {nature for _, _, nature in seen} == {None, "shock_pending", "structural", "bump"}
    assert {reason for reason, _, _ in seen} == {None, "short_history", "stale_feed"}
    assert {direction for _, direction, _ in seen} >= {"improving", "deteriorating", "perimeter_shift"}
    assert horizons == {None, "short", "long", "both"}
    assert trajectory([], params).reason == "short_history"


def _ramp(first: float, last: float, count: int = 24) -> list[float]:
    return [first + (last - first) * index / (count - 1) for index in range(count)]


def test_a_slow_drift_is_seen_by_the_long_horizon_only(score_parts, params) -> None:
    """Under a point a month never reaches |delta3| >= 6; twelve months of it add up."""
    cfg = params.trajectory
    for first, last, expected in ((45.0, 65.0, "improving"), (82.0, 62.0, "deteriorating")):
        history = _history(score_parts, params, _ramp(first, last))
        verdicts = _verdicts(history, params)
        assert verdicts == trajectories(history, params)
        slope = (last - first) / 23
        assert all(abs(item.delta3) < cfg.min_delta_points for item in verdicts if item.available)
        final = verdicts[-1]
        assert (final.direction, final.nature, final.horizon) == (expected, "structural", "long")
        assert not final.shock_pending and final.shock_month is None
        assert final.drift_months == cfg.long_horizon
        assert final.drift_points == pytest.approx(slope * cfg.long_horizon, abs=1e-6)
        # the call starts when the fitted drift crosses the bar and then holds month after month
        called = [index for index, item in enumerate(verdicts) if item.direction == expected]
        months_needed = next(h for h in range(cfg.long_min_months, cfg.long_horizon + 1)
                             if abs(slope) * h >= cfg.long_threshold)
        assert called == list(range(months_needed - 1, 24))
        assert [verdicts[index].persistence_months for index in called] == list(range(1, len(called) + 1))
        assert {verdicts[index].detected_since for index in called} == {history[called[0]].month}
        for index in range(cfg.min_scored_months - 1, called[0]):
            assert verdicts[index].direction == "stable" and verdicts[index].horizon is None
            assert verdicts[index].drift_points == pytest.approx(slope * (index + 1), abs=1e-6)

    # below the bar over twelve months: stable on both horizons, the drift is still reported
    flat = trajectory(_history(score_parts, params, _ramp(70.0, 70.0 - 0.5 * 23)), params)
    assert (flat.direction, flat.horizon, flat.nature) == ("stable", None, None)
    assert flat.drift_points == pytest.approx(-6.0, abs=1e-6)


def test_long_horizon_is_robust_to_a_spike_and_needs_six_months(score_parts, params) -> None:
    # one bad month inside a flat year: the median slope does not move
    spiked = [70.0] * 12
    spiked[6] = 40.0
    verdict = trajectory(_history(score_parts, params, spiked), params)
    assert verdict.drift_points == pytest.approx(0.0, abs=TOL) and verdict.direction == "stable"
    # a noisy entity needs a larger drift: 2 sigma of its own monthly changes
    rng = random.Random(64)
    noisy = [60.0]
    for _ in range(11):
        noisy.append(noisy[-1] + rng.choice([-9.0, 9.0]))
    tail = [noisy[-1] - 0.8 * step for step in range(1, 13)]
    history = _history(score_parts, params, noisy + tail)
    verdict = trajectory(history, params)
    assert verdict.sigma > 5.0 and abs(verdict.drift_points) >= params.trajectory.long_threshold
    assert abs(verdict.drift_points) < params.trajectory.long_sigma_mult * verdict.sigma
    assert verdict.direction == "stable"
    # fewer than long_min_months comparable live months: no drift at all
    young = _history(score_parts, params, _ramp(80.0, 60.0, 6))
    stale = [score_parts.stale(item.month, item.score, params, score=80.0, carried_from=START)
             if index in (2, 3) else item for index, item in enumerate(young)]
    assert trajectory(young, params).drift_months == 6
    assert trajectory(stale + _history(score_parts, params, [0] * 6 + [60.0])[6:], params).drift_points is None


def test_both_horizons_and_the_long_one_wins_a_conflict(score_parts, params) -> None:
    falling = _ramp(90.0, 68.0, 12) + [58.0]  # a slow fall that ends with a drop
    verdict = trajectory(_history(score_parts, params, falling), params)
    assert (verdict.direction, verdict.horizon, verdict.nature) == ("deteriorating", "both", "structural")
    assert verdict.persistence_months >= 1 and not verdict.shock_pending

    # a year of steady decline and a rebound in the last month: the long horizon keeps the call
    rebound = _ramp(90.0, 57.0, 12) + [72.0]
    verdict = trajectory(_history(score_parts, params, rebound), params)
    assert verdict.delta3 > params.trajectory.min_delta_points and verdict.drift_points < 0
    assert (verdict.direction, verdict.horizon, verdict.nature) == ("deteriorating", "long", "structural")


def test_long_window_only_holds_months_measured_like_the_last_one(score_parts, params) -> None:
    def ramp(**late):
        months = []
        for index in range(14):
            extra = late if index >= 5 else {}
            months.append(_scored(score_parts, params, index, liquidity=40.0 + 2.5 * index,
                                  activity=40.0 + 2.5 * index, **extra))
        return months

    plain = trajectory(ramp(), params)
    assert plain.horizon in ("long", "both") and plain.drift_months == params.trajectory.long_horizon
    # a pillar that comes online in between: the fit starts there
    arrived = ramp(debt=90.0)
    assert arrived[5].score - arrived[4].score > 6
    verdict = trajectory(arrived, params)
    assert verdict.drift_months == 9 and verdict.drift_points == pytest.approx(
        9 * 2.5 * (1 - params.weights["debt"] / (1 - params.weights["payments"] - params.weights["collections"])),
        abs=1e-6,
    )
    # months before a perimeter shift describe another perimeter
    shifted = ramp()
    shifted[9] = replace(shifted[9], flags=("perimeter_changed", "perimeter_shift"))
    assert trajectory(shifted, params).drift_points is None  # four months since: not enough
    assert trajectory(shifted[:10], params).direction == "perimeter_shift"
    assert trajectory(shifted[:10], params).drift_points is None


def test_a_size_band_change_is_not_like_for_like(score_parts, params) -> None:
    """Another band reads another liquidity table: the level moves, the entity did not."""
    def history(liquidity_after: float, activity_after: float = 70.0):
        months = []
        for index in range(11):
            late = index >= 8
            parts = _scored(score_parts, params, index, liquidity=liquidity_after if late else 40.0,
                            activity=activity_after if late else 70.0)
            months.append(replace(parts, size_band="medium" if late else "small"))
        return months

    jumped = history(85.0)
    assert jumped[8].score - jumped[7].score > 15 and jumped[8].branch == jumped[7].branch
    verdicts = _verdicts(jumped, params)
    assert [item.direction for item in verdicts[8:]] == ["stable"] * 3
    assert verdicts[8].delta3 == pytest.approx(jumped[8].score - jumped[5].score, abs=TOL)
    assert own_sigma(jumped + jumped[-1:] * 0, params) == params.trajectory.sigma_floor
    same_band = [replace(item, size_band="small") for item in jumped]
    assert trajectory(same_band[:9], params).direction == "improving"
    confirmed = _verdicts(history(85.0, activity_after=90.0), params)  # activity, comparable, moves too
    assert [item.direction for item in confirmed[8:10]] == ["improving"] * 2
    # with absolute anchors the band plays no part
    absolute = replace(params, liquidity=replace(params.liquidity, segmented=False))
    assert trajectory(jumped[:9], absolute).direction == "improving"
