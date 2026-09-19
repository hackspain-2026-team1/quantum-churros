"""Debt pillar: is a DSCR proxy measurable from bank flows, and is debt-service burden?

Usage: python3 analysis/debt_burden_stability.py --data <dir>

Per group, EUR by static FX on the account currency, booked in-window rows.

* debt service = amount < 0 in debt_repayment, interest_charge
* **DSCR proxy** = (operating inflow - operating outflow) / debt service, with the
  strict flow lists (4 inflow categories, 7 outflow categories)
* **burden** = debt service / inflow. Three denominators: *inclusive* (every positive
  row except transfer, investment_return, refunds, withdrawals), *strict* (the 4
  operating-inflow categories) and *shipped* (strict plus '-' rows defaulted by sign).
  ``winsorised`` caps each monthly total at 3 x the median month of the same window,
  on both sums as the engine does, or on debt service only (the first measurement).

A metric a score can stand on must rank groups the same way in two disjoint halves of
the window: half-vs-half Spearman between months 1-12 and 13-24, over the groups with
debt service in both halves.
"""

from __future__ import annotations

import time
from collections import defaultdict

from _common import (
    DEBT_SERVICE,
    N_MONTHS,
    OP_IN,
    OP_OUT,
    booked_transactions,
    load_groups,
    load_products,
    parse_args,
    pct,
    piecewise,
    quantile,
    report,
    rnd,
    spearman,
    to_eur,
    winsorised_sum,
)

