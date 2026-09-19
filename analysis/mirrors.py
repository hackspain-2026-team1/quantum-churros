"""Intra-group mirror netting: how much of the measured outflow is internal money movement.

Usage: python3 analysis/mirrors.py --data <dir>

Three recipes run on the same booked, in-window rows:

* **shipped** (the engine recipe): first drop same-account reversals (same product,
  opposite sign, equal cents, within 1 day); then pair rows of the same group, same
  account currency, equal integer cents, opposite sign, different product, at least
  100 EUR, within 1 day, or within 3 days when the earlier leg falls on a Friday or
  Saturday. Nearest date first, 1:1, both legs in the same calendar month (a closed
  month never changes when later rows arrive); what that last rule leaves in is
  reported apart.
* **no_reversal_step**: the shipped mirror pairing without the reversal step, to show
  how much value the two steps compete for.
* **flat2** (the recipe the headline numbers were first measured with): different
  product, flat window of 2 days, no amount floor, no reversal step.

Each recipe is re-run as two placebos with fresh state: a date placebo (legs 9 to 11
days apart) and an amount placebo (the negative leg must equal 1.01 x the positive
leg to the cent, exact-cent matches excluded). Ties inside a bucket are broken by
(date, file order); buckets are 1x1 in the vast majority of cases.
"""

from __future__ import annotations

import time
from array import array
from collections import Counter, defaultdict
from datetime import date

