from datetime import date

import polars as pl
import pytest
from xray_engine.features import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
    add_future_targets,
    build_monthly_features,
)
from xray_engine.modeling import group_temporal_split, score_with_model, train_model


def test_invoice_state_does_not_leak_future_payment(tmp_path) -> None:
    (tmp_path / "companies.csv").write_text(
        "company_id,group_id,country,currency,erp,created_at\nA,G,ES,EUR,sap,2024-01-01\n"
    )
    (tmp_path / "transactions.csv").write_text(
        "transaction_id,company_id,product_id,date,value_date,amount,exchange_rate,status,accounting_status,category,description,counterparty_id\n"
        "T1,A,P1,2026-09-01,2026-09-01,100,1,booked,RECONCILIATION_COMPLETED,collection,test,C1\n"
        "T2,A,P1,2026-10-01,2026-10-01,100,1,booked,RECONCILIATION_COMPLETED,collection,test,C1\n"
        "T3,A,P1,2026-11-01,2026-11-01,100,1,booked,RECONCILIATION_COMPLETED,collection,test,C1\n"
    )
    (tmp_path / "invoices.csv").write_text(
        "operation_id,company_id,document_type,issuance_date,due_date,payment_date,amount,pending_amount,currency,accounting_currency,exchange_rate,status,concept,counterparty_id\n"
        "I1,A,invoice,2026-09-01,2026-09-10,2026-11-15,100,0,EUR,EUR,1,paid,test,C1\n"
    )
    result = build_monthly_features(tmp_path, include_targets=False)
    september = result.filter(pl.col("month") == date(2026, 9, 1)).row(0, named=True)
    october = result.filter(pl.col("month") == date(2026, 10, 1)).row(0, named=True)
    november = result.filter(pl.col("month") == date(2026, 11, 1)).row(0, named=True)
    assert september["collection_delay_days"] == 0
    assert october["collection_delay_days"] == 0
    assert september["receivable_open_amount"] == 100
    assert october["receivable_overdue_amount"] == 100
    assert november["receivable_open_amount"] == 0
    assert november["collection_delay_days"] == 66


def test_future_target_uses_only_subsequent_months() -> None:
    frame = pl.DataFrame(
        {"company_id": ["A"] * 5, "observed_health": [40.0, 50.0, 60.0, 70.0, 80.0]}
    )
    result = add_future_targets(frame, horizon=3)
    assert result["future_health"][0] == pytest.approx(60.0)
    assert result["future_delta"][0] == pytest.approx(20.0)
    assert result["future_health"][2] is None


def _training_fixture() -> pl.DataFrame:
    rows = []
    months = [date(2025, month, 1) for month in range(1, 10)]
    for group_index in range(8):
        for month_index, month in enumerate(months):
            observed = (
                42.0
                + group_index * 2.0
                + month_index * (1.0 if group_index % 2 == 0 else -0.7)
            )
            row = {
                "company_id": f"C{group_index}",
                "group_id": f"G{group_index}",
                "month": month,
                "observed_health": observed,
                "future_health": observed + (4.0 if group_index % 2 == 0 else -4.0),
            }
            for feature_index, feature in enumerate(NUMERIC_FEATURES):
                row[feature] = observed / 100.0 + feature_index * 0.01
            for feature in CATEGORICAL_FEATURES:
                row[feature] = (
                    "ES"
                    if feature == "country"
                    else "EUR"
                    if feature == "currency"
                    else "sap"
                )
            rows.append(row)
    return pl.DataFrame(rows)


def test_group_temporal_split_is_disjoint_and_forward() -> None:
    train, validation, details = group_temporal_split(
        _training_fixture(), validation_months=3, validation_group_fraction=0.25
    )
    assert set(train["group_id"].unique()).isdisjoint(
        set(validation["group_id"].unique())
    )
    assert train["month"].max() < validation["month"].min()
    assert details["validation_groups"] == 2


def test_training_scoring_and_shap_decomposition(tmp_path) -> None:
    features = _training_fixture()
    metadata = train_model(features, tmp_path, "fixture", iterations=50, seed=7)
    scored = score_with_model(features.drop("future_health"), tmp_path, "fixture")
    first = scored.row(0, named=True)
    explained = (
        0.55 * first["observed_score"]
        + 0.45 * first["shap_base_value"]
        + sum(driver["contribution"] for driver in first["drivers"])
        + first["explanation_residual"]
    )
    assert metadata["feature_version"] == "features-v2"
    assert set(MODEL_FEATURES) == set(metadata["model_features"])
    assert 0 <= scored["score"].min() <= scored["score"].max() <= 100
    assert 0 <= scored["confidence"].min() <= scored["confidence"].max() <= 1
    assert first["score"] == pytest.approx(explained, abs=0.03)
    assert first["drivers"]
