import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# app.main builds its SQLAlchemy engine at import time. Point it at a throwaway SQLite
# file before anything imports the app, so the suite never reads or writes a developer
# database and never needs the challenge dataset.
_DB_DIR = Path(tempfile.mkdtemp(prefix="xray-api-tests-"))
os.environ["DATABASE_URL"] = os.environ.get(
    "XRAY_TEST_DATABASE_URL", f"sqlite:///{_DB_DIR / 'test.db'}"
)

from app import models  # noqa: F401
from app.benchmarks import seed_benchmark_studies
from app.config import settings
from app.main import engine
from sqlmodel import Session, SQLModel

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_BUNDLE = REPO_ROOT / "tests" / "fixtures" / "bundle" / "v1"


def pytest_sessionfinish() -> None:
    engine.dispose()
    shutil.rmtree(_DB_DIR, ignore_errors=True)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_benchmark_studies(session)
        session.commit()


@pytest.fixture
def fixture_bundle(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Serve the contract fixture bundle (three synthetic groups) from the API."""
    assert (FIXTURE_BUNDLE / "manifest.json").is_file(), "contract fixture bundle is missing"
    monkeypatch.setattr(settings, "bundle_dir", FIXTURE_BUNDLE)
    yield FIXTURE_BUNDLE
