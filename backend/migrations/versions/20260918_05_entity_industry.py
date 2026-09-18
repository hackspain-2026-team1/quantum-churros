"""Create dataset-versioned entity industry classifications."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_05"
down_revision: str | None = "20260918_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "entityindustry",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("industry_slug", sa.String(), nullable=False),
        sa.Column("industry_label", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("classifier_version", sa.String(), nullable=False),
        sa.Column("signals_json", sa.String(), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_hash",
            "entity_id",
            "classifier_version",
            name="uq_entityindustry_dataset_entity_version",
        ),
    )
    op.create_index("ix_entityindustry_dataset_hash", "entityindustry", ["dataset_hash"])
    op.create_index("ix_entityindustry_entity_id", "entityindustry", ["entity_id"])
    op.create_index("ix_entityindustry_industry_slug", "entityindustry", ["industry_slug"])
    op.create_index(
        "ix_entityindustry_classifier_version", "entityindustry", ["classifier_version"]
    )
    op.create_index("ix_entityindustry_source", "entityindustry", ["source"])


def downgrade() -> None:
    op.drop_index("ix_entityindustry_source", table_name="entityindustry")
    op.drop_index("ix_entityindustry_classifier_version", table_name="entityindustry")
    op.drop_index("ix_entityindustry_industry_slug", table_name="entityindustry")
    op.drop_index("ix_entityindustry_entity_id", table_name="entityindustry")
    op.drop_index("ix_entityindustry_dataset_hash", table_name="entityindustry")
    op.drop_table("entityindustry")
