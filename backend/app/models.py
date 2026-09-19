from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class RecommendedAction(SQLModel, table=True):
    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    title: str
    owner: str
    status: str = Field(default="pending", index=True)
    expected_impact: str
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


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
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


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
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    resolved_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ScenarioRecord(SQLModel, table=True):
    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    base_score: float
    assumptions_json: str
    status: str = Field(default="calculated", index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


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
    available_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )


class BenchmarkStudy(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source: str = Field(index=True)
    title: str
    data_period: str
    report_year: int = Field(index=True)
    source_url: str
    description: str | None = None
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class BenchmarkIndustryMetric(SQLModel, table=True):
    id: str = Field(primary_key=True)
    study_id: str = Field(index=True, foreign_key="benchmarkstudy.id")
    industry: str
    industry_slug: str = Field(index=True)
    rank: int = Field(index=True)
    avg_days_to_collect: float
    open_ar_overdue_ratio: float
    overdue_aging_120d_ratio: float
    ar_health_index: float
    commentary: str | None = None


class BenchmarkIndustryMetricRead(SQLModel):
    industry: str
    industry_slug: str
    rank: int
    avg_days_to_collect: float
    open_ar_overdue_ratio: float
    overdue_aging_120d_ratio: float
    ar_health_index: float
    commentary: str | None = None


class BenchmarkStudyRead(SQLModel):
    id: str
    source: str
    title: str
    data_period: str
    report_year: int
    source_url: str
    description: str | None = None
    industries: list[BenchmarkIndustryMetricRead]


class EntityIndustry(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("dataset_hash", "entity_id", "classifier_version"),)

    id: str = Field(primary_key=True)
    dataset_hash: str = Field(index=True, max_length=64)
    entity_id: str = Field(index=True)
    industry_slug: str = Field(index=True)
    industry_label: str
    confidence: float
    source: str = Field(index=True)
    reason: str
    classifier_version: str = Field(index=True)
    signals_json: str
    classified_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class IndustryClassificationRead(SQLModel):
    entity_id: str
    industry_slug: str
    industry_label: str
    confidence: float
    source: str
    reason: str
    classifier_version: str
    dataset_hash: str


class DebtProductRead(SQLModel):
    product_id: str
    type: str
    type_label: str
    label: str
    bank_name: str
    currency: str
    granted: float | None = None
    outstanding: float | None = None


class CompanyDebtProductsRead(SQLModel):
    entity_id: str
    products: list[DebtProductRead]


def utc_now() -> datetime:
    return datetime.now(UTC)


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: str = Field(primary_key=True)
    kind: str = Field(index=True)
    name: str
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", "role"),)

    id: str = Field(primary_key=True)
    organization_id: str = Field(foreign_key="organizations.id", index=True)
    user_id: str = Field(index=True)
    role: str = Field(index=True)
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class FundingNeed(SQLModel, table=True):
    __tablename__ = "funding_needs"

    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    score_snapshot_id: str
    score: float
    previous_score: float
    amount_low: float
    amount_high: float
    needed_from: date
    needed_to: date
    confidence: float
    source_month: date
    detected_since: date | None = None
    trajectory: str
    trajectory_nature: str | None = None
    model_version: str
    params_hash: str
    dataset_hash: str
    explanation_method: str = "exact_additive"
    drivers_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    profile_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    status: str = Field(default="detected", index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class FinancingCase(SQLModel, table=True):
    __tablename__ = "financing_cases"

    id: str = Field(primary_key=True)
    funding_need_id: str = Field(foreign_key="funding_needs.id", index=True)
    consultant_org_id: str = Field(foreign_key="organizations.id", index=True)
    company_org_id: str = Field(foreign_key="organizations.id", index=True)
    objective: str
    amount: float
    term_months: int
    product_types_json: list[str] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    status: str = Field(default="in_review", index=True)
    version: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Mandate(SQLModel, table=True):
    __tablename__ = "mandates"

    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="financing_cases.id", index=True)
    scope_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    granted_by: str
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProviderCapability(SQLModel, table=True):
    __tablename__ = "provider_capabilities"
    __table_args__ = (UniqueConstraint("provider_org_id", "product_type"),)

    id: str = Field(primary_key=True)
    provider_org_id: str = Field(foreign_key="organizations.id", index=True)
    product_type: str = Field(index=True)
    eligibility_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    terms_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    active: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Opportunity(SQLModel, table=True):
    __tablename__ = "opportunities"
    __table_args__ = (UniqueConstraint("case_id"), UniqueConstraint("public_code"))

    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="financing_cases.id", index=True)
    public_code: str = Field(index=True)
    teaser_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    status: str = Field(default="open", index=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class IndicativeOffer(SQLModel, table=True):
    __tablename__ = "indicative_offers"
    __table_args__ = (UniqueConstraint("opportunity_id", "provider_org_id"),)

    id: str = Field(primary_key=True)
    opportunity_id: str = Field(foreign_key="opportunities.id", index=True)
    provider_org_id: str = Field(foreign_key="organizations.id", index=True)
    amount: float
    annual_rate: float
    term_months: int
    opening_fee: float
    guarantee: str
    terms_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    status: str = Field(default="submitted", index=True)
    valid_until: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DisclosureGrant(SQLModel, table=True):
    __tablename__ = "disclosure_grants"

    id: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="financing_cases.id", index=True)
    grantee_org_id: str = Field(foreign_key="organizations.id", index=True)
    scope_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"

    id: str = Field(primary_key=True)
    actor_id: str = Field(index=True)
    case_id: str | None = Field(default=None, foreign_key="financing_cases.id", index=True)
    event_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )


class OutboxEvent(SQLModel, table=True):
    __tablename__ = "outbox_events"

    id: str = Field(primary_key=True)
    aggregate_type: str = Field(index=True)
    aggregate_id: str = Field(index=True)
    event_type: str = Field(index=True)
    payload_json: dict[str, Any] = Field(sa_column=Column(JSON_DOCUMENT, nullable=False))
    status: str = Field(default="pending", index=True)
    attempts: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    delivered_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class Proposal(SQLModel, table=True):
    id: str = Field(primary_key=True)
    entity_id: str = Field(index=True)
    group_id: str = Field(index=True)
    kind: str
    corte: str = Field(index=True)
    bundle_id: str
    score_actual_tenths: int
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProposalAction(SQLModel, table=True):
    id: str = Field(primary_key=True)
    proposal_id: str = Field(index=True, foreign_key="proposal.id")
    action_id: str
    pillar: str
    title: str
    uplift_tenths: int
    new_score_tenths: int
    current: float | None = None
    target: float | None = None
    unit: str | None = None


class ProposalFinancing(SQLModel, table=True):
    id: str = Field(primary_key=True)
    proposal_id: str = Field(index=True, foreign_key="proposal.id")
    instrument_id: str
    kind: str
    title: str
    amount: float | None = None
    uplift_tenths: int
    bank: str | None = None
    rate: float | None = None
    rate_type: str | None = None
    rate_fuente: str | None = None
