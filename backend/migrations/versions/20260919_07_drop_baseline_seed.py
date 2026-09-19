"""Remove the rows the retired baseline seed left in databases that already applied it.

Revision ID: 20260919_07
Revises: 20260919_06
"""

revision = "20260919_07"
down_revision = "20260919_06"
branch_labels = None
depends_on = None

from alembic import op

LEGACY_TABLES = ("scoredriverrecord", "alertrecord", "scoresnapshotrecord", "scorerun", "entity")


def upgrade() -> None:
    for table in LEGACY_TABLES:
        op.execute(f"DELETE FROM {table}")


def downgrade() -> None:
    pass
