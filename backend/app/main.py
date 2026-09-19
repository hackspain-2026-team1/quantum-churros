import json
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, create_engine, select
from xray_engine.artifacts import read_entity_scores, read_entity_series, read_latest_score
from xray_engine.demo import demo_overview

from .benchmarks import seed_benchmark_studies
from .benchmarks.demo_overrides import apply_demo_override
from .config import settings
from .debt_products import list_debt_products
from .industry import get_classification, get_classifications, industry_distribution
from .models import (
    ActionUpdate,
    BenchmarkIndustryMetric,
    BenchmarkIndustryMetricRead,
    BenchmarkStudy,
    BenchmarkStudyRead,
    Entity,
    CompanyDebtProductsRead,
    IndustryClassificationRead,
    RecommendedAction,
    ScenarioProjection,
    ScenarioRecord,
    ScenarioRequest,
    ScenarioResponse,
    Workspace,
)

engine = create_engine(settings.database_url, pool_pre_ping=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    with Session(engine) as session:
        if session.get(Workspace, "WORKSPACE_DEMO") is None:
            session.add(Workspace(id="WORKSPACE_DEMO", name="Embat X-Ray Demo"))
        demo_entities = [
            Entity(id="GROUP_0042", workspace_id="WORKSPACE_DEMO", name="Grupo Velasco", kind="group"),
            Entity(
                id="COMP_0680",
                workspace_id="WORKSPACE_DEMO",
                parent_id="GROUP_0042",
                name="Velasco Industrial",
                kind="company",
            ),
        ]
        for demo_entity in demo_entities:
            if session.get(Entity, demo_entity.id) is None:
                session.add(demo_entity)
        seeds = [
            RecommendedAction(
                id="collect-overdue",
                entity_id="COMP_0680",
                title="Priorizar el cobro de cinco facturas",
                owner="Tesorería",
                status="in_progress",
                expected_impact="+4–6 puntos",
            ),
            RecommendedAction(
                id="refinance-line",
                entity_id="COMP_0680",
                title="Renegociar la línea de circulante",
                owner="CFO",
                status="pending",
                expected_impact="+180 k€ de margen",
            ),
            RecommendedAction(
                id="monitor-volatility",
                entity_id="COMP_0680",
                title="Vigilar la volatilidad de caja",
                owner="Analista",
                status="in_progress",
                expected_impact="Revisar en el próximo cierre",
            ),
        ]
        for action in seeds:
            if session.get(RecommendedAction, action.id) is None:
                session.add(action)
        seed_benchmark_studies(session)
        session.commit()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/demo")
def get_demo() -> dict[str, object]:
    overview = demo_overview()
    score_history = read_entity_scores(settings.scores_path, "COMP_0680")
    if score_history:
        latest = score_history[-1]
        overview["snapshot"] = latest
        overview["trajectory"] = [row["score"] for row in score_history]
        overview["trajectory_months"] = [str(row["month"]) for row in score_history]
        months, invoice_amount = read_entity_series(
            settings.scores_path, "COMP_0680", "invoice_amount"
        )
        _, invoice_count = read_entity_series(
            settings.scores_path, "COMP_0680", "invoice_count"
        )
        _, collection_delay = read_entity_series(
            settings.scores_path, "COMP_0680", "collection_delay_days"
        )
        if months:
            overview["series"] = {
                "months": months,
                "invoice_amount": invoice_amount,
                "invoice_count": invoice_count,
                "collection_delay_days": collection_delay,
            }
        overview["group"]["score"] = latest["score"]
        overview["group"]["delta"] = latest["delta"]
        for company in overview["companies"]:
            if company["id"] == latest["entity_id"]:
                company["score"] = latest["score"]
                company["delta"] = latest["delta"]
                company["signal"] = {
                    "improving": "Mejora prevista",
                    "deteriorating": "Deterioro previsto",
                    "stable": "Trayectoria estable",
                }[latest["trend"]]
    with Session(engine) as session:
        stored = {
            action.id: action.status
            for action in session.exec(select(RecommendedAction))
        }
    labels = {
        "pending": "Por iniciar",
        "in_progress": "En curso",
        "resolved": "Resuelta",
        "reopened": "Reabierta",
    }
    for action in overview["actions"]:
        action["status"] = labels.get(
            stored.get(action["id"], "pending"), stored.get(action["id"], "Por iniciar")
        )
    with Session(engine) as session:
        company_ids = [company["id"] for company in overview["companies"]]
        classifications = get_classifications(
            session,
            company_ids,
            dataset_hash=settings.active_dataset_hash,
        )
        for company in overview["companies"]:
            record = classifications.get(company["id"])
            if record is None:
                continue
            company["industry"] = apply_demo_override(
                company["id"],
                record.model_dump(),
            )
    return overview


@app.get("/api/v1/actions", response_model=list[RecommendedAction])
def get_actions() -> list[RecommendedAction]:
    with Session(engine) as session:
        return list(session.exec(select(RecommendedAction)))


def _build_benchmark_study(session: Session, study: BenchmarkStudy) -> BenchmarkStudyRead:
    industries = session.exec(
        select(BenchmarkIndustryMetric)
        .where(BenchmarkIndustryMetric.study_id == study.id)
        .order_by(BenchmarkIndustryMetric.rank)
    ).all()
    return BenchmarkStudyRead(
        id=study.id,
        source=study.source,
        title=study.title,
        data_period=study.data_period,
        report_year=study.report_year,
        source_url=study.source_url,
        description=study.description,
        industries=[
            BenchmarkIndustryMetricRead(
                industry=metric.industry,
                industry_slug=metric.industry_slug,
                rank=metric.rank,
                avg_days_to_collect=metric.avg_days_to_collect,
                open_ar_overdue_ratio=metric.open_ar_overdue_ratio,
                overdue_aging_120d_ratio=metric.overdue_aging_120d_ratio,
                ar_health_index=metric.ar_health_index,
                commentary=metric.commentary,
            )
            for metric in industries
        ],
    )


@app.get("/api/v1/benchmarks", response_model=list[BenchmarkStudyRead])
def list_benchmarks() -> list[BenchmarkStudyRead]:
    with Session(engine) as session:
        studies = session.exec(select(BenchmarkStudy).order_by(BenchmarkStudy.report_year.desc())).all()
        return [_build_benchmark_study(session, study) for study in studies]


@app.get("/api/v1/benchmarks/{study_id}", response_model=BenchmarkStudyRead)
def get_benchmark(study_id: str) -> BenchmarkStudyRead:
    with Session(engine) as session:
        study = session.get(BenchmarkStudy, study_id.upper())
        if study is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Benchmark study not found")
        return _build_benchmark_study(session, study)


@app.get("/api/v1/companies/{entity_id}/debt-products", response_model=CompanyDebtProductsRead)
def get_company_debt_products(entity_id: str) -> CompanyDebtProductsRead:
    normalized = entity_id.upper()
    return CompanyDebtProductsRead(
        entity_id=normalized,
        products=list_debt_products(normalized),
    )


@app.get("/api/v1/companies/{entity_id}/industry", response_model=IndustryClassificationRead)
def get_company_industry(
    entity_id: str,
    dataset_hash: str | None = None,
) -> IndustryClassificationRead:
    with Session(engine) as session:
        record = get_classification(
            session,
            entity_id,
            dataset_hash=dataset_hash or settings.active_dataset_hash,
        )
        if record is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Industry classification not found")
        return IndustryClassificationRead.model_validate(
            apply_demo_override(entity_id, record.model_dump())
        )


@app.get("/api/v1/companies/industry", response_model=list[IndustryClassificationRead])
def list_companies_industry(
    ids: str,
    dataset_hash: str | None = None,
) -> list[IndustryClassificationRead]:
    entity_ids = [item.strip() for item in ids.split(",") if item.strip()]
    with Session(engine) as session:
        records = get_classifications(
            session,
            entity_ids,
            dataset_hash=dataset_hash or settings.active_dataset_hash,
        )
    return [
        IndustryClassificationRead.model_validate(
            apply_demo_override(entity_id, records[entity_id].model_dump())
        )
        for entity_id in entity_ids
        if entity_id.upper() in records
    ]


@app.get("/api/v1/industry/distribution")
def get_industry_distribution(dataset_hash: str | None = None) -> dict[str, int]:
    with Session(engine) as session:
        return industry_distribution(
            session,
            dataset_hash=dataset_hash or settings.active_dataset_hash,
        )


@app.get("/api/v1/scores/{entity_id}")
def get_scores(entity_id: str) -> list[dict[str, object]]:
    return read_entity_scores(settings.scores_path, entity_id)


@app.patch("/api/v1/actions/{action_id}", response_model=RecommendedAction)
def update_action(action_id: str, update: ActionUpdate) -> RecommendedAction:
    with Session(engine) as session:
        action = session.get(RecommendedAction, action_id)
        if action is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Action not found")
        action.status = update.status
        session.add(action)
        session.commit()
        session.refresh(action)
        return action


@app.post("/api/v1/scenarios", response_model=ScenarioResponse)
def calculate_scenario(request: ScenarioRequest) -> ScenarioResponse:
    latest = read_latest_score(settings.scores_path, "COMP_0680")
    base_score = float(latest["score"]) if latest else 68.0
    improvement = min(
        18,
        request.collection_days * 0.22
        + request.refinance_amount / 60_000
        + request.payment_extension_days * 0.12,
    )
    projected = round(base_score + improvement, 1)
    scenario_id = f"SCN_{uuid4().hex[:12]}" if request.persist else "preview"
    low = max(0, projected - 3.5)
    high = min(100, projected + 2.5)
    if request.persist:
        with Session(engine) as session:
            session.add(
                ScenarioRecord(
                    id=scenario_id,
                    entity_id="COMP_0680",
                    base_score=base_score,
                    assumptions_json=json.dumps(request.model_dump()),
                    status="calculated",
                )
            )
            projection_path = [
                round(base_score + (projected - base_score) * offset / 4, 2)
                for offset in range(1, 5)
            ]
            for offset, score in enumerate(projection_path, start=1):
                session.add(
                    ScenarioProjection(
                        id=f"{scenario_id}_{offset}",
                        scenario_id=scenario_id,
                        month_offset=offset,
                        score=score,
                        confidence_low=max(0, score - 3.5),
                        confidence_high=min(100, score + 2.5),
                    )
                )
            session.commit()
    return ScenarioResponse(
        scenario_id=scenario_id,
        status="calculated" if request.persist else "preview",
        base_score=base_score,
        projected_score=projected,
        projected_cash=int(
            request.refinance_amount
            + request.collection_days * 2_800
            + request.payment_extension_days * 1_500
        ),
        confidence_low=low,
        confidence_high=high,
    )
