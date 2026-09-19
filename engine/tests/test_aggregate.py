"""Aggregate beyond the identities: monotonicity, confidence tables, drivers, determinism."""

from __future__ import annotations

import itertools
import random
from dataclasses import replace

import pytest
from xray_engine.aggregate import (
    abstention,
    aggregate,
    confidence_label,
    confidence_parts,
    explain,
    score_flags,
)
from xray_engine.contracts import (
    BRANCH_NONE,
    CAP_TEXTS,
    PANEL_COLUMNS,
    PILLAR_KEYS,
    PILLAR_LABELS,
    UNLOCK_HINTS,
    PillarResult,
)
from xray_engine.pillars import compute_pillars, pillar_note

TOL = 1e-9
N_ROWS = 2_000
MASKS = list(itertools.product([True, False], repeat=len(PILLAR_KEYS)))
LIVE = dict(rows_month=100, rows_3m=300, rows_base_median=100.0, rows_base_months=9,
            zero_row_month=False, months_observed=24)


@pytest.fixture(scope="module")
def params(params):
    medians = {"liquidity": 55.0, "payments": 72.0, "collections": 66.0, "activity": 61.0, "debt": 78.0}
    return replace(params, reference=replace(params.reference, medians=medians))


def _fixed(**scores: float | None) -> dict[str, PillarResult]:
    return {
        key: PillarResult(key=key, score=scores.get(key), gates=() if scores.get(key) is not None else ("no_base",))
        for key in PILLAR_KEYS
    }


def _random(rng: random.Random, mask: tuple[bool, ...]) -> dict[str, float | None]:
    return {
        key: rng.choice([0.0, 100.0, rng.uniform(0, 100), rng.uniform(15, 50)]) if available else None
        for key, available in zip(PILLAR_KEYS, mask)
    }


def test_a_better_pillar_never_lowers_the_score(panel_rows, params) -> None:
    """On a fixed coverage branch the level is monotone in every pillar, through
    the penalty, its floor and both caps."""
    rng = random.Random(31)
    raised = capped = penalised = 0
    for _ in range(N_ROWS):
        scores = _random(rng, rng.choice(MASKS[:-1]))
        row = panel_rows.random(rng)
        before = aggregate(_fixed(**scores), row, params)
        key = rng.choice([name for name, value in scores.items() if value is not None])
        better = dict(scores, **{key: min(100.0, scores[key] + rng.choice([0.5, 5.0, 30.0, 100.0]))})
        after = aggregate(_fixed(**better), row, params)
        assert after.branch == before.branch and after.base == before.base
        assert after.score >= before.score - TOL, (scores, key)
        assert after.penalty <= before.penalty + TOL or before.penalty == before.level_weighted
        raised += after.score > before.score + TOL
        capped += before.cap_adjustment > 0
        penalised += before.penalty > 0
    assert raised > N_ROWS // 2 and capped > 50 and penalised > 200


def test_aggregate_is_deterministic_and_ignores_the_mapping_order(panel_rows, params) -> None:
    rng = random.Random(32)
    for _ in range(300):
        row = panel_rows.random(rng)
        pillars = compute_pillars(row, params)
        parts = aggregate(pillars, row, params)
        assert aggregate(pillars, row, params) == parts
        backwards = dict(reversed(list(pillars.items())))
        other = aggregate(backwards, row, params)
        assert other == parts
        assert list(other.weights_effective) == list(parts.weights_effective)  # PILLAR_KEYS order
        assert list(other.pillar_scores) == list(PILLAR_KEYS)
    # a pillar left out of the mapping reads as not available
    row = panel_rows.random(rng, **LIVE)
    partial = aggregate({"liquidity": PillarResult("liquidity", 70.0)}, row, params)
    assert partial.branch == "liquidity" and partial.score == pytest.approx(70.0, abs=TOL)
    assert partial.pillar_scores == {key: (70.0 if key == "liquidity" else None) for key in PILLAR_KEYS}


