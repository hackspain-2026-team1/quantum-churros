"""Exact explanation: score = base + sum(contributions) - penalty - cap, to 1e-9.

The score is the level itself: confidence is reported next to it and never
moves it, nothing is smoothed, and the base belongs to the coverage branch.
"""

from __future__ import annotations

import itertools
import random
from dataclasses import replace

import pytest
from xray_engine.aggregate import aggregate, delta_parts
from xray_engine.contracts import (
    ABSTAIN_REASONS,
    BRANCH_NONE,
    CAP_KEYS,
    CONFIDENCE_LABEL_KEYS,
    PILLAR_KEYS,
    SCORE_FLAGS,
    PillarResult,
    ScoreParts,
    band_of,
)
from xray_engine.export import round_preserving_sum
from xray_engine.pillars import compute_pillars

TOL = 1e-9
N_ROWS = 2_000
LIVE = dict(rows_month=100, rows_3m=300, rows_base_median=100.0, rows_base_months=9,
            zero_row_month=False, months_observed=24)


@pytest.fixture(scope="module")
def params(params):
    """Reference medians that differ by pillar, as after fit-reference: with the
    flat placeholders every branch would share one base and hide a wrong one."""
    medians = {"liquidity": 55.0, "payments": 72.0, "collections": 66.0, "activity": 61.0, "debt": 78.0}
    return replace(params, reference=replace(params.reference, medians=medians))


def _pillars(rng: random.Random, mask: tuple[bool, ...]) -> dict[str, PillarResult]:
    results = {}
    for key, available in zip(PILLAR_KEYS, mask):
        score = rng.choice([0.0, 100.0, rng.uniform(0, 100), rng.uniform(0, 30)]) if available else None
        results[key] = PillarResult(key=key, score=score, gates=() if available else ("no_base",))
    return results


def _fixed(**scores: float | None) -> dict[str, PillarResult]:
    return {
        key: PillarResult(key=key, score=scores.get(key), gates=() if scores.get(key) is not None else ("no_base",))
        for key in PILLAR_KEYS
    }


def _check_identity(parts: ScoreParts, pillars: dict[str, PillarResult], params) -> None:
    available = [key for key in PILLAR_KEYS if pillars[key].score is not None]
    medians = params.reference.medians
    assert parts.branch == ("+".join(available) if available else BRANCH_NONE)
    assert list(parts.weights_effective) == available == list(parts.contributions)
    assert dict(parts.pillar_scores) == {key: pillars[key].score for key in PILLAR_KEYS}
    if available:
        assert sum(parts.weights_effective.values()) == pytest.approx(1.0, abs=TOL)
        total = sum(params.weights[key] for key in available)
        for key in available:
            assert parts.weights_effective[key] == pytest.approx(params.weights[key] / total, abs=TOL)
        weighted = sum(parts.weights_effective[key] * pillars[key].score for key in available)
        expected_base = sum(parts.weights_effective[key] * medians[key] for key in available)
    else:  # nothing observable: the reference level, abstained
        weighted = expected_base = sum(params.weights[key] * medians[key] for key in PILLAR_KEYS)
        assert parts.abstained
    assert parts.level_weighted == pytest.approx(weighted, abs=TOL)
    assert parts.base == pytest.approx(expected_base, abs=TOL)  # one base per branch, no confidence
    for key in available:
        expected = parts.weights_effective[key] * (pillars[key].score - medians[key])
        assert parts.contributions[key] == pytest.approx(expected, abs=TOL)

    assert parts.penalty >= 0.0 and parts.cap_adjustment >= 0.0
    assert parts.score == pytest.approx(parts.level_weighted - parts.penalty - parts.cap_adjustment, abs=TOL)
    explained = parts.base + sum(parts.contributions.values()) - parts.penalty - parts.cap_adjustment
    assert parts.score == pytest.approx(explained, abs=TOL)
    assert 0.0 <= parts.score <= 100.0
    assert parts.level == parts.score and parts.carried_from is None  # aggregate never carries
    assert parts.band == band_of(parts.score, params.bands)
    assert set(parts.caps_fired) <= set(CAP_KEYS)
    if parts.cap_adjustment > 0:
        assert parts.caps_fired
    if not parts.feed_live:
        assert "stale_feed" in parts.flags
        assert parts.penalty == 0.0 and parts.cap_adjustment == 0.0 and parts.caps_fired == ()
        assert parts.abstain_reason == "stale_feed"

    confidence = parts.confidence
    assert 0.0 <= confidence <= 1.0
    assert confidence == pytest.approx(parts.confidence_parts.value, abs=TOL)
    assert parts.confidence_label in CONFIDENCE_LABEL_KEYS
    assert list(parts.flags) == [flag for flag in SCORE_FLAGS if flag in parts.flags]
    assert parts.abstained == (parts.abstain_reason is not None) == (parts.unlock_hint is not None)
    assert parts.abstain_reason is None or parts.abstain_reason in ABSTAIN_REASONS


