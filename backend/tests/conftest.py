from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel

from app import models  # noqa: F401
from app.benchmarks import seed_benchmark_studies
from app.industry import run_classification
from app.main import engine

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"


@pytest.fixture(autouse=True)
def ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_benchmark_studies(session)
        session.commit()
        if DATA_DIR.exists():
            run_classification(session, DATA_DIR, force=True)
