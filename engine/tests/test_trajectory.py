"""Direction and nature: own-noise threshold, shock then structural (confirmed, not moving back,
expected to hold or spread over the window), bump, perimeter shift."""

from __future__ import annotations

import random
import statistics
from dataclasses import replace
from datetime import date

import pytest
from xray_engine.aggregate import aggregate
from xray_engine.contracts import PILLAR_KEYS, PanelRow, PillarResult
from xray_engine.trajectory import own_level, own_sigma, trajectories, trajectory, trajectory_note

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
    # half undone is the bar of a bump; short of it the call stands, unconfirmed while the score comes back
    partial = _verdicts(_history(score_parts, params, [70] * 8 + [56, 62.9, 62.9]), params)
    assert (partial[9].direction, partial[9].nature) == ("deteriorating", "shock_pending")
    assert partial[9].shock_month == partial[8].shock_month and partial[9].persistence_months == 2


def _natures(score_parts, params, scores) -> list[str]:
    codes = {("deteriorating", "shock_pending"): "d?", ("deteriorating", "structural"): "D",
             ("improving", "shock_pending"): "i?", ("improving", "structural"): "I",
             ("stable", "bump"): "b", ("stable", None): "-"}
    return [codes[(item.direction, item.nature)] for item in _verdicts(_history(score_parts, params, scores), params)]


def test_a_spike_on_its_way_back_is_not_a_second_month(score_parts, params) -> None:
    """A one-month event often takes two months to leave the score: the month in between is
    still beyond the threshold, and already six points or more on its way back."""
    spike = [70] * 8 + [40, 55, 69, 70, 70]
    assert _natures(score_parts, params, spike)[8:] == ["d?", "d?", "b", "b", "-"]
    verdicts = _verdicts(_history(score_parts, params, spike), params)
    assert verdicts[9].delta3 == pytest.approx(-15.0) and verdicts[9].persistence_months == 2
    # the bump names the first month of the shock, and no month of it is a base to compare against
    assert verdicts[10].shock_month == verdicts[11].shock_month == score_parts.month_add(START, 8)
    assert [verdicts[index].delta3 for index in (11, 12)] == [pytest.approx(30.0), pytest.approx(15.0)]
    assert _natures(score_parts, params, [50] * 8 + [80, 66, 51, 50, 50])[8:] == ["i?", "i?", "b", "b", "-"]
    # under six points back the second month confirms
    assert _natures(score_parts, params, [70] * 8 + [40, 45.9, 46, 46])[8:10] == ["d?", "D"]
    assert _natures(score_parts, params, [70] * 8 + [40, 46, 46, 46])[8:10] == ["d?", "d?"]


def test_a_two_month_dip_is_not_structural_unless_half_of_it_still_makes_a_move(score_parts, params) -> None:
    shallow = _natures(score_parts, params, [70] * 8 + [60, 60, 70, 70, 70])
    assert shallow[8:] == ["d?", "d?", "b", "b", "-"] and "D" not in shallow
    # a deep one cannot be told from a step in its second month; the month it comes back says so
    deep = _verdicts(_history(score_parts, params, [70] * 8 + [50, 50, 70, 70, 70]), params)
    assert [(item.direction, item.nature) for item in deep[8:]] == [
        ("deteriorating", "shock_pending"), ("deteriorating", "structural"), ("stable", "bump"),
        ("stable", None), ("stable", None),
    ]
    assert deep[10].shock_month == score_parts.month_add(START, 8)
    assert deep[12].delta3 == pytest.approx(20.0)  # against a month of the bump: no echo


def test_a_step_is_structural_when_it_is_expected_to_hold(score_parts, params) -> None:
    """Own level 70: a score is expected to keep half of its gap to it, and what is left
    must still be six points beyond the pre-move level."""
    cfg = params.trajectory
    assert (cfg.own_level_months, cfg.own_level_min_months, cfg.structural_retention) == (12, 4, 0.5)
    assert _natures(score_parts, params, [70] * 8 + [58] * 4)[8:] == ["d?", "D", "D", "-"]  # 6 left
    small = _natures(score_parts, params, [70] * 8 + [58.1] * 8)  # 5.95 left: never by the short horizon
    assert small[8:11] == ["d?", "d?", "d?"] and small[11] == "-"
    assert small[12:15] == ["d?", "D", "D"]  # the long horizon sees the new level some months later
    assert _natures(score_parts, params, [50] * 8 + [62] * 4)[8:] == ["i?", "I", "I", "-"]
    # back to the own level from an unusual quarter: nothing left to give back
    back = _natures(score_parts, params, [60] * 8 + [78, 78, 78, 61, 60, 60, 60])
    assert back[8:] == ["i?", "I", "I", "d?", "D", "D", "-"]
    # the same nine points away from the own level: half of them is not a move
    assert _natures(score_parts, params, [60] * 8 + [51] * 4)[8:] == ["d?", "d?", "d?", "-"]