def test_identity_on_every_branch(panel_rows, params) -> None:
    rng = random.Random(11)
    for mask in itertools.product([True, False], repeat=len(PILLAR_KEYS)):
        for _ in range(40):
            pillars = _pillars(rng, mask)
            parts = aggregate(pillars, panel_rows.random(rng), params)
            _check_identity(parts, pillars, params)


def test_identity_from_random_panel_rows(panel_rows, params) -> None:
    rng = random.Random(12)
    branches = set()
    for _ in range(N_ROWS):
        row = panel_rows.random(rng)
        pillars = compute_pillars(row, params)
        assert list(pillars) == list(PILLAR_KEYS)
        for result in pillars.values():
            assert result.score is None or 0.0 <= result.score <= 100.0
            assert result.score is not None or result.gates
        parts = aggregate(pillars, row, params)
        _check_identity(parts, pillars, params)
        branches.add(parts.branch)
    assert len(branches) >= 6  # the generator reaches the main coverage branches


def test_penalty_and_the_two_caps(panel_rows, params) -> None:
    rng = random.Random(13)
    row = panel_rows.random(rng, **LIVE, neg_liquidity_months_6m=0, no_cash_anchor_share=0.0)
    weak_liquidity = _fixed(liquidity=20.0, payments=80.0, collections=80.0, activity=80.0, debt=80.0)
    parts = aggregate(weak_liquidity, row, params)
    assert parts.feed_live and parts.caps_fired == ()  # a weak liquidity pillar is no cap any more
    assert parts.penalty == pytest.approx(0.5 * (45 - 20), abs=TOL)
    assert parts.score == pytest.approx(0.3 * 20 + 0.7 * 80 - 12.5, abs=TOL)

    drained = aggregate(weak_liquidity, replace(row, neg_liquidity_months_6m=3), params)
    assert drained.caps_fired == ("negative_liquidity",) and drained.score == pytest.approx(40.0, abs=TOL)
    assert drained.cap_adjustment == pytest.approx(62.0 - 12.5 - 40.0, abs=TOL)
    short = aggregate(weak_liquidity, replace(row, neg_liquidity_months_6m=2), params)
    assert short.caps_fired == ()
    # under-stated cash cannot trigger the negative-liquidity cap
    blind = aggregate(
        weak_liquidity, replace(row, neg_liquidity_months_6m=6, no_cash_anchor_share=0.5), params
    )
    assert blind.caps_fired == ()

    late_payer = _fixed(liquidity=90.0, payments=24.9, collections=90.0, activity=90.0, debt=90.0)
    capped = aggregate(late_payer, row, params)
    assert capped.caps_fired == ("weak_payments",) and capped.score == pytest.approx(50.0, abs=TOL)
    both = aggregate(late_payer, replace(row, neg_liquidity_months_6m=4), params)
    assert both.caps_fired == ("negative_liquidity", "weak_payments")  # strictest first
    assert both.score == pytest.approx(40.0, abs=TOL)
    on_the_line = _fixed(liquidity=90.0, payments=25.0, collections=90.0, activity=90.0, debt=90.0)
    assert aggregate(on_the_line, row, params).caps_fired == ()

    # a cap only removes what is above its ceiling
    low = _fixed(liquidity=10.0, activity=30.0)
    floor = aggregate(low, replace(row, neg_liquidity_months_6m=6), params)
    assert floor.caps_fired == ("negative_liquidity",) and floor.cap_adjustment == 0.0
    # the penalty never pushes the level below zero
    zero = aggregate(_fixed(liquidity=0.0, activity=0.0), row, params)
    assert zero.score == 0.0 and zero.penalty == 0.0 and zero.level_weighted == 0.0