def test_a_row_of_nulls_is_scored_without_a_crash(panel_rows, params) -> None:
    """A panel column that arrives null reads as not observable, never as an error."""
    rng = random.Random(39)
    row = panel_rows.random(rng, **LIVE)
    keys = ("entity_kind", "entity_id", "group_id", "month")
    blank = replace(row, **{name: None for name in PANEL_COLUMNS if name not in keys})
    pillars = compute_pillars(blank, params, blank)
    assert all(result.score is None and result.gates and result.evidence == () for result in pillars.values())
    parts = aggregate(pillars, blank, params)
    assert parts.branch == BRANCH_NONE and not parts.feed_live and parts.abstain_reason == "stale_feed"
    assert parts.months_observed == 0 and parts.confidence == 0.0 and explain(parts, pillars, params) == []
    for name in PANEL_COLUMNS:  # one hole at a time on an otherwise complete row
        if name in keys:
            continue
        holed = replace(row, **{name: None})
        results = compute_pillars(holed, params, holed)
        scored = aggregate(results, holed, params)
        assert 0.0 <= scored.score <= 100.0
        assert all(result.score is not None or result.gates for result in results.values())


def test_caps_hold_without_any_pillar(panel_rows, params) -> None:
    rng = random.Random(33)
    row = panel_rows.random(rng, **LIVE, neg_liquidity_months_6m=4, no_cash_anchor_share=0.0)
    empty = aggregate(_fixed(), row, params)
    reference = sum(params.weights[key] * params.reference.medians[key] for key in PILLAR_KEYS)
    assert empty.branch == BRANCH_NONE and empty.penalty == 0.0 and empty.abstained
    assert empty.base == pytest.approx(reference, abs=TOL) and empty.caps_fired == ("negative_liquidity",)
    assert empty.score == pytest.approx(40.0, abs=TOL)
    assert empty.score == pytest.approx(empty.base - empty.cap_adjustment, abs=TOL)
    quiet = aggregate(_fixed(), replace(row, neg_liquidity_months_6m=0), params)
    assert quiet.score == pytest.approx(reference, abs=TOL) and quiet.caps_fired == ()
    assert quiet.confidence == 0.0 and quiet.confidence_label == "low"  # nothing is covered


def test_a_swept_subsidiary_is_not_capped_on_its_own_balance(panel_rows, params) -> None:
    rng = random.Random(38)
    row = panel_rows.random(rng, **LIVE, neg_liquidity_months_6m=6, no_cash_anchor_share=0.0)
    own = _fixed(liquidity=85.0, activity=70.0)
    assert aggregate(own, row, params).caps_fired == ("negative_liquidity",)
    inherited = dict(own, liquidity=PillarResult("liquidity", 85.0, gates=("inherited_from_group",)))
    parts = aggregate(inherited, row, params)
    assert parts.caps_fired == () and parts.score == pytest.approx(parts.level_weighted, abs=TOL)
    assert "inherited_from_group" in parts.flags


def test_confidence_tables(panel_rows, params) -> None:
    rng = random.Random(34)
    clean = dict(dash_share=0.0, fx_excluded_share=0.0, orphan_product_share=0.0,
                 no_cash_anchor_share=0.0, limit_assumed_constant=False)
    row = panel_rows.random(rng, **LIVE, **clean)
    full = _fixed(liquidity=70.0, payments=70.0, collections=70.0, activity=70.0, debt=70.0)
    parts = confidence_parts(full, row, params, True)
    assert (parts.history, parts.coverage, parts.quality) == (1.0, 1.0, 1.0) and parts.value == 1.0
    # coverage reads the nominal weights of what is available: liquidity + activity = 0.5
    bank_only = confidence_parts(_fixed(liquidity=70.0, activity=70.0), row, params, True)
    assert bank_only.coverage == pytest.approx(0.7, abs=TOL)
    assert confidence_parts(full, replace(row, months_observed=6), params, True).history == pytest.approx(0.7)
    assert confidence_parts(full, replace(row, months_observed=3), params, True).history == pytest.approx(0.4)
    # quality multiplies one factor per defect; an unknown share is no defect
    dirty = replace(row, dash_share=0.6, fx_excluded_share=0.2, orphan_product_share=0.05,
                    no_cash_anchor_share=0.5, limit_assumed_constant=True)
    assert confidence_parts(full, dirty, params, True).quality == pytest.approx(0.8 * 0.8 * 0.9 * 0.8 * 0.95)
    unknown = replace(row, dash_share=None, fx_excluded_share=None, orphan_product_share=None,
                      no_cash_anchor_share=None)
    assert confidence_parts(full, unknown, params, True).quality == 1.0
    assert confidence_parts(full, row, params, False).quality == pytest.approx(0.6)
    assert [confidence_label(value, params) for value in (1.0, 0.75, 0.7499, 0.5, 0.4999, 0.0)] == [
        "high", "high", "medium", "medium", "low", "low",
    ]
    for _ in range(500):
        other = panel_rows.random(rng)
        pillars = compute_pillars(other, params)
        for live in (True, False):
            found = confidence_parts(pillars, other, params, live)
            assert all(0.0 <= part <= 1.0 for part in (found.history, found.coverage, found.quality))
        parts = aggregate(pillars, other, params)
        assert parts.confidence_label == confidence_label(parts.confidence, params)
        assert parts.flags == score_flags(pillars, other, params, parts.feed_live)
        assert (parts.abstain_reason, parts.unlock_hint) == abstention(pillars, other, params, parts.feed_live)


