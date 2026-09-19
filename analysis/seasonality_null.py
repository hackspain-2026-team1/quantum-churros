"""Seasonality: does month-of-year explain operating inflow beyond what noise explains?

Usage: python3 analysis/seasonality_null.py --data <dir> [--permutations 200] [--seed 7]

Units: companies, then groups, with operating inflow in all 24 months. Monthly inflow
= amount > 0 in the four operating-inflow categories, EUR, each row capped at the
company's own 95th percentile; a group is the sum of its members. Log scale.

R2 of twelve month-of-year dummies on 24 points: each calendar month is fitted by the
mean of its two observations. Under pure noise E[R2] = 11/23 = 0.478, so a raw R2
near 0.5 is not evidence of seasonality. The null is measured, not assumed: the 24
values of each unit are shuffled ``--permutations`` times. Out of sample, the
month-of-year factors of year 1 are removed from year 2; a ratio above 1 means the
"deseasonalised" series is noisier than the raw one.
"""

from __future__ import annotations

import math
import random
import time
from collections import defaultdict

from _common import (
    N_MONTHS,
    OP_IN,
    booked_transactions,
    load_groups,
    load_products,
    parse_args,
    pct,
    quantile,
    report,
    rnd,
    to_eur,
)


def month_of_year_r2(y):
    mean = sum(y) / len(y)
    total = sum((v - mean) ** 2 for v in y)
    within = sum((y[m] - y[m + 12]) ** 2 / 2 for m in range(12))
    return 1 - within / total if total > 0 else None


def detrend(y):
    n = len(y)
    t_mean, y_mean = (n - 1) / 2, sum(y) / n
    slope = sum((t - t_mean) * (v - y_mean) for t, v in enumerate(y)) / sum((t - t_mean) ** 2 for t in range(n))
    return [v - slope * (t - t_mean) for t, v in enumerate(y)]


def variance(y):
    mean = sum(y) / len(y)
    return sum((v - mean) ** 2 for v in y) / len(y)


def study(series_by_unit, permutations, rng):
    observed, null_mean, beats_null95, detrended, detrended_null, oos = [], [], 0, [], [], []
    for unit in sorted(series_by_unit):
        y = series_by_unit[unit]
        r2 = month_of_year_r2(y)
        if r2 is None:
            continue
        shuffled, draws = list(y), []
        for _ in range(permutations):
            rng.shuffle(shuffled)
            draws.append(month_of_year_r2(shuffled))
        observed.append(r2)
        null_mean.append(sum(draws) / len(draws))
        beats_null95 += r2 > quantile(draws, 0.95)

        flat = detrend(y)
        detrended.append(month_of_year_r2(flat))
        shuffled, draws = list(flat), []
        for _ in range(permutations):
            rng.shuffle(shuffled)
            draws.append(month_of_year_r2(shuffled))
        detrended_null.append(sum(draws) / len(draws))

        year1, year2 = y[:12], y[12:]
        base = sum(year1) / 12
        adjusted = [year2[m] - (year1[m] - base) for m in range(12)]
        if variance(year2) > 0:
            oos.append(variance(adjusted) / variance(year2))
    return {
        "units": len(observed),
        "r2_p50": rnd(quantile(observed, 0.5), 3),
        "null_r2_p50": rnd(quantile(null_mean, 0.5), 3),
        "pct_units_above_own_null_p95": pct(beats_null95, len(observed), 1),
        "detrended_r2_p50": rnd(quantile(detrended, 0.5), 3),
        "detrended_null_r2_p50": rnd(quantile(detrended_null, 0.5), 3),
        "out_of_sample_variance_ratio_p50": rnd(quantile(oos, 0.5), 2),
        "pct_units_helped_out_of_sample": pct(sum(1 for r in oos if r < 1), len(oos), 1),
    }


def main() -> None:
    args = parse_args(
        __doc__.splitlines()[0],
        permutations={"type": int, "default": 200, "help": "shuffles per unit"},
        seed={"type": int, "default": 7, "help": "seed of the permutation generator"},
    )
    started = time.time()
    groups, products = load_groups(args.data), load_products(args.data)
    company_rows = defaultdict(list)  # company -> [(month, eur)]
    for company, product, _day, month, amount, category in booked_transactions(args.data):
        if amount > 0 and category in OP_IN:
            info = products.get(product)
            value = to_eur(amount, info[2] if info else None)
            if value is not None:
                company_rows[company].append((month, value))

    company_months, group_months = {}, defaultdict(lambda: [0.0] * N_MONTHS)
    for company, rows in company_rows.items():
        cap = quantile([v for _, v in rows], 0.95)
        monthly = [0.0] * N_MONTHS
        for month, value in rows:
            monthly[month] += min(value, cap)
            group_months[groups[company]][month] += min(value, cap)
        company_months[company] = monthly

    def log_series(monthly_by_unit):
        return {u: [math.log(v) for v in months] for u, months in monthly_by_unit.items() if all(v > 0 for v in months)}

    rng = random.Random(args.seed)
    result = {
        "expected_r2_under_noise": round(11 / 23, 3),
        "permutations": args.permutations,
        "seed": args.seed,
        "companies": study(log_series(company_months), args.permutations, rng),
        "groups": study(log_series(group_months), args.permutations, rng),
    }
    c, g = result["companies"], result["groups"]
    table = [
        ("metric", "companies", "groups", "validated companies / groups"),
        ("units with inflow in all 24 months", c["units"], g["units"], "211 / 76"),
        ("month-of-year R2, p50", c["r2_p50"], g["r2_p50"], "0.505 / 0.487"),
        ("permutation null R2, p50 (theory 0.478)", c["null_r2_p50"], g["null_r2_p50"], "0.479 / 0.480"),
        (
            "% of units above their own null p95",
            c["pct_units_above_own_null_p95"],
            g["pct_units_above_own_null_p95"],
            "21-29",
        ),
        (
            "detrended R2 p50 vs null",
            f"{c['detrended_r2_p50']} vs {c['detrended_null_r2_p50']}",
            f"{g['detrended_r2_p50']} vs {g['detrended_null_r2_p50']}",
            "0.538 vs 0.480 / -",
        ),
        (
            "year-1 factors applied to year 2: variance ratio p50",
            c["out_of_sample_variance_ratio_p50"],
            g["out_of_sample_variance_ratio_p50"],
            "1.49 / 1.68",
        ),
        (
            "  % of units where it lowers variance",
            c["pct_units_helped_out_of_sample"],
            g["pct_units_helped_out_of_sample"],
            "27 / 25",
        ),
    ]
    report("seasonality_null", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
