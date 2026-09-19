"""Invoice facts are read as of each month end: a later payment never leaks back."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from xray_engine import cleaning, invoices as invoices_module, io
from xray_engine.features import invoice_states_as_of
from xray_engine.invoices import CLEAN_INVOICE_COLUMNS, DBT_COLUMNS, clean_invoices, days_beyond_terms_as_of


def _clean_invoice(**values: object) -> dict[str, object]:
    row: dict[str, object] = {
        "operation_id": "I1", "company_id": "A", "group_id": "G", "counterparty_id": "C1",
        "side": "AR", "issuance_date": date(2026, 3, 1), "due_date": date(2026, 3, 10),
        "settled_date": date(2026, 5, 15), "amount_cents": 10_000, "currency": "EUR",
        "fx_rate": 1.0, "fx_excluded": False, "terms_days": 9, "stamped": False,
    }
    row.update(values)
    return row


def test_invoice_state_does_not_leak_future_payment() -> None:
    invoices = pl.DataFrame(
        [
            _clean_invoice(),
            _clean_invoice(operation_id="I2", side="AP", settled_date=None, amount_cents=2_500,
                           issuance_date=date(2026, 4, 20), due_date=date(2026, 5, 20)),
            _clean_invoice(operation_id="I3", issuance_date=date(2026, 4, 2),
                           due_date=date(2026, 4, 2), settled_date=date(2026, 4, 2)),
        ],
        schema=CLEAN_INVOICE_COLUMNS,
    )
    assert cleaning.CLEAN_INVOICE_COLUMNS is invoices_module.CLEAN_INVOICE_COLUMNS
    states = invoice_states_as_of(invoices, date(2026, 6, 1))
    receivable = {
        row["month"]: row for row in states.filter(pl.col("side") == "AR").to_dicts()
    }
    # paid on 2026-05-15: still open and overdue at the end of March and April
    assert receivable[date(2026, 3, 1)]["open_cents"] == 10_000
    assert receivable[date(2026, 3, 1)]["overdue_cents"] == 10_000
    assert receivable[date(2026, 4, 1)]["open_cents"] == 10_000
    assert receivable[date(2026, 4, 1)]["open_n"] == 1  # I3 settled inside April: never open
    assert date(2026, 5, 1) not in receivable and date(2026, 6, 1) not in receivable
    payable = {row["month"]: row for row in states.filter(pl.col("side") == "AP").to_dicts()}
    assert payable[date(2026, 4, 1)]["overdue_cents"] == 0
    assert payable[date(2026, 5, 1)]["overdue_cents"] == 2_500
    assert payable[date(2026, 6, 1)]["open_cents"] == 2_500

    # the same question asked earlier gives the same answer for the shared months
    earlier = invoice_states_as_of(invoices, date(2026, 4, 1))
    assert earlier.equals(states.filter(pl.col("month") <= date(2026, 4, 1)))


def test_settled_date_is_only_trusted_when_paid_in_full(params) -> None:
    def cached(operation_id: str, **values: object) -> dict[str, object]:
        row: dict[str, object] = {
            "operation_id": operation_id, "company_id": "A", "document_type": "invoice",
            "issuance_date": date(2026, 3, 1), "due_date": date(2026, 3, 31),
            "payment_date": date(2026, 4, 20), "amount_cents": 10_000, "pending_cents": 0,
            "currency": "EUR", "status": "paid", "counterparty_id": "C1",
        }
        row.update(values)
        return row

    invoices = pl.DataFrame(
        [
            cached("paid"),
            cached("payable", amount_cents=-4_000),
            cached("partial", pending_cents=2_000),
            cached("overdue", status="overdue", pending_cents=10_000, payment_date=date(2026, 3, 31)),
            cached("expected", payment_date=date(2026, 10, 5)),
            cached("stamped", due_date=date(2026, 3, 1), payment_date=date(2026, 3, 1)),
            cached("before_issue", payment_date=date(2026, 2, 1)),
            cached("due_before_issue", due_date=date(2026, 2, 1)),
            cached("cancelled", status="cancel"),
            cached("settlement_doc", document_type="paymentDocument"),
            cached("credit_note", document_type="note", amount_cents=-500),
            cached("foreign", currency="HUF"),
        ],
        schema=io.CACHE_SCHEMAS["invoices"],
    )
    companies = pl.DataFrame(
        [{"company_id": "A", "group_id": "G", "country": None, "currency": "EUR", "erp": None,
          "created_at": date(2024, 1, 1)}],
        schema=io.CACHE_SCHEMAS["companies"],
    )
    clean = clean_invoices(invoices, companies, params, as_of=date(2026, 9, 1))
    assert dict(clean.schema) == CLEAN_INVOICE_COLUMNS
    rows = {row["operation_id"]: row for row in clean.to_dicts()}
    assert set(rows) == {"paid", "payable", "partial", "overdue", "expected", "stamped", "foreign"}
    assert rows["paid"]["settled_date"] == date(2026, 4, 20) and rows["paid"]["side"] == "AR"
    assert rows["payable"]["side"] == "AP" and rows["payable"]["amount_cents"] == 4_000
    assert rows["partial"]["settled_date"] is None
    assert rows["overdue"]["settled_date"] is None
    assert rows["expected"]["settled_date"] is None
    assert rows["stamped"]["stamped"] and not rows["paid"]["stamped"]
    assert rows["paid"]["terms_days"] == 30 and rows["paid"]["group_id"] == "G"
    assert rows["foreign"]["fx_excluded"] and rows["foreign"]["fx_rate"] is None
    assert rows["paid"]["fx_rate"] == 1.0


def _payable(operation_id: str, due: date, settled: date | None, cents: int, **values: object) -> dict[str, object]:
    issued = values.pop("issued", date(2025, 12, 1))
    return _clean_invoice(
        operation_id=operation_id, side="AP", issuance_date=issued, due_date=due, settled_date=settled,
        amount_cents=cents, terms_days=(due - issued).days, **values,
    )


def test_days_beyond_terms_are_read_as_of_each_month_end(params) -> None:
    march, april = date(2026, 3, 1), date(2026, 4, 1)
    rows = [
        _payable("late", date(2026, 3, 10), date(2026, 3, 20), 10_000),
        _payable("open_until_may", date(2026, 3, 20), date(2026, 5, 15), 30_000),
        _payable("very_early", date(2026, 2, 1), date(2025, 12, 23), 20_000),  # -40 days, clipped to -30
        _payable("stamped", date(2026, 3, 5), date(2026, 3, 5), 50_000, issued=date(2026, 3, 5), stamped=True),
        _payable("dollars", date(2026, 3, 15), date(2026, 3, 25), 100_000, currency="USD", fx_rate=0.92),
        _payable("no_rate", date(2026, 3, 12), date(2026, 3, 12), 70_000, currency="HUF", fx_rate=None,
                 fx_excluded=True),
        _payable("too_old", date(2025, 12, 30), None, 900_000),  # due outside (T - 90 days, T] in March
        _payable("due_in_april", date(2026, 4, 10), date(2026, 4, 10), 40_000, issued=date(2026, 3, 11)),
        _payable("sister", date(2026, 3, 25), None, 100_000, company_id="B"),
        _clean_invoice(operation_id="receivable", due_date=date(2026, 3, 10), settled_date=date(2026, 3, 15),
                       issuance_date=date(2026, 2, 8), terms_days=30),
    ]
    frame = pl.DataFrame(rows, schema=CLEAN_INVOICE_COLUMNS)
    result = days_beyond_terms_as_of(frame, [march, april], params)
    assert dict(result.schema) == DBT_COLUMNS
    keys = ["entity_kind", "entity_id", "side", "month"]
    assert result.select(keys).rows() == sorted(result.select(keys).rows())
    found = {tuple(row[key] for key in keys): row for row in result.to_dicts()}

    a_march = found[("company", "A", "AP", march)]
    assert (a_march["n_all"], a_march["n"]) == (6, 4) and a_march["group_id"] == "G"
    assert a_march["amount"] == pytest.approx(1_520.0)
    assert a_march["days_beyond_terms"] == pytest.approx(7_500.0 / 1_520.0)  # 10, 11 (open), -30, 10
    assert a_march["neff"] == pytest.approx(1_520.0**2 / (100.0**2 + 300.0**2 + 200.0**2 + 920.0**2))
    assert a_march["stamped_share"] == pytest.approx(1 / 6)
    assert a_march["open_share"] == pytest.approx(300.0 / 1_520.0)

    a_april = found[("company", "A", "AP", april)]
    assert (a_april["n_all"], a_april["n"]) == (7, 5)
    assert a_april["days_beyond_terms"] == pytest.approx(16_500.0 / 1_920.0)  # the open invoice aged to 41
    assert a_april["open_share"] == pytest.approx(300.0 / 1_920.0)

    group = found[("group", "G", "AP", march)]  # members pooled; AP and AR never mixed
    assert (group["n_all"], group["n"]) == (7, 5)
    assert group["days_beyond_terms"] == pytest.approx((7_500.0 + 1_000.0 * 6) / 2_520.0)
    receivable = found[("company", "A", "AR", march)]
    assert (receivable["n"], receivable["days_beyond_terms"]) == (1, pytest.approx(5.0))
    assert receivable["neff"] == pytest.approx(1.0)
    assert ("company", "B", "AR", march) not in found  # no invoice in the window: no row

    # no look-ahead: March is the same when April and the May payment do not exist yet
    known_in_march = frame.filter(pl.col("operation_id") != "due_in_april").with_columns(
        pl.when(pl.col("settled_date") > date(2026, 3, 31)).then(None).otherwise(pl.col("settled_date"))
        .alias("settled_date")
    )
    assert days_beyond_terms_as_of(known_in_march, [march], params).equals(
        result.filter(pl.col("month") == march)
    )
    only_stamped = frame.filter(pl.col("operation_id") == "stamped")
    row = days_beyond_terms_as_of(only_stamped, [march], params).filter(pl.col("entity_kind") == "company")
    assert row.to_dicts()[0] | {"entity_id": "A"} == {
        "entity_kind": "company", "entity_id": "A", "group_id": "G", "month": march, "side": "AP",
        "n_all": 1, "n": 0, "neff": None, "amount": 0.0, "days_beyond_terms": None,
        "stamped_share": 1.0, "open_share": None,
    }
