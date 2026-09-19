"""Create the ``xray`` schema that holds the engine outputs, one attribute per column.

Revision ID: 20260919_06
Revises: 20260918_05
"""

revision = "20260919_06"
down_revision = "20260918_05"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

from app.engine_tables import (
    ALERTS_COLUMNS,
    ALERTS_TABLE,
    PANEL_COLUMNS,
    PANEL_TABLE,
    SCORES_COLUMNS,
    SCORES_TABLE,
)

SCHEMA = "xray"
TYPES = {
    "float": sa.Float,
    "bigint": sa.BigInteger,
    "text": sa.Text,
    "boolean": sa.Boolean,
    "date": sa.Date,
    "jsonb": postgresql.JSONB,
}
RUN_COLUMNS = ("dataset_hash", "params_hash")
ENTITY_KEY = ("dataset_hash", "entity_kind", "entity_id", "month")


def _columns(spec, key):
    names = [name for name, *_ in spec]
    run = [sa.Column(name, sa.Text(), nullable=False) for name in RUN_COLUMNS if name not in names]
    return run + [sa.Column(name, TYPES[kind](), nullable=name not in key) for name, kind, *_ in spec]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    for table, spec in ((PANEL_TABLE, PANEL_COLUMNS), (SCORES_TABLE, SCORES_COLUMNS)):
        op.create_table(
            table, *_columns(spec, ENTITY_KEY), sa.PrimaryKeyConstraint(*ENTITY_KEY), schema=SCHEMA
        )
        op.create_index(f"ix_xray_{table}_group", table, ["dataset_hash", "group_id", "month"], schema=SCHEMA)
    op.create_table(ALERTS_TABLE, *_columns(ALERTS_COLUMNS, ("dataset_hash",)), schema=SCHEMA)
    op.create_index(
        f"ix_xray_{ALERTS_TABLE}_entity", ALERTS_TABLE, ["dataset_hash", "entity_id", "month"], schema=SCHEMA
    )


def downgrade() -> None:
    for table in (ALERTS_TABLE, SCORES_TABLE, PANEL_TABLE):
        op.drop_table(table, schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA}")
