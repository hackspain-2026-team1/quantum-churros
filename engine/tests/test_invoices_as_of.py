"""Invoice facts are read as of each month end: a later payment never leaks back."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from xray_engine import cleaning, io
from xray_engine.features import invoice_states_as_of


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
        schema=cleaning.CLEAN_INVOICE_COLUMNS,
    )
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


@pytest.mark.xfail(raises=NotImplementedError, strict=False, reason="cleaning is a stub")
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
    clean = cleaning.invoices_as_of(invoices, companies, params, as_of=date(2026, 9, 1))
    assert dict(clean.schema) == cleaning.CLEAN_INVOICE_COLUMNS
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
