from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb


@dataclass(frozen=True)
class TableSpec:
    filename: str
    table: str
    columns: tuple[str, ...]
    keys: tuple[str, ...]


TABLES = (
    TableSpec(
        "groups.csv",
        "groups",
        ("group_id", "erp", "n_companies_in_sample"),
        ("group_id",),
    ),
    TableSpec(
        "companies.csv",
        "companies",
        ("company_id", "group_id", "country", "currency", "erp", "created_at"),
        ("company_id",),
    ),
    TableSpec(
        "banking_products.csv",
        "banking_products",
        (
            "product_id",
            "company_id",
            "label",
            "type",
            "bank_name",
            "service",
            "currency",
            "created_at",
        ),
        ("product_id",),
    ),
    TableSpec(
        "debt_products.csv",
        "debt_products",
        (
            "product_id",
            "company_id",
            "label",
            "type",
            "bank_name",
            "service",
            "currency",
            "created_at",
            "granted",
            "outstanding",
            "liquidity",
        ),
        ("product_id",),
    ),
    TableSpec(
        "debt_schedule_config.csv",
        "debt_schedule_config",
        (
            "product_id",
            "company_id",
            "settlement_product_id",
            "currency",
            "amortization_type",
            "interest_calc_method",
            "amortising_frequency",
            "granted_balance",
            "outstanding_balance",
            "total_periods",
            "next_payment_date",
            "last_payment_date",
            "annual_interest_rate_or_spread",
            "interest_type",
        ),
        ("product_id",),
    ),
    TableSpec(
        "transactions.csv",
        "transactions",
        (
            "transaction_id",
            "company_id",
            "product_id",
            "date",
            "value_date",
            "amount",
            "exchange_rate",
            "status",
            "accounting_status",
            "category",
            "description",
            "counterparty_id",
        ),
        ("transaction_id",),
    ),
    TableSpec(
        "invoices.csv",
        "invoices",
        (
            "operation_id",
            "company_id",
            "document_type",
            "issuance_date",
            "due_date",
            "payment_date",
            "amount",
            "pending_amount",
            "currency",
            "accounting_currency",
            "exchange_rate",
            "status",
            "concept",
            "counterparty_id",
        ),
        ("operation_id",),
    ),
    TableSpec(
        "balances.csv",
        "balances",
        (
            "product_id",
            "company_id",
            "date",
            "balance",
            "available",
            "granted",
            "liquidity",
            "countable",
        ),
        ("product_id", "date"),
    ),
)


def source_paths(input_dir: Path) -> list[Path]:
    paths = [input_dir / spec.filename for spec in TABLES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing source files: {', '.join(missing)}")
    return paths


def dataset_fingerprint(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode())
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def postgres_dsn(database_url: str) -> str:
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError(
            "Dataset ingestion requires PostgreSQL; run it against the Docker database"
        )
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def _copy_table(
    cursor: psycopg.Cursor, input_dir: Path, dataset_hash: str, spec: TableSpec
) -> int:
    stage_name = f"stage_{spec.table}"
    identifiers = sql.SQL(", ").join(map(sql.Identifier, spec.columns))
    cursor.execute(
        sql.SQL(
            "CREATE TEMP TABLE {} ON COMMIT DROP AS SELECT {} FROM {}.{} WITH NO DATA"
        ).format(
            sql.Identifier(stage_name),
            identifiers,
            sql.Identifier("source"),
            sql.Identifier(spec.table),
        )
    )
    copy_statement = sql.SQL(
        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
    ).format(sql.Identifier(stage_name), identifiers)
    with (
        cursor.copy(copy_statement) as copy,
        (input_dir / spec.filename).open("rb") as source,
    ):
        while chunk := source.read(1024 * 1024):
            copy.write(chunk)
    cursor.execute(
        sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(stage_name))
    )
    row_count = cursor.fetchone()[0]
    conflict_columns = ("dataset_hash", *spec.keys)
    update_columns = [column for column in spec.columns if column not in spec.keys]
    conflict_sql = sql.SQL(", ").join(map(sql.Identifier, conflict_columns))
    assignments = sql.SQL(", ").join(
        sql.SQL("{} = EXCLUDED.{}").format(
            sql.Identifier(column), sql.Identifier(column)
        )
        for column in update_columns
    )
    insert_statement = sql.SQL(
        "INSERT INTO {}.{} ({}, {}) SELECT %s, {} FROM {} ON CONFLICT ({}) DO UPDATE SET {}"
    ).format(
        sql.Identifier("source"),
        sql.Identifier(spec.table),
        sql.Identifier("dataset_hash"),
        identifiers,
        identifiers,
        sql.Identifier(stage_name),
        conflict_sql,
        assignments,
    )
    cursor.execute(insert_statement, (dataset_hash,))
    return row_count


def ingest_dataset(
    input_dir: Path, database_url: str
) -> tuple[str, dict[str, int], bool]:
    paths = source_paths(input_dir)
    fingerprint = dataset_fingerprint(paths)
    row_counts: dict[str, int] = {}
    with (
        psycopg.connect(postgres_dsn(database_url)) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT status, row_counts FROM source.dataset_import WHERE dataset_hash = %s",
            (fingerprint,),
        )
        existing = cursor.fetchone()
        if existing and existing[0] == "completed":
            return fingerprint, dict(existing[1]), True
        cursor.execute(
            "INSERT INTO source.dataset_import (dataset_hash, source_path, status, row_counts) VALUES (%s, %s, 'running', '{}'::jsonb) ON CONFLICT (dataset_hash) DO UPDATE SET source_path = EXCLUDED.source_path, status = 'running', started_at = now(), completed_at = NULL",
            (fingerprint, str(input_dir.resolve())),
        )
        for spec in TABLES:
            row_counts[spec.table] = _copy_table(cursor, input_dir, fingerprint, spec)
        cursor.execute(
            "UPDATE source.dataset_import SET status = 'completed', row_counts = %s, completed_at = now() WHERE dataset_hash = %s",
            (Jsonb(row_counts), fingerprint),
        )
    return fingerprint, row_counts, False
