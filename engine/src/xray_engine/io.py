"""Dataset reading: fingerprint, typed parquet cache and table loading.

Works on any folder holding the eight CSVs of the challenge schema. Nothing
here depends on ``Params``: the cache is a faithful, typed copy of the source.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl

DEFAULT_CACHE_DIR = Path("artifacts/cache")
CACHE_VERSION = 1  # bump when the cached layout changes: older folders are rebuilt
MANIFEST_FILE = "manifest.json"
PENDING_STATUS = "pending"
BOOKED_STATUS = "booked"
DASH_CATEGORY = "-"

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
# Cached cents column -> source column.
CENTS_SOURCES: dict[str, dict[str, str]] = {
    "debt_products": {
        "granted_cents": "granted",
        "outstanding_cents": "outstanding",
        "liquidity_cents": "liquidity",
    },
    "debt_schedule_config": {
        "granted_cents": "granted_balance",
        "outstanding_cents": "outstanding_balance",
    },
    "transactions": {"amount_cents": "amount"},
    "invoices": {"amount_cents": "amount", "pending_cents": "pending_amount"},
    "balances": {
        "balance_cents": "balance",
        "available_cents": "available",
        "granted_cents": "granted",
        "liquidity_cents": "liquidity",
        "countable_cents": "countable",
    },
}
# Sort key of every cached table.
PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    "groups": ("group_id",),
    "companies": ("company_id",),
    "banking_products": ("product_id",),
    "debt_products": ("product_id",),
    "debt_schedule_config": ("product_id", "settlement_product_id"),
    "transactions": ("transaction_id",),
    "invoices": ("operation_id",),
    "balances": ("product_id", "date"),
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
    physical lines overcount, and ``transactions.csv`` holds NUL bytes, which
    the reader rejects. ``\x00`` is stripped from every physical line before
    it reaches the reader (per line, so multi-line quoted fields still parse).
    """
    limit = csv.field_size_limit(sys.maxsize)
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as source:
            reader = csv.reader(line.replace("\x00", "") for line in source)
            next(reader, None)
            return sum(1 for _ in reader)
    finally:
        csv.field_size_limit(limit)


def derive_window(transactions: pl.DataFrame, balances: pl.DataFrame) -> Window:
    """Window from the cached transactions (booked rows only) and balances.

    ``as_of`` is the latest of the transaction and balance dates. ``last_month``
    is the month of ``as_of`` when that date is a month end, else the month
    before it. ``first_month`` is the month of the earliest transaction.
    Raises ValueError when no complete month exists.
    """
    first_day = transactions["date"].min()
    if first_day is None:
        raise ValueError("No booked transaction: the window is undefined")
    as_of = max(day for day in (transactions["date"].max(), balances["date"].max()) if day is not None)
    last_month = as_of.replace(day=1)
    if (as_of + timedelta(days=1)).day != 1:  # the month of as_of is not complete
        last_month = (last_month - timedelta(days=1)).replace(day=1)
    first_month = first_day.replace(day=1)
    if last_month < first_month:
        raise ValueError(f"No complete month between {first_day} and {as_of}")
    return Window(first_month=first_month, last_month=last_month, as_of=as_of)


def _read_csv(path: Path, table: str) -> pl.DataFrame:
    """Every record of the file, limited to the columns the cache keeps."""
    with path.open(newline="", encoding="utf-8-sig") as source:
        header = next(csv.reader(line.replace("\x00", "") for line in source), [])
    missing = [name for name in SCHEMAS[table] if name not in header]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    sources = {*CACHE_SCHEMAS[table], *CENTS_SOURCES.get(table, {}).values()}
    # every dtype is forced: small folders have all-null columns
    scan = pl.scan_csv(path, schema_overrides=SCHEMAS[table], infer_schema=False)
    return scan.select([name for name in SCHEMAS[table] if name in sources]).collect()


def _text(name: str) -> pl.Expr:
    text = pl.col(name).str.replace_all("\x00", "", literal=True)
    return pl.when(text.str.len_bytes() > 0).then(text).alias(name)


def _day(name: str) -> pl.Expr:
    return pl.col(name).str.slice(0, 10).str.to_date("%Y-%m-%d")


