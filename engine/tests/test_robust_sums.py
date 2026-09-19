"""Trailing sums cap each month at three times the median positive month of the window."""

from __future__ import annotations

import random

import pytest
from xray_engine.panel import winsorised, winsorised_sum


def test_a_lumpy_month_is_capped_and_a_quarterly_payer_is_not() -> None:
    steady = [100.0, 110.0, 90.0, 100.0, 5_000.0, 105.0]
    assert winsorised(steady, 3.0) == [100.0, 110.0, 90.0, 100.0, 307.5, 105.0]  # median 102.5
    assert winsorised_sum(steady, 3.0) == pytest.approx(812.5)
    quarterly = [0.0, 0.0, 300.0, 0.0, 0.0, 300.0, 0.0, 0.0, 300.0, 0.0, 0.0, 300.0]
    assert winsorised_sum(quarterly, 3.0) == 1_200.0  # empty months do not drag the cap to zero
    assert winsorised_sum([0.0, 0.0, 0.0], 3.0) == 0.0 and winsorised([], 3.0) == []
    assert winsorised_sum([250.0], 3.0) == 250.0  # one month cannot be judged against itself
    assert winsorised_sum([10.0, 10.0, 1_000.0, 1_000.0], 3.0) == pytest.approx(10 + 10 + 1_000 + 1_000)


def test_the_cap_is_scale_free_and_as_of() -> None:
    rng = random.Random(81)
    for _ in range(200):
        months = [rng.choice([0.0, rng.uniform(1, 100), rng.uniform(1, 100) * 50]) for _ in range(rng.randint(1, 12))]
        total = winsorised_sum(months, 3.0)
        assert 0.0 <= total <= sum(months) + 1e-9
        assert winsorised_sum([value * 1024.0 for value in months], 3.0) == pytest.approx(total * 1024.0)
        assert winsorised_sum(list(reversed(months)), 3.0) == pytest.approx(total)
        assert winsorised_sum(months, 1e9) == pytest.approx(sum(months))
