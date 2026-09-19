"""Invoice cleaning and as-of days beyond terms: hand-made rows, the synthetic dataset, the real one."""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from xray_engine import io
from xray_engine.invoices import (
    CLEAN_INVOICE_COLUMNS,
    DBT_COLUMNS,
    EVIDENCE_COLUMNS,
    SETTLED_LATE_COLUMNS,
    clean_invoices,
    days_beyond_terms_as_of,
    invoice_states_as_of,
    settled_late_summary,
    window_evidence_as_of,
)

KEYS = ["entity_kind", "entity_id", "side", "month"]
MARCH, APRIL, MAY, JUNE = (date(2026, month, 1) for month in (3, 4, 5, 6))


def _invoice(operation_id: str, due: date, settled: date | None, cents: int = 10_000, **values: object) -> dict:
    issued = values.pop("issued", due - timedelta(days=30))
    row: dict[str, object] = {
        "operation_id": operation_id, "company_id": "A", "group_id": "G", "counterparty_id": "C1",
        "side": "AP", "issuance_date": issued, "due_date": due, "settled_date": settled,
        "amount_cents": cents, "currency": "EUR", "fx_rate": 1.0, "fx_excluded": False,
        "terms_days": (due - issued).days, "stamped": False,
    }
    row.update(values)
    return row


def _frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=CLEAN_INVOICE_COLUMNS)


def _by_key(frame: pl.DataFrame) -> dict[tuple, dict]:
    return {tuple(row[key] for key in KEYS): row for row in frame.to_dicts()}


