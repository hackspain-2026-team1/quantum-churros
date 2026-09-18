from pathlib import Path

import pytest
from app.ingest import TABLES, dataset_fingerprint, postgres_dsn, source_paths


def _source_fixture(root: Path, suffix: str = "") -> None:
    for spec in TABLES:
        header = ",".join(spec.columns)
        (root / spec.filename).write_text(f"{header}\n{suffix}")


def test_dataset_fingerprint_is_content_addressed(tmp_path) -> None:
    _source_fixture(tmp_path)
    first = dataset_fingerprint(source_paths(tmp_path))
    (tmp_path / "groups.csv").write_text(
        "group_id,erp,n_companies_in_sample\nGROUP_1,,1\n"
    )
    second = dataset_fingerprint(source_paths(tmp_path))
    assert first != second
    assert len(first) == 64


def test_source_paths_reports_every_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="groups.csv"):
        source_paths(tmp_path)


def test_ingestion_rejects_non_postgres_database() -> None:
    with pytest.raises(ValueError, match="requires PostgreSQL"):
        postgres_dsn("sqlite:///xray.db")
    assert (
        postgres_dsn("postgresql+psycopg://xray:secret@postgres/xray")
        == "postgresql://xray:secret@postgres/xray"
    )