from _common import (
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

SLOTS = 1 << 20  # room for the (group, currency) or product index packed under the cents
PAYMENT_COLLECTION = ("payment", "collection", "bulk_payment", "bulk_collection")


def load(data: str):
    groups, products = load_groups(data), load_products(data)
    intern: dict = {}
    slot, prod, comp, cat = array("i"), array("i"), array("i"), array("i")
    cents, day, eur = array("q"), array("i"), array("d")
    stats: Counter = Counter()
    for company, product, d, _month, amount, category in booked_transactions(data, stats=stats):
        info = products.get(product)
        currency = info[2] if info else None
        value = to_eur(abs(amount), currency)
        if info is None:
            stats["orphan_product_rows"] += 1
        elif value is None:
            stats["fx_excluded_rows"] += 1
        # a row without an account currency cannot assert "same currency": slot -1 never pairs
        group = groups.get(company)
        slot.append(intern.setdefault(("s", group, currency), len(intern)) if currency and group else -1)
        prod.append(intern.setdefault(("p", product), len(intern)))
        comp.append(intern.setdefault(("c", company), len(intern)))
        cat.append(intern.setdefault(("k", category), len(intern)))
        cents.append(round(amount * 100))
        day.append(d)
        eur.append(-1.0 if value is None else value)  # -1 marks "no EUR value"
    categories = {v: k[1] for k, v in intern.items() if k[0] == "k"}
    return stats, categories, slot, prod, comp, cat, cents, day, eur


_MONTHS: dict[int, int] = {}


def month_of(ordinal: int) -> int:
    if ordinal not in _MONTHS:
        when = date.fromordinal(ordinal)
        _MONTHS[ordinal] = when.year * 12 + when.month
    return _MONTHS[ordinal]


def find_pairs(
    rows, key_of, target_keys, cents, day, prod, gaps, bridge_from=None, same_product=False, same_month=False
):
    """Greedy 1:1 pairing of negative rows with positive rows, nearest date first.

    ``key_of(i)`` buckets a row; ``target_keys(key)`` lists the negative-side keys a
    positive bucket may pair with (itself for exact-cent matching). ``gaps`` are the
    signed day offsets positive-minus-negative, tried in order. From ``bridge_from``
    days on, a gap is only allowed when the earlier leg is a Friday or a Saturday.
    ``same_month`` refuses a pair whose legs fall in different calendar months.
    """
    negs, poss = defaultdict(list), defaultdict(list)
    for i in rows:
        if cents[i]:
            (negs if cents[i] < 0 else poss)[key_of(i)].append(i)
    taken, pairs = set(), []
    for key in sorted(poss):
        candidates = [i for k in target_keys(key) for i in negs.get(k, ()) if i not in taken]
        if not candidates:
            continue
        by_day = defaultdict(list)
        for j in sorted(poss[key], key=lambda j: (day[j], j)):
            by_day[day[j]].append(j)
        free = sorted(candidates, key=lambda i: (day[i], i))
        for gap in gaps:
            rest = []
            for i in free:
                waiting = by_day.get(day[i] + gap)
                hit = None
                if same_month and gap and month_of(day[i]) != month_of(day[i] + gap):
                    waiting = None
                if waiting and (
                    bridge_from is None
                    or abs(gap) < bridge_from
                    or (min(day[i], day[i] + gap) + 6) % 7 in (4, 5)  # ordinal weekday, Monday = 0
                ):
                    hit = next((j for j in waiting if (prod[j] == prod[i]) == same_product), None)
                if hit is None:
                    rest.append(i)
                else:
                    waiting.remove(hit)
                    taken.add(i)
                    pairs.append((i, hit))
            free = rest
    return pairs


def exact(key):
    return (key,)


def one_percent_more(key):
    """Negative-side keys whose cents sit within 1 cent of 1.01 x the positive cents."""
    c, slot = divmod(key, SLOTS)
    lo, hi = 1.01 * c - 1, 1.01 * c + 1
    return [n * SLOTS + slot for n in range(int(lo), int(hi) + 2) if lo <= n <= hi and n != c]


def measure(cols, categories, *, gaps, bridge_from, floor_eur, reversals, same_month=False):
    slot, prod, comp, cat, cents, day, eur = cols
    n = len(cents)
    out_rows = sum(1 for i in range(n) if cents[i] < 0)
    out_value = sum(eur[i] for i in range(n) if cents[i] < 0 and eur[i] >= 0)

    def share(pairs):
        value = sum(eur[i] for i, _ in pairs if eur[i] >= 0)
        return {
            "pairs": len(pairs),
            "pct_outflow_rows": pct(len(pairs), out_rows),
            "pct_outflow_value": pct(value, out_value, 3),
        }

    def by_product(i):
        return abs(cents[i]) * SLOTS + prod[i]

    def by_group_currency(i):
        return abs(cents[i]) * SLOTS + slot[i]

    def net(same_month):
        """(reversal pairs, mirror pairs, rows still in the pool when mirrors are paired)."""
        undone, pool = [], range(n)
        if reversals:
            undone = find_pairs(
                pool, by_product, exact, cents, day, prod, [0, 1, -1], same_product=True, same_month=same_month
            )
            gone = {i for pair in undone for i in pair}
            pool = [i for i in pool if i not in gone]
        pool = [i for i in pool if slot[i] >= 0 and (floor_eur <= 0 or eur[i] >= floor_eur)]
        found = find_pairs(pool, by_group_currency, exact, cents, day, prod, gaps, bridge_from, same_month=same_month)
        return undone, found, pool

    result = {}
    undone, pairs, pool = net(same_month)
    if reversals:
        result["reversals"] = share(undone)
        result["reversals_placebo_date_9_11d"] = share(
            find_pairs(range(n), by_product, exact, cents, day, prod, [9, -9, 10, -10, 11, -11], same_product=True)
        )
    result["mirrors"] = share(pairs)
    result["netted_total"] = share(undone + pairs)
    if same_month:
        loose = share([pair for found in net(False)[:2] for pair in found])
        result["left_in_by_same_month_rule"] = {
            "pairs": loose["pairs"] - result["netted_total"]["pairs"],
            "pct_outflow_value": round(loose["pct_outflow_value"] - result["netted_total"]["pct_outflow_value"], 3),
        }
    result["placebo_date_9_11d"] = share(
        find_pairs(pool, by_group_currency, exact, cents, day, prod, [9, -9, 10, -10, 11, -11])
    )
    result["placebo_amount_x1.01"] = share(
        find_pairs(pool, by_group_currency, one_percent_more, cents, day, prod, gaps, bridge_from)
    )

    legs = Counter(categories[cat[i]] for pair in pairs for i in pair)
    total = sum(legs.values())
    result["mirror_rows_category_pct"] = {
        "transfer": pct(legs["transfer"], total),
        "payment_collection_incl_bulk": pct(sum(legs[c] for c in PAYMENT_COLLECTION), total),
        "uncategorised_dash": pct(legs["-"], total),
        "other": pct(total - legs["transfer"] - legs["-"] - sum(legs[c] for c in PAYMENT_COLLECTION), total),
    }
    result["mirror_pairs_crossing_companies_pct"] = pct(sum(1 for i, j in pairs if comp[i] != comp[j]), len(pairs))
    result["mirror_value_crossing_companies_pct"] = pct(
        sum(eur[i] for i, j in pairs if comp[i] != comp[j] and eur[i] >= 0),
        sum(eur[i] for i, _ in pairs if eur[i] >= 0),
    )

    # per company: share of outflow that is netted, and what netting does to operating inflow
    out_all, out_netted, in_raw, in_netted = Counter(), Counter(), Counter(), Counter()
    for i in range(n):
        if eur[i] < 0:
            continue
        if cents[i] < 0:
            out_all[comp[i]] += eur[i]
        elif cents[i] > 0 and categories[cat[i]] in OP_IN:
            in_raw[comp[i]] += eur[i]
    for i, j in undone + pairs:
        if eur[i] >= 0:
            out_netted[comp[i]] += eur[i]
        if eur[j] >= 0 and categories[cat[j]] in OP_IN:
            in_netted[comp[j]] += eur[j]
    result["companies_with_outflow_value"] = sum(1 for v in out_all.values() if v > 0)
    result["companies_over_50pct_outflow_netted"] = sum(
        1 for c, v in out_all.items() if v > 0 and out_netted[c] / v > 0.5
    )
    kept = [max(0.0, v - in_netted[c]) / v for c, v in in_raw.items() if v > 0]
    result["operating_inflow_retained"] = {
        "companies": len(kept),
        **{f"p{int(q * 100)}": rnd(quantile(kept, q), 3) for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
        "lose_over_30pct": sum(1 for k in kept if k < 0.7),
        "net_to_exactly_zero": sum(1 for k in kept if k == 0.0),
    }
    large = sum(eur[i] for i in range(n) if cents[i] < 0 and eur[i] >= 100_000)
    result["outflow"] = {
        "rows": out_rows,
        "value_eur_m": round(out_value / 1e6),
        "pct_value_in_rows_of_100k_eur_or_more": pct(large, out_value, 1),
    }
    return result


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    stats, categories, *cols = load(args.data)
    engine_gaps = [0, 1, -1, 2, -2, 3, -3]
    runs = {
        "shipped": measure(
            cols, categories, gaps=engine_gaps, bridge_from=2, floor_eur=100.0, reversals=True, same_month=True
        ),
        "no_reversal_step": measure(
            cols, categories, gaps=engine_gaps, bridge_from=2, floor_eur=100.0, reversals=False, same_month=True
        ),
        "flat2": measure(cols, categories, gaps=[0, 1, -1, 2, -2], bridge_from=None, floor_eur=0.0, reversals=False),
    }

    def row(label, path, validated=""):
        cells = []
        for run in runs.values():
            for step in path:
                run = run.get(step, "-") if isinstance(run, dict) else "-"
            cells.append(run)
        return (label, *cells, validated)

    table = [
        ("metric", "shipped", "shipped, no reversal step", "flat +-2d", "validated (flat +-2d)"),
        ("booked in-window rows", *[stats["in_scope"]] * 3, "2,540,630"),
        row("outflow rows", ("outflow", "rows"), "1,493,806"),
        row("outflow value, EUR m", ("outflow", "value_eur_m"), "125,200"),
        row("  % of it in rows of 100k EUR or more", ("outflow", "pct_value_in_rows_of_100k_eur_or_more"), "95"),
        row("reversal pairs (same account)", ("reversals", "pairs")),
        row("reversals: % of outflow value", ("reversals", "pct_outflow_value")),
        row("reversals, date placebo 9-11d: % of value", ("reversals_placebo_date_9_11d", "pct_outflow_value")),
        row("mirror pairs", ("mirrors", "pairs"), "98,231"),
        row("mirrors: % of outflow rows", ("mirrors", "pct_outflow_rows"), "6.58"),
        row("mirrors: % of outflow value", ("mirrors", "pct_outflow_value"), "46.58"),
        row("reversals + mirrors: % of outflow rows", ("netted_total", "pct_outflow_rows")),
        row("reversals + mirrors: % of outflow value", ("netted_total", "pct_outflow_value")),
        row("left in by the same-month rule: pairs", ("left_in_by_same_month_rule", "pairs")),
        row("left in by the same-month rule: % of outflow value", ("left_in_by_same_month_rule", "pct_outflow_value")),
        row("date placebo 9-11d: % of rows", ("placebo_date_9_11d", "pct_outflow_rows"), "1.24"),
        row("date placebo 9-11d: % of value", ("placebo_date_9_11d", "pct_outflow_value"), "1.90"),
        row("amount placebo x1.01: % of rows", ("placebo_amount_x1.01", "pct_outflow_rows"), "0.18"),
        row("amount placebo x1.01: % of value", ("placebo_amount_x1.01", "pct_outflow_value"), "0.001"),
        row("mirror rows labelled transfer, %", ("mirror_rows_category_pct", "transfer"), "33.66"),
        row(
            "mirror rows labelled payment/collection, %",
            ("mirror_rows_category_pct", "payment_collection_incl_bulk"),
            "42.48",
        ),
        row("mirror rows labelled '-', %", ("mirror_rows_category_pct", "uncategorised_dash"), "14.24"),
        row("mirror pairs crossing companies, %", ("mirror_pairs_crossing_companies_pct",), "60"),
        row("  ... share of mirror value", ("mirror_value_crossing_companies_pct",)),
        row("companies with >50% of outflow netted", ("companies_over_50pct_outflow_netted",), "142"),
        row("operating inflow retained, p25", ("operating_inflow_retained", "p25"), "0.678"),
        row("operating inflow retained, p50", ("operating_inflow_retained", "p50"), "0.913"),
        row("companies losing >30% of operating inflow", ("operating_inflow_retained", "lose_over_30pct"), "337"),
        row("companies netting to exactly 0 inflow", ("operating_inflow_retained", "net_to_exactly_zero")),
    ]
    report("mirrors", started, {"scope": dict(stats), **runs}, table, args.json_only)


if __name__ == "__main__":
    main()
