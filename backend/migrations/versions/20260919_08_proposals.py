"""Store client proposals and the banks/actions chosen in each one.

Revision ID: 20260919_08
Revises: 20260919_07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_08"
down_revision: str | None = "20260919_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposal",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("corte", sa.String(), nullable=False),
        sa.Column("bundle_id", sa.String(), nullable=False),
        sa.Column("score_actual_tenths", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposal_entity_id", "proposal", ["entity_id"])
    op.create_index("ix_proposal_group_id", "proposal", ["group_id"])
    op.create_index("ix_proposal_corte", "proposal", ["corte"])

    op.create_table(
        "proposalaction",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("pillar", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("uplift_tenths", sa.Integer(), nullable=False),
        sa.Column("new_score_tenths", sa.Integer(), nullable=False),
        sa.Column("current", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposal.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proposalaction_proposal_id", "proposalaction", ["proposal_id"])

    op.create_table(
        "proposalfinancing",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("instrument_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("uplift_tenths", sa.Integer(), nullable=False),
        sa.Column("bank", sa.String(), nullable=True),
        sa.Column("rate", sa.Float(), nullable=True),
        sa.Column("rate_type", sa.String(), nullable=True),
        sa.Column("rate_fuente", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposal.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proposalfinancing_proposal_id", "proposalfinancing", ["proposal_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_proposalfinancing_proposal_id", table_name="proposalfinancing")
    op.drop_table("proposalfinancing")
    op.drop_index("ix_proposalaction_proposal_id", table_name="proposalaction")
    op.drop_table("proposalaction")
    op.drop_index("ix_proposal_corte", table_name="proposal")
    op.drop_index("ix_proposal_group_id", table_name="proposal")
    op.drop_index("ix_proposal_entity_id", table_name="proposal")
    op.drop_table("proposal")
