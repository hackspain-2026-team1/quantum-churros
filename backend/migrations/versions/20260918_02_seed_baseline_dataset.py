"""Former seed of the retired baseline run. Kept as a no-op so the revision chain holds.

Scores are never shipped inside a migration: the engine measures them from the
ingested dataset and ``xray-db publish`` loads them into the ``xray`` schema.

Revision ID: 20260918_02
Revises: 20260918_01
"""

revision = "20260918_02"
down_revision = "20260918_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