def _month_end(month: date) -> date:
    return (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _month_add(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _gate(params) -> pl.Expr:
    limits = params.invoices
    return (
        (pl.col("n") >= limits.min_invoices)
        & (pl.col("neff") >= limits.min_effective_n)
        & (pl.col("stamped_share") < limits.stamped_share_max)
    ).fill_null(False)


# --------------------------------------------------------------------------
# hand-made rows
# --------------------------------------------------------------------------


def test_window_is_counted_in_days_open_on_the_left_closed_on_the_right(params) -> None:
    assert params.invoices.window_days == 90
    frame = _frame(
        [
            _invoice("out_left", date(2025, 12, 31), None),  # exactly T - 90 days
            _invoice("first_day", date(2026, 1, 1), None),  # 89 days open
            _invoice("last_day", date(2026, 3, 31), None),  # due at T: open, not overdue
            _invoice("out_right", date(2026, 4, 1), None),
        ]
    )
    result = _by_key(days_beyond_terms_as_of(frame, [MARCH], params))
    row = result[("company", "A", "AP", MARCH)]
    assert (row["n_all"], row["n"]) == (2, 2)
    assert row["days_beyond_terms"] == pytest.approx((89 + 0) / 2)
    evidence = _by_key(window_evidence_as_of(frame, [MARCH], params))[("company", "A", "AP", MARCH)]
    assert (evidence["open_overdue_n"], evidence["settled_n"]) == (1, 0)
    # February has 28 days: the window is still 90 days, not three months
    february = _by_key(days_beyond_terms_as_of(frame, [date(2026, 2, 1)], params))
    assert february[("company", "A", "AP", date(2026, 2, 1))]["n_all"] == 2  # 12-31 and 01-01
    early = _frame([_invoice("x", date(2025, 11, 30), None), _invoice("y", date(2025, 12, 1), None)])
    assert days_beyond_terms_as_of(early, [date(2026, 2, 1)], params)["n_all"].to_list() == [1, 1]


def test_a_payment_after_month_end_does_not_exist_yet(params) -> None:
    paid_later = _frame([_invoice("late", date(2026, 3, 10), date(2026, 4, 20))])
    never_paid = _frame([_invoice("late", date(2026, 3, 10), None)])
    months = [MARCH, APRIL, MAY, JUNE]
    dbt = _by_key(days_beyond_terms_as_of(paid_later, months, params))
    evidence = _by_key(window_evidence_as_of(paid_later, months, params))
    march, april, may = (("company", "A", "AP", month) for month in (MARCH, APRIL, MAY))

    assert dbt[march]["days_beyond_terms"] == pytest.approx(21.0)  # open: aged to 03-31
    assert dbt[march]["open_share"] == pytest.approx(1.0)
    assert (evidence[march]["open_overdue_n"], evidence[march]["late_paid_n"]) == (1, 0)
    assert evidence[march]["open_overdue_amount"] == pytest.approx(100.0)
    assert dbt[april]["days_beyond_terms"] == dbt[may]["days_beyond_terms"] == pytest.approx(41.0)
    assert dbt[april]["open_share"] == 0.0
    assert (evidence[april]["open_overdue_n"], evidence[april]["late_paid_n"]) == (0, 1)
    assert evidence[april]["late_paid_amount"] == pytest.approx(100.0)
    assert ("company", "A", "AP", JUNE) not in dbt  # due 03-10 left the 90 days of June

    # March is the same whether or not the April payment is already in the file
    unknown = days_beyond_terms_as_of(never_paid, [MARCH], params)
    assert unknown.equals(days_beyond_terms_as_of(paid_later, [MARCH], params))
    assert window_evidence_as_of(never_paid, [MARCH], params).equals(
        window_evidence_as_of(paid_later, [MARCH], params)
    )


def test_each_invoice_is_clipped_before_weighting(params) -> None:
    low, high = params.invoices.clip_days
    frame = _frame(
        [
            _invoice("very_early", date(2026, 3, 20), date(2026, 1, 5), 30_000, issued=date(2025, 12, 1)),
            _invoice("late", date(2026, 3, 1), date(2026, 3, 21), 10_000),
        ]
    )
    row = _by_key(days_beyond_terms_as_of(frame, [MARCH], params))[("company", "A", "AP", MARCH)]
    assert row["days_beyond_terms"] == pytest.approx((300 * low + 100 * 20) / 400)
    assert low <= row["days_beyond_terms"] <= high


def test_kish_effective_n(params) -> None:
    due = date(2026, 3, 10)
    even = _frame([_invoice(f"i{index}", due, due, 5_000) for index in range(4)])
    lumpy = _frame([_invoice("big", due, due, 1_000_000)] + [_invoice(f"i{index}", due, due, 10_000) for index in range(3)])
    assert days_beyond_terms_as_of(even, [MARCH], params)["neff"].to_list() == pytest.approx([4.0, 4.0])
    expected = 10_300.0**2 / (10_000.0**2 + 3 * 100.0**2)
    assert days_beyond_terms_as_of(lumpy, [MARCH], params)["neff"].to_list() == pytest.approx([expected] * 2)
    assert expected < 1.1  # four invoices, one payment decision


def test_stamped_and_unconverted_rows_only_count(params) -> None:
    due = date(2026, 3, 10)
    frame = _frame(
        [
            _invoice("real", due, date(2026, 3, 15)),
            _invoice("stamped", due, due, issued=due, stamped=True),
            _invoice("no_rate", due, date(2026, 3, 30), currency="HUF", fx_rate=None, fx_excluded=True),
            _invoice("dollars", due, date(2026, 3, 25), 20_000, currency="USD", fx_rate=0.92),
        ]
    )
    row = _by_key(days_beyond_terms_as_of(frame, [MARCH], params))[("company", "A", "AP", MARCH)]
    assert (row["n_all"], row["n"]) == (4, 2)
    assert row["stamped_share"] == pytest.approx(0.25)
    assert row["amount"] == pytest.approx(100.0 + 184.0)
    assert row["days_beyond_terms"] == pytest.approx((100.0 * 5 + 184.0 * 15) / 284.0)


def test_sides_and_entities_stay_apart(params) -> None:
    due = date(2026, 3, 10)
    frame = _frame(
        [
            _invoice("a_ap", due, date(2026, 3, 20)),
            _invoice("a_ar", due, date(2026, 3, 12), side="AR"),
            _invoice("b_ap", due, None, company_id="B"),
            _invoice("other", due, date(2026, 3, 11), company_id="Z", group_id="H"),
        ]
    )
    result = days_beyond_terms_as_of(frame, [MARCH], params)
    assert dict(result.schema) == DBT_COLUMNS and list(result.schema) == list(DBT_COLUMNS)
    assert result.select(KEYS).rows() == sorted(result.select(KEYS).rows())
    found = _by_key(result)
    assert set(found) == {
        ("company", "A", "AP", MARCH), ("company", "A", "AR", MARCH), ("company", "B", "AP", MARCH),
        ("company", "Z", "AP", MARCH), ("group", "G", "AP", MARCH), ("group", "G", "AR", MARCH),
        ("group", "H", "AP", MARCH),
    }
    assert found[("group", "G", "AP", MARCH)]["days_beyond_terms"] == pytest.approx((10 + 21) / 2)
    assert found[("group", "G", "AR", MARCH)]["days_beyond_terms"] == pytest.approx(2.0)
    assert found[("group", "H", "AP", MARCH)]["group_id"] == "H"
    # group counts are the sum of the member counts
    members = result.filter(pl.col("entity_kind") == "company").group_by("group_id", "side", "month").agg(
        pl.col("n_all").sum(), pl.col("n").sum(), pl.col("amount").sum()
    )
    groups = result.filter(pl.col("entity_kind") == "group").select("group_id", "side", "month", "n_all", "n", "amount")
    assert members.sort("group_id", "side").equals(groups.sort("group_id", "side"))


def _random_invoices(seed: int, count: int = 400) -> pl.DataFrame:
    rng = random.Random(seed)
    rows = []
    for index in range(count):
        issued = date(2025, 10, 1) + timedelta(days=rng.randint(0, 200))
        due = issued + timedelta(days=rng.choice([0, 15, 30, 60]))
        settled = rng.choice([None, due, due + timedelta(days=rng.randint(-40, 80))])
        if settled is not None and settled < issued:
            settled = issued
        rows.append(
            _invoice(
                f"op{index:04d}", due, settled, rng.randint(1_000, 5_000_000), issued=issued,
                company_id=rng.choice("ABCD"), group_id="G", side=rng.choice(["AP", "AR"]),
                stamped=due == issued and settled == due,
            )
        )
    return _frame(rows)


def test_row_order_and_money_scale_do_not_matter(params) -> None:
    frame = _random_invoices(3)
    months = [date(2026, month, 1) for month in range(1, 7)]
    base = days_beyond_terms_as_of(frame, months, params)
    shuffled = frame.sample(fraction=1.0, shuffle=True, seed=11)
    assert days_beyond_terms_as_of(shuffled, months, params).equals(base)
    assert window_evidence_as_of(shuffled, months, params).equals(window_evidence_as_of(frame, months, params))

    scaled = days_beyond_terms_as_of(frame.with_columns(pl.col("amount_cents") * 7), months, params)
    for name in ("days_beyond_terms", "neff", "stamped_share", "open_share"):
        assert scaled[name].to_list() == pytest.approx(base[name].to_list(), rel=1e-12, abs=1e-12), name
    assert scaled["amount"].to_list() == pytest.approx((base["amount"] * 7).to_list(), rel=1e-12)
    assert scaled.select(KEYS + ["n_all", "n"]).equals(base.select(KEYS + ["n_all", "n"]))


def test_evidence_counts_are_consistent_with_the_average(params) -> None:
    frame = _random_invoices(5)
    months = [date(2026, month, 1) for month in range(1, 7)]
    dbt = days_beyond_terms_as_of(frame, months, params)
    evidence = window_evidence_as_of(frame, months, params)
    assert dict(evidence.schema) == EVIDENCE_COLUMNS and list(evidence.schema) == list(EVIDENCE_COLUMNS)
    assert evidence.select(KEYS + ["n"]).equals(dbt.select(KEYS + ["n"]))
    assert evidence.filter(pl.col("late_paid_n") > pl.col("settled_n")).is_empty()
    assert evidence.filter(pl.col("settled_n") + pl.col("open_overdue_n") > pl.col("n")).is_empty()
    assert evidence.filter(pl.col("zero_terms_open_n") > pl.col("zero_terms_n")).is_empty()
    assert evidence["late_paid_n"].sum() > 0 and evidence["open_overdue_n"].sum() > 0
    joined = dbt.join(evidence, on=KEYS)
    # nothing late and nothing overdue: the average cannot be positive
    clean_books = joined.filter((pl.col("late_paid_n") == 0) & (pl.col("open_overdue_n") == 0) & (pl.col("n") > 0))
    assert clean_books.filter(pl.col("days_beyond_terms") > 0).is_empty()
    assert joined.filter(pl.col("open_overdue_amount") > pl.col("amount") * pl.col("open_share") + 1e-6).is_empty()


def test_aged_invoices_tell_whether_the_erp_records_payments(params) -> None:
    frame = _frame(
        [
            _invoice("in_window", date(2026, 3, 10), None),
            _invoice("aged_open", date(2025, 10, 15), None),
            _invoice("aged_paid_in_april", date(2025, 11, 15), date(2026, 4, 2)),
            _invoice("aged_paid", date(2025, 12, 1), date(2025, 12, 1)),
            _invoice("aged_stamped", date(2025, 12, 5), date(2025, 12, 5), issued=date(2025, 12, 5), stamped=True),
            _invoice("just_left_the_window", date(2025, 12, 31), None),  # exactly T - 90 days in March
            _invoice("a_year_old", date(2025, 3, 31), None),  # exactly T - 365 days in March
        ]
    )
    evidence = _by_key(window_evidence_as_of(frame, [MARCH, APRIL], params))
    march, april = evidence[("company", "A", "AP", MARCH)], evidence[("company", "A", "AP", APRIL)]
    assert (march["n"], march["aged_n"], march["aged_open_n"]) == (1, 4, 3)
    assert (april["n"], april["aged_n"], april["aged_open_n"]) == (1, 4, 2)  # the April payment is known now
    assert evidence[("group", "G", "AP", MARCH)]["aged_open_n"] == 3
    alone = window_evidence_as_of(frame.filter(pl.col("operation_id") == "in_window"), [MARCH], params)
    assert alone["aged_n"].to_list() == [0, 0] and alone["aged_open_n"].to_list() == [0, 0]


def test_truncating_hand_made_history_keeps_every_earlier_month(params) -> None:
    frame = _random_invoices(9)
    months = [date(2026, month, 1) for month in range(1, 7)]
    full = days_beyond_terms_as_of(frame, months, params)
    for month in months:
        cut = _month_end(month)
        known = frame.filter(pl.col("issuance_date") <= cut).with_columns(
            pl.when(pl.col("settled_date") <= cut).then(pl.col("settled_date")).alias("settled_date")
        )
        earlier = [item for item in months if item <= month]
        assert days_beyond_terms_as_of(known, earlier, params).equals(full.filter(pl.col("month") <= month))


def test_empty_inputs_keep_the_schema(params) -> None:
    empty = pl.DataFrame(schema=CLEAN_INVOICE_COLUMNS)
    for frame, months in ((empty, [MARCH]), (_random_invoices(1, 20), [])):
        assert dict(days_beyond_terms_as_of(frame, months, params).schema) == DBT_COLUMNS
        assert days_beyond_terms_as_of(frame, months, params).is_empty()
        assert dict(window_evidence_as_of(frame, months, params).schema) == EVIDENCE_COLUMNS


def test_cleaning_rules_row_by_row(params) -> None:
    def cached(operation_id: str, **values: object) -> dict[str, object]:
        row: dict[str, object] = {
            "operation_id": operation_id, "company_id": "A", "document_type": "invoice",
            "issuance_date": date(2026, 3, 1), "due_date": date(2026, 3, 31),
            "payment_date": date(2026, 4, 20), "amount_cents": -10_000, "pending_cents": 0,
            "currency": "EUR", "status": "paid", "counterparty_id": "COUNTERPARTY_00042",
        }
        row.update(values)
        return row

    invoices = pl.DataFrame(
        [
            cached("z_paid"),
            cached("paid_on_extraction_day", payment_date=date(2026, 9, 1)),
            cached("paid_tomorrow", payment_date=date(2026, 9, 2)),
            cached("in_progress", status="payment_in_progress", pending_cents=-4_000),
            cached("order_without_pending", status="paymentOrder"),
            cached("blank_status", status=None),
            cached("unpaid_placeholder_before_issue", status="overdue", pending_cents=-10_000,
                   payment_date=date(2026, 2, 1)),
            cached("no_payment_date", payment_date=None),
            cached("same_day", due_date=date(2026, 3, 1), payment_date=date(2026, 3, 1)),
            cached("same_day_unpaid", due_date=date(2026, 3, 1), payment_date=date(2026, 3, 1),
                   status="overdue", pending_cents=-10_000),
            cached("zero", amount_cents=0),
            cached("no_due_date", due_date=None),
            cached("unknown_company", company_id="NOBODY"),
            cached("no_currency", currency=None),
        ],
        schema=io.CACHE_SCHEMAS["invoices"],
    )
    companies = pl.DataFrame(
        [{"company_id": "A", "group_id": "G", "country": None, "currency": "EUR", "erp": None,
          "created_at": date(2024, 1, 1)}],
        schema=io.CACHE_SCHEMAS["companies"],
    )
    clean = clean_invoices(invoices, companies, params, as_of=date(2026, 9, 1))
    assert dict(clean.schema) == CLEAN_INVOICE_COLUMNS and list(clean.schema) == list(CLEAN_INVOICE_COLUMNS)
    assert clean["operation_id"].to_list() == sorted(clean["operation_id"].to_list())
    rows = {row["operation_id"]: row for row in clean.to_dicts()}
    assert set(invoices["operation_id"]) - set(rows) == {"zero", "no_due_date"}
    settled = {key for key, row in rows.items() if row["settled_date"] is not None}
    assert settled == {"z_paid", "paid_on_extraction_day", "same_day", "unknown_company", "no_currency"}
    assert {key for key, row in rows.items() if row["stamped"]} == {"same_day"}
    assert rows["same_day_unpaid"]["terms_days"] == 0 and not rows["same_day_unpaid"]["stamped"]
    assert rows["unknown_company"]["group_id"] is None
    assert rows["no_currency"]["fx_excluded"] and rows["no_currency"]["fx_rate"] is None
    assert rows["z_paid"]["counterparty_id"] == "COUNTERPARTY_00042"
    assert all(row["side"] == "AP" and row["amount_cents"] == 10_000 for row in rows.values())

    # a company outside the master file keeps its company rows and joins no group
    dbt = days_beyond_terms_as_of(clean, [MARCH], params)
    assert dbt.filter(pl.col("entity_id") == "NOBODY")["entity_kind"].to_list() == ["company"]
    assert dbt.filter(pl.col("entity_kind") == "group")["entity_id"].to_list() == ["G"]


def test_settled_late_summary_reads_the_cached_rows(params) -> None:
    def cached(operation_id: str, cents: int, due: date, paid: date, **values: object) -> dict[str, object]:
        row: dict[str, object] = {
            "operation_id": operation_id, "company_id": "A", "document_type": "invoice",
            "issuance_date": date(2026, 3, 1), "due_date": due, "payment_date": paid,
            "amount_cents": cents, "pending_cents": 0, "currency": "EUR", "status": "paid",
            "counterparty_id": None,
        }
        row.update(values)
        return row

    due = date(2026, 3, 31)
    invoices = pl.DataFrame(
        [
            cached("late", -10_000, due, date(2026, 4, 2)),
            cached("late_usd", -10_000, due, date(2026, 4, 2), currency="USD"),
            cached("on_time", -10_000, due, due),
            cached("early", 10_000, due, date(2026, 3, 15)),
            cached("late_ar", 25_000, due, date(2026, 5, 1)),
            cached("partial", -10_000, due, date(2026, 4, 2), pending_cents=-100),
            cached("unpaid", -10_000, due, date(2026, 4, 2), status="overdue"),
            cached("note", -10_000, due, date(2026, 4, 2), document_type="note"),
        ],
        schema=io.CACHE_SCHEMAS["invoices"],
    )
    summary = settled_late_summary(invoices, params)
    assert dict(summary.schema) == SETTLED_LATE_COLUMNS
    assert summary.rows() == [("AP", 3, 2, pytest.approx(192.0)), ("AR", 2, 1, pytest.approx(250.0))]


# --------------------------------------------------------------------------
# dataset folders, read with an explicit schema (nothing is inferred)
# --------------------------------------------------------------------------


def _day(name: str) -> pl.Expr:
    return pl.col(name).str.slice(0, 10).str.to_date("%Y-%m-%d")


def _cents(name: str) -> pl.Expr:
    return (pl.col(name) * 100).round().cast(pl.Int64)


def _cached_invoices(folder: Path) -> pl.DataFrame:
    raw = pl.scan_csv(folder / "invoices.csv", schema_overrides=io.SCHEMAS["invoices"])
    frame = raw.select(
        "operation_id", "company_id", "document_type", _day("issuance_date"), _day("due_date"),
        _day("payment_date"), _cents("amount").alias("amount_cents"),
        _cents("pending_amount").alias("pending_cents"), "currency", "status", "counterparty_id",
    ).collect()
    assert dict(frame.schema) == io.CACHE_SCHEMAS["invoices"]
    return frame.sort("operation_id")


def _cached_companies(folder: Path) -> pl.DataFrame:
    raw = pl.read_csv(folder / "companies.csv", schema_overrides=io.SCHEMAS["companies"])
    return raw.with_columns(_day("created_at"))


def _extraction_date(folder: Path) -> date:
    balances = pl.read_csv(folder / "balances.csv", schema_overrides=io.SCHEMAS["balances"])
    return balances.select(_day("date").max()).item()


def _clean_folder(folder: Path, params, as_of: date) -> pl.DataFrame:
    return clean_invoices(_cached_invoices(folder), _cached_companies(folder), params, as_of)


def _months(first: date, last: date) -> list[date]:
    months = [first]
    while months[-1] < last:
        months.append(_month_add(months[-1], 1))
    return months


# --------------------------------------------------------------------------
# synthetic dataset
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synthetic_clean(synthetic, params) -> pl.DataFrame:
    return _clean_folder(synthetic.path, params, synthetic.as_of)


@pytest.fixture(scope="module")
def synthetic_months(synthetic) -> list[date]:
    return _months(synthetic.first_month, synthetic.last_month)


def test_synthetic_cleaning(synthetic, synthetic_clean) -> None:
    clean = synthetic_clean
    rows = {row["operation_id"]: row for row in clean.to_dicts()}
    assert not set(rows) & set(synthetic.ignored_invoice_ids)
    assert clean["group_id"].null_count() == 0
    for operation_id in synthetic.late_ap_invoice_ids + synthetic.late_ar_invoice_ids:
        assert rows[operation_id]["settled_date"] > rows[operation_id]["due_date"]
    for operation_id in synthetic.unpaid_ap_invoice_ids + synthetic.unpaid_ar_invoice_ids:
        assert rows[operation_id]["settled_date"] is None
    assert {rows[item]["side"] for item in synthetic.late_ap_invoice_ids} == {"AP"}
    assert {rows[item]["side"] for item in synthetic.unpaid_ar_invoice_ids} == {"AR"}
    assert clean.filter(pl.col("settled_date") > synthetic.as_of).is_empty()
    assert clean.filter(pl.col("amount_cents") <= 0).is_empty()

    stamped = clean.filter(pl.col("company_id") == synthetic.stamped_company_id)
    assert stamped.filter(pl.col("terms_days") != 0).is_empty()
    assert stamped.filter(pl.col("settled_date").is_not_null() != pl.col("stamped")).is_empty()
    assert clean.filter(pl.col("company_id") == synthetic.non_stamped_company_id)["stamped"].sum() == 0
    dollars = clean.filter(pl.col("currency") == "USD")
    assert dollars.height == 1 and dollars["fx_rate"][0] == 0.92 and not dollars["fx_excluded"][0]
    # partial payment: still open
    in_progress = clean.filter(pl.col("amount_cents") == 400_000)
    assert in_progress.height >= 1 and in_progress.filter(pl.col("settled_date").is_null()).height >= 1


def test_synthetic_regimes_reach_the_gate_inputs(synthetic, synthetic_clean, synthetic_months, params) -> None:
    dbt = days_beyond_terms_as_of(synthetic_clean, synthetic_months, params)
    companies = dbt.filter(pl.col("entity_kind") == "company")
    stamped = companies.filter(pl.col("entity_id") == synthetic.stamped_company_id)
    assert stamped.height > 0
    assert stamped.filter(pl.col("stamped_share") < params.invoices.stamped_share_max).is_empty()
    assert stamped.filter(_gate(params)).is_empty()

    real = companies.filter(pl.col("entity_id") == synthetic.non_stamped_company_id)
    assert real["stamped_share"].max() == 0.0
    settled_in = real.filter(pl.col("month") >= _month_add(synthetic.first_month, 4))
    assert settled_in.height == 2 * (len(synthetic_months) - 4)  # both sides, every month
    assert settled_in.filter(~_gate(params)).is_empty()
    low, high = params.invoices.clip_days
    assert dbt.filter(pl.col("days_beyond_terms").is_not_null())["days_beyond_terms"].is_between(low, high).all()

    groups = dbt.filter(pl.col("entity_kind") == "group")["entity_id"].unique().to_list()
    assert synthetic.no_invoice_group_id not in groups
    assert synthetic.short_history_group_id not in groups

    # more invoices late or unpaid: more days beyond terms on the same company
    weak = companies.filter((pl.col("entity_id") == synthetic.deteriorating_company_id) & (pl.col("side") == "AP"))
    first_year = weak.filter(pl.col("month") < date(2025, 9, 1))["days_beyond_terms"].mean()
    last_quarter = weak.filter(pl.col("month") >= _month_add(synthetic.last_month, -2))["days_beyond_terms"].mean()
    assert last_quarter > first_year


@pytest.mark.parametrize("month", [date(2025, 8, 1), date(2026, 2, 1), date(2026, 5, 1)])
def test_synthetic_truncation(synthetic, synthetic_clean, synthetic_months, datasets, params, tmp_path, month) -> None:
    cut_dir = datasets.truncate(synthetic.path, tmp_path / "cut", month)
    cut = _clean_folder(cut_dir, params, datasets.month_end(month))
    months = [item for item in synthetic_months if item <= month]
    full = days_beyond_terms_as_of(synthetic_clean, synthetic_months, params)
    assert days_beyond_terms_as_of(cut, months, params).equals(full.filter(pl.col("month") <= month))
    evidence = window_evidence_as_of(synthetic_clean, synthetic_months, params)
    assert window_evidence_as_of(cut, months, params).equals(evidence.filter(pl.col("month") <= month))
    assert invoice_states_as_of(cut, month).equals(
        invoice_states_as_of(synthetic_clean, synthetic.last_month).filter(pl.col("month") <= month)
    )


def test_synthetic_isolation_shuffle_and_scale(
    synthetic, synthetic_clean, synthetic_months, datasets, params, tmp_path
) -> None:
    full = days_beyond_terms_as_of(synthetic_clean, synthetic_months, params)
    group_id = synthetic.late_member_group_id
    alone = _clean_folder(datasets.filter(synthetic.path, tmp_path / "alone", [group_id]), params, synthetic.as_of)
    assert days_beyond_terms_as_of(alone, synthetic_months, params).equals(
        full.filter(pl.col("group_id") == group_id)
    )
    shuffled = _clean_folder(datasets.shuffle(synthetic.path, tmp_path / "shuffled"), params, synthetic.as_of)
    assert shuffled.equals(synthetic_clean)

    scaled = _clean_folder(datasets.scale(synthetic.path, tmp_path / "scaled", 3), params, synthetic.as_of)
    tripled = days_beyond_terms_as_of(scaled, synthetic_months, params)
    assert tripled.select(KEYS + ["n_all", "n"]).equals(full.select(KEYS + ["n_all", "n"]))
    for name in ("days_beyond_terms", "neff", "stamped_share", "open_share"):
        assert tripled[name].to_list() == pytest.approx(full[name].to_list(), rel=1e-9, abs=1e-9), name
    assert tripled["amount"].to_list() == pytest.approx((full["amount"] * 3).to_list(), rel=1e-9)


# --------------------------------------------------------------------------
# real dataset: aggregate invariants only
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real(real_data_dir, params) -> dict:
    as_of = _extraction_date(real_data_dir)
    last = as_of.replace(day=1) if as_of == _month_end(as_of) else _month_add(as_of.replace(day=1), -1)
    cached = _cached_invoices(real_data_dir)
    clean = clean_invoices(cached, _cached_companies(real_data_dir), params, as_of)
    months = _months(_month_add(last, -23), last)
    return {
        "cached": cached, "clean": clean, "months": months, "last": last, "as_of": as_of,
        "dbt": days_beyond_terms_as_of(clean, months, params),
        "groups": pl.read_csv(real_data_dir / "groups.csv", schema_overrides=io.SCHEMAS["groups"]),
    }


@pytest.mark.dataset
def test_real_headline_supplier_invoices_settled_late(real, params) -> None:
    assert real["cached"].height == 897_894
    summary = {row["side"]: row for row in settled_late_summary(real["cached"], params).to_dicts()}
    assert summary["AP"]["settled_late_n"] == pytest.approx(121_989, rel=0.01)
    assert summary["AR"]["settled_late_n"] == pytest.approx(78_153, rel=0.01)
    assert 0.33 < summary["AP"]["settled_late_n"] / summary["AP"]["marked_paid_n"] < 0.38
    # what the score may read: no expected dates, no impossible dates
    clean = real["clean"]
    late = clean.filter((pl.col("side") == "AP") & (pl.col("settled_date") > pl.col("due_date"))).height
    assert 0.90 * summary["AP"]["settled_late_n"] < late <= summary["AP"]["settled_late_n"]


@pytest.mark.dataset
def test_real_cleaning_invariants(real) -> None:
    clean, cached = real["clean"], real["cached"]
    assert real["last"] == date(2026, 8, 1)
    invoices = cached.filter(pl.col("document_type") == "invoice").height
    assert 0.93 * invoices < clean.height < 0.97 * invoices  # cancelled, zero and impossible dates
    assert clean["operation_id"].is_unique().all() and clean["operation_id"].is_sorted()
    assert clean["group_id"].null_count() == 0
    assert clean.filter(pl.col("settled_date") > real["as_of"]).is_empty()
    assert clean.filter(pl.col("due_date") < pl.col("issuance_date")).is_empty()
    assert clean.filter(pl.col("settled_date") < pl.col("issuance_date")).is_empty()
    stamped = clean.filter("stamped").group_by("side").len()
    counts = dict(zip(stamped["side"], stamped["len"]))
    assert counts["AP"] == pytest.approx(68_706, rel=0.01) and counts["AR"] == pytest.approx(56_646, rel=0.01)
    assert clean["fx_excluded"].mean() < 0.01


@pytest.mark.dataset
def test_real_share_of_groups_scorable_on_punctuality(real, params) -> None:
    n_groups = real["groups"].height
    assert n_groups == 250
    last = real["dbt"].filter((pl.col("entity_kind") == "group") & (pl.col("month") == real["last"]))
    passing = last.filter(_gate(params))
    share = {side: passing.filter(pl.col("side") == side).height / n_groups for side in ("AP", "AR")}
    assert 0.30 < share["AP"] < 0.50
    assert 0.25 < share["AR"] < 0.45
    assert share["AR"] < share["AP"]
    # no invoice due in the window is the main reason, not the gate
    with_rows = {side: last.filter(pl.col("side") == side).height / n_groups for side in ("AP", "AR")}
    assert 0.55 < with_rows["AP"] < 0.70 and 0.50 < with_rows["AR"] < 0.65
    for side in ("AP", "AR"):
        days = passing.filter(pl.col("side") == side)["days_beyond_terms"]
        assert 5 < days.median() < 20
        assert days.quantile(0.05) > -15 and days.quantile(0.95) < 60


@pytest.mark.dataset
def test_real_aggregates_are_coherent(real, params) -> None:
    dbt = real["dbt"]
    low, high = params.invoices.clip_days
    measured = dbt.filter(pl.col("n") > 0)
    assert measured["days_beyond_terms"].is_between(low, high).all()
    assert measured.filter(pl.col("neff") > pl.col("n") + 1e-9).is_empty()
    assert measured.filter(pl.col("neff") < 1 - 1e-9).is_empty()
    assert dbt.filter(pl.col("n") > pl.col("n_all")).is_empty()
    assert dbt["stamped_share"].is_between(0, 1).all() and measured["open_share"].is_between(0, 1 + 1e-9).all()
    empty = dbt.filter(pl.col("n") == 0)
    assert empty.select(pl.col("days_beyond_terms", "neff", "open_share").is_null().all()).row(0) == (True,) * 3
    members = (
        dbt.filter(pl.col("entity_kind") == "company")
        .group_by(pl.col("group_id").alias("entity_id"), "side", "month")
        .agg(pl.col("n_all").sum(), pl.col("n").sum())
        .sort("entity_id", "side", "month")
    )
    groups = dbt.filter(pl.col("entity_kind") == "group").select("entity_id", "side", "month", "n_all", "n")
    assert members.equals(groups.sort("entity_id", "side", "month"))


@pytest.mark.dataset
def test_real_months_do_not_read_the_future(real, params) -> None:
    clean, full = real["clean"], real["dbt"]
    for month in (real["months"][8], real["months"][17]):
        cut = _month_end(month)
        known = clean.filter(pl.col("issuance_date") <= cut).with_columns(
            pl.when(pl.col("settled_date") <= cut).then(pl.col("settled_date")).alias("settled_date")
        )
        months = [item for item in real["months"] if item <= month]
        assert days_beyond_terms_as_of(known, months, params).equals(full.filter(pl.col("month") <= month))


@pytest.mark.dataset
def test_real_sixty_groups_alone_equal_the_full_run(real, params) -> None:
    ids = sorted(real["groups"]["group_id"].to_list())
    chosen = random.Random(60).sample(ids, 60)
    alone = days_beyond_terms_as_of(real["clean"].filter(pl.col("group_id").is_in(chosen)), real["months"], params)
    assert alone.equals(real["dbt"].filter(pl.col("group_id").is_in(chosen)))


@pytest.mark.dataset
def test_real_unrecorded_payments_are_a_regime_of_the_erp(real, params) -> None:
    """Groups whose year-old invoices are nearly all open look late only because
    nobody records the payments: a minority, far from the rest of the groups."""
    evidence = window_evidence_as_of(real["clean"], [real["last"]], params)
    last = real["dbt"].filter((pl.col("entity_kind") == "group") & (pl.col("month") == real["last"]))
    scored = last.filter(_gate(params)).join(evidence.select(KEYS + ["aged_n", "aged_open_n"]), on=KEYS)
    for side in ("AP", "AR"):
        known = scored.filter((pl.col("side") == side) & (pl.col("aged_n") >= 20))
        unrecorded = pl.col("aged_open_n") >= 0.8 * pl.col("aged_n")
        regime, rest = known.filter(unrecorded), known.filter(~unrecorded)
        assert 0.05 < regime.height / known.height < 0.25
        assert rest.filter(pl.col("aged_open_n") <= 0.2 * pl.col("aged_n")).height > 0.5 * rest.height
        assert regime["days_beyond_terms"].median() > rest["days_beyond_terms"].median() + 10
