"""Create the immutable source-data schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260918_03"
down_revision: str | None = "20260918_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns(identifier: str) -> list[sa.Column]:
    return [
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column(identifier, sa.Text(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS source")
    op.create_table(
        "dataset_import",
        sa.Column("dataset_hash", sa.String(length=64), primary_key=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "row_counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="source",
    )
    op.create_index(
        "ix_source_dataset_import_status", "dataset_import", ["status"], schema="source"
    )
    op.create_table(
        "groups",
        *_identity_columns("group_id"),
        sa.Column("erp", sa.Text(), nullable=True),
        sa.Column("n_companies_in_sample", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("dataset_hash", "group_id"),
        schema="source",
    )
    op.create_table(
        "companies",
        *_identity_columns("company_id"),
        sa.Column("group_id", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("erp", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("dataset_hash", "company_id"),
        schema="source",
    )
    op.create_index(
        "ix_source_companies_group",
        "companies",
        ["dataset_hash", "group_id"],
        schema="source",
    )
    for table_name in ("banking_products", "debt_products"):
        extra_columns = []
        if table_name == "debt_products":
            extra_columns = [
                sa.Column("granted", sa.Float(), nullable=True),
                sa.Column("outstanding", sa.Float(), nullable=True),
                sa.Column("liquidity", sa.Float(), nullable=True),
            ]
        op.create_table(
            table_name,
            *_identity_columns("product_id"),
            sa.Column("company_id", sa.Text(), nullable=False),
            sa.Column("label", sa.Text(), nullable=False),
            sa.Column("type", sa.Text(), nullable=False),
            sa.Column("bank_name", sa.Text(), nullable=False),
            sa.Column("service", sa.Text(), nullable=False),
            sa.Column("currency", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            *extra_columns,
            sa.PrimaryKeyConstraint("dataset_hash", "product_id"),
            schema="source",
        )
        op.create_index(
            f"ix_source_{table_name}_company",
            table_name,
            ["dataset_hash", "company_id"],
            schema="source",
        )
    op.create_table(
        "debt_schedule_config",
        *_identity_columns("product_id"),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("settlement_product_id", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("amortization_type", sa.Text(), nullable=True),
        sa.Column("interest_calc_method", sa.Text(), nullable=True),
        sa.Column("amortising_frequency", sa.Text(), nullable=True),
        sa.Column("granted_balance", sa.Float(), nullable=True),
        sa.Column("outstanding_balance", sa.Float(), nullable=True),
        sa.Column("total_periods", sa.Integer(), nullable=True),
        sa.Column("next_payment_date", sa.DateTime(), nullable=True),
        sa.Column("last_payment_date", sa.DateTime(), nullable=True),
        sa.Column("annual_interest_rate_or_spread", sa.Float(), nullable=True),
        sa.Column("interest_type", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("dataset_hash", "product_id"),
        schema="source",
    )
    op.create_index(
        "ix_source_debt_schedule_company",
        "debt_schedule_config",
        ["dataset_hash", "company_id"],
        schema="source",
    )
    op.create_table(
        "transactions",
        *_identity_columns("transaction_id"),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("value_date", sa.DateTime(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("exchange_rate", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("accounting_status", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("counterparty_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("dataset_hash", "transaction_id"),
        schema="source",
    )
    op.create_index(
        "ix_source_transactions_company_date",
        "transactions",
        ["dataset_hash", "company_id", "date"],
        schema="source",
    )
    op.create_index(
        "ix_source_transactions_counterparty",
        "transactions",
        ["dataset_hash", "counterparty_id"],
        schema="source",
    )
    op.create_table(
        "invoices",
        *_identity_columns("operation_id"),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=True),
        sa.Column("issuance_date", sa.DateTime(), nullable=False),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("payment_date", sa.DateTime(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("pending_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("accounting_currency", sa.Text(), nullable=True),
        sa.Column("exchange_rate", sa.Float(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("concept", sa.Text(), nullable=True),
        sa.Column("counterparty_id", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("dataset_hash", "operation_id"),
        schema="source",
    )
    op.create_index(
        "ix_source_invoices_company_issuance",
        "invoices",
        ["dataset_hash", "company_id", "issuance_date"],
        schema="source",
    )
    op.create_index(
        "ix_source_invoices_counterparty",
        "invoices",
        ["dataset_hash", "counterparty_id"],
        schema="source",
    )
    op.create_table(
        "balances",
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Text(), nullable=False),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.Column("balance", sa.Float(), nullable=False),
        sa.Column("available", sa.Float(), nullable=True),
        sa.Column("granted", sa.Float(), nullable=True),
        sa.Column("liquidity", sa.Float(), nullable=True),
        sa.Column("countable", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("dataset_hash", "product_id", "date"),
        schema="source",
    )
    op.create_index(
        "ix_source_balances_company_date",
        "balances",
        ["dataset_hash", "company_id", "date"],
        schema="source",
    )


def downgrade() -> None:
    for table_name in (
        "balances",
        "invoices",
        "transactions",
        "debt_schedule_config",
        "debt_products",
        "banking_products",
        "companies",
        "groups",
        "dataset_import",
    ):
        op.drop_table(table_name, schema="source")
    op.execute("DROP SCHEMA source")
