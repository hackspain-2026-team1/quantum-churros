"""Suggested actions: a lever is a delta over the measured month and the uplift
is the aggregate recomputed over the month it produces, never an estimate."""

from __future__ import annotations

import random

from xray_engine.actions import (
    MAX_ACTIONS,
    MAX_STAGES,
    MAX_STEP,
    MIN_UPLIFT,
    TARGET_CEILING,
    invert,
    plan_actions,
    step_target,
    suggest_actions,
)
from xray_engine.aggregate import aggregate
from xray_engine.contracts import PILLAR_KEYS
from xray_engine.pillars import compute_pillars

LIVE = dict(rows_month=100, rows_3m=300, rows_base_median=100.0, rows_base_months=9,
            zero_row_month=False, months_observed=24)
N_ROWS = 1_500


def _cases(panel_rows, params, seed: int, **overrides):
    rng = random.Random(seed)
    for _ in range(N_ROWS):
        row = panel_rows.random(rng, **{**LIVE, **overrides})
        pillars = compute_pillars(row, params)
        yield row, pillars, aggregate(pillars, row, params)


def test_uplift_is_the_engine_rescoring_the_month_with_the_lever(panel_rows, params) -> None:
    seen: set[str] = set()
    for row, pillars, parts in _cases(panel_rows, params, 71):
        plan = plan_actions(row, pillars, parts, params)
        combined_row = row
        for action in plan.actions:
            result = pillars[action.pillar]
            assert result.score is not None and result.score < TARGET_CEILING
            new_row = action.row_delta(row)
            new_pillars = compute_pillars(new_row, params)
            again = aggregate(new_pillars, new_row, params)
            assert action.new_score == again.score
            assert action.pillar_target == new_pillars[action.pillar].score
            assert action.pillar_target >= result.score - 1e-9  # the lever helps its own pillar
            assert action.uplift == again.score - parts.score
            assert action.uplift_tenths == action.new_score_tenths - round(parts.score * 10)
            assert action.id.startswith(f"{action.pillar}-") and action.effort in ("bajo", "medio", "alto")
            assert action.title and action.detail and len(action.detail) <= 400
            combined_row = action.row_delta(combined_row)
            seen.add(action.id)
        combined_pillars = compute_pillars(combined_row, params)
        assert plan.combined_score == aggregate(combined_pillars, combined_row, params).score
        assert plan.combined_uplift == plan.combined_score - parts.score
    assert {key for key in PILLAR_KEYS} == {name.split("-")[0] for name in seen}


def test_actions_never_lower_the_score_and_are_sorted_and_bounded(panel_rows, params) -> None:
    with_actions = 0
    for row, pillars, parts in _cases(panel_rows, params, 72):
        plan = plan_actions(row, pillars, parts, params)
        uplifts = [action.uplift for action in plan.actions]
        assert all(uplift >= MIN_UPLIFT for uplift in uplifts)
        assert uplifts == sorted(uplifts, reverse=True) and len(uplifts) <= MAX_ACTIONS
        assert len({action.pillar for action in plan.actions}) == len(uplifts)
        with_actions += bool(uplifts)
    assert with_actions > N_ROWS // 4


def test_the_ladder_rescores_each_stage_up_to_the_best_achievable(panel_rows, params) -> None:
    ladders = 0
    for row, pillars, parts in _cases(panel_rows, params, 78):
        plan = plan_actions(row, pillars, parts, params)
        if not plan.stages:
            assert plan.actions == () and plan.max_score == parts.score
            continue
        ladders += 1
        assert [stage.number for stage in plan.stages] == list(range(1, len(plan.stages) + 1))
        assert len(plan.stages) <= MAX_STAGES
        state = row
        for stage in plan.stages:
            assert stage.actions  # every stage suggests something
            for action in stage.actions:
                state = action.row_delta(state)
            new_pillars = compute_pillars(state, params)
            assert stage.score == aggregate(new_pillars, state, params).score
            assert stage.uplift == stage.score - parts.score
        assert plan.max_score == plan.stages[-1].score
        assert plan.max_uplift == plan.max_score - parts.score
        assert plan.max_uplift >= 0.0
    assert ladders > N_ROWS // 4


