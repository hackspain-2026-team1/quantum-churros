"""Create benchmark reference tables for external AR studies."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_04"
down_revision: str | None = "20260918_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benchmarkstudy",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("data_period", sa.String(), nullable=False),
        sa.Column("report_year", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_benchmarkstudy_source", "benchmarkstudy", ["source"])
    op.create_index("ix_benchmarkstudy_report_year", "benchmarkstudy", ["report_year"])
    op.create_table(
        "benchmarkindustrymetric",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("study_id", sa.String(), nullable=False),
        sa.Column("industry", sa.String(), nullable=False),
        sa.Column("industry_slug", sa.String(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("avg_days_to_collect", sa.Float(), nullable=False),
        sa.Column("open_ar_overdue_ratio", sa.Float(), nullable=False),
        sa.Column("overdue_aging_120d_ratio", sa.Float(), nullable=False),
        sa.Column("ar_health_index", sa.Float(), nullable=False),
        sa.Column("commentary", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["study_id"], ["benchmarkstudy.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_benchmarkindustrymetric_study_id", "benchmarkindustrymetric", ["study_id"]
    )
    op.create_index(
        "ix_benchmarkindustrymetric_industry_slug",
        "benchmarkindustrymetric",
        ["industry_slug"],
    )
    op.create_index("ix_benchmarkindustrymetric_rank", "benchmarkindustrymetric", ["rank"])


def downgrade() -> None:
    op.drop_index("ix_benchmarkindustrymetric_rank", table_name="benchmarkindustrymetric")
    op.drop_index(
        "ix_benchmarkindustrymetric_industry_slug", table_name="benchmarkindustrymetric"
    )
    op.drop_index(
        "ix_benchmarkindustrymetric_study_id", table_name="benchmarkindustrymetric"
    )
    op.drop_table("benchmarkindustrymetric")
    op.drop_index("ix_benchmarkstudy_report_year", table_name="benchmarkstudy")
    op.drop_index("ix_benchmarkstudy_source", table_name="benchmarkstudy")
    op.drop_table("benchmarkstudy")
