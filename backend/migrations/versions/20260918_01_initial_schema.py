"""Create the operational X-Ray schema."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260918_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("workspace", sa.Column("id", sa.String(), nullable=False), sa.Column("name", sa.String(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_table("entity", sa.Column("id", sa.String(), nullable=False), sa.Column("workspace_id", sa.String(), nullable=False), sa.Column("parent_id", sa.String(), nullable=True), sa.Column("name", sa.String(), nullable=False), sa.Column("kind", sa.String(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_entity_workspace_id", "entity", ["workspace_id"])
    op.create_index("ix_entity_parent_id", "entity", ["parent_id"])
    op.create_index("ix_entity_kind", "entity", ["kind"])
    op.create_table("scorerun", sa.Column("id", sa.String(), nullable=False), sa.Column("dataset_hash", sa.String(), nullable=False), sa.Column("feature_version", sa.String(), nullable=False), sa.Column("model_version", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_scorerun_dataset_hash", "scorerun", ["dataset_hash"])
    op.create_index("ix_scorerun_status", "scorerun", ["status"])
    op.create_table("scoresnapshotrecord", sa.Column("id", sa.String(), nullable=False), sa.Column("run_id", sa.String(), nullable=False), sa.Column("entity_id", sa.String(), nullable=False), sa.Column("month", sa.Date(), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("delta", sa.Float(), nullable=False), sa.Column("trend", sa.String(), nullable=False), sa.Column("persistence_months", sa.Integer(), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("detected_since", sa.Date(), nullable=True), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_scoresnapshotrecord_run_id", "scoresnapshotrecord", ["run_id"])
    op.create_index("ix_scoresnapshotrecord_entity_id", "scoresnapshotrecord", ["entity_id"])
    op.create_index("ix_scoresnapshotrecord_month", "scoresnapshotrecord", ["month"])
    op.create_table("scoredriverrecord", sa.Column("id", sa.String(), nullable=False), sa.Column("snapshot_id", sa.String(), nullable=False), sa.Column("feature", sa.String(), nullable=False), sa.Column("direction", sa.String(), nullable=False), sa.Column("contribution", sa.Float(), nullable=False), sa.Column("observed", sa.Float(), nullable=False), sa.Column("baseline", sa.Float(), nullable=False), sa.Column("evidence", sa.String(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_scoredriverrecord_snapshot_id", "scoredriverrecord", ["snapshot_id"])
    op.create_table("alertrecord", sa.Column("id", sa.String(), nullable=False), sa.Column("entity_id", sa.String(), nullable=False), sa.Column("snapshot_id", sa.String(), nullable=False), sa.Column("kind", sa.String(), nullable=False), sa.Column("severity", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_alertrecord_entity_id", "alertrecord", ["entity_id"])
    op.create_index("ix_alertrecord_snapshot_id", "alertrecord", ["snapshot_id"])
    op.create_index("ix_alertrecord_severity", "alertrecord", ["severity"])
    op.create_index("ix_alertrecord_status", "alertrecord", ["status"])
    op.create_table("scenariorecord", sa.Column("id", sa.String(), nullable=False), sa.Column("entity_id", sa.String(), nullable=False), sa.Column("base_score", sa.Float(), nullable=False), sa.Column("assumptions_json", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_scenariorecord_entity_id", "scenariorecord", ["entity_id"])
    op.create_index("ix_scenariorecord_status", "scenariorecord", ["status"])
    op.create_table("scenarioprojection", sa.Column("id", sa.String(), nullable=False), sa.Column("scenario_id", sa.String(), nullable=False), sa.Column("month_offset", sa.Integer(), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("confidence_low", sa.Float(), nullable=False), sa.Column("confidence_high", sa.Float(), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_scenarioprojection_scenario_id", "scenarioprojection", ["scenario_id"])
    op.create_table("recommendedaction", sa.Column("id", sa.String(), nullable=False), sa.Column("entity_id", sa.String(), nullable=False), sa.Column("title", sa.String(), nullable=False), sa.Column("owner", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("expected_impact", sa.String(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_recommendedaction_entity_id", "recommendedaction", ["entity_id"])
    op.create_index("ix_recommendedaction_status", "recommendedaction", ["status"])
    op.create_table("macroobservation", sa.Column("id", sa.String(), nullable=False), sa.Column("indicator", sa.String(), nullable=False), sa.Column("month", sa.Date(), nullable=False), sa.Column("scope", sa.String(), nullable=False), sa.Column("value", sa.Float(), nullable=False), sa.Column("source", sa.String(), nullable=False), sa.Column("series", sa.String(), nullable=False), sa.Column("available_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_macroobservation_indicator", "macroobservation", ["indicator"])
    op.create_index("ix_macroobservation_month", "macroobservation", ["month"])
    op.create_index("ix_macroobservation_available_at", "macroobservation", ["available_at"])


def downgrade() -> None:
    for table in ("macroobservation", "recommendedaction", "scenarioprojection", "scenariorecord", "alertrecord", "scoredriverrecord", "scoresnapshotrecord", "scorerun", "entity", "workspace"):
        op.drop_table(table)
