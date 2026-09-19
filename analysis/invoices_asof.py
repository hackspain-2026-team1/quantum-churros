"""Invoices as-of: late settlements hidden behind status 'paid', ERP stamping, scorability.

Usage: python3 analysis/invoices_asof.py --data <dir>

Only ``document_type == 'invoice'``. An invoice is **settled** when ``status == 'paid'``
and ``pending_amount == 0``; its settlement date is ``payment_date``. AP = amount < 0,
AR = amount > 0. A row is **ERP-stamped** when ``due_date == issuance_date`` and the
settlement date equals the due date (the ERP wrote the dates, nobody behaved).
EUR by static FX on the invoice currency. The late-settlement counts use the whole
file, as validated. The two scorability gates read the last month end T as the engine
does: status ``cancel`` and impossible dates (due or payment before issuance) are
dropped, and a payment dated after T has not happened yet.

* **as-of gate** (shipped): unstamped invoices with due_date in (T - 90d, T]; needs
  >= 10 of them, Kish effective n >= 5 on EUR weights, stamped share < 50%.
* **due-cohort gate** (the design it replaced): invoices due in the month before the
  last one; needs >= 10 settlements within due + 30d and a stamped share < 50% over
  the six due-months ending there.
"""

from __future__ import annotations

import os
import time
from collections import Counter, defaultdict

from _common import N_MONTHS, load_groups, month_end_ordinal, parse_args, parse_day, pct, read_csv, report, to_eur

BANDS = ((15, "1-15d"), (30, "16-30d"), (60, "31-60d"), (90, "61-90d"), (10**9, ">90d"))
COLUMNS = (
    "company_id",
    "document_type",
    "issuance_date",
    "due_date",
    "payment_date",
    "amount",
    "pending_amount",
    "currency",
    "status",
)


