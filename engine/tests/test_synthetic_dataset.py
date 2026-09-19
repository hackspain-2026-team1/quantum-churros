"""The synthetic dataset must look like the real files and hold every trap."""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import pytest
from xray_engine import io, scoring


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


def test_mirror_pairs_are_the_only_opposite_twins(synthetic, datasets, params) -> None:
    records = _records(synthetic.path / "transactions.csv")
    companies = {row["company_id"]: row["group_id"] for row in _records(synthetic.path / "companies.csv")}
    currency = {row["product_id"]: row["currency"] for row in _records(synthetic.path / "banking_products.csv")}
    currency |= {row["product_id"]: row["currency"] for row in _records(synthetic.path / "debt_products.csv")}
    by_id = {row["transaction_id"]: row for row in records}
    scopes = Counter(pair.scope for pair in synthetic.mirror_pairs)
    assert scopes["intra_company"] > 20 and scopes["intra_group"] > 100
    # the category is no criterion: most pairs are not labelled transfer on both legs
    mislabelled = [pair for pair in synthetic.mirror_pairs if pair.out_category == "payment"]
    assert mislabelled and all(pair.in_category == "collection" for pair in mislabelled)
    assert {pair.day_offset for pair in synthetic.mirror_pairs} == {-3, -1, 0, 1, 2, 3}
    assert sum(pair.ambiguous for pair in synthetic.mirror_pairs) == 2
    assert Counter(pair.kind for pair in synthetic.mirror_decoys) == {
        "day_gap": 3, "below_gate": 1, "cross_currency": 1,
    }

    def legs(pair):
        out_leg, in_leg = by_id[pair.out_id], by_id[pair.in_id]
        assert datasets.to_cents(out_leg["amount"]) == -pair.amount_cents
        assert datasets.to_cents(in_leg["amount"]) == pair.amount_cents
        assert out_leg["product_id"] != in_leg["product_id"]
        assert companies[out_leg["company_id"]] == companies[in_leg["company_id"]] == pair.group_id
        same_company = out_leg["company_id"] == in_leg["company_id"]
        assert pair.scope == ("intra_company" if same_company else "intra_group")
        return out_leg, in_leg

    def recipe_allows(pair) -> bool:
        out_leg, in_leg = legs(pair)
        same_currency = currency[out_leg["product_id"]] == currency[in_leg["product_id"]]
        rate = params.fx.rates.get(currency[out_leg["product_id"]])
        return same_currency and datasets.may_net(
            date.fromisoformat(out_leg["date"][:10]), date.fromisoformat(in_leg["date"][:10]),
            pair.amount_cents, rate, params,
        )

    for pair in synthetic.mirror_pairs:
        assert recipe_allows(pair), pair
        if pair.kind == "weekend_bridge":
            out_leg, in_leg = legs(pair)
            earlier = min(out_leg["date"], in_leg["date"])[:10]
            assert date.fromisoformat(earlier).weekday() in params.mirror.weekend_bridge_weekdays
    for pair in synthetic.mirror_decoys:
        assert not recipe_allows(pair), pair
    for negative_id, positive_id in synthetic.reversal_pairs:
        negative, positive = by_id[negative_id], by_id[positive_id]
        assert negative["product_id"] == positive["product_id"]
        assert datasets.to_cents(negative["amount"]) == -datasets.to_cents(positive["amount"]) < 0
        gap = date.fromisoformat(negative["date"][:10]) - date.fromisoformat(positive["date"][:10])
        assert abs(gap.days) <= params.mirror.reversal_max_day_gap

    # no accidental twin: every (group, month, |amount|) outside the handles is unique
    handled = {item for pair in synthetic.mirror_pairs + synthetic.mirror_decoys
               for item in (pair.out_id, pair.in_id)}
    handled |= {item for pair in synthetic.reversal_pairs for item in pair}
    handled |= set(synthetic.dash_adjustment_ids)
    seen: dict[tuple, str] = {}
    for row in records:
        if row["transaction_id"] in handled or currency.get(row["product_id"]) != "EUR":
            continue
        key = (companies[row["company_id"]], row["date"][:7], abs(datasets.to_cents(row["amount"])))
        assert key not in seen, (key, seen.get(key), row["transaction_id"])
        seen[key] = row["transaction_id"]


