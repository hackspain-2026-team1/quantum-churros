"""Shared helpers for the analysis scripts. Standard library only.

Every script reads the eight challenge CSVs from ``--data <dir>`` and never
writes to it. Scope rules shared by all scripts:

* a transaction is **booked** when ``status != 'pending'`` (blank counts as booked);
* the **window** is the 24 complete months 2024-09..2026-08, judged on ``date``;
* values are converted to EUR with a static table keyed on the ACCOUNT currency
  (``product_id`` -> product file); ``exchange_rate`` is never used. Rows whose
  currency is outside the table, or whose product is in no product file, stay in
  row counts and leave every value aggregate (``eur is None``).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import time
from collections import Counter
from datetime import date
from operator import itemgetter

csv.field_size_limit(1 << 30)

FX_TO_EUR = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.17,
    "CHF": 1.05,
    "MXN": 0.050,
    "DKK": 0.134,
    "SEK": 0.088,
    "NOK": 0.086,
    "PLN": 0.23,
    "CZK": 0.040,
    "AUD": 0.60,
    "NZD": 0.55,
    "CAD": 0.67,
    "BRL": 0.17,
    "COP": 0.00022,
    "CLP": 0.00098,
    "PEN": 0.25,
    "AED": 0.25,
    "JPY": 0.0060,
    "MYR": 0.20,
    "INR": 0.011,
    "ARS": 0.0010,
}

WINDOW_START = "2024-09"
WINDOW_END = "2026-08"

OP_IN = frozenset({"collection", "bulk_collection", "pos_settlement", "cash_settlement"})
OP_OUT = frozenset({"payment", "bulk_payment", "salary", "tax", "social_security", "utility", "fee"})
DEBT_SERVICE = frozenset({"debt_repayment", "interest_charge"})
CASH_TYPES = frozenset({"checking", "saving", "wallet"})
SENTINEL_BALANCE = 9e8


# ---------------------------------------------------------------- months and dates


def month_index(ym: str) -> int:
    """Months since WINDOW_START: '2024-09' -> 0, '2026-08' -> 23."""
    return (int(ym[:4]) - int(WINDOW_START[:4])) * 12 + int(ym[5:7]) - int(WINDOW_START[5:7])


N_MONTHS = month_index(WINDOW_END) + 1


def month_label(index: int) -> str:
    total = int(WINDOW_START[:4]) * 12 + int(WINDOW_START[5:7]) - 1 + index
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_end_ordinal(index: int) -> int:
    nxt = month_label(index + 1)
    return date(int(nxt[:4]), int(nxt[5:7]), 1).toordinal() - 1


_DAY_CACHE: dict[str, tuple[int, int] | None] = {}


def parse_day(text: str) -> tuple[int, int] | None:
    """'2025-02-15 00:00:00' -> (proleptic ordinal, month index); None when unparseable."""
    key = text[:10]
    try:
        return _DAY_CACHE[key]
    except KeyError:
        try:
            parsed = (date(int(key[:4]), int(key[5:7]), int(key[8:10])).toordinal(), month_index(key))
        except ValueError:
            parsed = None
        _DAY_CACHE[key] = parsed
        return parsed


# ---------------------------------------------------------------- readers


def read_csv(path: str, *columns: str):
    """Yield one tuple per record with the requested columns.

    NUL bytes are stripped per physical line (the csv module rejects them) and the
    line iterator is handed to ``csv.reader`` so quoted multi-line descriptions
    still parse as one record.
    """
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(line.replace("\x00", "") for line in handle)
        header = next(reader)
        pick = itemgetter(*[header.index(c) for c in columns])
        width = len(header)
        single = len(columns) == 1
        for record in reader:
            if len(record) == width:
                yield (pick(record),) if single else pick(record)


def load_groups(data: str) -> dict[str, str]:
    """company_id -> group_id."""
    return dict(read_csv(os.path.join(data, "companies.csv"), "company_id", "group_id"))


def load_products(data: str) -> dict[str, tuple[str, str, str]]:
    """product_id -> (company_id, type, currency) over both product files."""
    products = {}
    for name in ("banking_products.csv", "debt_products.csv"):
        for pid, company, kind, currency in read_csv(
            os.path.join(data, name), "product_id", "company_id", "type", "currency"
        ):
            products[pid] = (company, kind, currency)
    return products


def booked_transactions(data: str, *extra: str, in_window: bool = True, stats: Counter | None = None):
    """Yield (company_id, product_id, day, month, amount, category, *extra) for booked rows.

    ``day`` is a date ordinal, ``month`` the month index (0..23 inside the window).
    With ``in_window=False`` rows dated after the window are yielded too (the cash
    back-roll needs them). ``stats`` collects the scope counters.
    """
    stats = stats if stats is not None else Counter()
    columns = ("company_id", "product_id", "date", "amount", "status", "category") + extra
    for record in read_csv(os.path.join(data, "transactions.csv"), *columns):
        stats["records"] += 1
        if record[4] == "pending":
            stats["pending"] += 1
            continue
        when = parse_day(record[2])
        if when is None:
            stats["bad_date"] += 1
            continue
        day, month = when
        if in_window and not 0 <= month < N_MONTHS:
            stats["out_of_window"] += 1
            continue
        stats["in_scope"] += 1
        yield (record[0], record[1], day, month, float(record[3]), record[5]) + record[6:]


def to_eur(amount: float, currency: str | None) -> float | None:
    rate = FX_TO_EUR.get(currency) if currency else None
    return None if rate is None else amount * rate


def month_end_balances(data: str, products: dict, kinds) -> tuple[dict, dict, set]:
    """Back-roll the balance snapshot to every month end of the window.

    balance(T) = balance row - booked amounts in (T, anchor date] + booked amounts in
    (anchor date, T], per product, anchored on the balance row's own date. Integer
    cents of the account currency, so an empty account is exactly 0 and never a
    float-noise negative. Sentinel balances (|x| >= 9e8) are dropped.

    Returns (balances, first_move, unanchored): product -> 24 month-end values in
    cents; product -> first window month with a booked row; products of ``kinds``
    that move but have no usable balance row.
    """
    anchors = {}
    for pid, when, balance in read_csv(os.path.join(data, "balances.csv"), "product_id", "date", "balance"):
        day = parse_day(when)
        if (
            pid in products
            and products[pid][1] in kinds
            and day
            and balance != ""
            and abs(float(balance)) < SENTINEL_BALANCE
        ):
            anchors[pid] = (day[0], round(float(balance) * 100))
    before = {pid: Counter() for pid in anchors}  # month -> cents dated on or before the anchor
    after = {pid: Counter() for pid in anchors}  # month -> cents dated after the anchor
    first_move: dict[str, int] = {}
    unanchored = set()
    for _company, pid, day, month, amount, _category in booked_transactions(data, in_window=False):
        if pid in anchors:
            (before if day <= anchors[pid][0] else after)[pid][month] += round(amount * 100)
            if 0 <= month < N_MONTHS:
                first_move[pid] = min(month, first_move.get(pid, N_MONTHS))
        elif pid in products and products[pid][1] in kinds:
            unanchored.add(pid)
    balances = {
        pid: [
            cents + sum(v for k, v in after[pid].items() if k <= m) - sum(v for k, v in before[pid].items() if k > m)
            for m in range(N_MONTHS)
        ]
        for pid, (_day, cents) in anchors.items()
    }
    return balances, first_move, unanchored


def load_credit_limits(data: str) -> dict[str, float]:
    """product_id -> |granted|, from the balance row when present, else from debt_products."""
    limits = {}
    for pid, granted in read_csv(os.path.join(data, "balances.csv"), "product_id", "granted"):
        if granted != "":
            limits[pid] = abs(float(granted))
    for pid, granted in read_csv(os.path.join(data, "debt_products.csv"), "product_id", "granted"):
        if granted != "" and pid not in limits:
            limits[pid] = abs(float(granted))
    return limits


# ---------------------------------------------------------------- statistics


def quantile(values, q: float) -> float | None:
    """Linear-interpolation quantile (same convention as numpy's default)."""
    data = sorted(values)
    if not data:
        return None
    pos = (len(data) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def median(values) -> float | None:
    return quantile(values, 0.5)


def ranks(values) -> list[float]:
    """Average ranks (ties share the mean rank)."""
    order = sorted(range(len(values)), key=values.__getitem__)
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def pearson(xs, ys) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / math.sqrt(sxx * syy)


def spearman(xs, ys) -> float | None:
    return pearson(ranks(list(xs)), ranks(list(ys)))


def piecewise(anchors, x: float) -> float:
    """Piecewise-linear map through ``anchors`` [(x, y), ...], clamped at both ends."""
    if x <= anchors[0][0]:
        return anchors[0][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:], strict=False):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return anchors[-1][1]


def winsorised_sum(months, multiple: float = 3.0) -> float:
    """Sum of monthly totals, each capped at ``multiple`` x the median month of the same window."""
    cap = multiple * (median(months) or 0.0)
    return sum(min(m, cap) for m in months) if cap > 0 else sum(months)


# ---------------------------------------------------------------- command line and output


def parse_args(description: str, **extra):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--data", required=True, help="folder with the eight challenge CSVs (read-only)")
    parser.add_argument("--json-only", action="store_true", help="print the JSON line and skip the table")
    for flag, options in extra.items():
        parser.add_argument("--" + flag.replace("_", "-"), **options)
    return parser.parse_args()


def rnd(value: float | None, digits: int) -> float | None:
    """round() that lets an undefined statistic (None) through."""
    return None if value is None else round(value, digits)


def pct(numerator: float, denominator: float, digits: int = 2) -> float | None:
    return round(100.0 * numerator / denominator, digits) if denominator else None


def report(name: str, started: float, result: dict, table: list[tuple], json_only: bool = False) -> None:
    """Print one compact JSON line, then a human table of (metric, value, note) rows."""
    result = {"script": name, "runtime_s": round(time.time() - started, 1), **result}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    if json_only or not table:
        return
    rows = [tuple("" if c is None else str(c) for c in row) for row in table]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    print()
    for n, row in enumerate(rows):
        print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
        if n == 0:
            print("  ".join("-" * w for w in widths))