def test_targets_move_the_input_in_the_right_direction(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 73):
        for action in suggest_actions(row, pillars, parts, params):
            lower_is_better = action.pillar in ("payments", "collections", "debt")
            assert (action.target < action.current) if lower_is_better else (action.target > action.current)


def test_paying_suppliers_earlier_costs_cash(panel_rows, params) -> None:
    """The payments lever moves cash out, so the rescored liquidity pays for it."""
    checked = 0
    for row, pillars, parts in _cases(panel_rows, params, 79):
        for action in plan_actions(row, pillars, parts, params).actions:
            if action.pillar != "payments":
                continue
            new_row = action.row_delta(row)
            assert new_row.cash_month_end < row.cash_month_end  # cash went out
            checked += 1
            break
        if checked:
            break
    assert checked > 0


def test_no_actions_on_abstained_or_stale_months(panel_rows, params) -> None:
    abstained = stale = 0
    for row, pillars, parts in _cases(panel_rows, params, 74, months_observed=1):
        if parts.abstained:
            abstained += 1
            assert plan_actions(row, pillars, parts, params).actions == ()
    for row, pillars, parts in _cases(panel_rows, params, 75, rows_month=0, rows_3m=0, zero_row_month=True):
        if not parts.feed_live:
            stale += 1
            plan = plan_actions(row, pillars, parts, params)
            assert plan.actions == () and plan.combined_uplift == 0.0
    assert abstained > 100 and stale > 100


def test_inherited_liquidity_is_not_a_lever(panel_rows, params) -> None:
    rng = random.Random(76)
    checked = 0
    for _ in range(400):
        row = panel_rows.random(rng, **LIVE, swept_subsidiary=True)
        group_row = panel_rows.random(rng, **LIVE)
        pillars = compute_pillars(row, params, group_row)
        parts = aggregate(pillars, row, params, group_row)
        checked += "inherited_from_group" in pillars["liquidity"].gates
        assert all(a.pillar != "liquidity" for a in suggest_actions(row, pillars, parts, params, group_row))
    assert checked == 400


def test_actions_are_deterministic(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 77):
        first = plan_actions(row, pillars, parts, params)
        shuffled = dict(reversed(list(pillars.items())))
        assert first == plan_actions(row, pillars, parts, params) == plan_actions(row, shuffled, parts, params)


def test_invert_and_step_target(params) -> None:
    for key in ("payments", "collections", "debt_burden", "activity_coverage"):
        table = params.anchors[key]
        for score in (0.0, 12.5, 40.0, 61.0, 79.0):
            target = step_target(score, table)
            if target is None or score < min(y for _, y in table.points):
                continue
            assert score < target <= min(TARGET_CEILING, score + MAX_STEP)
            x = invert(table, target, table.points[0][0])
            assert x is not None and abs(table(x) - target) < 1e-9
    assert step_target(80.0, params.anchors["payments"]) is None


def test_levers_never_ask_for_more_than_a_plausible_move(panel_rows, params) -> None:
    from xray_engine.actions import MAX_BURDEN_CUT, MAX_COVERAGE_GAIN, MAX_DAYS_GAIN, MAX_EXTRA_BUFFER_DAYS

    kinds: set[str] = set()
    for row, pillars, parts in _cases(panel_rows, params, 74):
        for action in plan_actions(row, pillars, parts, params).actions:
            kind = action.id.split("-", 1)[1]
            kinds.add(kind)
            if kind == "buffer":
                assert action.target - action.current <= MAX_EXTRA_BUFFER_DAYS + 1e-6
            elif kind in ("punctuality", "speed"):
                assert action.current - action.target <= MAX_DAYS_GAIN + 1e-6
            elif kind == "coverage":
                assert action.target <= action.current * (1 + MAX_COVERAGE_GAIN) + 1e-9
            else:
                assert action.target >= action.current * (1 - MAX_BURDEN_CUT) - 1e-9
    assert kinds == {"buffer", "punctuality", "speed", "coverage", "burden"}