def test_unlock_hints_say_what_is_missing(panel_rows, params) -> None:
    rng = random.Random(35)
    row = panel_rows.random(rng, **LIVE)
    full = _fixed(liquidity=70.0, activity=70.0)
    assert abstention(full, row, params, True) == (None, None)
    reason, hint = abstention(full, replace(row, months_observed=2), params, True)
    assert reason == "short_history" and hint == UNLOCK_HINTS["short_history"].format(months=4)
    assert "4 meses" in hint and "{" not in hint
    assert abstention(full, row, params, False) == ("stale_feed", UNLOCK_HINTS["stale_feed"])
    assert abstention(_fixed(debt=70.0), row, params, True) == ("no_bank_pillar", UNLOCK_HINTS["no_bank_pillar"])


def test_drivers_add_up_to_the_score(panel_rows, params) -> None:
    rng = random.Random(36)
    seen = set()
    for _ in range(N_ROWS // 2):
        row = panel_rows.random(rng)
        pillars = compute_pillars(row, params, panel_rows.random(rng, entity_kind="group"))
        parts = aggregate(pillars, row, params)
        drivers = explain(parts, pillars, params)
        assert parts.score == pytest.approx(parts.base + sum(item.contribution for item in drivers), abs=TOL)
        features = [item.feature for item in drivers]
        expected = list(parts.contributions)
        expected += ["penalty"] if parts.penalty > 0 else []
        expected += ["cap"] if parts.cap_adjustment > 0 else []
        assert features == expected
        for item in drivers:
            seen.add(item.feature)
            assert item.source == "observable" and 1 <= len(item.evidence) <= 400 and item.label
            sign = "positive" if item.contribution > 0 else "negative" if item.contribution < 0 else "neutral"
            assert item.direction == sign
            if item.feature in PILLAR_KEYS:
                assert item.label == PILLAR_LABELS[item.feature]
                assert item.observed == parts.pillar_scores[item.feature]
                assert item.baseline == params.reference.medians[item.feature]
                assert item.contribution == parts.contributions[item.feature]
                assert item.evidence == pillar_note(pillars[item.feature], params)
    assert seen == {*PILLAR_KEYS, "penalty", "cap"}


def test_penalty_and_cap_drivers_explain_themselves(panel_rows, params) -> None:
    rng = random.Random(37)
    row = panel_rows.random(rng, **LIVE, neg_liquidity_months_6m=5, no_cash_anchor_share=0.0)
    pillars = _fixed(liquidity=20.0, payments=80.0, activity=90.0)
    parts = aggregate(pillars, row, params)
    penalty, cap = explain(parts, pillars, params)[-2:]
    assert (penalty.feature, penalty.observed, penalty.baseline) == ("penalty", 20.0, 45.0)
    assert penalty.contribution == pytest.approx(-12.5, abs=TOL)
    assert penalty.evidence == (
        "El pilar más débil (liquidez, 20,0 puntos) queda por debajo de 45: resta 12,5 puntos."
    )
    assert (cap.feature, cap.baseline, cap.evidence) == ("cap", 40.0, CAP_TEXTS["negative_liquidity"])
    assert cap.observed == pytest.approx(parts.level_weighted - parts.penalty, abs=TOL)
    assert cap.contribution == pytest.approx(-parts.cap_adjustment, abs=TOL) and cap.contribution < 0
    # a stale month has neither
    stale = aggregate(pillars, replace(row, rows_3m=0, rows_month=0, zero_row_month=True), params)
    assert [item.feature for item in explain(stale, pillars, params)] == ["liquidity", "payments", "activity"]
