"""The cache is a faithful copy: every record counted, NUL bytes and quoted newlines included."""

from __future__ import annotations

import json

import polars as pl
import pytest
from xray_engine import io

pytestmark = pytest.mark.xfail(raises=NotImplementedError, strict=False, reason="io is a stub")

REAL_RECORDS = {"transactions": 2_556_437, "invoices": 897_894}


def test_records_are_counted_not_lines(synthetic) -> None:
    for name, expected in synthetic.row_counts.items():
        assert io.count_csv_records(synthetic.path / name) == expected, name


def test_cache_keeps_every_booked_record(synthetic, tmp_path) -> None:
    folder = io.build_cache(synthetic.path, tmp_path / "cache")
    assert folder == tmp_path / "cache" / io.dataset_fingerprint(synthetic.path)
    assert io.build_cache(synthetic.path, tmp_path / "cache") == folder  # idempotent
    for name in io.TABLE_NAMES:
        frame = pl.read_parquet(folder / f"{name}.parquet")
        assert dict(frame.schema) == io.CACHE_SCHEMAS[name], name
    tables = io.load_tables(synthetic.path, tmp_path / "cache")
    pending = len(synthetic.pending_transaction_ids)
    assert tables.transactions.height == synthetic.row_counts["transactions.csv"] - pending
    assert tables.invoices.height == synthetic.row_counts["invoices.csv"]
    ids = set(tables.transactions["transaction_id"])
    assert set(synthetic.blank_status_transaction_ids) <= ids  # blank status is booked
    assert set(synthetic.orphan_transaction_ids) <= ids  # unknown product: the row stays
    assert not ids & set(synthetic.pending_transaction_ids)
    texts = dict(tables.transactions.select("transaction_id", "description").iter_rows())
    assert "\x00" not in texts[synthetic.nul_transaction_id]
    assert "\n" in texts[synthetic.newline_transaction_id]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_hash"] == tables.dataset_hash
    assert (tables.window.first_month, tables.window.last_month, tables.window.as_of) == (
        synthetic.first_month, synthetic.last_month, synthetic.as_of,
    )


@pytest.mark.dataset
def test_real_record_counts(real_data_dir) -> None:
    for name, expected in REAL_RECORDS.items():
        assert io.count_csv_records(real_data_dir / f"{name}.csv") == expected, name
