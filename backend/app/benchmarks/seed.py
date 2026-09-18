from sqlmodel import Session

from ..models import BenchmarkIndustryMetric, BenchmarkStudy
from .tesorio_ar_2025 import (
    INDUSTRY_METRICS,
    STUDY_DATA_PERIOD,
    STUDY_DESCRIPTION,
    STUDY_ID,
    STUDY_REPORT_YEAR,
    STUDY_SOURCE,
    STUDY_SOURCE_URL,
    STUDY_TITLE,
)


def seed_benchmark_studies(session: Session) -> None:
    if session.get(BenchmarkStudy, STUDY_ID) is not None:
        return

    session.add(
        BenchmarkStudy(
            id=STUDY_ID,
            source=STUDY_SOURCE,
            title=STUDY_TITLE,
            data_period=STUDY_DATA_PERIOD,
            report_year=STUDY_REPORT_YEAR,
            source_url=STUDY_SOURCE_URL,
            description=STUDY_DESCRIPTION,
        )
    )
    session.flush()
    for metric in INDUSTRY_METRICS:
        session.add(
            BenchmarkIndustryMetric(
                id=f"{STUDY_ID}_{metric.industry_slug}",
                study_id=STUDY_ID,
                industry=metric.industry,
                industry_slug=metric.industry_slug,
                rank=metric.rank,
                avg_days_to_collect=metric.avg_days_to_collect,
                open_ar_overdue_ratio=metric.open_ar_overdue_ratio,
                overdue_aging_120d_ratio=metric.overdue_aging_120d_ratio,
                ar_health_index=metric.ar_health_index,
                commentary=metric.commentary,
            )
        )
