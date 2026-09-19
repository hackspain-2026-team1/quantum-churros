"""Financing recommendations: a delta over the measured month, rescored, bounded and honest."""

from __future__ import annotations

import random

from xray_engine.actions import MIN_UPLIFT
from xray_engine.aggregate import aggregate
from xray_engine.financing import MAX_RECOMMENDATIONS, Financing, recommendations
from xray_engine.pillars import compute_pillars

LIVE = dict(rows_month=100, rows_3m=300, rows_base_median=100.0, rows_base_months=9,
            zero_row_month=False, months_observed=24)
N_ROWS = 2_000
KINDS = {"factoring", "confirming", "line", "restructure", "sweep"}


def _cases(panel_rows, params, seed: int, **overrides):
    rng = random.Random(seed)
    for _ in range(N_ROWS):
        row = panel_rows.random(rng, **{**LIVE, **overrides})
        pillars = compute_pillars(row, params)
        yield row, pillars, aggregate(pillars, row, params)


def test_every_recommendation_is_the_engine_rescoring_the_month(panel_rows, params) -> None:
    seen: set[str] = set()
    for row, pillars, parts in _cases(panel_rows, params, 81):
        for item in recommendations(row, pillars, parts, params):
            new_row = item.row_delta(row)
            new_pillars = compute_pillars(new_row, params)
            again = aggregate(new_pillars, new_row, params)
            assert item.new_score == again.score
            assert item.uplift == again.score - parts.score
            assert item.uplift >= MIN_UPLIFT
            assert item.kind in KINDS and item.id == item.kind
            assert item.amount is None or item.amount >= 0
            assert item.title and item.detail and len(item.detail) <= 500
            seen.add(item.kind)
    assert seen  # at least one instrument fired across the random rows


def test_recommendations_are_sorted_and_bounded(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 82):
        found = recommendations(row, pillars, parts, params)
        uplifts = [item.uplift for item in found]
        assert uplifts == sorted(uplifts, reverse=True) and len(uplifts) <= MAX_RECOMMENDATIONS


def test_no_recommendations_on_abstained_or_stale_months(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 83, months_observed=1):
        if parts.abstained:
            assert recommendations(row, pillars, parts, params) == []
    for row, pillars, parts in _cases(panel_rows, params, 84, rows_month=0, rows_3m=0, zero_row_month=True):
        if not parts.feed_live:
            assert recommendations(row, pillars, parts, params) == []


def test_sweep_only_for_companies_with_a_group_row(panel_rows, params) -> None:
    rng = random.Random(85)
    for _ in range(800):
        row = panel_rows.random(rng, **LIVE)
        group_row = panel_rows.random(rng, **LIVE)
        pillars = compute_pillars(row, params, group_row)
        parts = aggregate(pillars, row, params, group_row)
        for item in recommendations(row, pillars, parts, params, group_row):
            if item.kind == "sweep":
                assert row.entity_kind == "company"
                assert "inherited_from_group" not in pillars["liquidity"].gates
                assert row.cash_month_end is not None and row.cash_month_end < 0
                assert group_row.cash_month_end is not None and group_row.cash_month_end >= -row.cash_month_end
            else:
                assert item.row_delta(row) is not None


def test_recommendations_are_deterministic(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 86):
        assert recommendations(row, pillars, parts, params) == recommendations(row, pillars, parts, params)


def test_financing_fields_are_consistent(panel_rows, params) -> None:
    for row, pillars, parts in _cases(panel_rows, params, 87):
        for item in recommendations(row, pillars, parts, params):
            assert item.new_score_tenths == round(min(100.0, max(0.0, item.new_score)) * 10)
            assert item.uplift_tenths == item.new_score_tenths - round(min(100.0, max(0.0, item.new_score - item.uplift)) * 10)
