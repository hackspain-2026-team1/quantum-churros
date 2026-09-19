"""Exact explanation: score = base + sum(contributions) - penalty - cap, to 1e-9."""

from __future__ import annotations

import itertools
import random
from dataclasses import replace

import pytest
from xray_engine.aggregate import aggregate, delta_parts
from xray_engine.contracts import BRANCH_NONE, PILLAR_KEYS, PillarResult, ScoreParts
from xray_engine.export import round_preserving_sum
from xray_engine.pillars import compute_pillars

TOL = 1e-9
N_ROWS = 2_000

pytestmark = pytest.mark.xfail(
    raises=NotImplementedError, strict=False, reason="pure core not implemented yet"
)


def _pillars(rng: random.Random, mask: tuple[bool, ...]) -> dict[str, PillarResult]:
    results = {}
    for key, available in zip(PILLAR_KEYS, mask):
        score = rng.choice([0.0, 100.0, rng.uniform(0, 100), rng.uniform(0, 30)]) if available else None
        results[key] = PillarResult(key=key, score=score, raw_score=score)
    return results


def _check_identity(parts: ScoreParts, pillars: dict[str, PillarResult], params) -> None:
    available = [key for key in PILLAR_KEYS if pillars[key].score is not None]
    assert parts.branch == ("+".join(available) if available else BRANCH_NONE)
    assert list(parts.weights_effective) == available == list(parts.contributions)
    if available:
        assert sum(parts.weights_effective.values()) == pytest.approx(1.0, abs=TOL)
        total = sum(params.weights[key] for key in available)
        for key in available:
            assert parts.weights_effective[key] == pytest.approx(params.weights[key] / total, abs=TOL)
    confidence = parts.confidence
    assert 0.0 <= confidence <= 1.0
    assert confidence == pytest.approx(parts.confidence_parts.value, abs=TOL)
    assert parts.abstained == (confidence < params.confidence.abstain_below)
    assert (parts.unlock_hint is not None) == parts.abstained

    assert parts.penalty_level >= 0.0 and parts.cap_adjustment_level >= 0.0
    assert parts.level_raw == pytest.approx(
        parts.level_weighted - parts.penalty_level - parts.cap_adjustment_level, abs=TOL
    )
    assert parts.penalty == pytest.approx(confidence * parts.penalty_level, abs=TOL)
    assert parts.cap_adjustment == pytest.approx(confidence * parts.cap_adjustment_level, abs=TOL)
    if not parts.feed_live:
        assert "stale_feed" in parts.flags
        assert parts.penalty_level == 0.0 and parts.cap_adjustment_level == 0.0
        assert parts.caps_fired == ()
    if parts.cap_adjustment_level > 0:
        assert parts.caps_fired

    medians = params.reference.medians
    expected_base = 50 + confidence * (
        sum(parts.weights_effective[key] * medians[key] for key in available) - 50
    )
    assert parts.base == pytest.approx(expected_base, abs=TOL)
    for key in available:
        expected = confidence * parts.weights_effective[key] * (pillars[key].score - medians[key])
        assert parts.contributions[key] == pytest.approx(expected, abs=TOL)
    assert parts.score == pytest.approx(50 + confidence * (parts.level_raw - 50), abs=TOL)
    explained = parts.base + sum(parts.contributions.values()) - parts.penalty - parts.cap_adjustment
    assert parts.score == pytest.approx(explained, abs=TOL)
    assert -TOL <= parts.score <= 100.0 + TOL and -TOL <= parts.level_raw <= 100.0 + TOL


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
            assert (result.score is None) == (result.raw_score is None)
            assert result.score is not None or result.gates
        parts = aggregate(pillars, row, params)
        _check_identity(parts, pillars, params)
        branches.add(parts.branch)
    assert len(branches) >= 6  # the generator reaches the main coverage branches


def test_penalty_and_caps_follow_the_spec(panel_rows, params) -> None:
    rng = random.Random(13)
    live = dict(rows_3m=300, rows_base_median=100.0, rows_base_months=9, months_observed=24,
                neg_liquidity_months_6m=0, granted=0.0, drawn=0.0, headroom=0.0)
    scores = dict(liquidity=20.0, payments=80.0, collections=80.0, activity=80.0, debt=80.0)
    pillars = {key: PillarResult(key=key, score=value, raw_score=value) for key, value in scores.items()}
    row = panel_rows.random(rng, **live)
    parts = aggregate(pillars, row, params)
    assert parts.feed_live
    assert parts.penalty_level == pytest.approx(0.5 * (45 - 20), abs=TOL)
    assert "weak_pillar" in parts.caps_fired and parts.level_raw <= 50 + TOL

    drained = replace(row, neg_liquidity_months_6m=3)
    assert "negative_liquidity" in aggregate(pillars, drained, params).caps_fired
    assert aggregate(pillars, drained, params).level_raw <= 40 + TOL

    healthy = {key: PillarResult(key=key, score=90.0, raw_score=90.0) for key in PILLAR_KEYS}
    maxed = replace(row, granted=1000.0, drawn=990.0, headroom=10.0)
    capped = aggregate(healthy, maxed, params)
    assert capped.caps_fired == ("lines_fully_drawn",)
    assert capped.level_raw == pytest.approx(60.0, abs=TOL)
    assert capped.cap_adjustment_level == pytest.approx(30.0, abs=TOL)

    quiet = aggregate(pillars, replace(row, rows_3m=100), params)
    assert not quiet.feed_live and quiet.penalty_level == 0.0 and quiet.caps_fired == ()
    assert quiet.confidence < parts.confidence


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
    same = aggregate(_pillars(rng, masks[0]), panel_rows.random(rng), params)
    still = delta_parts(same, replace(same))
    assert still.score == 0.0 and still.base == 0.0


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
