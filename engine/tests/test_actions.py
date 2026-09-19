"""Suggested actions: the uplift is the aggregate recomputed, never an estimate."""

from __future__ import annotations

import random
from dataclasses import replace

from xray_engine.actions import (
    MAX_ACTIONS,
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

LIVE = dict(
    rows_month=100,
    rows_3m=300,
    rows_base_median=100.0,
    rows_base_months=9,
    zero_row_month=False,
    months_observed=24,
)
N_ROWS = 1_500


def _cases(panel_rows, params, seed: int, **overrides):
    rng = random.Random(seed)
    for _ in range(N_ROWS):
        row = panel_rows.random(rng, **{**LIVE, **overrides})
        pillars = compute_pillars(row, params)
        yield row, pillars, aggregate(pillars, row, params)


def test_uplift_is_the_aggregate_recomputed_with_the_pillar_at_its_target(
    panel_rows, params
) -> None:
    seen: set[str] = set()
    for row, pillars, parts in _cases(panel_rows, params, 71):
        plan = plan_actions(row, pillars, parts, params)
        changed_all = dict(pillars)
        for action in plan.actions:
            result = pillars[action.pillar]
            assert result.score is not None and result.score < TARGET_CEILING
            assert (
                result.score
                < action.pillar_target
                <= min(TARGET_CEILING, result.score + MAX_STEP) + 1e-9
            )
            changed = {
                **pillars,
                action.pillar: replace(result, score=action.pillar_target),
            }
            again = aggregate(changed, row, params)
            assert action.new_score == again.score
            assert action.uplift == again.score - parts.score
            assert action.uplift_tenths == action.new_score_tenths - round(
                parts.score * 10
            )
            assert action.id.startswith(f"{action.pillar}-") and action.effort in (
                "bajo",
                "medio",
                "alto",
            )
            assert action.title and action.detail and len(action.detail) <= 400
            if action.pillar == "liquidity":
                assert action.amount_eur is not None and action.amount_eur > 0
            else:
                assert action.amount_eur is None
            changed_all[action.pillar] = changed[action.pillar]
            seen.add(action.id)
        assert plan.combined_score == aggregate(changed_all, row, params).score
        assert plan.combined_uplift == plan.combined_score - parts.score
    assert {key for key in PILLAR_KEYS} == {name.split("-")[0] for name in seen}


def test_actions_never_lower_the_score_and_are_sorted_and_bounded(
    panel_rows, params
) -> None:
    with_actions = 0
    for row, pillars, parts in _cases(panel_rows, params, 72):
        plan = plan_actions(row, pillars, parts, params)
        uplifts = [action.uplift for action in plan.actions]
        assert all(uplift >= MIN_UPLIFT for uplift in uplifts)
        assert uplifts == sorted(uplifts, reverse=True) and len(uplifts) <= MAX_ACTIONS
        assert len({action.pillar for action in plan.actions}) == len(uplifts)
        assert plan.combined_uplift >= max(uplifts, default=0.0) - 1e-9
        with_actions += bool(uplifts)
    assert with_actions > N_ROWS // 4


def test_targets_move_the_input_in_the_right_direction(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 73):
        for action in suggest_actions(row, pillars, parts, params):
            lower_is_better = action.pillar in ("payments", "collections", "debt")
            assert (
                (action.target < action.current)
                if lower_is_better
                else (action.target > action.current)
            )


def test_no_actions_on_abstained_or_stale_months(panel_rows, params) -> None:
    abstained = stale = 0
    for row, pillars, parts in _cases(panel_rows, params, 74, months_observed=1):
        if parts.abstained:
            abstained += 1
            assert plan_actions(row, pillars, parts, params).actions == ()
    for row, pillars, parts in _cases(
        panel_rows, params, 75, rows_month=0, rows_3m=0, zero_row_month=True
    ):
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
        assert all(
            a.pillar != "liquidity"
            for a in suggest_actions(row, pillars, parts, params, group_row)
        )
    assert checked == 400


def test_actions_are_deterministic(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 77):
        first = plan_actions(row, pillars, parts, params)
        shuffled = dict(reversed(list(pillars.items())))
        assert (
            first
            == plan_actions(row, pillars, parts, params)
            == plan_actions(row, shuffled, parts, params)
        )


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
