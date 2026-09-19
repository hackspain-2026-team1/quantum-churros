"""Liquidity: buffer days by size under absolute anchors, and persistence of negative cash.

Usage: python3 analysis/liquidity_size_gradient.py --data <dir>

Month-end cash is back-rolled per cash product (checking, saving, wallet) from its
balance row (``_common.month_end_balances``); EUR by static FX on the account
currency; group cash = sum over members.

buffer days(T) = cash(T) / (median monthly outflow of the 3 months ending in T / 30),
outflow = amount < 0 in payment, bulk_payment, salary, tax, social_security, utility,
fee, debt_repayment, interest_charge. Undefined when that median is 0. The variant
with headroom adds, per credit line, |granted| - drawn balance at T (limit assumed
constant). Absolute anchors 0->0, 13->35, 27->60, 62->85, 120->100 (JPMorgan Chase
Institute cash-buffer-days quartiles for the x values). Size = operating inflow of the
last 12 months: quartiles over the groups with any such inflow, and EU SME bands (<2M,
<10M, <50M, >=50M, annualised over the live months). Medians are taken over the groups
of each class that have a defined buffer.
"""

from __future__ import annotations

import time
from collections import defaultdict

from _common import (
    CASH_TYPES,
    DEBT_SERVICE,
    N_MONTHS,
    OP_IN,
    OP_OUT,
    booked_transactions,
    load_credit_limits,
    load_groups,
    load_products,
    median,
    month_end_balances,
    parse_args,
    pct,
    piecewise,
    quantile,
    report,
    rnd,
    to_eur,
)