def test_stale_feed_switches_penalty_and_caps_off(panel_rows, params) -> None:
    rng = random.Random(16)
    row = panel_rows.random(rng, **LIVE, neg_liquidity_months_6m=6, no_cash_anchor_share=0.0)
    pillars = _fixed(liquidity=10.0, payments=10.0, activity=70.0)
    live = aggregate(pillars, row, params)
    assert live.feed_live and live.penalty > 0 and live.caps_fired
    quiet = aggregate(pillars, replace(row, rows_3m=100), params)  # ratio 0.33 < 0.5
    assert not quiet.feed_live and quiet.penalty == 0.0 and quiet.caps_fired == ()
    assert quiet.score == pytest.approx(quiet.level_weighted, abs=TOL)
    assert quiet.abstained and quiet.abstain_reason == "stale_feed" and quiet.carried_from is None
    assert quiet.confidence < live.confidence  # a dead feed is never high confidence


def test_live_feed_rules(panel_rows, params) -> None:
    from xray_engine.aggregate import live_feed

    rng = random.Random(17)
    row = panel_rows.random(rng, **LIVE, entity_kind="company")
    assert live_feed(row, params)
    assert live_feed(replace(row, rows_3m=150), params)  # ratio exactly 0.5
    assert not live_feed(replace(row, rows_3m=149), params)
    assert live_feed(replace(row, rows_3m=240), params)  # 0.8: the old threshold is gone
    assert not live_feed(replace(row, rows_3m=0, rows_month=0, zero_row_month=True), params)
    # short history: baseline undefined reads as live, unless nothing arrives
    young = replace(row, rows_base_median=None, rows_base_months=1, rows_3m=5)
    assert live_feed(young, params)
    assert live_feed(replace(row, rows_base_months=2, rows_3m=5), params)
    assert live_feed(replace(row, rows_base_median=0.0, rows_3m=5), params)
    assert not live_feed(replace(young, rows_3m=0, rows_month=0, zero_row_month=True), params)
    # a month without rows kills a group feed at once; a company waits for the ratio
    gap = dict(rows_month=0, zero_row_month=True, rows_3m=200)
    assert live_feed(replace(row, **gap), params)
    assert not live_feed(replace(row, entity_kind="group", **gap), params)


def test_confidence_never_moves_the_score(panel_rows, params) -> None:
    rng = random.Random(18)
    for _ in range(200):
        row = panel_rows.random(rng, **LIVE)
        pillars = _pillars(rng, (True, rng.random() < 0.5, rng.random() < 0.5, True, rng.random() < 0.5))
        clean = replace(row, dash_share=0.0, fx_excluded_share=0.0, orphan_product_share=0.0,
                        limit_assumed_constant=False, no_cash_anchor_share=0.0)
        dirty = replace(clean, dash_share=0.9, fx_excluded_share=0.3, orphan_product_share=0.2,
                        limit_assumed_constant=True)
        one, other = aggregate(pillars, clean, params), aggregate(pillars, dirty, params)
        assert other.confidence < one.confidence
        assert (other.score, other.base, other.penalty, other.cap_adjustment) == (
            one.score, one.base, one.penalty, one.cap_adjustment,
        )
        assert other.abstained == one.abstained  # abstention does not read confidence
        young = aggregate(pillars, replace(clean, months_observed=6), params)
        assert young.confidence < one.confidence and young.score == one.score


def test_abstention_rules(panel_rows, params) -> None:
    rng = random.Random(19)
    row = panel_rows.random(rng, **LIVE)
    full = _fixed(liquidity=70.0, payments=70.0, collections=70.0, activity=70.0, debt=70.0)
    assert not aggregate(full, row, params).abstained
    for months, expected in ((1, True), (3, True), (4, False), (5, False)):
        parts = aggregate(full, replace(row, months_observed=months), params)
        assert parts.abstained is expected
        assert parts.abstain_reason == ("short_history" if expected else None)
        assert (parts.unlock_hint is not None) is expected
    invoices_only = _fixed(payments=70.0, collections=70.0, debt=70.0)
    parts = aggregate(invoices_only, row, params)
    assert parts.abstained and parts.abstain_reason == "no_bank_pillar" and 0 <= parts.score <= 100
    assert not aggregate(_fixed(activity=70.0), row, params).abstained
    assert not aggregate(_fixed(liquidity=70.0), row, params).abstained
    dead = replace(row, rows_3m=0, rows_month=0, zero_row_month=True, months_observed=2)
    assert aggregate(full, dead, params).abstain_reason == "stale_feed"  # first reason wins
    empty = aggregate(_fixed(), row, params)
    assert empty.abstained and empty.branch == BRANCH_NONE and empty.contributions == {}


