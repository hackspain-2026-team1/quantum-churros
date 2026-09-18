from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl


FEATURE_VERSION = "features-v1"
MODEL_VERSION = "baseline-v1"


def _dataset_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.name.encode())
        digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()[:16]


def _required(input_dir: Path, name: str) -> Path:
    path = input_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Required dataset file not found: {path}")
    return path


def build_monthly_features(input_dir: Path) -> pl.DataFrame:
    transaction_path = _required(input_dir, "transactions.csv")
    invoice_path = _required(input_dir, "invoices.csv")
    company_path = _required(input_dir, "companies.csv")

    companies = pl.scan_csv(company_path).select("company_id", "group_id")
    transactions = (
        pl.scan_csv(transaction_path, try_parse_dates=True, schema_overrides={"amount": pl.Float64, "exchange_rate": pl.Float64})
        .with_columns(
            pl.col("date").dt.truncate("1mo").alias("month"),
            pl.when(pl.col("amount") > 0).then(pl.col("amount")).otherwise(0).alias("inflow"),
            pl.when(pl.col("amount") < 0).then(-pl.col("amount")).otherwise(0).alias("outflow"),
        )
        .group_by("company_id", "month")
        .agg(
            pl.col("inflow").sum(),
            pl.col("outflow").sum(),
            pl.col("amount").sum().alias("net_flow"),
            pl.len().alias("transaction_count"),
            pl.col("counterparty_id").n_unique().alias("counterparty_count"),
            (pl.col("accounting_status") == "RECONCILIATION_COMPLETED").mean().alias("reconciled_rate"),
        )
    )
    invoices = (
        pl.scan_csv(invoice_path, try_parse_dates=True, schema_overrides={"amount": pl.Float64, "pending_amount": pl.Float64, "exchange_rate": pl.Float64})
        .with_columns(
            pl.col("issuance_date").dt.truncate("1mo").alias("month"),
            (pl.col("payment_date") - pl.col("due_date")).dt.total_days().clip(lower_bound=0).alias("late_days"),
        )
        .group_by("company_id", "month")
        .agg(
            pl.col("late_days").median().fill_null(0).alias("collection_delay_days"),
            (pl.col("pending_amount").abs().sum() / pl.col("amount").abs().sum().clip(lower_bound=1)).alias("pending_ratio"),
            pl.len().alias("invoice_count"),
        )
    )
    return (
        transactions.join(invoices, on=["company_id", "month"], how="left")
        .join(companies, on="company_id", how="left")
        .with_columns(
            (pl.col("net_flow") / (pl.col("inflow") + pl.col("outflow")).clip(lower_bound=1)).alias("cash_margin"),
            pl.col("collection_delay_days").fill_null(0),
            pl.col("pending_ratio").fill_null(0),
            pl.col("invoice_count").fill_null(0),
        )
        .sort("company_id", "month")
        .collect(engine="streaming")
    )


def score_features(features: pl.DataFrame, dataset_hash: str) -> pl.DataFrame:
    scored = features.with_columns(
        ((pl.col("cash_margin") + 1) / 2).clip(0, 1).alias("liquidity"),
        (1 - (pl.col("collection_delay_days") / 45).clip(0, 1)).alias("conversion"),
        pl.col("reconciled_rate").fill_null(0.5).clip(0, 1).alias("stability"),
        (1 - pl.col("pending_ratio").clip(0, 1)).alias("debt"),
        (pl.col("counterparty_count") / 20).clip(0, 1).alias("concentration"),
    ).with_columns(
        (100 * (0.28 * pl.col("liquidity") + 0.24 * pl.col("conversion") + 0.2 * pl.col("debt") + 0.18 * pl.col("stability") + 0.1 * pl.col("concentration"))).round(2).alias("score")
    )
    scored = scored.with_columns(
        pl.col("score").diff().over("company_id").fill_null(0).round(2).alias("delta"),
        pl.when(pl.col("score").diff().over("company_id") > 2).then(pl.lit("improving")).when(pl.col("score").diff().over("company_id") < -2).then(pl.lit("deteriorating")).otherwise(pl.lit("stable")).alias("trend"),
        (0.6 * (pl.col("transaction_count") / 80).clip(0, 1) + 0.4 * (pl.col("invoice_count") / 20).clip(0, 1)).round(3).alias("confidence"),
        pl.lit(FEATURE_VERSION).alias("feature_version"),
        pl.lit(MODEL_VERSION).alias("model_version"),
        pl.lit(dataset_hash).alias("dataset_hash"),
    )
    scored = scored.with_columns(pl.col("trend").rle_id().over("company_id").alias("_trend_run")).with_columns(
        pl.when(pl.col("trend") == "stable").then(0).otherwise(pl.int_range(1, pl.len() + 1).over(["company_id", "_trend_run"])).alias("persistence_months"),
        pl.when(pl.col("trend") == "stable").then(None).otherwise(pl.col("month").min().over(["company_id", "_trend_run"])).alias("detected_since"),
        pl.concat_list(
            [
                pl.struct(feature=pl.lit("liquidity"), label=pl.lit("Liquidez"), direction=pl.when(pl.col("liquidity") >= 0.5).then(pl.lit("positive")).otherwise(pl.lit("negative")), contribution=((pl.col("liquidity") - 0.5) * 28).round(2), observed=pl.col("liquidity").round(3), baseline=pl.lit(0.5), evidence=pl.lit("Margen de caja mensual frente al volumen de entradas y salidas.")),
                pl.struct(feature=pl.lit("conversion"), label=pl.lit("Conversión de caja"), direction=pl.when(pl.col("conversion") >= 0.5).then(pl.lit("positive")).otherwise(pl.lit("negative")), contribution=((pl.col("conversion") - 0.5) * 24).round(2), observed=pl.col("conversion").round(3), baseline=pl.lit(0.5), evidence=pl.lit("Retraso de cobro observado frente al umbral de 45 días.")),
                pl.struct(feature=pl.lit("debt"), label=pl.lit("Presión financiera"), direction=pl.when(pl.col("debt") >= 0.5).then(pl.lit("positive")).otherwise(pl.lit("negative")), contribution=((pl.col("debt") - 0.5) * 20).round(2), observed=pl.col("debt").round(3), baseline=pl.lit(0.5), evidence=pl.lit("Importe pendiente de facturas frente al volumen facturado.")),
                pl.struct(feature=pl.lit("stability"), label=pl.lit("Estabilidad"), direction=pl.when(pl.col("stability") >= 0.5).then(pl.lit("positive")).otherwise(pl.lit("negative")), contribution=((pl.col("stability") - 0.5) * 18).round(2), observed=pl.col("stability").round(3), baseline=pl.lit(0.5), evidence=pl.lit("Calidad de conciliación de los movimientos bancarios.")),
                pl.struct(feature=pl.lit("concentration"), label=pl.lit("Diversificación"), direction=pl.when(pl.col("concentration") >= 0.5).then(pl.lit("positive")).otherwise(pl.lit("negative")), contribution=((pl.col("concentration") - 0.5) * 10).round(2), observed=pl.col("concentration").round(3), baseline=pl.lit(0.5), evidence=pl.lit("Número de contrapartes activas durante el mes.")),
            ]
        ).alias("drivers"),
    )
    return scored.drop("_trend_run")


def score_dataset(input_dir: Path) -> pl.DataFrame:
    paths = [_required(input_dir, name) for name in ("companies.csv", "transactions.csv", "invoices.csv")]
    return score_features(build_monthly_features(input_dir), _dataset_hash(paths))
