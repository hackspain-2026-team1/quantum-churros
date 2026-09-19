"""Scope: record counts and the rows every other script leaves out, and why.

Usage: python3 analysis/scope.py --data <dir>

Counts the traps a naive reader falls into: NUL bytes (the csv module rejects them),
quoted descriptions that span several physical lines (line-based tools over-count),
pending rows, the single day after the 24-month window, rows whose product is in no
product file (no account currency) and rows in currencies outside the static FX table
(both stay in row counts and leave value aggregates).
"""

from __future__ import annotations

import os
import time
from collections import Counter

from _common import FX_TO_EUR, N_MONTHS, load_products, parse_args, parse_day, pct, read_csv, report


def physical(path: str) -> tuple[int, int]:
    """(physical lines, NUL bytes) of a file, read as bytes."""
    lines = nuls = 0
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 24):
            lines += chunk.count(b"\n")
            nuls += chunk.count(b"\x00")
    return lines, nuls


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    products = load_products(args.data)
    tx_path, inv_path = os.path.join(args.data, "transactions.csv"), os.path.join(args.data, "invoices.csv")
    tx_lines, tx_nuls = physical(tx_path)

    c: Counter = Counter()
    outside_currencies = Counter()
    for status, when, product, description in read_csv(tx_path, "status", "date", "product_id", "description"):
        c["records"] += 1
        c["multi_line_descriptions"] += "\n" in description
        if status == "pending":
            c["pending"] += 1
            continue
        c["blank_status_kept_as_booked"] += status == ""
        day = parse_day(when)
        if day is None or not 0 <= day[1] < N_MONTHS:
            c["booked_outside_window"] += 1
            continue
        c["booked_in_window"] += 1
        info = products.get(product)
        if info is None:
            c["product_in_no_product_file"] += 1
        elif info[2] not in FX_TO_EUR:
            c["currency_outside_fx_table"] += 1
            outside_currencies[info[2]] += 1
    invoice_records = sum(1 for _ in read_csv(inv_path, "operation_id"))

    result = {
        "transaction_records": c["records"],
        "transaction_physical_lines": tx_lines,
        "extra_physical_lines_from_quoted_newlines": tx_lines - c["records"] - 1,
        "records_with_a_multi_line_description": c["multi_line_descriptions"],
        "nul_bytes_in_transactions": tx_nuls,
        "invoice_records": invoice_records,
        "pending": c["pending"],
        "blank_status_kept_as_booked": c["blank_status_kept_as_booked"],
        "booked_outside_window": c["booked_outside_window"],
        "booked_in_window": c["booked_in_window"],
        "product_in_no_product_file": c["product_in_no_product_file"],
        "orphan_product_share_pct": pct(c["product_in_no_product_file"], c["booked_in_window"], 3),
        "currency_outside_fx_table": c["currency_outside_fx_table"],
        "fx_excluded_share_pct": pct(c["currency_outside_fx_table"], c["booked_in_window"], 3),
        "currencies_outside_fx_table": dict(outside_currencies.most_common()),
    }
    table = [
        ("metric", "measured", "validated"),
        ("transaction records", c["records"], "2,556,437"),
        ("  physical lines beyond one per record", result["extra_physical_lines_from_quoted_newlines"], "74,512"),
        ("  records whose description spans several lines", c["multi_line_descriptions"], ""),
        ("  NUL bytes", tx_nuls, "present"),
        ("invoice records", invoice_records, "897,894"),
        ("pending rows (excluded)", c["pending"], "6,579"),
        ("blank status (kept as booked)", c["blank_status_kept_as_booked"], "29,839"),
        ("booked rows outside the window (2026-09-01)", c["booked_outside_window"], "9,228"),
        ("booked in-window rows", c["booked_in_window"], "2,540,630"),
        ("  product in no product file", c["product_in_no_product_file"], "1,313"),
        ("  currency outside the static FX table", c["currency_outside_fx_table"], "11,969"),
    ]
    report("scope", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