def _to_cache(raw: pl.DataFrame, table: str) -> pl.DataFrame:
    """Raw frame (``SCHEMAS`` dtypes) -> ``CACHE_SCHEMAS``, sorted by the primary key."""
    frame = raw.lazy().with_columns(
        _text(name) for name, dtype in raw.schema.items() if dtype == pl.String
    )
    if table == "transactions":
        frame = frame.filter(pl.col("status").is_null() | (pl.col("status") != PENDING_STATUS))
        frame = frame.with_columns(
            pl.col("status").fill_null(BOOKED_STATUS), pl.col("category").fill_null(DASH_CATEGORY)
        )
    columns: list[pl.Expr] = []
    for name, dtype in CACHE_SCHEMAS[table].items():
        if name in CENTS_SOURCES.get(table, {}):
            amount = pl.col(CENTS_SOURCES[table][name])
            columns.append((amount * 100).round().cast(pl.Int64).alias(name))
        elif name == "month":
            columns.append(_day("date").dt.month_start().alias(name))
        elif dtype == pl.Date:
            columns.append(_day(name))
        else:
            columns.append(pl.col(name))
    cached = frame.select(columns).collect()
    key = list(PRIMARY_KEYS[table])
    if cached.select(key).is_duplicated().any():  # the other columns break the ties
        key += [name for name in cached.columns if name not in key]
    return cached.sort(key)


def _replace(path: Path, write: Callable[[Path], object]) -> None:
    # whole files only: a concurrent reader never sees a half-written one
    partial = path.with_name(f".{path.name}.{os.getpid()}.partial")
    try:
        write(partial)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def _cache_table(input_dir: Path, folder: Path, table: str) -> dict[str, int]:
    source = input_dir / f"{table}.csv"
    raw = _read_csv(source, table)
    records = count_csv_records(source)
    if raw.height != records:
        raise ValueError(f"{source.name}: {raw.height} records parsed, the csv recount gives {records}")
    pending = raw.filter(pl.col("status") == PENDING_STATUS).height if table == "transactions" else 0
    target = folder / f"{table}.parquet"
    _replace(target, _to_cache(raw, table).write_parquet)
    cached = pl.scan_parquet(target).select(pl.len()).collect().item()
    if cached != records - pending:
        raise ValueError(f"{target.name}: {cached} rows cached, expected {records - pending}")
    return {"records": records, "pending_dropped": pending, "cached": cached}


def _manifest(folder: Path) -> dict[str, Any] | None:
    """Manifest of a complete cache folder of this layout, else None."""
    try:
        manifest = json.loads((folder / MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    complete = all((folder / f"{table}.parquet").is_file() for table in TABLE_NAMES)
    return manifest if complete and manifest.get("cache_version") == CACHE_VERSION else None


def _ensure_cache(input_dir: Path, cache_dir: Path, dataset_hash: str) -> tuple[Path, dict[str, Any]]:
    folder = cache_dir / dataset_hash
    manifest = _manifest(folder)
    if manifest is not None:
        return folder, manifest
    folder.mkdir(parents=True, exist_ok=True)
    tables = {table: _cache_table(input_dir, folder, table) for table in TABLE_NAMES}
    window = derive_window(
        pl.read_parquet(folder / "transactions.parquet", columns=["date"]),
        pl.read_parquet(folder / "balances.parquet", columns=["date"]),
    )
    manifest = {
        "cache_version": CACHE_VERSION,
        "dataset_hash": dataset_hash,
        "tables": tables,
        "window": {
            "first_month": window.first_month.isoformat(),
            "last_month": window.last_month.isoformat(),
            "as_of": window.as_of.isoformat(),
        },
    }
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    _replace(folder / MANIFEST_FILE, lambda partial: partial.write_text(text, encoding="utf-8"))
    return folder, manifest


def build_cache(input_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Write ``<cache_dir>/<dataset_hash>/<table>.parquet`` for the eight tables.

    Reads with ``pl.scan_csv(schema_overrides=SCHEMAS[table])`` (quoted
    newlines), removes NUL bytes from text, asserts the parsed record count of
    every file against ``count_csv_records`` (any difference raises), converts
    to ``CACHE_SCHEMAS`` and sinks to parquet. Every record is kept except
    pending transactions: rows of products missing from both product files and
    rows in any currency stay, cleaning decides what they may feed. Also
    writes ``manifest.json`` with dataset_hash, per-table raw row counts,
    pending rows dropped and the window. Idempotent: an existing complete cache
    is returned untouched. Returns the cache folder.
    """
    input_dir = Path(input_dir)
    return _ensure_cache(input_dir, Path(cache_dir), dataset_fingerprint(input_dir))[0]


def load_tables(input_dir: Path, cache_dir: Path = DEFAULT_CACHE_DIR) -> Tables:
    """Build the cache when missing and load it as ``Tables``.

    Row order of every frame is deterministic: sorted by its primary key
    (transaction_id, operation_id, product_id + date, ...), so shuffled input
    files give identical frames.
    """
    input_dir = Path(input_dir)
    dataset_hash = dataset_fingerprint(input_dir)
    folder, manifest = _ensure_cache(input_dir, Path(cache_dir), dataset_hash)
    frames = {table: pl.read_parquet(folder / f"{table}.parquet") for table in TABLE_NAMES}
    window = Window(**{key: date.fromisoformat(day) for key, day in manifest["window"].items()})
    return Tables(**frames, dataset_hash=dataset_hash, window=window)
