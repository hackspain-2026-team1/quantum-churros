"""Scores read money only through ratios: the currency scale must not matter."""

from __future__ import annotations

import random
from dataclasses import asdict

import pytest
from xray_engine.aggregate import aggregate
from xray_engine.contracts import PANEL_COLUMNS, PANEL_MONEY_COLUMNS, PILLAR_KEYS
from xray_engine.pillars import compute_pillars
from xray_engine.scoring import score_dataset

TOL = 1e-9
# descriptive columns that carry EUR amounts by design
MONEY_BEARING_SNAPSHOT_COLUMNS = ("series", "drivers", "dataset_hash")

stub = pytest.mark.xfail(
    raises=NotImplementedError, strict=False, reason="engine modules are stubs"
)


def _close(left: object, right: object) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return abs(left - right) <= TOL
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_close(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(_close(a, b) for a, b in zip(left, right))
    return left == right


def test_scaling_a_row_touches_money_columns_only(panel_rows) -> None:
    row = panel_rows.random(random.Random(21), cash_month_end=1000.0)
    scaled = panel_rows.scale(row, 1024.0)
    assert scaled.cash_month_end == 1024000.0 and len(PANEL_MONEY_COLUMNS) > 20
    for name in PANEL_COLUMNS:
        value, other = getattr(row, name), getattr(scaled, name)
        if name not in PANEL_MONEY_COLUMNS or value is None:
            assert other == value, name
        elif isinstance(value, tuple):
            assert other == tuple(None if item is None else item * 1024.0 for item in value)
        else:
            assert other == value * 1024.0, name


@stub
@pytest.mark.parametrize("exponent", [-10, 10])
def test_pure_core_is_scale_invariant(panel_rows, params, exponent) -> None:
    rng = random.Random(22)
    for _ in range(500):
        row = panel_rows.random(rng)
        group_row = panel_rows.random(rng, entity_kind="group")
        factor = 2.0**exponent
        results = compute_pillars(row, params, group_row)
        scaled = compute_pillars(
            panel_rows.scale(row, factor), params, panel_rows.scale(group_row, factor)
        )
        for key in PILLAR_KEYS:
            assert _close(results[key].score, scaled[key].score), key
            assert results[key].gates == scaled[key].gates, key
        before = aggregate(results, row, params)
        after = aggregate(scaled, panel_rows.scale(row, factor), params)
        assert _close(asdict(before), asdict(after))


@stub
def test_dataset_times_1024_gives_the_same_scores(
    synthetic, datasets, params, same_frames, tmp_path
) -> None:
    scaled_dir = datasets.scale(synthetic.path, tmp_path / "scaled", 1024)
    base = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache")
    scaled = score_dataset(scaled_dir, params, cache_dir=tmp_path / "cache")
    same_frames(
        base.snapshots, scaled.snapshots, keys=["entity_kind", "entity_id", "month"],
        tol=TOL, ignore=MONEY_BEARING_SNAPSHOT_COLUMNS,
    )
    assert [(a.id, a.state) for a in base.alerts] == [(a.id, a.state) for a in scaled.alerts]
