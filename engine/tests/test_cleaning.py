"""Transaction cleaning: currency, mirror netting, reversals, flow classes, counterparty key."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from xray_engine import cleaning, io
from xray_engine.contracts import FLOW_CLASSES
from xray_engine.invoices import CLEAN_INVOICE_COLUMNS

REAL_CACHE_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "cache"

# product -> (company, group, currency)
ACCOUNTS = {
    "P_A1": ("C_A", "G_1", "EUR"),
    "P_A2": ("C_A", "G_1", "EUR"),
    "P_B1": ("C_B", "G_1", "EUR"),
    "P_USD": ("C_A", "G_1", "USD"),
    "P_HUF": ("C_B", "G_1", "HUF"),
    "P_X1": ("C_X", "G_2", "EUR"),
}


def clean_transactions(transactions, products, companies, params) -> pl.DataFrame:
    frame = cleaning.assign_currency(transactions, products, companies, params)
    frame = cleaning.net_mirror_pairs(frame, params)
    frame = cleaning.net_reversals(frame, params)
    return cleaning.classify_flows(frame, params)


def run(rows: list[tuple], params) -> dict[str, dict]:
    """rows: (id, product, day, cents[, category[, description[, counterparty]]]) -> cleaned rows by id."""
    records = []
    for key, product, day, cents, *rest in rows:
        category, description, counterparty = (*rest, None, None, None)[:3]
        records.append({
            "transaction_id": key, "company_id": ACCOUNTS.get(product, ("C_A",))[0], "product_id": product,
            "date": day, "month": day.replace(day=1), "amount_cents": cents, "status": "booked",
            "accounting_status": None, "category": category or "payment", "description": description,
            "counterparty_id": counterparty,
        })
    transactions = pl.DataFrame(records, schema=io.CACHE_SCHEMAS["transactions"])
    companies = pl.DataFrame(
        [{"company_id": company, "group_id": group} for company, group, _ in set(ACCOUNTS.values())],
        schema=io.CACHE_SCHEMAS["companies"],
    ).unique("company_id")
    products = pl.DataFrame(
        [
            {"product_id": product, "company_id": company, "group_id": group, "currency": currency,
             "product_type": "checking", "product_family": "banking"}
            for product, (company, group, currency) in ACCOUNTS.items()
        ],
        schema=cleaning.PRODUCT_COLUMNS,
    )
    frame = clean_transactions(transactions, products, companies, params)
    assert frame.height == len(rows)
    return {row["transaction_id"]: row for row in frame.to_dicts()}


@pytest.fixture(scope="module")
def tables(synthetic, tmp_path_factory) -> io.Tables:
    return io.load_tables(synthetic.path, tmp_path_factory.mktemp("cleaning-cache"))


@pytest.fixture(scope="module")
def cleaned(tables, params) -> dict[str, dict]:
    products = cleaning.build_products(tables)
    frame = clean_transactions(tables.transactions, products, tables.companies, params)
    assert frame.height == tables.transactions.height
    return {row["transaction_id"]: row for row in frame.to_dicts()}


# --------------------------------------------------------------------------
# synthetic dataset
# --------------------------------------------------------------------------


def test_mirror_legs_are_netted_whatever_their_category(synthetic, cleaned) -> None:
    categories = Counter()
    for pair in synthetic.mirror_pairs:
        for key in (pair.out_id, pair.in_id):
            assert cleaned[key]["mirror_id"] is not None and cleaned[key]["flow_class"] == "internal"
            assert cleaned[key]["mirror_scope"] == pair.scope and cleaned[key]["reversal_id"] is None
        categories[(pair.out_category, pair.in_category)] += 1
    # the recipe never reads the category: payment / collection twins go like transfers
    assert categories[("payment", "collection")] > 20 and categories[("-", "-")] > 20
    assert categories[("transfer", "transfer")] > 20
    netted = {key for key, row in cleaned.items() if row["mirror_id"] is not None}
    assert netted == {key for pair in synthetic.mirror_pairs for key in (pair.out_id, pair.in_id)}
    legs = Counter(row["mirror_id"] for row in cleaned.values() if row["mirror_id"] is not None)
    assert set(legs.values()) == {2}  # 1:1, the twin transfers of one day included
    assert any(pair.kind == "weekend_bridge" for pair in synthetic.mirror_pairs)


def test_decoys_stay_in_the_operating_flows(synthetic, cleaned) -> None:
    kinds = set()
    for pair in synthetic.mirror_decoys:
        kinds.add(pair.kind)
        assert cleaned[pair.out_id]["flow_class"] == "op_out" and cleaned[pair.out_id]["mirror_id"] is None
        assert cleaned[pair.in_id]["flow_class"] == "op_in" and cleaned[pair.in_id]["mirror_id"] is None
    assert kinds == {"day_gap", "below_gate", "cross_currency"}


def test_a_booking_and_its_undo_are_a_reversal(synthetic, cleaned) -> None:
    for negative_id, positive_id in synthetic.reversal_pairs:
        for key in (negative_id, positive_id):
            row = cleaned[key]
            assert (row["reversal_id"], row["mirror_id"], row["flow_class"]) == (negative_id, None, "internal")
        assert cleaned[negative_id]["product_id"] == cleaned[positive_id]["product_id"]
    reversed_rows = {key for key, row in cleaned.items() if row["reversal_id"] is not None}
    assert reversed_rows == {key for pair in synthetic.reversal_pairs for key in pair}


def test_account_currency_comes_from_the_product(synthetic, cleaned, params) -> None:
    dollars = [row for row in cleaned.values() if row["product_id"] == synthetic.usd_product_id]
    assert dollars and {(row["currency"], row["fx_rate"], row["fx_excluded"]) for row in dollars} == {
        ("USD", params.fx.rates["USD"], False)
    }
    assert {row["flow_class"] for row in dollars} == {"op_in"}
    foreign = [row for row in cleaned.values() if row["product_id"] == synthetic.fx_excluded_product_id]
    assert foreign and all(row["fx_excluded"] and row["fx_rate"] is None and row["currency"] == "HUF" for row in foreign)
    orphans = [cleaned[key] for key in synthetic.orphan_transaction_ids]
    assert all(row["orphan_product"] and row["fx_excluded"] and row["currency"] is None for row in orphans)
    assert all(row["group_id"] is not None and row["product_family"] is None for row in orphans)
    known = [row for row in cleaned.values() if not row["orphan_product"]]
    assert {row["product_family"] for row in known} == {"banking", "debt"}
    line = [row for row in cleaned.values() if row["product_id"] == synthetic.credit_line_product_id]
    assert {row["product_type"] for row in line} == {"lineofcredit"}
    assert {"op_out", "internal"} == {row["flow_class"] for row in line}  # an operating account


def test_pending_rows_and_text_traps(synthetic, cleaned) -> None:
    assert not set(synthetic.pending_transaction_ids) & set(cleaned)
    assert set(synthetic.blank_status_transaction_ids) <= set(cleaned)
    newline = cleaned[synthetic.newline_transaction_id]
    assert "\n" in newline["description"] and newline["flow_class"] == "debt_service"
    nul = cleaned[synthetic.nul_transaction_id]
    assert "\x00" not in nul["description"] and nul["flow_class"] == "op_out"
    assert all(row["flow_class"] in FLOW_CLASSES for row in cleaned.values())


def test_dash_rows_follow_the_rule_table(synthetic, cleaned, params) -> None:
    rules = {rule.id: rule for rule in params.dash_rules}
    fired = Counter()
    for key, (flow_class, rule_id) in synthetic.dash_expected.items():
        row = cleaned[key]
        if row["mirror_id"] is not None:
            assert (row["flow_class"], row["label"], row["label_rule"]) == ("internal", "-", None)
            continue
        assert (row["flow_class"], row["label_rule"]) == (flow_class, rule_id)
        assert row["label"] == (rules[rule_id].label if rule_id else "-")
        fired[rule_id] += 1
    assert fired[None] > 100 and len(fired) >= 10
    assert {cleaned[key]["flow_class"] for key in synthetic.dash_debt_service_ids} == {"debt_service"}
    assert {cleaned[key]["flow_class"] for key in synthetic.dash_adjustment_ids} == {"adjustment"}


def test_clean_wires_every_table(tables, params, monkeypatch) -> None:
    monkeypatch.setattr(cleaning, "clean_invoices", lambda *_: pl.DataFrame(schema=CLEAN_INVOICE_COLUMNS))
    clean = cleaning.clean(tables, params)
    expected = {**io.CACHE_SCHEMAS["transactions"], **cleaning.CLEAN_TRANSACTION_COLUMNS}
    assert list(clean.transactions.schema.items()) == list(expected.items())
    assert clean.transactions["transaction_id"].to_list() == tables.transactions["transaction_id"].to_list()
    assert dict(clean.products.schema) == cleaning.PRODUCT_COLUMNS
    assert clean.products.height == tables.banking_products.height + tables.debt_products.height
    assert clean.products["product_id"].is_sorted() and clean.products["group_id"].null_count() == 0
    added = {"group_id": pl.String, "currency": pl.String, "product_type": pl.String, "fx_rate": pl.Float64}
    assert dict(clean.balances.schema) == {**io.CACHE_SCHEMAS["balances"], **added}
    assert clean.balances.height == tables.balances.height and clean.balances["group_id"].null_count() == 0
    assert (clean.window, clean.dataset_hash) == (tables.window, tables.dataset_hash)


def test_netting_does_not_depend_on_row_order(tables, cleaned, params) -> None:
    products = cleaning.build_products(tables)
    shuffled = tables.transactions.sample(fraction=1.0, shuffle=True, seed=5)
    again = clean_transactions(shuffled, products, tables.companies, params)
    assert again["transaction_id"].to_list() == shuffled["transaction_id"].to_list()  # order kept
    assert {row["transaction_id"]: row for row in again.to_dicts()} == cleaned


def _cleaned_folder(folder: Path, cache: Path, params) -> dict[str, dict]:
    tables = io.load_tables(folder, cache)
    frame = clean_transactions(tables.transactions, cleaning.build_products(tables), tables.companies, params)
    return {row["transaction_id"]: row for row in frame.to_dicts()}


def test_later_rows_never_change_an_earlier_month(synthetic, datasets, cleaned, params, tmp_path) -> None:
    cut = date(2025, 10, 1)
    early = _cleaned_folder(datasets.truncate(synthetic.path, tmp_path / "cut", cut), tmp_path / "cache", params)
    assert early == {key: row for key, row in cleaned.items() if row["month"] <= cut}
    assert any(row["mirror_id"] for row in early.values()) and any(row["month"] == cut for row in early.values())


def test_a_group_cleaned_alone_equals_the_full_run(synthetic, datasets, cleaned, params, tmp_path) -> None:
    groups = [synthetic.late_member_group_id, synthetic.no_invoice_group_id]
    alone = _cleaned_folder(datasets.filter(synthetic.path, tmp_path / "alone", groups), tmp_path / "cache", params)
    assert alone == {key: row for key, row in cleaned.items() if row["group_id"] in groups}
    assert any(row["mirror_scope"] == "intra_group" for row in alone.values())


# --------------------------------------------------------------------------
# hand-made rows
# --------------------------------------------------------------------------

D = date(2025, 3, 12)  # a Wednesday


def test_mirrors_go_before_reversals(params) -> None:
    rows = run(
        [
            # funded payment: the treasury tops up the account, the account pays a supplier
            ("fund_out", "P_B1", D, -250_000, "payment"),
            ("fund_in", "P_A1", D, 250_000, "collection"),
            ("supplier", "P_A1", D, -250_000, "payment"),
            # nothing on another account explains these two: a booking and its undo
            ("booked", "P_A2", D, 90_000, "collection"),
            ("undone", "P_A2", D + timedelta(days=1), -90_000, "payment"),
            # reversals have no amount floor, mirrors do
            ("small_out", "P_A1", D, -4_000), ("small_in", "P_B1", D, 4_000, "collection"),
            ("fee", "P_X1", D, -150, "fee"), ("fee_back", "P_X1", D, 150, "payment_refund"),
        ],
        params,
    )
    assert rows["fund_out"]["mirror_id"] == rows["fund_in"]["mirror_id"] == "fund_out"
    assert rows["fund_in"]["mirror_scope"] == "intra_group"
    assert (rows["supplier"]["mirror_id"], rows["supplier"]["reversal_id"]) == (None, None)
    assert rows["supplier"]["flow_class"] == "op_out"  # the real payment stays
    assert rows["booked"]["reversal_id"] == rows["undone"]["reversal_id"] == "undone"
    assert rows["small_out"]["flow_class"] == "op_out" and rows["small_in"]["flow_class"] == "op_in"
    assert rows["fee"]["reversal_id"] == rows["fee_back"]["reversal_id"] == "fee"
    assert rows["fee_back"]["flow_class"] == "internal"


def test_a_row_is_a_leg_of_one_rule_only_in_either_call_order(tables, params) -> None:
    products = cleaning.build_products(tables)
    frame = cleaning.assign_currency(tables.transactions, products, tables.companies, params)
    orders = [(cleaning.net_mirror_pairs, cleaning.net_reversals), (cleaning.net_reversals, cleaning.net_mirror_pairs)]
    for first, second in orders:
        netted = second(first(frame, params), params)
        assert netted.height == frame.height
        both = netted.filter(pl.col("mirror_id").is_not_null() & pl.col("reversal_id").is_not_null())
        assert both.height == 0
        assert netted["mirror_id"].drop_nulls().len() > 0 and netted["reversal_id"].drop_nulls().len() > 0


def test_nearest_date_wins_and_pairs_stay_inside_the_month(params) -> None:
    friday = date(2025, 3, 14)
    rows = run(
        [
            ("out", "P_A1", D, -500_000), ("same_day", "P_A2", D, 500_000, "collection"),
            ("next_day", "P_B1", D + timedelta(days=1), 500_000, "collection"),
            # Friday to Monday is bridged, Wednesday to Saturday is not
            ("fri_out", "P_A1", friday, -610_000), ("mon_in", "P_B1", friday + timedelta(days=3), 610_000),
            ("wed_out", "P_A1", D, -620_000), ("sat_in", "P_B1", D + timedelta(days=3), 620_000),
            # the earlier leg may be the positive one
            ("sat_in_2", "P_A2", friday + timedelta(days=1), 630_000), ("mon_out", "P_A1", friday + timedelta(days=3), -630_000),
            # month end to the first of the next month: never paired, on two accounts or on one
            ("jan_out", "P_A1", date(2025, 1, 31), -640_000), ("feb_in", "P_A2", date(2025, 2, 1), 640_000),
            ("jan_booked", "P_X1", date(2025, 1, 31), 650_000), ("feb_undone", "P_X1", date(2025, 2, 1), -650_000),
            # other group, other currency, excluded currency
            ("g1_out", "P_A1", D, -660_000), ("g2_in", "P_X1", D, 660_000),
            ("eur_out", "P_A1", D, -670_000), ("usd_in", "P_USD", D, 670_000),
            ("huf_out", "P_HUF", D, -680_000), ("huf_in", "P_HUF", D, 680_000),
        ],
        params,
    )
    assert rows["same_day"]["mirror_id"] == "out" and rows["same_day"]["mirror_scope"] == "intra_company"
    assert rows["next_day"]["mirror_id"] is None
    assert rows["fri_out"]["mirror_id"] == rows["mon_in"]["mirror_id"] == "fri_out"
    assert rows["wed_out"]["mirror_id"] is None and rows["sat_in"]["mirror_id"] is None
    assert rows["sat_in_2"]["mirror_id"] == rows["mon_out"]["mirror_id"] == "mon_out"
    for key in ("jan_out", "feb_in", "jan_booked", "feb_undone", "g1_out", "g2_in", "eur_out", "usd_in"):
        assert (rows[key]["mirror_id"], rows[key]["reversal_id"]) == (None, None), key
    assert rows["huf_out"]["mirror_id"] is None and rows["huf_out"]["fx_excluded"]
    assert rows["huf_out"]["reversal_id"] == rows["huf_in"]["reversal_id"] == "huf_out"  # same account: no rate needed


def _expected_pairs(rows: list[dict], params) -> tuple[dict[str, str], dict[str, str]]:
    """Row-by-row reading of the recipe: mirrors, then reversals; one pass per gap."""
    mirror = params.mirror
    free = {row["transaction_id"]: row for row in rows if row["amount_cents"] != 0}

    def passes(candidates: dict, key, max_gap: int, free_gap: int, weekdays, other_product: bool) -> dict[str, str]:
        found: dict[str, str] = {}
        for gap in [0, *(sign * days for days in range(1, max_gap + 1) for sign in (1, -1))]:
            ordered = sorted(candidates.values(), key=lambda row: row["transaction_id"])
            positives = [row for row in ordered if row["amount_cents"] > 0]
            for negative in (row for row in ordered if row["amount_cents"] < 0):
                target = negative["date"] + timedelta(days=gap)
                if target.replace(day=1) != negative["month"]:
                    continue
                if abs(gap) > free_gap and min(target, negative["date"]).weekday() not in weekdays:
                    continue
                for positive in positives:
                    if positive["transaction_id"] in found or positive["date"] != target:
                        continue
                    if key(positive) != key(negative):
                        continue
                    if (positive["product_id"] != negative["product_id"]) != other_product:
                        continue
                    found[negative["transaction_id"]] = found[positive["transaction_id"]] = negative["transaction_id"]
                    break
            candidates = {name: row for name, row in candidates.items() if name not in found}
        return found

    eligible = {
        name: row for name, row in free.items()
        if row["fx_rate"] is not None and abs(row["amount_cents"]) / 100 * row["fx_rate"] >= mirror.min_amount_eur
    }
    mirrors = passes(
        eligible, lambda row: (row["group_id"], row["currency"], abs(row["amount_cents"])),
        max(mirror.max_day_gap, mirror.weekend_bridge_day_gap), mirror.max_day_gap,
        mirror.weekend_bridge_weekdays, True,
    )
    rest = {name: row for name, row in free.items() if name not in mirrors}
    reversals = passes(
        rest, lambda row: (row["product_id"], abs(row["amount_cents"])),
        mirror.reversal_max_day_gap, mirror.reversal_max_day_gap, (), False,
    )
    return mirrors, reversals


@pytest.mark.parametrize("seed", range(12))
def test_pairing_equals_the_row_by_row_greedy(params, seed) -> None:
    rng = random.Random(seed)
    products = list(ACCOUNTS)
    rows = []
    for index in range(260):  # few amounts and few days: crowded buckets, accounts on both sides
        key = hashlib.md5(f"{seed}:{index}".encode()).hexdigest()
        day = date(2025, 2, 20) + timedelta(days=rng.randint(0, 16))
        cents = rng.choice([-1, 1]) * rng.choice([250_000, 310_000, 4_000, 0])
        rows.append((key, rng.choice(products), day, cents))
    cleaned = run(rows, params)
    mirrors, reversals = _expected_pairs(list(cleaned.values()), params)
    assert {key: row["mirror_id"] for key, row in cleaned.items() if row["mirror_id"]} == mirrors
    assert {key: row["reversal_id"] for key, row in cleaned.items() if row["reversal_id"]} == reversals
    assert len(mirrors) >= 30 and len(reversals) >= 6  # legs


def test_flow_classes_of_categorised_rows(params) -> None:
    rows = run(
        [
            ("collection", "P_A1", D, 1_100, "collection"), ("settlement", "P_A1", D, 1_200, "cash_settlement"),
            ("refund_in", "P_A1", D, 1_300, "payment_refund"), ("salary", "P_A1", D, -1_400, "salary"),
            ("salary_back", "P_A1", D, 1_500, "salary"), ("interest", "P_A1", D, -1_600, "interest_charge"),
            ("loan", "P_A1", D, -1_700, "debt_repayment"), ("drawdown", "P_A1", D, 1_800, "debt_repayment"),
            ("transfer", "P_A1", D, -1_900, "transfer"), ("invest", "P_A1", D, -2_000, "investment_deployment"),
            ("withdrawal", "P_A1", D, -2_100, "cash_withdrawal"), ("zero", "P_A1", D, 0, "payment"),
            ("huf", "P_HUF", D, 2_200, "collection"),
        ],
        params,
    )
    assert {key: row["flow_class"] for key, row in rows.items()} == {
        "collection": "op_in", "settlement": "op_in", "refund_in": "other", "salary": "op_out",
        "salary_back": "other", "interest": "debt_service", "loan": "debt_service", "drawdown": "other",
        "transfer": "internal", "invest": "financial", "withdrawal": "other", "zero": "other", "huf": "op_in",
    }
    assert all(row["label"] == row["category"] and row["label_rule"] is None for row in rows.values())


def test_dash_rules_on_hand_made_narratives(params) -> None:
    rows = run(
        [
            ("multi_line", "P_A1", D, -46_500, "-", "CARGO POR\r\n  AMORTIZACION\nPRESTAMO [NUM]"),
            ("lower_case", "P_A1", D, -46_600, "-", "cargo por amortización de préstamo"),
            ("veto", "P_A1", D, -1_250, "-", "COMISION AMORTIZACION ANTICIPADA"),
            ("wrong_sign", "P_A1", D, 46_700, "-", "AMORTIZ. PTMO [NUM]"),
            ("tax_refund", "P_A1", D, 9_900, "-", "AEAT DEVOLUCION [NUM]"),
            ("hold", "P_A1", D, 90_000_000, "-", "AP.RET.DST: [ACCOUNT]"),
            ("zero", "P_A1", D, 0, "-", "PAYOUT [NUM]"),
            ("no_text", "P_A1", D, -700, "-"),
            ("netted_out", "P_A1", D, -333_300, "-", "PAYOUT [NUM]"),
            ("netted_in", "P_A2", D, 333_300, "-", "TGSS [NUM]"),
            ("labelled", "P_A1", D, -5_500, "payment", "PAYOUT TGSS AEAT"),
        ],
        params,
    )
    got = {key: (row["flow_class"], row["label"], row["label_rule"]) for key, row in rows.items()}
    assert got == {
        "multi_line": ("debt_service", "debt_repayment", "amortisation_charge"),
        "lower_case": ("debt_service", "debt_repayment", "amortisation_charge"),
        "veto": ("op_out", "fee", "commission"),
        "wrong_sign": ("op_in", "-", None),
        "tax_refund": ("op_in", "-", None),
        "hold": ("adjustment", "balance_adjustment", "retention_adjustment"),
        "zero": ("other", "-", None),
        "no_text": ("op_out", "-", None),
        "netted_out": ("internal", "-", None),
        "netted_in": ("internal", "-", None),
        "labelled": ("op_out", "payment", None),
    }


def test_counterparty_key(params) -> None:
    rows = run(
        [
            ("own_id", "P_A1", D, 1_000, "collection", "DE COUNTERPARTY_00007 FRA", "COUNTERPARTY_00042"),
            ("one_token", "P_A1", D, 1_001, "collection", "TRANSFERENCIA DE COUNTERPARTY_00007\nFRA [NUM]"),
            ("two_tokens", "P_A1", D, 1_002, "bulk_collection", "REMESA COUNTERPARTY_00011 COUNTERPARTY_00012"),
            ("twice", "P_A1", D, 1_003, "collection", "COUNTERPARTY_00011 / COUNTERPARTY_00011"),
            ("short_id", "P_A1", D, 1_004, "collection", "DE COUNTERPARTY_7 FRA"),
            ("no_token", "P_A1", D, 1_005, "collection", "TRANSFERENCIA DE [COMPANY]"),
            ("no_text", "P_A1", D, 1_006, "collection"),
        ],
        params,
    )
    assert {key: row["counterparty_key"] for key, row in rows.items()} == {
        "own_id": "COUNTERPARTY_00042", "one_token": "COUNTERPARTY_00007", "two_tokens": None,
        "twice": "COUNTERPARTY_00011", "short_id": "COUNTERPARTY_7", "no_token": None, "no_text": None,
    }


# --------------------------------------------------------------------------
# real dataset: aggregate invariants only
# --------------------------------------------------------------------------


@pytest.mark.dataset
def test_real_data_invariants(real_data_dir, params) -> None:
    tables = io.load_tables(real_data_dir, REAL_CACHE_DIR)
    products = cleaning.build_products(tables)
    frame = clean_transactions(tables.transactions, products, tables.companies, params)
    assert frame.height == tables.transactions.height
    assert frame["flow_class"].null_count() == 0 and set(frame["flow_class"].unique()) == set(FLOW_CLASSES)

    window = frame.filter(pl.col("month").is_between(tables.window.first_month, tables.window.last_month))
    window = window.with_columns(eur=pl.col("amount_cents").abs() / 100 * pl.col("fx_rate"))
    outflow = window.filter(pl.col("amount_cents") < 0)
    mirrored = outflow.filter(pl.col("mirror_id").is_not_null())
    assert 0.05 <= mirrored.height / outflow.height <= 0.08
    assert 0.40 <= mirrored["eur"].sum() / outflow["eur"].sum() <= 0.52
    legs = window.filter(pl.col("mirror_id").is_not_null())
    assert 0.30 <= legs.filter(pl.col("category") == "transfer").height / legs.height <= 0.38
    assert 0.35 <= legs.filter(pl.col("category").is_in(["payment", "collection"])).height / legs.height <= 0.50
    assert 0.50 <= legs.filter(pl.col("mirror_scope") == "intra_group").height / legs.height <= 0.70
    undone = outflow.filter(pl.col("reversal_id").is_not_null())
    assert 0.02 <= undone.height / outflow.height <= 0.04
    assert 0.08 <= undone["eur"].sum() / outflow["eur"].sum() <= 0.16

    # every pair is 1:1 and obeys its rule
    for column, same_product in (("mirror_id", False), ("reversal_id", True)):
        pairs = frame.filter(pl.col(column).is_not_null()).group_by(column).agg(
            pl.len().alias("legs"), pl.col("amount_cents").sum().alias("net"),
            pl.col("product_id").n_unique().alias("products"), pl.col("month").n_unique().alias("months"),
            pl.col("group_id").n_unique().alias("groups"), pl.col("currency").n_unique().alias("currencies"),
            (pl.col("date").max() - pl.col("date").min()).dt.total_days().alias("gap"),
            pl.col("date").min().dt.weekday().alias("first_weekday"),
        )
        assert pairs.select(
            ((pl.col("legs") == 2) & (pl.col("net") == 0) & (pl.col("months") == 1)
             & (pl.col("products") == (1 if same_product else 2))).all()
        ).item(), column
        if same_product:
            assert pairs["gap"].max() <= params.mirror.reversal_max_day_gap
        else:
            assert pairs.select(((pl.col("groups") == 1) & (pl.col("currencies") == 1)).all()).item()
            bridged = pairs.filter(pl.col("gap") > params.mirror.max_day_gap)
            assert bridged["gap"].max() <= params.mirror.weekend_bridge_day_gap
            weekdays = [day + 1 for day in params.mirror.weekend_bridge_weekdays]  # polars: Monday is 1
            assert bridged["first_weekday"].is_in(weekdays).all() and 0 < bridged.height < 0.1 * pairs.height
    assert frame.filter(pl.col("mirror_id").is_not_null() & pl.col("reversal_id").is_not_null()).height == 0
    floor = frame.filter(pl.col("mirror_id").is_not_null()).select(
        (pl.col("amount_cents").abs() / 100 * pl.col("fx_rate")).min()
    ).item()
    assert floor >= params.mirror.min_amount_eur

    # "-" rows: account-hold narratives carry a third of the value; pairs explain part of them
    dash = window.filter(pl.col("category") == params.flows.dash_category)
    assert 0.20 <= dash.height / window.height <= 0.30
    patterns = "|".join(f"(?i:{rule.pattern})" for rule in params.dash_rules if rule.flow_class == "adjustment")
    narrative = dash.filter(pl.col("description").str.replace_all(r"\s+", " ").str.contains(patterns))
    assert 0.30 <= narrative["eur"].sum() / dash["eur"].sum() <= 0.40 and narrative.height < 1_000
    adjustment = dash.filter(pl.col("flow_class") == "adjustment")
    assert set(window.filter(pl.col("flow_class") == "adjustment")["category"].unique()) == {"-"}
    assert 0.18 <= adjustment["eur"].sum() / dash["eur"].sum() <= 0.28
    assert narrative.filter(~pl.col("flow_class").is_in(["adjustment", "internal"])).height == 0
    by_sign = dash.filter(pl.col("label_rule").is_null() & pl.col("mirror_id").is_null() & pl.col("reversal_id").is_null())
    assert set(by_sign["flow_class"].unique()) <= {"op_in", "op_out", "other"}
    assert 0.85 <= by_sign.height / dash.height <= 0.97  # the sign default carries the "-" rows

    # rows that count but never weigh
    assert 1_000 <= window["orphan_product"].sum() <= 1_600
    assert 0.003 <= window.filter(pl.col("fx_excluded") & ~pl.col("orphan_product")).height / window.height <= 0.007
    assert window.filter(pl.col("orphan_product"))["group_id"].null_count() == 0
    harvested = window.filter(pl.col("counterparty_id").is_null() & pl.col("counterparty_key").is_not_null())
    assert 0.10 <= harvested.height / window.height <= 0.25
    names = harvested.select(pl.col("description").str.extract_all(r"COUNTERPARTY_\d+").list.n_unique().unique())
    assert names.to_series().to_list() == [1]  # a remittance names several: no key
