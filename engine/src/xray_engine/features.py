from __future__ import annotations

from pathlib import Path

import polars as pl

FEATURE_VERSION = "features-v2"
FORECAST_HORIZON_MONTHS = 3

CATEGORICAL_FEATURES = ["country", "currency", "erp"]
NUMERIC_FEATURES = [
    "cash_margin",
    "cash_margin_3m",
    "cash_margin_6m",
    "cash_margin_change_3m",
    "net_flow_3m",
    "net_flow_6m",
    "net_flow_volatility_6m",
    "inflow_3m",
    "outflow_3m",
    "inflow_change_3m",
    "collection_delay_days",
    "collection_delay_3m",
    "collection_delay_change_3m",
    "receivable_open_ratio",
    "receivable_overdue_ratio",
    "payable_overdue_ratio",
    "overdue_change_3m",
    "reconciled_rate",
    "counterparty_count",
    "counterparty_count_3m",
    "transaction_count",
    "invoice_count",
    "months_observed",
]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def _required(input_dir: Path, name: str) -> Path:
    path = input_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Required dataset file not found: {path}")
    return path


def _monthly_grid(
    companies: pl.DataFrame, minimum: object, maximum: object
) -> pl.DataFrame:
    months = pl.DataFrame(
        {
            "month": pl.date_range(
                minimum,
                maximum,
                interval="1mo",
                eager=True,
            )
        }
    )
    return companies.join(months, how="cross")


def _transaction_features(path: Path) -> tuple[pl.DataFrame, object, object]:
    transactions = pl.scan_csv(
        path,
        try_parse_dates=True,
        schema_overrides={"amount": pl.Float64, "exchange_rate": pl.Float64},
    ).with_columns(
        pl.col("date").cast(pl.Date).dt.truncate("1mo").alias("month"),
        pl.when(pl.col("amount") > 0)
        .then(pl.col("amount"))
        .otherwise(0.0)
        .alias("inflow"),
        pl.when(pl.col("amount") < 0)
        .then(-pl.col("amount"))
        .otherwise(0.0)
        .alias("outflow"),
    )
    bounds = transactions.select(
        pl.col("month").min().alias("minimum"),
        pl.col("month").max().alias("maximum"),
    ).collect()
    monthly = (
        transactions.group_by("company_id", "month")
        .agg(
            pl.col("inflow").sum(),
            pl.col("outflow").sum(),
            pl.col("amount").sum().alias("net_flow"),
            pl.len().alias("transaction_count"),
            pl.col("counterparty_id")
            .drop_nulls()
            .n_unique()
            .alias("counterparty_count"),
            (pl.col("accounting_status") == "RECONCILIATION_COMPLETED")
            .mean()
            .alias("reconciled_rate"),
        )
        .collect(engine="streaming")
    )
    return monthly, bounds["minimum"].item(), bounds["maximum"].item()


