"""Scores read money only through ratios: the currency scale must not matter.

Tested on the pure core. The row-level cleaning is not scale free on purpose:
the mirror recipe has a 100 EUR gate and the size band has EUR thresholds, so
the panel hands the band over as a label.
"""

from __future__ import annotations

import random
from dataclasses import asdict, replace
from datetime import date

import pytest
from xray_engine.aggregate import aggregate, explain
from xray_engine.contracts import PANEL_COLUMNS, PANEL_MONEY_COLUMNS, PILLAR_KEYS, SIZE_BANDS
from xray_engine.pillars import compute_pillars, pillar_note
from xray_engine.trajectory import trajectories

TOL = 1e-9


def _close(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return abs(left - right) <= TOL
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_close(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_close(a, b) for a, b in zip(left, right))
    return left == right


def test_scaling_a_row_touches_money_columns_only(panel_rows) -> None:
    row = panel_rows.random(random.Random(21), cash_month_end=1000.0, size_band="small")
    scaled = panel_rows.scale(row, 1024.0)
    assert scaled.cash_month_end == 1024000.0 and len(PANEL_MONEY_COLUMNS) > 20
    assert scaled.size_band == "small"  # the band is a label of the panel, not a function of the row
    for name in PANEL_COLUMNS:
        value, other = getattr(row, name), getattr(scaled, name)
        if name not in PANEL_MONEY_COLUMNS or value is None:
            assert other == value, name
        else:
            assert other == value * 1024.0, name


@pytest.mark.parametrize("exponent", [-10, -1, 3, 10])
@pytest.mark.parametrize("segmented", [True, False])
def test_pure_core_is_scale_invariant(panel_rows, params, exponent, segmented) -> None:
    """Money fields times 2**k: same scores, gates, aggregate, drivers and notes."""
    rng = random.Random(22)
    params = replace(params, liquidity=replace(params.liquidity, segmented=segmented))
    factor = 2.0**exponent
    for _ in range(500):
        row = panel_rows.random(rng)
        group_row = panel_rows.random(rng, entity_kind="group", size_band=rng.choice(SIZE_BANDS))
        results = compute_pillars(row, params, group_row)
        scaled = compute_pillars(
            panel_rows.scale(row, factor), params, panel_rows.scale(group_row, factor)
        )
        for key in PILLAR_KEYS:
            assert _close(results[key].score, scaled[key].score), key
            assert results[key].gates == scaled[key].gates, key
            assert pillar_note(results[key], params) == pillar_note(scaled[key], params), key
        before = aggregate(results, row, params)
        after = aggregate(scaled, panel_rows.scale(row, factor), params)
        assert _close(asdict(before), asdict(after))
        drivers = [item.model_dump() for item in explain(before, results, params)]
        assert _close(drivers, [item.model_dump() for item in explain(after, scaled, params)])


def test_a_trajectory_does_not_see_the_money_scale(panel_rows, params) -> None:
    rng = random.Random(23)
    rows = [
        panel_rows.random(rng, month=date(2025, 1 + index, 1), months_observed=12 + index,
                          entity_kind="group", perimeter_changed=False)
        for index in range(12)
    ]
    history = [aggregate(compute_pillars(row, params), row, params) for row in rows]
    scaled = [
        aggregate(compute_pillars(bigger, params), bigger, params)
        for bigger in (panel_rows.scale(row, 4096.0) for row in rows)
    ]
    one, other = trajectories(history, params), trajectories(scaled, params)
    assert any(verdict.available for verdict in one)
    assert _close([asdict(verdict) for verdict in one], [asdict(verdict) for verdict in other])
