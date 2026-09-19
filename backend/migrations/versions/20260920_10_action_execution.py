"""Persist action decisions, frozen baselines and append-only tracking."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260920_10"
down_revision = "20260919_09"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL search_path TO public")
    document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table("action_execution",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", document, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_action_execution_entity_id", "action_execution", ["entity_id"])
    op.create_index("ix_action_execution_group_id", "action_execution", ["group_id"])
    op.create_table("action_execution_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("execution_id", sa.String(), sa.ForeignKey("action_execution.id"), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", document, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_action_execution_event_execution_id", "action_execution_event", ["execution_id"])


def downgrade():
    op.execute("SET LOCAL search_path TO public")
    op.drop_table("action_execution_event")
    op.drop_table("action_execution")
