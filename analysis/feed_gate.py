"""Live-feed gate: which threshold separates a dead connector from ordinary volume noise.

Usage: python3 analysis/feed_gate.py --data <dir>

ratio(t) = booked rows in t-2..t / (3 x median monthly rows of t-12..t-4), per company
and per group (summed member rows), for the 12 months that have a full baseline.
The ratio is undefined when the baseline median is 0. Ground truth for a cut feed: an
entity is **dark** when its last month with a booked row is 2026-05 or earlier and
its first one is at least 6 months before that. Kill rules close the undefined cases:
no row in t-2..t, or (groups) a zero-row month after the first live month.

Second part: companies whose social-security payments stop (>= 6 months with such
rows, the last one 2026-05 or earlier). If their total row volume collapses at the
same time, the stop is feed decay and not a missed payment. Controls keep paying in
the last two months and are read at the same cut months as the stoppers.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict

from _common import (
    N_MONTHS,
    booked_transactions,
    load_groups,
    median,
    month_label,
    parse_args,
    pct,
    quantile,
    report,
    rnd,
)

THRESHOLDS = (0.5, 0.6, 0.7, 0.8)
LAST = N_MONTHS - 1
DARK_BY = LAST - 3  # last live month 2026-05 or earlier


def ratio(series, t):
    base = median([series[m] for m in range(t - 12, t - 3)])
    return None if not base else sum(series[m] for m in range(t - 2, t + 1)) / (3 * base)


def stale(series, t, threshold, kill_rules, zero_month_rule):
    """Gate verdict at month t for a list of monthly row counts."""
    recent = sum(series[m] for m in range(max(0, t - 2), t + 1))
    value = ratio(series, t) if t >= 12 else None
    if value is not None and value < threshold:
        return True
    if kill_rules and recent == 0:
        return True
    return bool(kill_rules and zero_month_rule and series[t] == 0 and any(series[:t]))


def sweep(entities, dark):
    """entities: id -> 24 monthly row counts. Returns one line per threshold."""
    lines = {}
    evaluable_months = sum(1 for s in entities.values() for t in range(12, N_MONTHS) if ratio(s, t) is not None)
    for threshold in THRESHOLDS:
        failing_months = sum(
            1
            for s in entities.values()
            for t in range(12, N_MONTHS)
            if (r := ratio(s, t)) is not None and r < threshold
        )
        failing = {e for e, s in entities.items() if stale(s, LAST, threshold, False, False)}
        lines[str(threshold)] = {
            "pct_of_evaluable_months_failing": pct(failing_months, evaluable_months, 1),
            "failing_at_last_month": len(failing),
            "of_which_dark": len(failing & dark),
            "precision_pct": pct(len(failing & dark), len(failing), 0),
        }
    return lines, evaluable_months


def with_kill_rules(entities, dark, threshold, zero_month_rule):
    flagged = {e for e, s in entities.items() if stale(s, LAST, threshold, True, zero_month_rule)}
    lags = []
    for e in dark:
        series = entities[e]
        last_live = max(m for m in range(N_MONTHS) if series[m])
        hit = next(
            (t for t in range(last_live + 1, N_MONTHS) if stale(series, t, threshold, True, zero_month_rule)), None
        )
        if hit is not None:
            lags.append(hit - last_live)
    return {
        "stale_at_last_month": len(flagged),
        "of_which_dark": len(flagged & dark),
        "dark_detected": len(lags),
        "dark_total": len(dark),
        "median_detection_lag_months": median(lags),
    }


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    groups = load_groups(args.data)
    rows = defaultdict(lambda: [0] * N_MONTHS)
    ss_months = defaultdict(set)
    for company, _product, _day, month, _amount, category in booked_transactions(args.data):
        rows[company][month] += 1
        if category == "social_security":
            ss_months[company].add(month)
    companies = {c: rows[c] for c in groups}  # companies without a booked row keep a zero series
    group_rows = defaultdict(lambda: [0] * N_MONTHS)
    for company, series in companies.items():
        for m, n in enumerate(series):
            group_rows[groups[company]][m] += n

    def dark_set(entities):
        live = {e: [m for m in range(N_MONTHS) if s[m]] for e, s in entities.items() if any(s)}
        return {e for e, months in live.items() if months[-1] <= DARK_BY and months[-1] - months[0] + 1 >= 6}

    dark_companies, dark_groups = dark_set(companies), dark_set(group_rows)
    company_sweep, company_months = sweep(companies, dark_companies)
    group_sweep, group_months = sweep(group_rows, dark_groups)
    undefined = {
        "companies": sum(1 for s in companies.values() if ratio(s, LAST) is None),
        "groups": sum(1 for s in group_rows.values() if ratio(s, LAST) is None),
        "dark_companies_passing_silently": sum(1 for c in dark_companies if ratio(companies[c], LAST) is None),
    }

    # first zero-row month of a group that had a real feed (median >= 10 rows a month
    # over its history up to t-3, at least 3 months): does the feed ever come back?
    first_zero = returned = 0
    for series in group_rows.values():
        if not any(series):
            continue
        first_live = next(m for m in range(N_MONTHS) if series[m])
        t = next((m for m in range(first_live + 1, N_MONTHS) if series[m] == 0), None)
        if t is not None and t - 2 - first_live >= 3 and median(series[first_live : t - 2]) >= 10:
            first_zero += 1
            returned += any(series[t + 1 :])

    # social-security stoppers vs controls
    def volume_ratio(series, cut):
        before = median(series[max(0, cut - 5) : cut + 1])
        return median(series[cut + 1 :]) / before if before else None

    stoppers = {c: max(ms) for c, ms in ss_months.items() if len(ms) >= 6 and max(ms) <= DARK_BY}
    stopper_ratios = {c: volume_ratio(companies[c], cut) for c, cut in stoppers.items()}
    stopper_values = [r for r in stopper_ratios.values() if r is not None]
    alive = [r for c, r in stopper_ratios.items() if r is not None and companies[c][LAST] > 0]
    controls = [c for c, ms in ss_months.items() if ms & {LAST - 1, LAST}]
    control_values = [
        r for c in controls for cut in stoppers.values() if (r := volume_ratio(companies[c], cut)) is not None
    ]

    result = {
        "evaluable_months": {"company": company_months, "group": group_months},
        "dark": {"companies": len(dark_companies), "groups": len(dark_groups)},
        "undefined_gate_at_last_month": undefined,
        "threshold_sweep_company": company_sweep,
        "threshold_sweep_group": group_sweep,
        "group_gate_0.5_with_kill_rules": with_kill_rules(group_rows, dark_groups, 0.5, True),
        "group_gate_0.8_with_kill_rules": with_kill_rules(group_rows, dark_groups, 0.8, True),
        "company_gate_0.5_with_kill_rules": with_kill_rules(companies, dark_companies, 0.5, False),
        "group_first_zero_month_events": {"events": first_zero, "never_returned": first_zero - returned},
        "social_security_stop": {
            "stoppers": len(stoppers),
            "cut_months": dict(sorted(Counter(month_label(m) for m in stoppers.values()).items())),
            "median_row_volume_ratio": rnd(median(stopper_values), 3),
            "q1_q3": [rnd(quantile(stopper_values, q), 3) for q in (0.25, 0.75)],
            "stoppers_with_zero_rows_in_last_month": sum(1 for c in stoppers if companies[c][LAST] == 0),
            "median_ratio_when_feed_still_alive": rnd(median(alive), 3),
            "stoppers_keeping_80pct_of_volume": sum(1 for r in stopper_values if r >= 0.8),
            "controls": len(controls),
            "control_median_ratio": rnd(median(control_values), 3),
            "control_pct_at_or_above_0.8": pct(sum(1 for r in control_values if r >= 0.8), len(control_values), 0),
        },
    }
    ss = result["social_security_stop"]
    table = [("metric", "measured", "validated")]
    for level, lines, reference in (
        ("company", company_sweep, {"0.5": "122 fail, 40 dark", "0.8": "234-244 fail, 40 dark; 19.6% of months"}),
        (
            "group",
            group_sweep,
            {"0.5": "19 fail, 9 dark", "0.6": "same set as 0.5", "0.8": "36 fail, 9 dark; 17.7% of months"},
        ),
    ):
        for threshold, line in lines.items():
            table.append(
                (
                    f"{level} gate < {threshold}",
                    f"{line['failing_at_last_month']} fail, {line['of_which_dark']} dark ({line['precision_pct']}% "
                    f"precision); {line['pct_of_evaluable_months_failing']}% of months",
                    reference.get(threshold, ""),
                )
            )
    kill = result["group_gate_0.5_with_kill_rules"]
    table += [
        (
            "gate undefined at 2026-08: companies / groups",
            f"{undefined['companies']} / {undefined['groups']}",
            "255 / 53",
        ),
        ("dark companies the bare ratio lets through", undefined["dark_companies_passing_silently"], "21 of 61"),
        (
            "dark companies / groups",
            f"{len(dark_companies)} / {len(dark_groups)}",
            "61 / 15 (groups: >= 6 live months)",
        ),
        (
            "group gate 0.5 + kill rules: stale at 2026-08",
            f"{kill['stale_at_last_month']} ({kill['of_which_dark']} dark)",
            "",
        ),
        (
            "  dark groups detected, median lag",
            f"{kill['dark_detected']} / {kill['dark_total']}, {kill['median_detection_lag_months']} month",
            "15 / 15, 1 month",
        ),
        ("group first zero-row month: events, never returned", f"{first_zero}, {first_zero - returned}", "9, 8"),
        ("social-security stoppers", ss["stoppers"], "47"),
        ("  median row volume after / before the stop", ss["median_row_volume_ratio"], "0.167"),
        ("  stoppers with no rows at all in 2026-08", ss["stoppers_with_zero_rows_in_last_month"], "22"),
        ("  median ratio when the feed is still alive", ss["median_ratio_when_feed_still_alive"], "0.403"),
        ("  stoppers keeping >= 80% of their volume", ss["stoppers_keeping_80pct_of_volume"], "8"),
        (
            "  controls: n, median ratio, % >= 0.8",
            f"{ss['controls']}, {ss['control_median_ratio']}, {ss['control_pct_at_or_above_0.8']}%",
            "560, 1.026, 89%",
        ),
    ]
    report("feed_gate", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
