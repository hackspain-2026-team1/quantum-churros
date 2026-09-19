"""Customer concentration: an event in any month, or a trait that needs a recurrence filter?

Usage: python3 analysis/concentration.py --data <dir>

Collections = amount > 0 in the four operating-inflow categories, EUR. The counterparty
of a row is ``counterparty_id`` when present, else the ``COUNTERPARTY_n`` token of the
description when there is exactly one (two or more tokens is a remittance: nobody).
Monthly share = top-1 counterparty / ALL collections of the month, unattributed rows
included in the denominator (dividing by attributed collections only inflates it).
A company is flagged when the share is >= 20% in >= 6 of the last 12 months; a month
without collections is not flagged.
"""

from __future__ import annotations

import re
import time
from collections import Counter, defaultdict

from _common import N_MONTHS, OP_IN, booked_transactions, load_products, parse_args, pct, quantile, report, rnd, to_eur

TOKEN = re.compile(r"COUNTERPARTY_\d+")
SHARE, MIN_MONTHS, TRAILING = 0.20, 6, 12


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    products = load_products(args.data)
    total = defaultdict(float)  # (company, month) -> EUR collected
    by_party = defaultdict(lambda: defaultdict(float))  # (company, month) -> counterparty -> EUR
    rows = Counter()
    for company, product, _day, month, amount, category, party, description in booked_transactions(
        args.data, "counterparty_id", "description"
    ):
        if amount <= 0 or category not in OP_IN:
            continue
        info = products.get(product)
        value = to_eur(amount, info[2] if info else None)
        if value is None:
            continue
        rows["collections"] += 1
        if party:
            rows["with_counterparty_id"] += 1
        else:
            tokens = TOKEN.findall(description)
            party = tokens[0] if len(tokens) == 1 else ""
            rows["with_single_token"] += bool(party)
        total[(company, month)] += value
        if party:
            by_party[(company, month)][party] += value

    share = {key: max(by_party[key].values(), default=0.0) / value for key, value in total.items() if value > 0}
    attributed = [s for key, s in share.items() if by_party.get(key)]
    companies = {company for company, _ in share}
    flagged_months = Counter({c: 0 for c in companies})
    ever = set()
    for (company, month), s in share.items():
        if s >= SHARE:
            ever.add(company)
            flagged_months[company] += month >= N_MONTHS - TRAILING
    recurrent = [c for c, n in flagged_months.items() if n >= MIN_MONTHS]
    histogram = Counter(flagged_months.values())

    result = {
        "collection_rows": rows["collections"],
        "pct_rows_with_counterparty_id": pct(rows["with_counterparty_id"], rows["collections"], 1),
        "pct_rows_attributed_after_token_harvest": pct(
            rows["with_counterparty_id"] + rows["with_single_token"], rows["collections"], 1
        ),
        "companies_with_collections": len(companies),
        "company_months_with_an_attributed_row": len(attributed),
        "top1_share_in_those_months": {f"p{int(q * 100)}": rnd(quantile(attributed, q), 3) for q in (0.1, 0.5, 0.9)},
        "flagged_in_any_month": len(ever),
        "pct_flagged_in_any_month": pct(len(ever), len(companies), 1),
        "flagged_recurrent": len(recurrent),
        "pct_flagged_recurrent": pct(len(recurrent), len(companies), 1),
        "flagged_months_histogram": {str(k): histogram[k] for k in range(TRAILING + 1)},
    }
    table = [
        ("metric", "measured", "validated"),
        ("companies with collections", len(companies), "1,261"),
        (
            "collection rows attributed: id only -> with single token, %",
            f"{result['pct_rows_with_counterparty_id']} -> {result['pct_rows_attributed_after_token_harvest']}",
            "",
        ),
        ("company-months with an attributed row", len(attributed), "12,384"),
        (
            "  top-1 share in those months p10 / p50 / p90",
            " / ".join(str(v) for v in result["top1_share_in_those_months"].values()),
            "0.010 / 0.264 / 0.998",
        ),
        ("top-1 >= 20% in at least one month", f"{len(ever)} = {result['pct_flagged_in_any_month']}%", "926 = 73.4%"),
        (
            "top-1 >= 20% in >= 6 of the last 12 months",
            f"{len(recurrent)} = {result['pct_flagged_recurrent']}%",
            "373 = 29.6%",
        ),
        (
            "companies at 0 / 5 / 6 / 7 / 12 flagged months",
            " / ".join(str(histogram[k]) for k in (0, 5, 6, 7, 12)),
            "398 / 65 / 50 / 73 / 69",
        ),
    ]
    report("concentration", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
