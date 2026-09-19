"""Point-in-time: month t computed from data cut at t equals month t of the full run."""

from __future__ import annotations

import random
from datetime import date

import polars as pl
import pytest
from xray_engine.outlook import outlooks
from xray_engine.scoring import score_entity, score_dataset

TOL = 1e-9
KEYS = ["entity_kind", "entity_id", "month"]


@pytest.fixture(scope="module")
def full_run(synthetic, params, tmp_path_factory):
    return score_dataset(synthetic.path, params, cache_dir=tmp_path_factory.mktemp("full-cache"))


@pytest.mark.parametrize("month", [date(2025, 8, 1), date(2026, 2, 1), date(2026, 5, 1)])
def test_rows_up_to_t_survive_truncation(
    synthetic, datasets, params, same_frames, full_run, tmp_path, month
) -> None:
    cut_dir = datasets.truncate(synthetic.path, tmp_path / "cut", month)
    cut = score_dataset(cut_dir, params, cache_dir=tmp_path / "cache")
    assert cut.window.last_month == month
    assert cut.snapshots["month"].max() == month
    same_frames(
        cut.snapshots, full_run.snapshots.filter(pl.col("month") <= month), keys=KEYS, tol=TOL,
        ignore=("dataset_hash",),
    )
    same_frames(cut.panel, full_run.panel.filter(pl.col("month") <= month), keys=KEYS, tol=TOL)
    early = [alert for alert in full_run.alerts if alert.month <= month]
    assert [(a.id, a.state, a.suppressed_by) for a in cut.alerts] == [
        (a.id, a.state, a.suppressed_by) for a in early
    ]


def test_window_is_derived_from_the_data(synthetic, full_run) -> None:
    assert full_run.window.last_month == synthetic.last_month  # the last day of data is not a month
    assert full_run.window.first_month == synthetic.first_month
    assert full_run.window.as_of == synthetic.as_of
    assert full_run.snapshots["month"].max() == synthetic.last_month


def test_entity_history_is_past_only(panel_rows, params) -> None:
    rng = random.Random(31)
    months = [date(2025, month, 1) for month in range(1, 13)]
    rows = [
        panel_rows.random(rng, entity_kind="group", entity_id="G", group_id="G", month=month,
                          months_observed=index + 8, months_since_perimeter_change=None,
                          perimeter_changed=False, members_joined=0, products_connected=0)
        for index, month in enumerate(months)
    ]
    whole = score_entity(rows, params)
    assert [item.row.month for item in whole] == months
    for size in (1, 5, 9):
        assert score_entity(rows[:size], params) == whole[:size]
    shuffled = rows[:]
    rng.shuffle(shuffled)
    assert score_entity(shuffled, params) == whole


def test_entity_outlook_is_past_only(panel_rows, params) -> None:
    """The scenarios of month t only read the history up to t: arriving later
    months never move them, so the chart of a cut dataset draws the same fan."""
    rng = random.Random(37)
    months = [date(2025, month, 1) for month in range(1, 13)]
    rows = [
        panel_rows.random(rng, entity_kind="group", entity_id="G", group_id="G", month=month,
                          months_observed=index + 8, months_since_perimeter_change=None,
                          perimeter_changed=False, members_joined=0, products_connected=0)
        for index, month in enumerate(months)
    ]
    whole = outlooks([item.parts for item in score_entity(rows, params)], params)
    for size in (1, 5, 9, len(rows)):
        cut = score_entity(rows[:size], params)
        assert [item.row.month for item in cut] == months[:size]
        assert outlooks([item.parts for item in cut], params) == whole[:size]
