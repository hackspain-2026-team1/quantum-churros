import polars as pl
import pytest

from xray_engine.scoring import build_monthly_features, score_features


def test_score_is_bounded_and_directional() -> None:
    features = pl.DataFrame(
        {
            "company_id": ["A", "A"],
            "group_id": ["G", "G"],
            "month": ["2026-08-01", "2026-09-01"],
            "cash_margin": [-0.2, 0.3],
            "collection_delay_days": [25.0, 8.0],
            "reconciled_rate": [0.7, 0.95],
            "pending_ratio": [0.4, 0.1],
            "counterparty_count": [4, 12],
            "transaction_count": [12, 30],
            "invoice_count": [4, 8],
        }
    )
    result = score_features(features, "fixture")
    assert result["score"].min() >= 0
    assert result["score"].max() <= 100
    assert result["trend"].to_list() == ["stable", "improving"]
    assert result["persistence_months"].to_list() == [0, 1]
    assert len(result["drivers"][1]) == 5
    assert 0 <= result["confidence"].min() <= result["confidence"].max() <= 1


def test_mixed_integer_and_decimal_invoice_amounts(tmp_path) -> None:
    (tmp_path / "companies.csv").write_text("company_id,group_id\nA,G\n")
    (tmp_path / "transactions.csv").write_text("transaction_id,company_id,product_id,date,value_date,amount,exchange_rate,status,accounting_status,category,description,counterparty_id\nT1,A,P1,2026-09-01,2026-09-01,100,1,booked,RECONCILIATION_COMPLETED,collection,test,C1\n")
    (tmp_path / "invoices.csv").write_text("operation_id,company_id,document_type,issuance_date,due_date,payment_date,amount,pending_amount,currency,accounting_currency,exchange_rate,status,concept,counterparty_id\nI1,A,invoice,2026-09-01,2026-09-10,2026-09-12,100,-12.56,EUR,EUR,1,paid,test,C1\n")
    result = build_monthly_features(tmp_path)
    assert result["pending_ratio"].item() == pytest.approx(0.1256)
