"""Add the financing workspace domain.

Revision ID: 20260919_08
Revises: 20260919_07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_08"
down_revision: str | None = "20260919_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO public")
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_kind", "organizations", ["kind"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", "role"),
    )
    for column in ("organization_id", "user_id", "role", "status"):
        op.create_index(f"ix_memberships_{column}", "memberships", [column])

    op.create_table(
        "funding_needs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("score_snapshot_id", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("previous_score", sa.Float(), nullable=False),
        sa.Column("amount_low", sa.Float(), nullable=False),
        sa.Column("amount_high", sa.Float(), nullable=False),
        sa.Column("needed_from", sa.Date(), nullable=False),
        sa.Column("needed_to", sa.Date(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_month", sa.Date(), nullable=False),
        sa.Column("detected_since", sa.Date(), nullable=True),
        sa.Column("trajectory", sa.String(), nullable=False),
        sa.Column("trajectory_nature", sa.String(), nullable=True),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("params_hash", sa.String(), nullable=False),
        sa.Column("dataset_hash", sa.String(), nullable=False),
        sa.Column("explanation_method", sa.String(), nullable=False),
        sa.Column("drivers_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_funding_needs_entity_id", "funding_needs", ["entity_id"])
    op.create_index("ix_funding_needs_status", "funding_needs", ["status"])

    op.create_table(
        "financing_cases",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("funding_need_id", sa.String(), nullable=False),
        sa.Column("consultant_org_id", sa.String(), nullable=False),
        sa.Column("company_org_id", sa.String(), nullable=False),
        sa.Column("objective", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("product_types_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["funding_need_id"], ["funding_needs.id"]),
        sa.ForeignKeyConstraint(["consultant_org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["company_org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("funding_need_id", "consultant_org_id", "company_org_id", "status"):
        op.create_index(f"ix_financing_cases_{column}", "financing_cases", [column])

    op.create_table(
        "mandates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("granted_by", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["case_id"], ["financing_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mandates_case_id", "mandates", ["case_id"])

    op.create_table(
        "provider_capabilities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("provider_org_id", sa.String(), nullable=False),
        sa.Column("product_type", sa.String(), nullable=False),
        sa.Column("eligibility_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("terms_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["provider_org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_org_id", "product_type"),
    )
    for column in ("provider_org_id", "product_type", "active"):
        op.create_index(f"ix_provider_capabilities_{column}", "provider_capabilities", [column])

    op.create_table(
        "opportunities",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("public_code", sa.String(), nullable=False),
        sa.Column("teaser_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["case_id"], ["financing_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
        sa.UniqueConstraint("public_code"),
    )
    op.create_index("ix_opportunities_case_id", "opportunities", ["case_id"])
    op.create_index("ix_opportunities_public_code", "opportunities", ["public_code"])
    op.create_index("ix_opportunities_status", "opportunities", ["status"])

    op.create_table(
        "indicative_offers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("opportunity_id", sa.String(), nullable=False),
        sa.Column("provider_org_id", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("annual_rate", sa.Float(), nullable=False),
        sa.Column("term_months", sa.Integer(), nullable=False),
        sa.Column("opening_fee", sa.Float(), nullable=False),
        sa.Column("guarantee", sa.String(), nullable=False),
        sa.Column("terms_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"]),
        sa.ForeignKeyConstraint(["provider_org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("opportunity_id", "provider_org_id"),
    )
    for column in ("opportunity_id", "provider_org_id", "status"):
        op.create_index(f"ix_indicative_offers_{column}", "indicative_offers", [column])

    op.create_table(
        "disclosure_grants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=False),
        sa.Column("grantee_org_id", sa.String(), nullable=False),
        sa.Column("scope_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["case_id"], ["financing_cases.id"]),
        sa.ForeignKeyConstraint(["grantee_org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_disclosure_grants_case_id", "disclosure_grants", ["case_id"])
    op.create_index("ix_disclosure_grants_grantee_org_id", "disclosure_grants", ["grantee_org_id"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("case_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["financing_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("actor_id", "case_id", "event_type", "created_at"):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("aggregate_type", "aggregate_id", "event_type", "status", "created_at"):
        op.create_index(f"ix_outbox_events_{column}", "outbox_events", [column])


def downgrade() -> None:
    op.execute("SET LOCAL search_path TO public")
    for table in (
        "outbox_events",
        "audit_events",
        "disclosure_grants",
        "indicative_offers",
        "opportunities",
        "provider_capabilities",
        "mandates",
        "financing_cases",
        "funding_needs",
        "memberships",
        "organizations",
    ):
        op.drop_table(table)