ANCHORS = [(0, 0), (13, 35), (27, 60), (62, 85), (120, 100)]
ANCHORS_180 = ANCHORS[:-1] + [(180, 100)]
OUTFLOW = OP_OUT | DEBT_SERVICE
LAST = N_MONTHS - 1
EU_BANDS = ((2e6, "micro <2M"), (10e6, "small <10M"), (50e6, "medium <50M"), (float("inf"), "large >=50M"))


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    groups, products = load_groups(args.data), load_products(args.data)
    limits = load_credit_limits(args.data)
    balances, _first_move, unanchored = month_end_balances(args.data, products, CASH_TYPES | {"lineofcredit"})

    cash = defaultdict(lambda: [0.0] * N_MONTHS)  # group -> month-end cash, EUR
    company_cash = defaultdict(lambda: [0.0] * N_MONTHS)
    headroom = defaultdict(float)  # group -> headroom at the last month end
    for product, cents in balances.items():
        company, kind, currency = products[product]
        if to_eur(1.0, currency) is None:
            continue
        if kind in CASH_TYPES:
            for m in range(N_MONTHS):
                value = to_eur(cents[m] / 100, currency)
                cash[groups[company]][m] += value
                company_cash[company][m] += value
        elif product in limits:
            headroom[groups[company]] += to_eur(limits[product] - max(0.0, -cents[LAST] / 100), currency)

    outflow = defaultdict(lambda: [0.0] * N_MONTHS)  # group -> monthly outflow, EUR
    inflow_12m, live_12m = defaultdict(float), defaultdict(set)
    for company, product, _day, month, amount, category in booked_transactions(args.data):
        info = products.get(product)
        value = to_eur(amount, info[2] if info else None)
        if value is None:
            continue
        group = groups[company]
        if amount < 0 and category in OUTFLOW:
            outflow[group][month] -= value
        if month > LAST - 12:
            live_12m[group].add(month)
            if amount > 0 and category in OP_IN:
                inflow_12m[group] += value

    def buffer_days(cash_value, monthly_outflow, m):
        burn = median(monthly_outflow[m - 2 : m + 1])
        return None if not burn else cash_value / (burn / 30)

    all_groups = sorted(set(groups.values()))
    buffers = {g: buffer_days(cash[g][LAST], outflow[g], LAST) for g in all_groups}
    buffers = {g: b for g, b in buffers.items() if b is not None}
    with_headroom = {g: buffer_days(cash[g][LAST] + headroom[g], outflow[g], LAST) for g in buffers}

    def spread(values, anchors=ANCHORS):
        scores = [piecewise(anchors, v) for v in values]
        return {
            "n": len(scores),
            **{f"p{int(q * 100)}": rnd(quantile(scores, q), 1) for q in (0.25, 0.5, 0.75)},
            "pct_at_0": pct(sum(1 for s in scores if s == 0), len(scores), 1),
            "pct_at_100": pct(sum(1 for s in scores if s == 100), len(scores), 1),
            "mean": round(sum(scores) / len(scores), 1),
        }

    def describe(part):
        return {
            "groups": len(part),
            "median_buffer_days": rnd(median([buffers[g] for g in part]), 1),
            "median_pillar": rnd(median([piecewise(ANCHORS, buffers[g]) for g in part]), 1),
            "median_pillar_with_headroom": rnd(median([piecewise(ANCHORS, with_headroom[g]) for g in part]), 1),
            "pct_groups_with_headroom": pct(sum(1 for g in part if headroom[g] > 0), len(part), 0),
        }

    ordered = sorted((g for g in all_groups if inflow_12m[g] > 0), key=lambda g: (inflow_12m[g], g))
    quartiles = {
        f"Q{q + 1}": describe([g for g in ordered[len(ordered) * q // 4 : len(ordered) * (q + 1) // 4] if g in buffers])
        for q in range(4)
    }
    bands = defaultdict(list)
    for g in buffers:
        annual = inflow_12m[g] * 12 / max(1, len(live_12m[g]))
        bands[next(name for limit, name in EU_BANDS if annual < limit)].append(g)
    eu = {name: describe(bands[name]) for _, name in EU_BANDS if bands[name]}

    def persistence(series_by_entity, state):
        """All (t, t+6) pairs pooled: how often is the state still there six months later?"""
        still = now_in = later_only = now_out = 0
        for entity, series in series_by_entity.items():
            for t in range(N_MONTHS - 6):
                now, later = state(entity, series, t), state(entity, series, t + 6)
                if now is None or later is None:
                    continue
                if now:
                    now_in += 1
                    still += later
                else:
                    now_out += 1
                    later_only += later
        return {
            "pairs_in_state": now_in,
            "pct_still_in_state_6m_later": pct(still, now_in, 1),
            "pct_in_state_6m_later_when_not_now": pct(later_only, now_out, 1),
            "base_rate_pct": pct(still + later_only, now_in + now_out, 2),
        }

    def negative(_entity, series, t):
        return series[t] < 0

    def thin(group, series, t):
        days = buffer_days(series[t], outflow[group], t) if t >= 2 else None
        return None if days is None else days < 13

    group_cash = {g: cash[g] for g in all_groups}
    unanchored_cash = [
        p for p in unanchored if products[p][1] in CASH_TYPES and to_eur(1.0, products[p][2]) is not None
    ]
    result = {
        "cash_products_with_movements_but_no_balance_row": len(unanchored_cash),
        "groups_with_defined_buffer": len(buffers),
        "group_buffer_days": {
            f"p{int(q * 100)}": rnd(quantile(buffers.values(), q), 1) for q in (0.05, 0.25, 0.5, 0.75, 0.95)
        },
        "pillar_absolute_anchors": spread(buffers.values()),
        "pillar_absolute_anchors_top_180d": spread(buffers.values(), ANCHORS_180),
        "pillar_with_headroom": spread(with_headroom.values()),
        "groups_with_headroom": sum(1 for g in buffers if headroom[g] > 0),
        "groups_with_operating_inflow_last_12m": len(ordered),
        "by_size_quartile": quartiles,
        "by_eu_size_band": eu,
        "negative_cash_persistence_group": persistence(group_cash, negative),
        "negative_cash_persistence_company": {"companies": len(company_cash), **persistence(company_cash, negative)},
        "buffer_under_13d_persistence_group": persistence(group_cash, thin),
    }

    p, h, big = (
        result["pillar_absolute_anchors"],
        result["pillar_with_headroom"],
        result["pillar_absolute_anchors_top_180d"],
    )
    gp, cp, thin_p = (
        result[k]
        for k in (
            "negative_cash_persistence_group",
            "negative_cash_persistence_company",
            "buffer_under_13d_persistence_group",
        )
    )
    days = result["group_buffer_days"]

    def across(parts, key):
        return " / ".join(str(part[key]) for part in parts.values())

    table = [
        ("metric", "measured", "validated"),
        ("groups with a defined buffer at 2026-08", len(buffers), "225"),
        ("group buffer days p25 / p50 / p75", f"{days['p25']} / {days['p50']} / {days['p75']}", "4.9 / 23.2 / 84.4"),
        ("pillar p25 / p50 / p75, absolute anchors", f"{p['p25']} / {p['p50']} / {p['p75']}", "13.3 / 53.2 / 90.8"),
        ("  % at 0 / % at 100 / mean", f"{p['pct_at_0']} / {p['pct_at_100']} / {p['mean']}", "6.2 / 19.6 / 51.2"),
        (
            "  top anchor at 180d: p50, % at 100",
            f"{big['p50']}, {big['pct_at_100']}",
            "13.3% at 100 (p50 cannot move: see EVIDENCE.md)",
        ),
        ("pillar p25 / p50 / p75 with headroom", f"{h['p25']} / {h['p50']} / {h['p75']}", "26.0 / 64.7 / 93.3"),
        ("median pillar by size quartile Q1..Q4", across(quartiles, "median_pillar"), "81.6 / 85.2 / 36.6 / 19.2"),
        ("  median buffer days Q1..Q4", across(quartiles, "median_buffer_days"), "57.2 / 62.9 / 13.9 / 7.1"),
        ("  with headroom Q1..Q4", across(quartiles, "median_pillar_with_headroom"), "85 -> 36"),
        ("  % of groups with headroom Q1..Q4", across(quartiles, "pct_groups_with_headroom"), "12 -> 61"),
        ("EU bands micro / small / medium / large: groups", across(eu, "groups"), ""),
        ("  median buffer days", across(eu, "median_buffer_days"), ""),
        ("  median pillar", across(eu, "median_pillar"), ""),
        ("  median pillar with headroom", across(eu, "median_pillar_with_headroom"), ""),
        (
            "group cash < 0 now -> still < 0 six months later, %",
            f"{gp['pct_still_in_state_6m_later']} (n={gp['pairs_in_state']})",
            "72.5 (n=371)",
        ),
        ("  ... when cash is positive now, %", gp["pct_in_state_6m_later_when_not_now"], "1.5"),
        ("  base rate, %", gp["base_rate_pct"], "7.33"),
        (
            "company cash < 0 now -> still < 0 six months later, %",
            f"{cp['pct_still_in_state_6m_later']} (n={cp['pairs_in_state']})",
            "64.6 (n=1,689)",
        ),
        (
            "  ... when positive now, % / base rate, %",
            f"{cp['pct_in_state_6m_later_when_not_now']} / {cp['base_rate_pct']}",
            "2.0 / 6.16 (6.16 implies 1.5)",
        ),
        (
            "group buffer < 13d now -> still six months later, %",
            f"{thin_p['pct_still_in_state_6m_later']} vs {thin_p['pct_in_state_6m_later_when_not_now']}",
            "73.8 vs 16.0",
        ),
        ("cash products with movements but no balance row", len(unanchored_cash), "98"),
    ]
    report("liquidity_size_gradient", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