def test_flags_follow_the_row(panel_rows, params) -> None:
    rng = random.Random(20)
    quiet = dict(perimeter_changed=False, new_perimeter_inflow_share_3m=0.0, limit_assumed_constant=False,
                 has_debt_products=False, fx_excluded_share=0.0, orphan_product_share=0.0,
                 no_cash_anchor_share=0.0, no_external_revenue=False, swept_subsidiary=False)
    row = panel_rows.random(rng, **LIVE, **quiet)
    pillars = _fixed(liquidity=70.0, activity=70.0)
    assert aggregate(pillars, row, params).flags == ()
    loud = replace(row, perimeter_changed=True, new_perimeter_inflow_share_3m=0.21,
                   limit_assumed_constant=True, has_debt_products=True, fx_excluded_share=0.1,
                   orphan_product_share=0.01, no_cash_anchor_share=0.5, no_external_revenue=True,
                   months_observed=5)
    assert aggregate(pillars, loud, params).flags == tuple(
        flag for flag in SCORE_FLAGS if flag not in ("stale_feed", "inherited_from_group")
    )
    assert "perimeter_shift" not in aggregate(
        pillars, replace(row, new_perimeter_inflow_share_3m=0.2), params
    ).flags
    inherited = dict(pillars, liquidity=PillarResult("liquidity", 70.0, gates=("inherited_from_group",)))
    assert aggregate(inherited, row, params).flags == ("inherited_from_group",)


def test_delta_identity_needs_the_base_term(panel_rows, params) -> None:
    rng = random.Random(14)
    masks = list(itertools.product([True, False], repeat=len(PILLAR_KEYS)))
    base_moved = 0
    for _ in range(N_ROWS // 4):
        before = aggregate(_pillars(rng, rng.choice(masks)), panel_rows.random(rng), params)
        after = aggregate(_pillars(rng, rng.choice(masks)), panel_rows.random(rng), params)
        change = delta_parts(after, before)
        assert change.score == pytest.approx(after.score - before.score, abs=TOL)
        assert change.base == pytest.approx(after.base - before.base, abs=TOL)
        assert set(change.contributions) == set(after.contributions) | set(before.contributions)
        explained = (
            change.base + sum(change.contributions.values()) - change.penalty - change.cap_adjustment
        )
        assert change.score == pytest.approx(explained, abs=TOL)
        base_moved += abs(change.base) > 1e-6
    assert base_moved > 0
    # same branch, same base: the base term only moves with the coverage branch
    one = aggregate(_fixed(liquidity=50.0, activity=60.0), panel_rows.random(rng), params)
    other = aggregate(_fixed(liquidity=80.0, activity=20.0), panel_rows.random(rng), params)
    assert delta_parts(other, one).base == pytest.approx(0.0, abs=TOL)
    still = delta_parts(one, replace(one))
    assert still.score == 0.0 and still.base == 0.0


@pytest.mark.xfail(raises=NotImplementedError, strict=False, reason="export is a stub")
def test_tenths_sum_exactly_as_integers(panel_rows, params) -> None:
    rng = random.Random(15)
    for _ in range(500):
        count = rng.randint(1, 7)
        parts = [rng.uniform(-30, 60) for _ in range(count)]
        total = sum(parts)
        tenths = round_preserving_sum(parts, total)
        assert all(isinstance(item, int) for item in tenths)
        assert sum(tenths) == round(total * 10)
        assert all(abs(item - part * 10) < 1 for item, part in zip(tenths, parts))
    assert round_preserving_sum([0.25, 0.25, 0.5], 1.0) == [3, 2, 5]
    assert round_preserving_sum([58.04, 3.33, -1.37], 60.0) == [581, 33, -14]
