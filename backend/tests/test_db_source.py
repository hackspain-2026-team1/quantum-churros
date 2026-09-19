"""The engine reading ``source.*`` must see exactly what it sees in the CSV folder.

Needs a PostgreSQL with the dataset ingested (``make db-seed``) and the folder it
was ingested from: XRAY_TEST_SOURCE_DATABASE_URL and XRAY_DATA. Skipped otherwise.
"""

import os
from pathlib import Path

import pytest
from xray_engine import io

DATABASE_URL = os.environ.get("XRAY_TEST_SOURCE_DATABASE_URL")
DATA_DIR = os.environ.get("XRAY_DATA")

pytestmark = pytest.mark.skipif(
    not (DATABASE_URL and DATA_DIR), reason="needs XRAY_TEST_SOURCE_DATABASE_URL and XRAY_DATA"
)


def test_database_source_equals_csv_source(tmp_path) -> None:
    from_csv = io.load_source(Path(DATA_DIR), tmp_path / "csv")
    from_db = io.load_source(DATABASE_URL, tmp_path / "db")
    assert from_db.dataset_hash == from_csv.dataset_hash
    assert from_db.window == from_csv.window
    for table in io.TABLE_NAMES:
        assert getattr(from_db, table).equals(getattr(from_csv, table)), table