def main() -> None:
    args = parse_args(__doc__.splitlines()[0])
    started = time.time()
    groups = load_groups(args.data)
    t_end = month_end_ordinal(N_MONTHS - 1)
    last, cohort_months = N_MONTHS - 1, range(N_MONTHS - 7, N_MONTHS - 1)

    settled, late, stamped, hygiene = Counter(), Counter(), Counter(), Counter()
    late_band, late_eur = defaultdict(Counter), defaultdict(Counter)
    groups_with_invoices = set()
    asof = defaultdict(lambda: {"weights": [], "stamped": 0})  # (group, side) -> due in (t-90d, t]
    cohort = defaultdict(lambda: {"due_last": 0.0, "settled": 0, "rows": 0, "stamped": 0})
    records = invoices = 0

    for company, doc, issue, due, paid, amount, pending, currency, status in read_csv(
        os.path.join(args.data, "invoices.csv"), *COLUMNS
    ):
        records += 1
        if doc != "invoice":
            continue
        invoices += 1
        group = groups.get(company)
        groups_with_invoices.add(group)
        value = float(amount)
        side = "AP" if value < 0 else "AR"
        due_day, issue_day, pay_day = parse_day(due), parse_day(issue), parse_day(paid)
        is_settled = status == "paid" and float(pending or 0) == 0 and pay_day is not None
        is_stamped = bool(
            is_settled and due_day and issue_day and due_day[0] == issue_day[0] and pay_day[0] == due_day[0]
        )
        eur = to_eur(abs(value), currency)

        if is_settled and due_day and value != 0:
            settled[side] += 1
            stamped[side] += is_stamped
            days_late = pay_day[0] - due_day[0]
            if days_late > 0:
                late[side] += 1
                band = next(name for limit, name in BANDS if days_late <= limit)
                late_band[side][band] += 1
                late_eur[side][band] += eur or 0.0
                hygiene[side + "_late_paid_after_extraction"] += pay_day[0] > t_end + 1
                hygiene[side + "_late_due_before_issue"] += bool(issue_day and due_day[0] < issue_day[0])

        # scorability at the last month end, engine hygiene applied
        impossible = issue_day and (
            (due_day and due_day[0] < issue_day[0]) or (is_settled and pay_day[0] < issue_day[0])
        )
        if due_day is None or value == 0 or status == "cancel" or impossible:
            continue
        key = (group, side)
        settled_by_t = is_settled and pay_day[0] <= t_end
        stamped_by_t = bool(settled_by_t and is_stamped)
        if t_end - 90 < due_day[0] <= t_end:
            if stamped_by_t:
                asof[key]["stamped"] += 1
            elif eur:
                asof[key]["weights"].append(eur)
        if due_day[1] in cohort_months:
            c = cohort[key]
            c["rows"] += 1
            c["stamped"] += stamped_by_t
            c["settled"] += bool(is_settled and pay_day[0] <= min(due_day[0] + 30, t_end + 1))
            if due_day[1] == last - 1 and eur:
                c["due_last"] += eur

    all_groups = set(groups.values())
    scorable, reasons = {}, {}
    for side in ("AP", "AR"):
        ok_asof = 0
        why = Counter()
        for g in all_groups:
            w, n_stamped = asof[(g, side)]["weights"], asof[(g, side)]["stamped"]
            kish = sum(w) ** 2 / sum(x * x for x in w) if w else 0.0
            total = len(w) + n_stamped
            if g not in groups_with_invoices:
                why["no_invoices"] += 1
            elif total == 0:
                why["nothing_due_in_window"] += 1
            elif n_stamped / total >= 0.5:
                why["stamped_share"] += 1
            elif len(w) < 10 or kish < 5:
                why["too_few_or_concentrated"] += 1
            else:
                ok_asof += 1
        ok_cohort = sum(
            1
            for g in all_groups
            if (c := cohort[(g, side)])["due_last"] > 0 and c["settled"] >= 10 and c["stamped"] / c["rows"] < 0.5
        )
        scorable[side] = {"as_of_gate": ok_asof, "due_cohort_gate": ok_cohort}
        reasons[side] = dict(why)

    result = {
        "invoice_records": records,
        "document_type_invoice": invoices,
        "settled": dict(settled),
        "settled_late": dict(late),
        "pct_settled_late": {s: pct(late[s], settled[s], 1) for s in settled},
        "late_by_band": {s: dict(late_band[s]) for s in late_band},
        "late_eur_m_by_band": {s: {b: round(v / 1e6, 1) for b, v in late_eur[s].items()} for s in late_eur},
        "erp_stamped_settled_rows": dict(stamped),
        "pct_settled_rows_stamped": {s: pct(stamped[s], settled[s], 1) for s in settled},
        "pct_late_excluding_stamped": {s: pct(late[s], settled[s] - stamped[s], 1) for s in settled},
        "late_rows_hygiene": dict(hygiene),
        "groups_without_invoices": len(all_groups - groups_with_invoices),
        "groups_scorable_at_last_month": scorable,
        "as_of_gate_not_scorable_reasons": reasons,
    }
    table = [("metric", "AP", "AR", "validated AP / AR")]
    table.append(("settled invoices", settled["AP"], settled["AR"], "345,467 / 207,867"))
    table.append(("marked paid, settled after due date", late["AP"], late["AR"], "121,989 / 78,153"))
    table.append(("  % of settled", result["pct_settled_late"]["AP"], result["pct_settled_late"]["AR"], "35.3 / 37.6"))
    for _, band in BANDS:
        table.append(
            (
                f"  late {band}: rows (EUR m)",
                *[f"{late_band[s][band]} ({late_eur[s][band] / 1e6:.1f})" for s in ("AP", "AR")],
                "",
            )
        )
    table.append(
        (
            "  late rows with payment_date after extraction",
            hygiene["AP_late_paid_after_extraction"],
            hygiene["AR_late_paid_after_extraction"],
            "4,002 / 2,756",
        )
    )
    table.append(
        (
            "  late rows with due_date before issuance",
            hygiene["AP_late_due_before_issue"],
            hygiene["AR_late_due_before_issue"],
            "3,924 / 1,771",
        )
    )
    table.append(("ERP-stamped settled rows", stamped["AP"], stamped["AR"], "68,706 / 56,646"))
    table.append(
        (
            "  % of settled rows",
            result["pct_settled_rows_stamped"]["AP"],
            result["pct_settled_rows_stamped"]["AR"],
            "20 / 27",
        )
    )
    table.append(
        (
            "  % late once stamped rows are excluded",
            result["pct_late_excluding_stamped"]["AP"],
            result["pct_late_excluding_stamped"]["AR"],
            "44.1 / 51.7",
        )
    )
    table.append(
        (
            "groups scorable at 2026-08, due-cohort gate",
            scorable["AP"]["due_cohort_gate"],
            scorable["AR"]["due_cohort_gate"],
            "98 / 52",
        )
    )
    table.append(
        (
            "groups scorable at 2026-08, as-of gate (shipped)",
            scorable["AP"]["as_of_gate"],
            scorable["AR"]["as_of_gate"],
            "",
        )
    )
    table.append(("groups with no invoices at all", result["groups_without_invoices"], "", "83"))
    report("invoices_asof", started, result, table, args.json_only)


if __name__ == "__main__":
    main()
