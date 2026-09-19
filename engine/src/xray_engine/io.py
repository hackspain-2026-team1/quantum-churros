"""Dataset reading: fingerprint, typed parquet cache and table loading.

Works on any folder holding the eight CSVs of the challenge schema. Nothing
here depends on ``Params``: the cache is a faithful, typed copy of the source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

DEFAULT_CACHE_DIR = Path("artifacts/cache")

# Raw CSV headers, in file order, with the dtype every reader must force.
# Small folders have all-null columns, so nothing is ever inferred.
SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "groups": {
        "group_id": pl.String,
        "erp": pl.String,
        "n_companies_in_sample": pl.Int64,
    },
    "companies": {
        "company_id": pl.String,
        "group_id": pl.String,
        "country": pl.String,
        "currency": pl.String,
        "erp": pl.String,
        "created_at": pl.String,
    },
    "banking_products": {
        "product_id": pl.String,
        "company_id": pl.String,
        "label": pl.String,
        "type": pl.String,
        "bank_name": pl.String,
        "service": pl.String,
        "currency": pl.String,
        "created_at": pl.String,
    },
    "debt_products": {
        "product_id": pl.String,
        "company_id": pl.String,
        "label": pl.String,
        "type": pl.String,
        "bank_name": pl.String,
        "service": pl.String,
        "currency": pl.String,
        "created_at": pl.String,
        "granted": pl.Float64,
        "outstanding": pl.Float64,
        "liquidity": pl.Float64,
    },
    "debt_schedule_config": {
        "product_id": pl.String,
        "company_id": pl.String,
        "settlement_product_id": pl.String,
        "currency": pl.String,
        "amortization_type": pl.String,
        "interest_calc_method": pl.String,
        "amortising_frequency": pl.String,
        "granted_balance": pl.Float64,
        "outstanding_balance": pl.Float64,
        "total_periods": pl.Int64,
        "next_payment_date": pl.String,
        "last_payment_date": pl.String,
        "annual_interest_rate_or_spread": pl.Float64,
        "interest_type": pl.String,
    },
    "transactions": {
        "transaction_id": pl.String,
        "company_id": pl.String,
        "product_id": pl.String,
        "date": pl.String,
        "value_date": pl.String,
        "amount": pl.Float64,
        "exchange_rate": pl.Float64,
        "status": pl.String,
        "accounting_status": pl.String,
        "category": pl.String,
        "description": pl.String,
        "counterparty_id": pl.String,
    },
    "invoices": {
        "operation_id": pl.String,
        "company_id": pl.String,
        "document_type": pl.String,
        "issuance_date": pl.String,
        "due_date": pl.String,
        "payment_date": pl.String,
        "amount": pl.Float64,
        "pending_amount": pl.Float64,
        "currency": pl.String,
        "accounting_currency": pl.String,
        "exchange_rate": pl.Float64,
        "status": pl.String,
        "concept": pl.String,
        "counterparty_id": pl.String,
    },
    "balances": {
        "product_id": pl.String,
        "company_id": pl.String,
        "date": pl.String,
        "balance": pl.Float64,
        "available": pl.Float64,
        "granted": pl.Float64,
        "liquidity": pl.Float64,
        "countable": pl.Float64,
    },
}
TABLE_NAMES: tuple[str, ...] = tuple(SCHEMAS)
CSV_FILES: tuple[str, ...] = tuple(f"{name}.csv" for name in SCHEMAS)

# Columns of each cached parquet table (and of every ``Tables`` frame).
# Money is Int64 cents in the currency of the account or invoice:
# cents = round(amount * 100). Timestamps are truncated to dates.
CACHE_SCHEMAS: dict[str, dict[str, pl.DataType]] = {
    "groups": {
        "group_id": pl.String,
        "erp": pl.String,
        "n_companies_in_sample": pl.Int64,
    },
    "companies": {
        "company_id": pl.String,
        "group_id": pl.String,
        "country": pl.String,
        "currency": pl.String,
        "erp": pl.String,
        "created_at": pl.Date,
    },
    "banking_products": {
        "product_id": pl.String,
        "company_id": pl.String,
        "label": pl.String,
        "type": pl.String,
        "bank_name": pl.String,
        "service": pl.String,
        "currency": pl.String,
        "created_at": pl.Date,
    },
    "debt_products": {
        "product_id": pl.String,
        "company_id": pl.String,
        "label": pl.String,
        "type": pl.String,
        "bank_name": pl.String,
        "service": pl.String,
        "currency": pl.String,
        "created_at": pl.Date,
        "granted_cents": pl.Int64,  # negative = limit, as in the source
        "outstanding_cents": pl.Int64,  # negative = owed
        "liquidity_cents": pl.Int64,
    },
    "debt_schedule_config": {
        "product_id": pl.String,
        "company_id": pl.String,
        "settlement_product_id": pl.String,
        "currency": pl.String,
        "amortization_type": pl.String,
        "interest_calc_method": pl.String,
        "amortising_frequency": pl.String,
        "granted_cents": pl.Int64,
        "outstanding_cents": pl.Int64,
        "total_periods": pl.Int64,
        "next_payment_date": pl.Date,
        "last_payment_date": pl.Date,
        "annual_interest_rate_or_spread": pl.Float64,
        "interest_type": pl.String,
    },
    # pending rows are dropped; blank status is booked; blank category is "-".
    # value_date and exchange_rate are never used and are not cached.
    "transactions": {
        "transaction_id": pl.String,
        "company_id": pl.String,
        "product_id": pl.String,
        "date": pl.Date,
        "month": pl.Date,  # first day of the month of date
        "amount_cents": pl.Int64,
        "status": pl.String,
        "accounting_status": pl.String,
        "category": pl.String,
        "description": pl.String,
        "counterparty_id": pl.String,
    },
    # every document type is kept; cleaning filters. concept, exchange_rate and
    # accounting_currency are not cached.
    "invoices": {
        "operation_id": pl.String,
        "company_id": pl.String,
        "document_type": pl.String,
        "issuance_date": pl.Date,
        "due_date": pl.Date,
        "payment_date": pl.Date,
        "amount_cents": pl.Int64,  # signed: AR > 0, AP < 0
        "pending_cents": pl.Int64,
        "currency": pl.String,
        "status": pl.String,
        "counterparty_id": pl.String,
    },
    "balances": {
        "product_id": pl.String,
        "company_id": pl.String,
        "date": pl.Date,
        "balance_cents": pl.Int64,
        "available_cents": pl.Int64,
        "granted_cents": pl.Int64,  # negative = limit
        "liquidity_cents": pl.Int64,
        "countable_cents": pl.Int64,
    },
}


@dataclass(frozen=True)
class Window:
    """Scorable window derived from the data, never hard-coded."""

    first_month: date  # month of the earliest booked transaction
    last_month: date  # last complete month
    as_of: date  # extraction date: latest of booked transaction and balance dates


@dataclass(frozen=True)
class Tables:
    """Eager frames following ``CACHE_SCHEMAS``, plus dataset identity."""

    groups: pl.DataFrame
    companies: pl.DataFrame
    banking_products: pl.DataFrame
    debt_products: pl.DataFrame
    debt_schedule_config: pl.DataFrame
    transactions: pl.DataFrame
    invoices: pl.DataFrame
    balances: pl.DataFrame
    dataset_hash: str
    window: Window


def dataset_fingerprint(input_dir: Path) -> str:
    """sha256 over name + content of the eight CSVs, sorted by file name.

    Same algorithm as the backend ingestion, so both layers agree on the hash.
    Raises FileNotFoundError naming the missing files.
    """
    paths = [Path(input_dir) / name for name in CSV_FILES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing source files: {', '.join(missing)}")
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode())
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def count_csv_records(path: Path) -> int:
    """Records in a CSV (header excluded) counted with the stdlib ``csv`` reader.

    Oracle for the row-count assertion: descriptions hold quoted newlines, so
    physical lines overcount.
    """
    raise NotImplementedError


def derive_window(transactions: pl.DataFrame, balances: pl.DataFrame) -> Window:
    """Window from the cached transactions (booked rows only) and balances.

    ``as_of`` is the latest of the transaction and balance dates. ``last_month``
    is the month of ``as_of`` when that date is a month end, else the month
    before it. ``first_month`` is the month of the earliest transaction.
    Raises ValueError when no complete month exists.
    """
    raise NotImplementedError


def build_cache(input_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Write ``<cache_dir>/<dataset_hash>/<table>.parquet`` for the eight tables.

    Reads with ``pl.scan_csv(schema_overrides=SCHEMAS[table])`` (quoted
    newlines), asserts the parsed record count of every file against
    ``count_csv_records``, converts to ``CACHE_SCHEMAS`` and sinks to parquet.
    Also writes ``manifest.json`` with dataset_hash, per-table raw row counts,
    pending rows dropped and the window. Idempotent: an existing complete cache
    is returned untouched. Returns the cache folder.
    """
    raise NotImplementedError


def load_tables(input_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR) -> Tables:
    """Build the cache when missing and load it as ``Tables``.

    Row order of every frame is deterministic: sorted by its primary key
    (transaction_id, operation_id, product_id + date, ...), so shuffled input
    files give identical frames.
    """
    raise NotImplementedError
