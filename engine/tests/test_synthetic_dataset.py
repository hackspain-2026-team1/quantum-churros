"""The synthetic dataset must look like the real files and hold every trap."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pytest
from xray_engine import io
from xray_engine.industry_classifier import classify_dataset


def _records(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _tree_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.iterdir()):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_headers_match_the_reader_schemas(synthetic, datasets) -> None:
    assert set(datasets.headers) == set(io.CSV_FILES)
    for name, header in datasets.headers.items():
        assert list(io.SCHEMAS[name.removesuffix(".csv")]) == header
        with (synthetic.path / name).open(newline="", encoding="utf-8") as source:
            assert next(csv.reader(source)) == header


@pytest.mark.dataset
def test_headers_match_the_real_files(real_data_dir, datasets) -> None:
    for name, header in datasets.headers.items():
        with (real_data_dir / name).open(newline="", encoding="utf-8") as source:
            assert next(csv.reader(source)) == header


def test_generator_is_deterministic_and_small(tmp_path, datasets, synthetic) -> None:
    again = datasets.make(tmp_path / "again", n_groups=6, seed=7)
    assert _tree_hash(again.path) == _tree_hash(synthetic.path)
    assert again.mirror_pairs == synthetic.mirror_pairs
    other = datasets.make(tmp_path / "other", n_groups=6, seed=8)
    assert _tree_hash(other.path) != _tree_hash(synthetic.path)
    assert synthetic.row_counts["transactions.csv"] < 20_000
    assert synthetic.row_counts["groups.csv"] == 6


def test_more_groups_keep_the_archetypes(tmp_path, datasets, synthetic) -> None:
    bigger = datasets.make(tmp_path / "bigger", n_groups=9, seed=7)
    assert len(bigger.group_ids) == 9
    assert bigger.group_ids[:6] == synthetic.group_ids
    assert bigger.swept_company_id == synthetic.swept_company_id
    with pytest.raises(ValueError):
        datasets.make(tmp_path / "tiny", n_groups=3)


def test_physical_lines_exceed_records(synthetic) -> None:
    path = synthetic.path / "transactions.csv"
    records = _records(path)
    assert len(records) == synthetic.row_counts["transactions.csv"]
    assert len(path.read_text(encoding="utf-8").splitlines()) - 1 > len(records)
    by_id = {row["transaction_id"]: row for row in records}
    assert "\n" in by_id[synthetic.newline_transaction_id]["description"]


def test_statuses_and_pending_rows(synthetic) -> None:
    records = {row["transaction_id"]: row for row in _records(synthetic.path / "transactions.csv")}
    assert Counter(row["status"] for row in records.values()).keys() == {"booked", "", "pending"}
    assert len(synthetic.pending_transaction_ids) == 4
    assert all(records[item]["status"] == "pending" for item in synthetic.pending_transaction_ids)
    assert all(records[item]["status"] == "" for item in synthetic.blank_status_transaction_ids)


def test_mirror_pairs_are_the_only_opposite_twins(synthetic, datasets) -> None:
    records = _records(synthetic.path / "transactions.csv")
    companies = {row["company_id"]: row["group_id"] for row in _records(synthetic.path / "companies.csv")}
    by_id = {row["transaction_id"]: row for row in records}
    scopes = Counter(pair.scope for pair in synthetic.mirror_pairs)
    assert scopes["intra_company"] > 20 and scopes["intra_group"] > 100
    mislabelled = [pair for pair in synthetic.mirror_pairs if pair.out_category == "payment"]
    assert mislabelled and all(pair.in_category == "collection" for pair in mislabelled)
    assert {pair.day_offset for pair in synthetic.mirror_pairs} == {-2, -1, 0, 1, 2}
    assert sum(pair.ambiguous for pair in synthetic.mirror_pairs) == 2
    for pair in synthetic.mirror_pairs:
        out_leg, in_leg = by_id[pair.out_id], by_id[pair.in_id]
        assert datasets.to_cents(out_leg["amount"]) == -pair.amount_cents
        assert datasets.to_cents(in_leg["amount"]) == pair.amount_cents
        assert out_leg["product_id"] != in_leg["product_id"]
        assert out_leg["date"][:7] == in_leg["date"][:7]
        same_company = out_leg["company_id"] == in_leg["company_id"]
        assert pair.scope == ("intra_company" if same_company else "intra_group")
    # no accidental twin: every (group, month, |amount|) outside the pairs is unique
    paired = {pair.out_id for pair in synthetic.mirror_pairs} | {
        pair.in_id for pair in synthetic.mirror_pairs
    }
    eur = {row["product_id"] for row in _records(synthetic.path / "banking_products.csv") if row["currency"] == "EUR"}
    eur |= {row["product_id"] for row in _records(synthetic.path / "debt_products.csv")}
    seen: dict[tuple, str] = {}
    for row in records:
        if row["transaction_id"] in paired or row["product_id"] not in eur:
            continue
        key = (companies[row["company_id"]], row["date"][:7], abs(datasets.to_cents(row["amount"])))
        assert key not in seen, (key, seen.get(key), row["transaction_id"])
        seen[key] = row["transaction_id"]


def test_dash_rows_carry_debt_narratives(synthetic, params) -> None:
    import re

    records = {row["transaction_id"]: row for row in _records(synthetic.path / "transactions.csv")}
    rules = {rule.label: rule for rule in params.dash_rules}
    assert len(synthetic.dash_installment_ids) == 12
    for transaction_id in synthetic.dash_installment_ids:
        row = records[transaction_id]
        assert row["category"] == "-" and row["amount"].startswith("-")
        assert re.search(rules["debt_installment"].pattern, row["description"], re.IGNORECASE)
    for transaction_id in synthetic.dash_drawdown_ids:
        row = records[transaction_id]
        assert row["category"] == "-" and not row["amount"].startswith("-")
        assert re.search(rules["debt_drawdown"].pattern, row["description"], re.IGNORECASE)
    for transaction_id in synthetic.dash_unrecoverable_ids[:20]:
        description = records[transaction_id]["description"]
        assert not any(re.search(rule.pattern, description, re.IGNORECASE) for rule in params.dash_rules)


def test_currencies_lines_and_balances(synthetic, datasets, params) -> None:
    banking = {row["product_id"]: row for row in _records(synthetic.path / "banking_products.csv")}
    debt = {row["product_id"]: row for row in _records(synthetic.path / "debt_products.csv")}
    balances = {row["product_id"]: row for row in _records(synthetic.path / "balances.csv")}
    companies = {row["company_id"]: row for row in _records(synthetic.path / "companies.csv")}
    assert banking[synthetic.usd_product_id]["currency"] == "USD"
    assert companies[synthetic.usd_company_id]["currency"] == "EUR"
    assert banking[synthetic.fx_excluded_product_id]["currency"] not in params.fx.rates
    line = balances[synthetic.credit_line_product_id]
    assert debt[synthetic.credit_line_product_id]["type"] == "lineofcredit"
    assert datasets.to_cents(line["granted"]) == -synthetic.credit_line_granted_cents
    assert datasets.to_cents(line["balance"]) == -synthetic.credit_line_drawn_cents
    assert datasets.to_cents(line["liquidity"]) == (
        synthetic.credit_line_granted_cents - synthetic.credit_line_drawn_cents
    )
    sentinel = datasets.to_cents(balances[synthetic.sentinel_product_id]["balance"])
    assert abs(sentinel) >= params.flows.sentinel_abs_balance * 100
    assert balances[synthetic.own_date_anchor_product_id]["date"].startswith("2026-08-28")
    assert set(balances) == set(banking) | set(debt)
    # every cash anchor closes the ledger: final balance = last month end + rows after it
    records = _records(synthetic.path / "transactions.csv")
    after: dict[str, int] = defaultdict(int)
    for row in records:
        if row["status"] != "pending" and row["date"][:10] > "2026-08-31":
            after[row["product_id"]] += datasets.to_cents(row["amount"])
    for product_id, row in balances.items():
        key = (product_id, synthetic.last_month)
        if product_id == synthetic.sentinel_product_id or key not in synthetic.month_end_balance_cents:
            continue
        expected = synthetic.month_end_balance_cents[key] + after[product_id]
        assert datasets.to_cents(row["balance"]) == expected, product_id


def test_perimeter_traps(synthetic) -> None:
    group = synthetic.late_member_group_id
    first = synthetic.company_first_month
    assert synthetic.late_member_company_id in synthetic.companies_by_group[group]
    assert first[synthetic.late_member_company_id] == date(2025, 2, 1)
    assert min(first[item] for item in synthetic.companies_by_group[group]) == synthetic.first_month
    assert synthetic.product_first_month[synthetic.mid_window_product_id] == date(2025, 6, 1)
    assert first[synthetic.mid_window_company_id] == synthetic.first_month
    assert first[synthetic.short_history_company_id] == date(2026, 4, 1)
    records = _records(synthetic.path / "transactions.csv")
    assert max(row["date"] for row in records).startswith(synthetic.as_of.isoformat())


def test_invoice_regimes(synthetic) -> None:
    invoices = _records(synthetic.path / "invoices.csv")
    companies = {row["company_id"]: row["group_id"] for row in _records(synthetic.path / "companies.csv")}
    by_id = {row["operation_id"]: row for row in invoices}
    groups_with_invoices = {companies[row["company_id"]] for row in invoices}
    assert synthetic.no_invoice_group_id not in groups_with_invoices
    assert synthetic.short_history_group_id not in groups_with_invoices
    stamped = [row for row in invoices if row["company_id"] == synthetic.stamped_company_id]
    assert stamped and all(row["due_date"] == row["issuance_date"] for row in stamped)
    assert all(row["payment_date"] == row["due_date"] for row in stamped)
    assert {row["status"] for row in stamped} == {"paid", "overdue"}
    for operation_id in synthetic.late_ap_invoice_ids + synthetic.late_ar_invoice_ids:
        row = by_id[operation_id]
        assert row["status"] == "paid" and row["pending_amount"] == "0"
        assert row["payment_date"] > row["due_date"]
    for operation_id in synthetic.unpaid_ap_invoice_ids + synthetic.unpaid_ar_invoice_ids:
        row = by_id[operation_id]
        assert row["status"] in ("overdue", "pending") and row["pending_amount"] == row["amount"]
        assert row["payment_date"] == row["due_date"]  # expected date, not a settlement
    assert all(by_id[item]["amount"].startswith("-") for item in synthetic.late_ap_invoice_ids)
    assert len(synthetic.late_ap_invoice_ids) > 20 and len(synthetic.unpaid_ar_invoice_ids) > 5
    kinds = {by_id[item]["document_type"] for item in synthetic.ignored_invoice_ids}
    assert {"paymentDocument", "note", "invoiceGroup"} <= kinds


def test_debt_coverage(synthetic) -> None:
    companies = {row["company_id"]: row["group_id"] for row in _records(synthetic.path / "companies.csv")}
    debt = _records(synthetic.path / "debt_products.csv")
    groups_with_debt = {companies[row["company_id"]] for row in debt}
    assert synthetic.no_debt_group_id not in groups_with_debt
    assert all(row["granted"] == "" or row["granted"].startswith("-") for row in debt)
    schedule = _records(synthetic.path / "debt_schedule_config.csv")
    assert [row["product_id"] for row in schedule] == [synthetic.loan_product_id]


def test_transforms_keep_the_files_consistent(tmp_path, synthetic, datasets) -> None:
    subset = datasets.filter(synthetic.path, tmp_path / "subset", ["GROUP_0001", "GROUP_0004"])
    members = {row["company_id"] for row in _records(subset / "companies.csv")}
    assert members == set(
        synthetic.companies_by_group["GROUP_0001"] + synthetic.companies_by_group["GROUP_0004"]
    )
    assert {row["company_id"] for row in _records(subset / "transactions.csv")} == members

    month = date(2026, 2, 1)
    cut = datasets.truncate(synthetic.path, tmp_path / "cut", month)
    assert max(row["date"] for row in _records(cut / "transactions.csv"))[:10] <= "2026-02-28"
    assert max(row["issuance_date"] for row in _records(cut / "invoices.csv"))[:10] <= "2026-02-28"
    assert not [
        row for row in _records(cut / "invoices.csv")
        if row["status"] == "paid" and row["payment_date"][:10] > "2026-02-28"
    ]
    for row in _records(cut / "balances.csv"):
        key = (row["product_id"], month)
        if row["product_id"] == synthetic.sentinel_product_id:
            assert datasets.to_cents(row["balance"]) == -99_999_999_900
        elif key in synthetic.month_end_balance_cents:
            assert datasets.to_cents(row["balance"]) == synthetic.month_end_balance_cents[key]
            assert row["date"].startswith("2026-02-28")

    scaled = datasets.scale(synthetic.path, tmp_path / "scaled", 1024)
    before = _records(synthetic.path / "transactions.csv")
    after = {row["transaction_id"]: row for row in _records(scaled / "transactions.csv")}
    assert all(
        datasets.to_cents(after[row["transaction_id"]]["amount"]) == 1024 * datasets.to_cents(row["amount"])
        for row in before
    )
    largest = max(
        abs(datasets.to_cents(row["balance"])) for row in _records(scaled / "balances.csv")
        if row["product_id"] != synthetic.sentinel_product_id
    )
    assert largest < 90_000_000_000  # scaling never fabricates a sentinel

    shuffled = datasets.shuffle(synthetic.path, tmp_path / "shuffled", seed=3)
    original = _records(synthetic.path / "invoices.csv")
    moved = _records(shuffled / "invoices.csv")
    assert moved != original
    assert sorted(moved, key=lambda row: row["operation_id"]) == sorted(
        original, key=lambda row: row["operation_id"]
    )


def test_existing_readers_accept_the_files(synthetic) -> None:
    fingerprint, classified = classify_dataset(synthetic.path)
    assert fingerprint == io.dataset_fingerprint(synthetic.path) or len(fingerprint) == 64
    assert {item.entity_id for item in classified} == set(synthetic.company_ids)