def _invoice_features(path: Path, maximum_month: object) -> pl.DataFrame:
    invoices = (
        pl.scan_csv(
            path,
            try_parse_dates=True,
            schema_overrides={
                "amount": pl.Float64,
                "pending_amount": pl.Float64,
                "exchange_rate": pl.Float64,
            },
        )
        .filter((pl.col("document_type") == "invoice") & (pl.col("status") != "cancel"))
        .select(
            "company_id",
            "counterparty_id",
            pl.col("issuance_date").cast(pl.Date),
            pl.col("due_date").cast(pl.Date),
            pl.col("payment_date").cast(pl.Date),
            pl.col("amount"),
        )
        .with_columns(
            pl.col("issuance_date").dt.truncate("1mo").alias("issuance_month"),
            pl.col("payment_date").dt.truncate("1mo").alias("payment_month"),
            pl.col("amount").abs().alias("absolute_amount"),
        )
        .collect(engine="streaming")
    )
    issued = invoices.group_by(
        "company_id", pl.col("issuance_month").alias("month")
    ).agg(
        pl.len().alias("invoice_count"),
        pl.col("absolute_amount").sum().alias("invoice_amount"),
    )
    paid = (
        invoices.filter(pl.col("payment_date").is_not_null())
        .with_columns(
            (pl.col("payment_date") - pl.col("due_date"))
            .dt.total_days()
            .clip(lower_bound=0)
            .alias("paid_delay_days")
        )
        .group_by("company_id", pl.col("payment_month").alias("month"))
        .agg(
            pl.col("paid_delay_days").median().alias("collection_delay_days"),
            pl.col("absolute_amount").sum().alias("paid_invoice_amount"),
        )
    )
    states = (
        invoices.with_columns(
            pl.date_ranges(
                pl.col("issuance_month"),
                pl.lit(maximum_month),
                interval="1mo",
                closed="both",
            ).alias("month")
        )
        .explode("month", empty_as_null=True)
        .with_columns(
            pl.col("month").dt.offset_by("1mo").dt.offset_by("-1d").alias("month_end")
        )
        .with_columns(
            (
                pl.col("payment_date").is_null()
                | (pl.col("payment_date") > pl.col("month_end"))
            ).alias("is_open")
        )
        .with_columns(
            (pl.col("is_open") & (pl.col("due_date") < pl.col("month_end"))).alias(
                "is_overdue"
            )
        )
        .group_by("company_id", "month")
        .agg(
            pl.when(pl.col("is_open") & (pl.col("amount") > 0))
            .then(pl.col("absolute_amount"))
            .otherwise(0.0)
            .sum()
            .alias("receivable_open_amount"),
            pl.when(pl.col("is_overdue") & (pl.col("amount") > 0))
            .then(pl.col("absolute_amount"))
            .otherwise(0.0)
            .sum()
            .alias("receivable_overdue_amount"),
            pl.when(pl.col("is_open") & (pl.col("amount") < 0))
            .then(pl.col("absolute_amount"))
            .otherwise(0.0)
            .sum()
            .alias("payable_open_amount"),
            pl.when(pl.col("is_overdue") & (pl.col("amount") < 0))
            .then(pl.col("absolute_amount"))
            .otherwise(0.0)
            .sum()
            .alias("payable_overdue_amount"),
        )
    )
    return issued.join(
        paid, on=["company_id", "month"], how="full", coalesce=True
    ).join(
        states,
        on=["company_id", "month"],
        how="full",
        coalesce=True,
    )


def _add_rolling_features(frame: pl.DataFrame) -> pl.DataFrame:
    frame = frame.with_columns(
        (
            pl.col("net_flow")
            / (pl.col("inflow") + pl.col("outflow")).clip(lower_bound=1.0)
        ).alias("cash_margin"),
        (
            pl.col("receivable_open_amount")
            / pl.col("inflow")
            .rolling_sum(3, min_samples=1)
            .over("company_id")
            .clip(lower_bound=1.0)
        )
        .clip(0, 10)
        .alias("receivable_open_ratio"),
        (
            pl.col("receivable_overdue_amount")
            / pl.col("receivable_open_amount").clip(lower_bound=1.0)
        )
        .clip(0, 1)
        .alias("receivable_overdue_ratio"),
        (
            pl.col("payable_overdue_amount")
            / pl.col("payable_open_amount").clip(lower_bound=1.0)
        )
        .clip(0, 1)
        .alias("payable_overdue_ratio"),
        pl.int_range(1, pl.len() + 1).over("company_id").alias("months_observed"),
    )
    return frame.with_columns(
        pl.col("cash_margin")
        .rolling_mean(3, min_samples=1)
        .over("company_id")
        .alias("cash_margin_3m"),
        pl.col("cash_margin")
        .rolling_mean(6, min_samples=1)
        .over("company_id")
        .alias("cash_margin_6m"),
        (pl.col("cash_margin") - pl.col("cash_margin").shift(3).over("company_id"))
        .fill_null(0.0)
        .alias("cash_margin_change_3m"),
        pl.col("net_flow")
        .rolling_sum(3, min_samples=1)
        .over("company_id")
        .alias("net_flow_3m"),
        pl.col("net_flow")
        .rolling_sum(6, min_samples=1)
        .over("company_id")
        .alias("net_flow_6m"),
        pl.col("net_flow")
        .rolling_std(6, min_samples=2)
        .over("company_id")
        .fill_null(0.0)
        .alias("net_flow_volatility_6m"),
        pl.col("inflow")
        .rolling_mean(3, min_samples=1)
        .over("company_id")
        .alias("inflow_3m"),
        pl.col("outflow")
        .rolling_mean(3, min_samples=1)
        .over("company_id")
        .alias("outflow_3m"),
        (
            (pl.col("inflow") - pl.col("inflow").shift(3).over("company_id"))
            / pl.col("inflow").shift(3).over("company_id").abs().clip(lower_bound=1.0)
        )
        .fill_null(0.0)
        .clip(-5, 5)
        .alias("inflow_change_3m"),
        pl.col("collection_delay_days")
        .rolling_mean(3, min_samples=1)
        .over("company_id")
        .alias("collection_delay_3m"),
        (
            pl.col("collection_delay_days")
            - pl.col("collection_delay_days").shift(3).over("company_id")
        )
        .fill_null(0.0)
        .alias("collection_delay_change_3m"),
        (
            pl.col("receivable_overdue_ratio")
            - pl.col("receivable_overdue_ratio").shift(3).over("company_id")
        )
        .fill_null(0.0)
        .alias("overdue_change_3m"),
        pl.col("counterparty_count")
        .rolling_mean(3, min_samples=1)
        .over("company_id")
        .alias("counterparty_count_3m"),
    )