def test_own_level_is_the_median_of_the_live_months_before_the_window(score_parts, params) -> None:
    history = _history(score_parts, params, [10, 20, 30, 40, 50, 60, 70, 80])
    assert own_level(history[:6], params) is None  # three months up to t - 3
    assert own_level(history[:7], params) == pytest.approx(25.0)  # months 0..3
    assert own_level(history, params) == pytest.approx(30.0)  # months 0..4; the window under test is left out
    long = _history(score_parts, params, list(range(20)))
    assert own_level(long, params) == pytest.approx(10.5)  # the twelve months 5..16
    stale = [score_parts.stale(item.month, 0.0, params, score=99.0, carried_from=START) if index in (1, 2) else item
             for index, item in enumerate(history)]
    assert own_level(stale, params) is None and own_level([], params) is None  # carried months do not count
    later = stale + _history(score_parts, params, [0] * 8 + [90])[8:]
    assert own_level(later, params) == pytest.approx(45.0)  # live months up to t - 3: 10, 40, 50, 60


def test_a_steady_decline_is_confirmed_by_its_spread_or_by_the_drift(score_parts, params) -> None:
    """The own level of a declining entity trails far above it, so the move is never expected
    to hold; it is confirmed because it does not rest on a single month."""
    fast = _verdicts(_history(score_parts, params, [70] * 8 + [70 - 3 * step for step in range(1, 9)]), params)
    assert [(item.nature, item.horizon) for item in fast[9:12]] == [
        ("shock_pending", "short"), ("structural", "short"), ("structural", "both"),
    ]
    assert fast[10].delta3 == pytest.approx(-9.0)  # without its largest step: six points, the bar
    slow = _verdicts(_history(score_parts, params, [70] * 8 + [70 - 2.5 * step for step in range(1, 9)]), params)
    assert [(item.nature, item.horizon) for item in slow[10:14]] == [
        ("shock_pending", "short"), ("shock_pending", "short"), ("shock_pending", "both"), ("structural", "both"),
    ]
    assert slow[13].delta3 == pytest.approx(-7.5) and slow[12].drift_call == slow[13].drift_call == "deteriorating"
    # one large step and two small ones: the move rests on one month
    lumpy = _natures(score_parts, params, [70] * 8 + [69, 68, 59, 59])
    assert lumpy[10:] == ["d?", "d?"]


def test_a_drift_is_not_confirmed_in_a_month_that_moves_back(score_parts, params) -> None:
    ramp = _ramp(82.0, 62.0)
    ramp[18] += 7.0  # one month six points or more against the drift
    verdicts = _verdicts(_history(score_parts, params, ramp), params)
    assert {item.drift_call for item in verdicts[10:]} == {"deteriorating"}  # the median slope does not move
    assert [item.nature for item in verdicts[16:21]] == [
        "structural", "structural", "shock_pending", "structural", "structural",
    ]
    assert verdicts[18].persistence_months == verdicts[17].persistence_months + 1  # the run goes on
    ramp[18] -= 1.5  # five and a half points back: still confirmed
    assert trajectory(_history(score_parts, params, ramp)[:19], params).nature == "structural"


