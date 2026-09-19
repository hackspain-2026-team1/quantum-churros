from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Protocol

import polars as pl

from .contracts import IndustryClassification

CLASSIFIER_VERSION = "rules-v1"
MIN_TRANSACTIONS = 50

INDUSTRY_LABELS: dict[str, str] = {
    "financial_services": "Servicios financieros",
    "marketing_advertising": "Marketing y publicidad",
    "logistics_supply_chain": "Logística y cadena de suministro",
    "software": "Software",
    "professional_services": "Servicios profesionales",
    "business_services": "Servicios empresariales",
    "healthcare": "Sanidad",
    "manufacturing": "Manufactura",
    "technology_services": "Servicios tecnológicos",
    "energy_utilities": "Energía y utilities",
}

SIGNAL_COLUMNS = (
    "tx_total",
    "tx_collection_share",
    "tx_payroll_share",
    "tx_pos_share",
    "tx_bulk_collection_share",
    "tx_fee_share",
    "tx_transfer_share",
    "tx_uncategorized_share",
    "invoice_count",
    "invoice_ticket",
    "invoice_issued_ratio",
    "counterparty_count",
    "has_factoring",
    "has_confirming",
    "has_leasing",
    "has_tpv",
    "debt_product_count",
)

PAYROLL_CATEGORIES = ("salary", "tax", "social_security")


