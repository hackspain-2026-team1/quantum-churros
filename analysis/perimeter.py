"""Perimeter: how much of the panel's movement is groups and accounts being connected.

Usage: python3 analysis/perimeter.py --data <dir>

First month of a company or an account = first month with a booked, in-window
transaction (never ``created_at``). A group is live in a month when any member has a
booked row in it. A connection event is an account whose first month is later than
its company's first month; events are deduped to (company, month). A collections
jump is a month, later than the company's first month, whose collections (collection
+ bulk_collection, EUR) exceed 1.5 x a non-zero previous month. Month pairs with no
booked row in either month are not eligible.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict

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

COLLECTIONS = ("collection", "bulk_collection")


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    groups, products = load_groups(args.data), load_products(args.data)

    rows = defaultdict(Counter)  # company -> month -> booked rows
    collections = defaultdict(Counter)  # company -> month -> EUR collected
    inflow = Counter()  # company -> operating inflow over the window, EUR
    product_first: dict[str, int] = {}
    product_owner: dict[str, str] = {}
    for company, product, _day, month, amount, category in booked_transactions(args.data):
        rows[company][month] += 1
        if month < product_first.get(product, N_MONTHS):
            product_first[product] = month
            product_owner[product] = company
        if amount > 0 and category in OP_IN:
            info = products.get(product)
            value = to_eur(amount, info[2] if info else None)
            if value is not None:
                inflow[company] += value
                if category in COLLECTIONS:
                    collections[company][month] += value

    company_first = {c: min(months) for c, months in rows.items()}
    all_groups = sorted(set(groups.values()))
    members = defaultdict(list)
    for company in company_first:
        members[groups[company]].append(company)
    group_first = {g: min(company_first[c] for c in cs) for g, cs in members.items()}
    live_months = {g: {m for c in cs for m in rows[c]} for g, cs in members.items()}

    # groups gaining a member after their own first month
    gaining = [g for g, cs in members.items() if any(company_first[c] > group_first[g] for c in cs)]
    multi_member = [g for g, cs in members.items() if len(cs) > 1]
    late_share = []
    for g in gaining:
        total = sum(inflow[c] for c in members[g])
        if total > 0:
            late_share.append(sum(inflow[c] for c in members[g] if company_first[c] > group_first[g]) / total)

    live_histogram = Counter(len(months) for months in live_months.values())

    # connection events: product level, then deduped to (company, month) and (group, month)
    product_events = [(product_owner[p], m) for p, m in product_first.items() if m > company_first[product_owner[p]]]
    company_months = set(product_events)
    group_months = {(groups[c], m) for c, m in company_months}
    group_months |= {(groups[c], m) for c, m in company_first.items() if m > group_first[groups[c]]}
    events_per_company = Counter(c for c, _ in company_months)

    # do large collection jumps coincide with a connection month?
    eligible = jumps = jumps_on_connection = 0
    for company, first in company_first.items():
        for m in range(first + 1, N_MONTHS):
            if rows[company][m] == 0 and rows[company][m - 1] == 0:
                continue
            eligible += 1
            before, now = collections[company][m - 1], collections[company][m]
            if before > 0 and now > 1.5 * before:
                jumps += 1
                jumps_on_connection += (company, m) in company_months

    result = {
        "groups": len(all_groups),
        "groups_gaining_a_member": len(gaining),
        "pct_of_groups": pct(len(gaining), len(all_groups), 1),
        "multi_member_groups": len(multi_member),
        "pct_of_multi_member_groups": pct(len(gaining), len(multi_member), 1),
        "late_joiner_inflow_share": {
            f"p{int(q * 100)}": rnd(quantile(late_share, q), 3) for q in (0.1, 0.25, 0.5, 0.75, 0.9)
        },
        "groups_with_over_half_inflow_from_late_joiners": sum(1 for s in late_share if s > 0.5),
        "groups_live_in_first_month": sum(1 for months in live_months.values() if 0 in months),
        "groups_live_all_months": live_histogram[N_MONTHS],
        "groups_live_9_months_or_fewer": sum(v for k, v in live_histogram.items() if k <= 9),
        "groups_live_10_months_or_fewer": sum(v for k, v in live_histogram.items() if k <= 10),
        "live_months_histogram": {str(k): live_histogram[k] for k in sorted(live_histogram)},
        "median_live_months": quantile([len(m) for m in live_months.values()], 0.5),
        "connection_events_product_level": len(product_events),
        "connection_company_months": len(company_months),
        "companies_with_a_connection": len(events_per_company),
        "companies_without_a_connection": len(company_first) - len(events_per_company),
        "perimeter_changed_group_months": len(group_months),
        "groups_with_a_perimeter_change": len({g for g, _ in group_months}),
        "eligible_company_month_pairs": eligible,
        "collection_jumps_over_1.5x": jumps,
        "jumps_in_a_connection_month": jumps_on_connection,
        "pct_jumps_coinciding_with_connection": pct(jumps_on_connection, jumps, 1),
        "pct_connection_months_with_a_jump": pct(jumps_on_connection, len(company_months), 1),
        "base_rate_pct_of_month_pairs_with_a_jump": pct(jumps, eligible, 1),
    }
    table = [
        ("metric", "measured", "validated"),
        (
            "groups gaining a member mid-window",
            f"{len(gaining)} / {len(all_groups)} = {result['pct_of_groups']}%",
            "110 / 250 = 44.0%",
        ),
        (
            "  ... of multi-member groups",
            f"{len(gaining)} / {len(multi_member)} = {result['pct_of_multi_member_groups']}%",
            "110 / 179 = 61.5%",
        ),
        (
            "late joiners' share of group inflow, p50 / p90",
            f"{result['late_joiner_inflow_share']['p50']} / {result['late_joiner_inflow_share']['p90']}",
            "0.121 / 0.808",
        ),
        (
            "groups with >50% of inflow from late joiners",
            result["groups_with_over_half_inflow_from_late_joiners"],
            "23",
        ),
        ("groups live in the first month (2024-09)", result["groups_live_in_first_month"], "95"),
        ("groups live in all 24 months", result["groups_live_all_months"], "86"),
        (
            "groups live in <=9 / <=10 months",
            f"{result['groups_live_9_months_or_fewer']} / {result['groups_live_10_months_or_fewer']}",
            "66 quoted as <=10; its histogram gives 66 / 80",
        ),
        ("connection events, product level", len(product_events), "2,378"),
        ("connection events, deduped to company-month", len(company_months), "1,563"),
        (
            "companies with / without a connection event",
            f"{len(events_per_company)} / {result['companies_without_a_connection']}",
            "752 / 534",
        ),
        (
            "perimeter_changed group-months (groups)",
            f"{len(group_months)} ({result['groups_with_a_perimeter_change']})",
            "1,049 (208)",
        ),
        ("eligible company month-pairs", eligible, "20,388"),
        ("collection jumps >1.5x", jumps, "4,528"),
        ("% of jumps coinciding with a connection", result["pct_jumps_coinciding_with_connection"], "10.8"),
        (
            "% of connection months with a jump (base rate)",
            f"{result['pct_connection_months_with_a_jump']} ({result['base_rate_pct_of_month_pairs_with_a_jump']})",
            "31.2 (22.2)",
        ),
    ]
    report("perimeter", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