def test_noise_around_a_level_is_seldom_structural(score_parts, params) -> None:
    rng = random.Random(65)
    cfg = params.trajectory
    structural = available = 0
    for _ in range(60):
        scores = [60.0 + rng.uniform(-4.0, 4.0) for _ in range(36)]
        history = _history(score_parts, params, scores)
        verdicts = trajectories(history, params)
        for index, item in enumerate(verdicts):
            available += item.available
            if item.nature != "structural":
                continue
            structural += 1
            sign = 1.0 if item.direction == "improving" else -1.0
            assert (scores[index] - scores[index - 1]) * sign > -cfg.min_delta_points  # never on its way back
            if item.horizon == "short":
                own = own_level(history[: index + 1], params)
                left = (own + cfg.structural_retention * (scores[index] - own) - scores[index - 3]) * sign
                steps = [(after - before) * sign for before, after in zip(scores[index - 3:], scores[index - 2: index + 1])]
                threshold = max(cfg.min_delta_points, cfg.min_sigma_multiple * item.sigma)
                assert left >= cfg.min_delta_points - TOL or sum(steps) - max(steps) >= threshold - TOL
    assert available > 1500 and structural <= 0.005 * available


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
    seen, horizons, conflicts = set(), set(), []
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
            threshold = None if verdict.delta3 is None else max(
                params.trajectory.min_delta_points, params.trajectory.min_sigma_multiple * verdict.sigma)
            if verdict.nature == "structural":
                # one horizon held its own condition, same sign, the month before too
                before = verdicts[size - 2]
                held_short = verdict.horizon in ("short", "both") and before.horizon in ("short", "both") \
                    and before.direction == verdict.direction
                held_long = verdict.drift_call == verdict.direction and before.drift_call == verdict.direction
                assert held_short or held_long
                assert history[size - 2].month == score_parts.month_add(history[size - 1].month, -1)
                # never a structural call against a three-month move beyond the threshold
                against = -verdict.delta3 if verdict.direction == "improving" else verdict.delta3
                assert against < threshold
            if verdict.drift_call not in (None, verdict.direction) and verdict.direction in ("improving", "deteriorating"):
                assert (verdict.nature, verdict.horizon) == ("shock_pending", "short")
                assert trajectory_note(verdict) is not None
                conflicts.append(verdict)
            else:
                assert trajectory_note(verdict) is None
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
    assert conflicts  # the conflict branch is exercised
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
        # the drift is confirmed like a short call: pending in its first month, structural from the next
        assert [verdicts[index].nature for index in called[:3]] == ["shock_pending", "structural", "structural"]
        assert verdicts[called[0]].shock_pending and {verdicts[index].horizon for index in called} == {"long"}
        assert all(verdicts[index].drift_call == expected for index in called)
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


def test_both_horizons_agree_and_the_short_one_makes_the_call_on_a_conflict(score_parts, params) -> None:
    falling = _ramp(90.0, 68.0, 12) + [58.0]  # a slow fall that ends with a drop
    verdict = trajectory(_history(score_parts, params, falling), params)
    assert (verdict.direction, verdict.horizon, verdict.nature) == ("deteriorating", "both", "structural")
    assert verdict.persistence_months >= 1 and not verdict.shock_pending and trajectory_note(verdict) is None

    # a year of steady decline and a sharp rebound: the recent move makes the call, unconfirmed,
    # for as long as the twelve-month drift points the other way
    rebound = _ramp(90.0, 57.0, 12) + [72.0, 74.0, 75.0]
    history = _history(score_parts, params, rebound)
    verdicts = trajectories(history, params)
    assert (verdicts[11].direction, verdicts[11].nature) == ("deteriorating", "structural")
    for verdict in verdicts[12:]:
        assert verdict.delta3 > params.trajectory.min_delta_points and verdict.drift_points < 0
        assert verdict.drift_call == "deteriorating"
        assert (verdict.direction, verdict.horizon, verdict.nature) == ("improving", "short", "shock_pending")
        note = trajectory_note(verdict)
        assert "todavía apunta a la baja" in note and f"{verdict.drift_months} meses" in note
    assert [verdict.persistence_months for verdict in verdicts[12:]] == [1, 2, 3]
    # the mirror case reads the other way
    slump = _history(score_parts, params, _ramp(40.0, 73.0, 12) + [58.0])
    verdict = trajectory(slump, params)
    assert (verdict.direction, verdict.horizon, verdict.nature) == ("deteriorating", "short", "shock_pending")
    assert "todavía apunta al alza" in trajectory_note(verdict)


def test_a_one_month_spike_never_confirms_the_long_horizon(score_parts, params) -> None:
    # a mild decline, under the long bar, and one bad month that pushes the fitted drift over it
    mild = [71.0, 69.4, 68.8, 69.2, 66.6, 67.5, 65.9, 64.8, 64.7, 63.6, 64.0, 63.9, 62.3]
    spike = mild + [mild[-1] - 25.0]
    history = _history(score_parts, params, spike)
    verdict = trajectory(history, params)
    assert verdict.drift_call == "deteriorating" and trajectory(history[:-1], params).drift_call is None
    assert (verdict.direction, verdict.horizon, verdict.nature) == ("deteriorating", "both", "shock_pending")
    # the month after, the score is back: a bump, never structural
    back = _history(score_parts, params, spike + [mild[-1] - 0.6])
    after = trajectory(back, params)
    assert (after.direction, after.nature, after.shock_month) == ("stable", "bump", history[-1].month)
    # a step that stays is structural in its second month
    step = _history(score_parts, params, spike + [mild[-1] - 25.0])
    stayed = trajectory(step, params)
    assert (stayed.direction, stayed.nature, stayed.persistence_months) == ("deteriorating", "structural", 2)


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