NOT_INCLUSIVE = {
    "transfer",
    "investment_return",
    "collection_refund",
    "payment_refund",
    "cash_withdrawal",
    "pos_withdrawal",
}
DSCR_ANCHORS = [(0.8, 10), (1.0, 35), (1.25, 60), (2.0, 90), (3.0, 100)]
H1, H2 = slice(0, N_MONTHS // 2), slice(N_MONTHS // 2, N_MONTHS)


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    groups, products = load_groups(args.data), load_products(args.data)

    def months():
        return [0.0] * N_MONTHS

    service, op_in, op_out, inclusive, dash_in = (defaultdict(months) for _ in range(5))
    for company, product, _day, month, amount, category in booked_transactions(args.data):
        info = products.get(product)
        value = to_eur(amount, info[2] if info else None)
        if value is None:
            continue
        group = groups[company]
        if amount < 0:
            if category in DEBT_SERVICE:
                service[group][month] -= value
            elif category in OP_OUT:
                op_out[group][month] -= value
        elif amount > 0:
            if category in OP_IN:
                op_in[group][month] += value
            if category not in NOT_INCLUSIVE:
                inclusive[group][month] += value
            if category == "-":
                dash_in[group][month] += value
    all_groups = sorted(set(groups.values()))
    shipped = {g: [a + b for a, b in zip(op_in[g], dash_in[g], strict=True)] for g in all_groups}

    def dscr(g, half):
        due = sum(service[g][half])
        return (sum(op_in[g][half]) - sum(op_out[g][half])) / due if due > 0 else None

    def dscr_pillar(g, half):
        value = dscr(g, half)
        return None if value is None else piecewise([(0.0, 0)] + DSCR_ANCHORS, value)

    def burden(inflow, winsorised=""):
        def measure(g, half):
            base = (winsorised_sum if winsorised == "both" else sum)(inflow[g][half])
            return (winsorised_sum if winsorised else sum)(service[g][half]) / base if base > 0 else None

        return measure

    def half_vs_half(measure):
        pairs = [
            (measure(g, H1), measure(g, H2)) for g in all_groups if sum(service[g][H1]) > 0 and sum(service[g][H2]) > 0
        ]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        return {"groups": len(pairs), "spearman": rnd(spearman(*zip(*pairs, strict=True)), 3)}

    stability = {
        "dscr_proxy": half_vs_half(dscr),
        "dscr_pillar_score": half_vs_half(dscr_pillar),
        "burden_inclusive_raw": half_vs_half(burden(inclusive)),
        "burden_inclusive_service_winsorised": half_vs_half(burden(inclusive, "service")),
        "burden_inclusive_winsorised": half_vs_half(burden(inclusive, "both")),
        "burden_strict_winsorised": half_vs_half(burden(op_in, "both")),
        "burden_shipped_winsorised": half_vs_half(burden(shipped, "both")),
    }

    # last 12 months: how the two metrics are distributed
    with_service = [g for g in all_groups if sum(service[g][H2]) > 0]
    with_flows = [g for g in all_groups if any(inclusive[g]) or any(service[g]) or any(op_out[g])]
    dscr_values = [dscr(g, H2) for g in with_service]
    pillar = [dscr_pillar(g, H2) for g in with_service]
    raw = [v for g in with_service if (v := burden(inclusive)(g, H2)) is not None]
    lumpiness = [max(service[g][H2]) / sum(service[g][H2]) for g in with_service]

    def over_half(inflow, winsorised):
        return sum(1 for g in with_service if (v := burden(inflow, winsorised)(g, H2)) is not None and v > 0.5)

    result = {
        "half_vs_half": stability,
        "groups_with_value_rows": len(with_flows),
        "groups_without_debt_service_last_12m": len(with_flows) - len(with_service),
        "dscr_last_12m": {
            "groups": len(dscr_values),
            "p25_p50_p75": [rnd(quantile(dscr_values, q), 2) for q in (0.25, 0.5, 0.75)],
            "pct_negative_numerator": pct(sum(1 for v in dscr_values if v < 0), len(dscr_values), 1),
            "pillar_pct_at_0": pct(sum(1 for s in pillar if s == 0), len(pillar), 1),
            "pillar_pct_at_100": pct(sum(1 for s in pillar if s == 100), len(pillar), 1),
        },
        "burden_inclusive_raw_last_12m": {
            f"p{int(q * 100)}": rnd(quantile(raw, q), 3) for q in (0.25, 0.5, 0.75, 0.95)
        },
        "groups_with_burden_over_50pct": {
            "strict_raw": over_half(op_in, ""),
            "inclusive_raw": over_half(inclusive, ""),
            "inclusive_service_winsorised": over_half(inclusive, "service"),
            "inclusive_both_winsorised": over_half(inclusive, "both"),
        },
        "largest_month_share_of_debt_service": {
            f"p{int(q * 100)}": rnd(quantile(lumpiness, q), 3) for q in (0.5, 0.75, 0.95)
        },
    }
    d, over = result["dscr_last_12m"], result["groups_with_burden_over_50pct"]
    b, lump = result["burden_inclusive_raw_last_12m"], result["largest_month_share_of_debt_service"]
    table = [
        ("metric", "measured", "validated"),
        (
            "half-vs-half Spearman, DSCR proxy (groups)",
            f"{stability['dscr_proxy']['spearman']} ({stability['dscr_proxy']['groups']})",
            "0.14",
        ),
        ("half-vs-half Spearman, DSCR mapped to its anchors", stability["dscr_pillar_score"]["spearman"], "0.14"),
        (
            "half-vs-half Spearman, burden / inclusive inflow, raw",
            stability["burden_inclusive_raw"]["spearman"],
            "0.66",
        ),
        (
            "  same, debt-service months winsorised at 3x the median month",
            stability["burden_inclusive_service_winsorised"]["spearman"],
            "",
        ),
        ("  same, both sums winsorised (engine rule)", stability["burden_inclusive_winsorised"]["spearman"], ""),
        ("  burden / strict operating inflow, winsorised", stability["burden_strict_winsorised"]["spearman"], ""),
        (
            "  burden / shipped operating inflow ('-' by sign), winsorised",
            stability["burden_shipped_winsorised"]["spearman"],
            "",
        ),
        (
            "groups without debt service in the last 12 months",
            f"{result['groups_without_debt_service_last_12m']} / {len(with_flows)}",
            "66 / 249",
        ),
        ("DSCR last 12m: groups, p50", f"{d['groups']}, {d['p25_p50_p75'][1]}", "183, -0.57"),
        ("  % with a negative numerator", d["pct_negative_numerator"], "54"),
        ("  pillar % at 0 / % at 100", f"{d['pillar_pct_at_0']} / {d['pillar_pct_at_100']}", "53.6 / 27.9"),
        (
            "burden last 12m p25 / p50 / p75 / p95",
            " / ".join(str(v) for v in b.values()),
            "0.001 / 0.018 / 0.074 / 0.235",
        ),
        (
            "groups with burden > 50%: strict raw / inclusive raw / service winsorised / both winsorised",
            " / ".join(str(v) for v in over.values()),
            "6 / 5 / 4 / -",
        ),
        (
            "largest month as share of 12m debt service p50 / p75 / p95",
            " / ".join(str(v) for v in lump.values()),
            "0.285 / 0.495 / 0.999",
        ),
    ]
    report("debt_burden_stability", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
