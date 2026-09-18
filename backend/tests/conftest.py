import pytest
from sqlmodel import Session, SQLModel

from app import models  # noqa: F401
from app.benchmarks import seed_benchmark_studies
from app.main import engine


@pytest.fixture(autouse=True)
def ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_benchmark_studies(session)
        session.commit()
