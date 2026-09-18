from datetime import UTC, date, datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class RecommendedAction(SQLModel, table=True):
    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    title: str
    owner: str
    status: str = Field(default="pending", index=True)
    expected_impact: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True), nullable=False))


class Workspace(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str


class Entity(SQLModel, table=True):
    id: str = Field(primary_key=True)
    workspace_id: str = Field(index=True)
    parent_id: str | None = Field(default=None, index=True)
    name: str
    kind: str = Field(index=True)


class ScoreRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    dataset_hash: str = Field(index=True)
    feature_version: str
    model_version: str
    status: str = Field(default="completed", index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True), nullable=False))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class ScoreSnapshotRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    run_id: str = Field(index=True)
    entity_id: str = Field(index=True)
    month: date = Field(index=True)
    score: float
    delta: float
    trend: str
    persistence_months: int
    confidence: float
    detected_since: date | None = None


class ScoreDriverRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    snapshot_id: str = Field(index=True)
    feature: str
    direction: str
    contribution: float
    observed: float
    baseline: float
    evidence: str


class AlertRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    snapshot_id: str = Field(index=True)
    kind: str
    severity: str = Field(index=True)
    status: str = Field(default="new", index=True)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True), nullable=False))
    resolved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class ScenarioRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    base_score: float
    assumptions_json: str
    status: str = Field(default="calculated", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True), nullable=False))


class ScenarioProjection(SQLModel, table=True):
    id: str = Field(primary_key=True)
    scenario_id: str = Field(index=True)
    month_offset: int
    score: float
    confidence_low: float
    confidence_high: float


class MacroObservation(SQLModel, table=True):
    id: str = Field(primary_key=True)
    indicator: str = Field(index=True)
    month: date = Field(index=True)
    scope: str
    value: float
    source: str
    series: str
    available_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))


class ScenarioRequest(SQLModel):
    collection_days: int = Field(default=12, ge=0, le=45)
    refinance_amount: int = Field(default=180_000, ge=0, le=2_000_000)
    payment_extension_days: int = Field(default=7, ge=0, le=30)
    persist: bool = False


class ScenarioResponse(SQLModel):
    scenario_id: str
    status: str
    base_score: float
    projected_score: float
    projected_cash: int
    confidence_low: float
    confidence_high: float


class ActionUpdate(SQLModel):
    status: str