def dataset_fingerprint(input_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in sorted(
        (
            "companies.csv",
            "transactions.csv",
            "invoices.csv",
            "debt_products.csv",
            "banking_products.csv",
        )
    ):
        path = input_dir / name
        digest.update(name.encode())
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


# Columns the signals read, with the dtype forced on every reader: small folders
# have all-null columns, so nothing is inferred.
_CSV_COLUMNS: dict[str, dict[str, pl.DataType]] = {
    "companies": {"company_id": pl.String},
    "transactions": {"company_id": pl.String, "category": pl.String},
    "invoices": {"company_id": pl.String, "amount": pl.Float64, "counterparty_id": pl.String},
    "debt_products": {"company_id": pl.String, "type": pl.String},
    "banking_products": {"company_id": pl.String, "type": pl.String},
}


def _read_frames(input_dir: Path) -> dict[str, pl.DataFrame]:
    return {
        name: pl.read_csv(input_dir / f"{name}.csv", columns=list(columns), schema_overrides=columns)
        for name, columns in _CSV_COLUMNS.items()
    }


def _table_frames(tables: Any) -> dict[str, pl.DataFrame]:
    """Frames of ``io.Tables`` (preferred: every document type) or ``cleaning.CleanTables``.

    Booked rows only, money in cents. Clean invoices store magnitudes: the
    side gives the sign back.
    """
    invoices = tables.invoices
    if "amount" not in invoices.columns:
        amount = pl.col("amount_cents") / 100.0
        if "side" in invoices.columns:
            amount = pl.when(pl.col("side") == "AP").then(-amount).otherwise(amount)
        invoices = invoices.with_columns(amount.alias("amount"))
    products = getattr(tables, "products", None)
    if products is not None:  # union of both product files
        kinds = products.select("company_id", pl.col("product_type").alias("type"), "product_family")
        debt = kinds.filter(pl.col("product_family") == "debt")
        banking = kinds.filter(pl.col("product_family") == "banking")
    else:
        debt, banking = tables.debt_products, tables.banking_products
    return {
        "companies": tables.companies, "transactions": tables.transactions, "invoices": invoices,
        "debt_products": debt, "banking_products": banking,
    }


def build_company_signals(source: Path | str | Any) -> pl.DataFrame:
    """Signals per company from a dataset folder or from tables already in memory.

    A folder is read once, only the columns the signals need and with forced
    dtypes. Tables (``io.Tables`` or ``cleaning.CleanTables``) are used as they
    are, so the big files are not parsed again; they hold booked rows only.
    """
    frames = _read_frames(Path(source)) if isinstance(source, (str, Path)) else _table_frames(source)
    return company_signals(**frames)


def company_signals(
    companies: pl.DataFrame,
    transactions: pl.DataFrame,
    invoices: pl.DataFrame,
    debt_products: pl.DataFrame,
    banking_products: pl.DataFrame,
) -> pl.DataFrame:
    transactions = transactions.select(
        "company_id", pl.col("category").fill_null("-").alias("category")
    )
    invoices = invoices.select("company_id", "amount", "counterparty_id")
    debt = debt_products.select("company_id", "type")
    banking = banking_products.select("company_id", "type")
    companies = companies.select("company_id")

    tx_totals = transactions.group_by("company_id").agg(pl.len().alias("tx_total"))
    tx_shares = transactions.group_by("company_id").agg(
        pl.col("category").eq("collection").mean().fill_null(0.0).alias("tx_collection_share"),
        pl.col("category")
        .is_in(PAYROLL_CATEGORIES)
        .mean()
        .fill_null(0.0)
        .alias("tx_payroll_share"),
        pl.col("category").eq("pos_settlement").mean().fill_null(0.0).alias("tx_pos_share"),
        pl.col("category")
        .eq("bulk_collection")
        .mean()
        .fill_null(0.0)
        .alias("tx_bulk_collection_share"),
        pl.col("category").eq("fee").mean().fill_null(0.0).alias("tx_fee_share"),
        pl.col("category").eq("transfer").mean().fill_null(0.0).alias("tx_transfer_share"),
        pl.col("category").eq("-").mean().fill_null(0.0).alias("tx_uncategorized_share"),
    )

    invoice_features = (
        invoices.with_columns(
            pl.col("amount").cast(pl.Float64, strict=False).fill_null(0.0)
        )
        .group_by("company_id")
        .agg(
            pl.len().alias("invoice_count"),
            pl.col("amount").abs().mean().fill_null(0.0).alias("invoice_ticket"),
            (
                pl.col("amount").filter(pl.col("amount") > 0).len().truediv(pl.len())
            )
            .fill_null(0.0)
            .alias("invoice_issued_ratio"),
            pl.col("counterparty_id").n_unique().alias("counterparty_count"),
        )
    )

    debt_features = debt.group_by("company_id").agg(
        (pl.col("type") == "factoring").any().cast(pl.Int8).alias("has_factoring"),
        (pl.col("type") == "confirming").any().cast(pl.Int8).alias("has_confirming"),
        (pl.col("type") == "leasing").any().cast(pl.Int8).alias("has_leasing"),
        pl.len().alias("debt_product_count"),
    )

    banking_features = banking.group_by("company_id").agg(
        (pl.col("type") == "tpv").any().cast(pl.Int8).alias("has_tpv"),
    )

    return (
        companies.join(tx_totals, on="company_id", how="left")
        .join(tx_shares, on="company_id", how="left")
        .join(invoice_features, on="company_id", how="left")
        .join(debt_features, on="company_id", how="left")
        .join(banking_features, on="company_id", how="left")
        .fill_null(0)
        .rename({"company_id": "entity_id"})
    )


def _rule_predicates(frame: pl.DataFrame) -> pl.DataFrame:
    treasury = (pl.col("tx_uncategorized_share") > 0.40) & (
        pl.col("tx_transfer_share") > 0.20
    )
    return frame.with_columns(
        pl.when(pl.col("tx_total") < MIN_TRANSACTIONS)
        .then(pl.lit("insufficient_data"))
        .otherwise(pl.lit("signal"))
        .alias("source"),
        pl.when(pl.col("tx_total") < MIN_TRANSACTIONS)
        .then(pl.lit("business_services"))
        .when(
            ((pl.col("has_factoring") == 1) | (pl.col("has_confirming") == 1))
            & (pl.col("tx_collection_share") > 0.15)
        )
        .then(pl.lit("financial_services"))
        .when(
            (pl.col("tx_bulk_collection_share") > 0.02)
            & (pl.col("tx_collection_share") > 0.25)
            & (pl.col("invoice_count") > 500)
        )
        .then(pl.lit("logistics_supply_chain"))
        .when((pl.col("has_tpv") == 1) | (pl.col("tx_pos_share") > 0.04))
        .then(pl.lit("marketing_advertising"))
        .when(
            (pl.col("has_leasing") == 1)
            & (pl.col("invoice_ticket") > 5_000)
            & (pl.col("invoice_count") > 200)
        )
        .then(pl.lit("manufacturing"))
        .when(
            (pl.col("invoice_ticket") > 40_000)
            & (pl.col("tx_payroll_share") < 0.10)
            & (pl.col("invoice_count").is_between(50, 1000))
        )
        .then(pl.lit("software"))
        .when(
            (pl.col("tx_payroll_share") > 0.15)
            & (pl.col("invoice_count").is_between(150, 2000))
            & (pl.col("invoice_ticket") < 50_000)
        )
        .then(pl.lit("professional_services"))
        .when(
            (pl.col("tx_fee_share") > 0.08)
            & (pl.col("invoice_count") > 500)
            & (pl.col("counterparty_count") > 30)
        )
        .then(pl.lit("technology_services"))
        .when(
            (pl.col("debt_product_count") >= 3)
            & (pl.col("invoice_count") < 150)
            & (pl.col("tx_collection_share") < 0.15)
        )
        .then(pl.lit("energy_utilities"))
        .when(treasury)
        .then(pl.lit("business_services"))
        .otherwise(pl.lit("business_services"))
        .alias("industry_slug"),
    ).with_columns(
        pl.when(pl.col("source") == "insufficient_data")
        .then(pl.lit(0.0))
        .when(pl.col("industry_slug") == "financial_services")
        .then(pl.lit(0.70))
        .when(pl.col("industry_slug") == "logistics_supply_chain")
        .then(pl.lit(0.68))
        .when(pl.col("industry_slug") == "marketing_advertising")
        .then(pl.lit(0.65))
        .when(pl.col("industry_slug") == "manufacturing")
        .then(pl.lit(0.62))
        .when(pl.col("industry_slug") == "software")
        .then(pl.lit(0.60))
        .when(pl.col("industry_slug") == "professional_services")
        .then(pl.lit(0.58))
        .when(pl.col("industry_slug") == "technology_services")
        .then(pl.lit(0.55))
        .when(pl.col("industry_slug") == "energy_utilities")
        .then(pl.lit(0.52))
        .when(treasury)
        .then(pl.lit(0.55))
        .otherwise(pl.lit(0.40))
        .alias("confidence"),
        pl.when(pl.col("source") == "insufficient_data")
        .then(pl.lit("Datos insuficientes: menos de 50 transacciones"))
        .when(pl.col("industry_slug") == "financial_services")
        .then(pl.lit("Financiación (factoring/confirming) y cobro elevado"))
        .when(pl.col("industry_slug") == "logistics_supply_chain")
        .then(pl.lit("Cobros masivos, alto ratio de cobro y volumen de facturas"))
        .when(pl.col("industry_slug") == "marketing_advertising")
        .then(pl.lit("TPV o cobro POS dominante"))
        .when(pl.col("industry_slug") == "manufacturing")
        .then(pl.lit("Leasing, ticket alto y volumen medio de facturas"))
        .when(pl.col("industry_slug") == "software")
        .then(pl.lit("Ticket muy alto, baja nómina y facturación moderada"))
        .when(pl.col("industry_slug") == "professional_services")
        .then(pl.lit("Alta nómina y volumen medio de facturas"))
        .when(pl.col("industry_slug") == "technology_services")
        .then(pl.lit("Comisiones altas, muchas facturas y contrapartes"))
        .when(pl.col("industry_slug") == "energy_utilities")
        .then(pl.lit("Alta deuda, poca facturación y bajo cobro directo"))
        .when(treasury)
        .then(pl.lit("Empresa tesorera: transferencias y tx sin categorizar"))
        .otherwise(pl.lit("Perfil operativo genérico"))
        .alias("reason"),
    )


class ClassifierStrategy(Protocol):
    version: str

    def classify(
        self, signals: pl.DataFrame, dataset_hash: str
    ) -> list[IndustryClassification]: ...


class RulesClassifierStrategy:
    version = CLASSIFIER_VERSION

    def classify(
        self, signals: pl.DataFrame, dataset_hash: str
    ) -> list[IndustryClassification]:
        classified = _rule_predicates(signals)
        results: list[IndustryClassification] = []
        for row in classified.iter_rows(named=True):
            slug = row["industry_slug"]
            source: Literal["signal", "insufficient_data"] = row["source"]
            signal_payload = {
                key: float(row.get(key, 0) or 0)
                for key in SIGNAL_COLUMNS
                if key in row
            }
            results.append(
                IndustryClassification(
                    entity_id=row["entity_id"],
                    industry_slug=slug,
                    industry_label=INDUSTRY_LABELS[slug],
                    confidence=float(row["confidence"]),
                    source=source,
                    reason=row["reason"],
                    classifier_version=self.version,
                    dataset_hash=dataset_hash,
                    signals=signal_payload,
                )
            )
        return results


def classify_dataset(
    input_dir: Path,
    strategy: ClassifierStrategy | None = None,
) -> tuple[str, list[IndustryClassification]]:
    fingerprint = dataset_fingerprint(input_dir)
    classifier = strategy or RulesClassifierStrategy()
    signals = build_company_signals(input_dir)
    return fingerprint, classifier.classify(signals, fingerprint)


def classify_tables(
    tables: Any,
    strategy: ClassifierStrategy | None = None,
) -> dict[str, IndustryClassification]:
    """Classification per company_id from tables already in memory (context only)."""
    classifier = strategy or RulesClassifierStrategy()
    results = classifier.classify(build_company_signals(tables), tables.dataset_hash)
    return {item.entity_id: item for item in results}


def distribution(classifications: list[IndustryClassification]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in classifications:
        counts[item.industry_slug] = counts.get(item.industry_slug, 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))


def signals_to_json(signals: dict[str, float]) -> str:
    return json.dumps(signals, sort_keys=True)