def add_observed_health(frame: pl.DataFrame) -> pl.DataFrame:
    frame = frame.with_columns(
        ((pl.col("cash_margin_3m") + 1.0) / 2.0).clip(0, 1).alias("health_liquidity"),
        (1.0 - (pl.col("collection_delay_3m") / 60.0).clip(0, 1)).alias(
            "health_conversion"
        ),
        (1.0 - pl.col("receivable_overdue_ratio"))
        .clip(0, 1)
        .alias("health_receivables"),
        (
            1.0
            - (
                pl.col("net_flow_volatility_6m")
                / pl.col("inflow_3m").abs().clip(lower_bound=1.0)
            ).clip(0, 1)
        ).alias("health_stability"),
        (pl.col("counterparty_count_3m") / 20.0)
        .clip(0, 1)
        .alias("health_diversification"),
    )
    return frame.with_columns(
        (
            100
            * (
                0.30 * pl.col("health_liquidity")
                + 0.20 * pl.col("health_conversion")
                + 0.25 * pl.col("health_receivables")
                + 0.15 * pl.col("health_stability")
                + 0.10 * pl.col("health_diversification")
            )
        )
        .clip(0, 100)
        .alias("observed_health")
    )


def add_future_targets(
    frame: pl.DataFrame, horizon: int = FORECAST_HORIZON_MONTHS
) -> pl.DataFrame:
    future_values = [
        pl.col("observed_health").shift(-offset).over("company_id")
        for offset in range(1, horizon + 1)
    ]
    target = pl.mean_horizontal(future_values)
    available = (
        pl.col("observed_health").shift(-horizon).over("company_id").is_not_null()
    )
    return frame.with_columns(
        pl.when(available).then(target).otherwise(None).alias("future_health"),
        pl.when(available)
        .then(target - pl.col("observed_health"))
        .otherwise(None)
        .alias("future_delta"),
    ).with_columns(
        pl.when(pl.col("future_delta") >= 3.0)
        .then(pl.lit("improving"))
        .when(pl.col("future_delta") <= -3.0)
        .then(pl.lit("deteriorating"))
        .otherwise(pl.lit("stable"))
        .alias("future_direction")
    )


def build_monthly_features(
    input_dir: Path, include_targets: bool = True
) -> pl.DataFrame:
    companies = (
        pl.read_csv(_required(input_dir, "companies.csv"), try_parse_dates=True)
        .select("company_id", "group_id", "country", "currency", "erp")
        .with_columns(pl.col(CATEGORICAL_FEATURES).fill_null("UNKNOWN"))
    )
    transactions, minimum_month, maximum_month = _transaction_features(
        _required(input_dir, "transactions.csv")
    )
    invoices = _invoice_features(_required(input_dir, "invoices.csv"), maximum_month)
    numeric_defaults = {
        "inflow": 0.0,
        "outflow": 0.0,
        "net_flow": 0.0,
        "transaction_count": 0,
        "counterparty_count": 0,
        "reconciled_rate": 0.5,
        "invoice_count": 0,
        "invoice_amount": 0.0,
        "paid_invoice_amount": 0.0,
        "collection_delay_days": 0.0,
        "receivable_open_amount": 0.0,
        "receivable_overdue_amount": 0.0,
        "payable_open_amount": 0.0,
        "payable_overdue_amount": 0.0,
    }
    frame = (
        _monthly_grid(companies, minimum_month, maximum_month)
        .join(transactions, on=["company_id", "month"], how="left")
        .join(invoices, on=["company_id", "month"], how="left")
        .with_columns(
            [
                pl.col(column).fill_null(value)
                for column, value in numeric_defaults.items()
            ]
        )
        .sort("company_id", "month")
        .filter(pl.col("transaction_count").cum_sum().over("company_id") > 0)
    )
    frame = add_observed_health(_add_rolling_features(frame))
    return add_future_targets(frame) if include_targets else frame