def test_dash_rows_follow_the_rule_table(synthetic, datasets, params) -> None:
    records = {row["transaction_id"]: row for row in _records(synthetic.path / "transactions.csv")}
    dash = {key for key, row in records.items() if row["category"] == "-" and row["status"] != "pending"}
    assert dash == set(synthetic.dash_expected)
    for transaction_id, expected in synthetic.dash_expected.items():
        row = records[transaction_id]
        verdict = datasets.classify_dash(row["description"], datasets.to_cents(row["amount"]), params)
        assert verdict == expected, (row["description"], verdict, expected)
    fired = Counter(rule for _, rule in synthetic.dash_expected.values())
    assert set(fired) == {rule.id for rule in params.dash_rules} | {None}
    assert fired[None] > fired["commission"] > 0  # the sign default carries most rows
    assert len(synthetic.dash_debt_service_ids) == 12
    for transaction_id in synthetic.dash_debt_service_ids:
        assert synthetic.dash_expected[transaction_id][0] == "debt_service"
        assert records[transaction_id]["amount"].startswith("-")
    # narratives the rule table leaves out on purpose stay with the sign default
    for text, cents in (("NOMINA [PERSON]", -1), ("ABONO POR DISPOSICION", 1), ("CUOTA NUMERO 12", -1),
                        ("TRASPASO ENTRE CUENTAS", -1), ("LIQUIDACION PERIODICA", -1)):
        assert datasets.classify_dash(text, cents, params)[1] is None, text
    holds = [records[item] for item in synthetic.dash_adjustment_ids]
    assert sum(datasets.to_cents(row["amount"]) for row in holds) == 0
    assert all(abs(datasets.to_cents(row["amount"])) >= 100_000_000 for row in holds)


def test_input_traps(synthetic) -> None:
    raw = (synthetic.path / "transactions.csv").read_bytes()
    assert raw.count(b"\x00") == 1
    records = {row["transaction_id"]: row for row in _records(synthetic.path / "transactions.csv")}
    assert "\x00" in records[synthetic.nul_transaction_id]["description"]
    products = {row["product_id"] for row in _records(synthetic.path / "banking_products.csv")}
    products |= {row["product_id"] for row in _records(synthetic.path / "debt_products.csv")}
    orphans = [row for row in records.values() if row["product_id"] not in products]
    assert {row["transaction_id"] for row in orphans} == set(synthetic.orphan_transaction_ids)
    assert {row["product_id"] for row in orphans} == {synthetic.orphan_product_id}
    assert len(orphans) == 3


def test_feed_and_revenue_archetypes(synthetic, datasets) -> None:
    records = _records(synthetic.path / "transactions.csv")
    months = Counter(
        row["date"][:7] for row in records
        if row["company_id"] == synthetic.stale_company_id and row["status"] != "pending"
    )
    last = synthetic.stale_company_last_active_month
    assert max(months) == last.strftime("%Y-%m") and len(months) >= 12
    assert last < synthetic.last_month
    # the captive company only receives mirror legs: no inflow survives the netting
    paired = {pair.in_id for pair in synthetic.mirror_pairs}
    inflows = [
        row for row in records
        if row["company_id"] == synthetic.no_external_revenue_company_id
        and not row["amount"].startswith("-")
    ]
    assert inflows and all(row["transaction_id"] in paired for row in inflows)
    assert {row["category"] for row in inflows} == {"transfer", "collection"}


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


def test_context_reader_never_blocks_a_run(synthetic, tmp_path) -> None:
    found = scoring.classify_industry(synthetic.path)
    assert set(found) <= set(synthetic.company_ids)
    assert all(item.entity_id == key for key, item in found.items())
    assert scoring.classify_industry(tmp_path) == {}  # no files: no context, no exception
