"""Credit lines: is back-rolled utilisation a persistent level, so headroom can be as-of?

Usage: python3 analysis/credit_lines.py --data <dir>

utilisation(T) = drawn balance at month end T / |granted|, clipped to [0, 1], for every
``lineofcredit`` product with a balance row and a granted limit. The balance is
back-rolled from the snapshot (``_common.month_end_balances``); the limit is the
snapshot value, assumed constant. Lines without a single booked row have a constant
series and inflate any pooled correlation, so the honest figure is the one for lines
that move, counted from their first movement.
"""

from __future__ import annotations

import time

from _common import (
    N_MONTHS,
    load_credit_limits,
    load_products,
    month_end_balances,
    parse_args,
    pct,
    pearson,
    quantile,
    report,
    rnd,
    spearman,
)

LAST = N_MONTHS - 1


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    products = load_products(args.data)
    limits = load_credit_limits(args.data)
    balances, first_move, _ = month_end_balances(args.data, products, {"lineofcredit"})

    utilisation = {
        pid: [min(1.0, max(0.0, -c / 100 / limits[pid])) for c in cents]
        for pid, cents in balances.items()
        if limits.get(pid, 0) > 0
    }
    raw_ratio = {pid: [-c / 100 / limits[pid] for c in balances[pid]] for pid in utilisation}

    def lagged(series_by_line, lag, movers_only):
        xs, ys = [], []
        for pid, series in series_by_line.items():
            if movers_only and pid not in first_move:
                continue
            for t in range(first_move[pid] if movers_only else 0, N_MONTHS - lag):
                xs.append(series[t])
                ys.append(series[t + lag])
        return {"pairs": len(xs), "pearson": rnd(pearson(xs, ys), 3), "spearman": rnd(spearman(xs, ys), 3)}

    snapshot = [series[LAST] for series in utilisation.values()]
    result = {
        "lines_with_balance_and_limit": len(utilisation),
        "lines_that_move": sum(1 for pid in utilisation if pid in first_move),
        "lag3_all_lines": lagged(utilisation, 3, False),
        "lag3_lines_that_move": lagged(utilisation, 3, True),
        "lag1_lines_that_move": lagged(utilisation, 1, True),
        "lag3_all_lines_unclipped": lagged(raw_ratio, 3, False),
        "utilisation_at_last_month": {
            f"p{int(q * 100)}": rnd(quantile(snapshot, q), 3) for q in (0.25, 0.5, 0.75, 0.95)
        },
        "pct_lines_undrawn_at_last_month": pct(sum(1 for u in snapshot if u <= 0.01), len(snapshot), 1),
        "pct_lines_98pct_drawn_at_last_month": pct(sum(1 for u in snapshot if u >= 0.98), len(snapshot), 1),
    }
    everyone, movers, raw = result["lag3_all_lines"], result["lag3_lines_that_move"], result["lag3_all_lines_unclipped"]
    last = result["utilisation_at_last_month"]
    table = [
        ("metric", "measured", "validated"),
        ("credit lines with a balance row and a limit", len(utilisation), "462"),
        ("  of which with at least one booked row", result["lines_that_move"], "288"),
        (
            "lag-3 autocorrelation, lines that move: Pearson / Spearman (pairs)",
            f"{movers['pearson']} / {movers['spearman']} ({movers['pairs']})",
            "0.742 / 0.752 (3,214)",
        ),
        (
            "lag-3 autocorrelation, all lines: Pearson / Spearman (pairs)",
            f"{everyone['pearson']} / {everyone['spearman']} ({everyone['pairs']})",
            "0.898 / 0.899 (9,702)",
        ),
        ("lag-3 Pearson without clipping to [0, 1]", raw["pearson"], "about 0 (outliers)"),
        (
            "utilisation at 2026-08 p25 / p50 / p75 / p95",
            " / ".join(str(v) for v in last.values()),
            "0.00 / 0.059 / 0.844 / 1.00",
        ),
        ("% of lines undrawn (<= 1%) at 2026-08", result["pct_lines_undrawn_at_last_month"], "46.5"),
    ]
    report("credit_lines", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
