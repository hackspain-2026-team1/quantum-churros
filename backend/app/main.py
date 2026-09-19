from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import Session, create_engine, select
from xray_engine.artifacts import read_entity_scores

from .benchmarks import seed_benchmark_studies
from .config import settings
from .industry import get_classification, get_classifications, industry_distribution
from .models import (
    BenchmarkIndustryMetric,
    BenchmarkIndustryMetricRead,
    BenchmarkStudy,
    BenchmarkStudyRead,
    IndustryClassificationRead,
)

engine = create_engine(settings.database_url, pool_pre_ping=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Published reference studies only; scores and entities always come from the engine.
    with Session(engine) as session:
        seed_benchmark_studies(session)
        session.commit()
    yield


app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
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


@app.get("/api/v1/bundle/{path:path}")
def get_bundle_file(path: str) -> FileResponse:
    """Serve one file of the engine's static export bundle (the same files the public site hosts)."""
    root = settings.bundle_dir.resolve()
    # resolve() collapses '..' and follows symlinks, so the guard sees the real location.
    target = (root / path).resolve()
    if (
        not target.is_relative_to(root)
        or target.suffix != ".json"
        or not target.is_file()
    ):
        raise HTTPException(status_code=404, detail="Bundle file not found")
    return FileResponse(
        target,
        media_type="application/json",
        headers={"Cache-Control": "no-cache"},
    )


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
            raise HTTPException(status_code=404, detail="Benchmark study not found")
        return _build_benchmark_study(session, study)


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
        raise HTTPException(status_code=404, detail="Industry classification not found")
    return record


@app.get("/api/v1/companies/industry", response_model=list[IndustryClassificationRead])
def list_companies_industry(
    ids: str,
    dataset_hash: str | None = None,
) -> list[IndustryClassificationRead]:
    entity_ids = [item.strip().upper() for item in ids.split(",") if item.strip()]
    with Session(engine) as session:
        records = get_classifications(
            session,
            entity_ids,
            dataset_hash=dataset_hash or settings.active_dataset_hash,
        )
    return [records[entity_id] for entity_id in entity_ids if entity_id in records]


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
