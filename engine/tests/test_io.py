"""Cache build: record counts, integer cents, forced dtypes, window and idempotence."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from xray_engine import io

REAL_RECORDS = {"transactions": 2_556_437, "invoices": 897_894}
REAL_CACHE_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "cache"


@pytest.fixture(scope="module")
def cache(synthetic, tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("io-cache")


@pytest.fixture(scope="module")
def tables(synthetic, cache) -> io.Tables:
    return io.load_tables(synthetic.path, cache)


def _source(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(line.replace("\x00", "") for line in source))


def test_records_are_not_lines(tmp_path) -> None:
    path = tmp_path / "sample.csv"
    path.write_bytes(
        b"id,text\r\n"
        b'1,"two\r\nlines"\r\n'
        b'2,"three\n\nlines, a comma and a ""quote"""\r\n'
        b"3,nul\x00 inside\r\n"
        b'4,"nul\x00 and\nnewline"\r\n'
        b"5,\r\n"
    )
    assert io.count_csv_records(path) == 5
    assert len(path.read_bytes().splitlines()) > 6  # physical lines overcount
    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbfid,text\n1,a\n")
    assert io.count_csv_records(bom) == 1
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"id,text\n")
    assert io.count_csv_records(empty) == 0


def test_cache_holds_exactly_the_recounted_records(synthetic, cache, tables) -> None:
    folder = cache / tables.dataset_hash
    manifest = json.loads((folder / io.MANIFEST_FILE).read_text(encoding="utf-8"))
    pending = len(synthetic.pending_transaction_ids)
    for name in io.TABLE_NAMES:
        records = len(_source(synthetic.path / f"{name}.csv"))
        dropped = pending if name == "transactions" else 0
        assert io.count_csv_records(synthetic.path / f"{name}.csv") == records, name
        assert manifest["tables"][name] == {
            "records": records, "pending_dropped": dropped, "cached": records - dropped,
        }, name
        assert pl.read_parquet(folder / f"{name}.parquet").height == records - dropped, name
        assert getattr(tables, name).height == records - dropped, name
    booked = {
        row["transaction_id"]: row for row in _source(synthetic.path / "transactions.csv")
        if row["status"] != "pending"
    }
    cached = {row["transaction_id"]: row for row in tables.transactions.to_dicts()}
    assert cached.keys() == booked.keys()
    for key, row in booked.items():  # every text field survives: newlines kept, NUL bytes removed
        assert cached[key]["description"] == (row["description"] or None)
        assert cached[key]["counterparty_id"] == (row["counterparty_id"] or None)
    assert "\n" in cached[synthetic.newline_transaction_id]["description"]
    raw = (synthetic.path / "transactions.csv").read_bytes()
    assert b"\x00" in raw and "\x00" not in cached[synthetic.nul_transaction_id]["description"]


def test_money_is_integer_cents(synthetic, datasets, tables) -> None:
    for name, key, columns in (
        ("transactions", "transaction_id", {"amount_cents": "amount"}),
        ("invoices", "operation_id", {"amount_cents": "amount", "pending_cents": "pending_amount"}),
        ("balances", "product_id", {"balance_cents": "balance", "granted_cents": "granted"}),
    ):
        source = {row[key]: row for row in _source(synthetic.path / f"{name}.csv")}
        frame = getattr(tables, name)
        for cached, raw in columns.items():
            assert frame.schema[cached] == pl.Int64
            for row_key, cents in frame.select(key, cached).iter_rows():
                text = source[row_key][raw]
                assert cents == (datasets.to_cents(text) if text else None), (name, raw)
    sentinel = tables.balances.filter(pl.col("product_id") == synthetic.sentinel_product_id)
    assert sentinel["balance_cents"].to_list() == [-99_999_999_900]


def test_booked_rows_are_normalised(synthetic, tables) -> None:
    frame = tables.transactions
    assert set(frame["status"].unique()) == {io.BOOKED_STATUS}  # blank status is booked
    assert set(synthetic.blank_status_transaction_ids) <= set(frame["transaction_id"])
    assert not set(synthetic.pending_transaction_ids) & set(frame["transaction_id"])
    assert frame["category"].null_count() == 0
    assert frame.select((pl.col("month") == pl.col("date").dt.month_start()).all()).item()
    assert frame["date"].dtype == pl.Date and frame["date"].null_count() == 0


def test_a_small_folder_with_all_null_columns_loads(synthetic, datasets, tmp_path) -> None:
    small = datasets.filter(synthetic.path, tmp_path / "small", [synthetic.short_history_group_id])
    rows = _source(small / "transactions.csv")
    for row in rows:  # columns a small extraction leaves empty
        row.update(counterparty_id="", accounting_status="", category="")
    with (small / "transactions.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=datasets.headers["transactions.csv"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tables = io.load_tables(small, tmp_path / "cache")
    for name in io.TABLE_NAMES:
        assert dict(getattr(tables, name).schema) == io.CACHE_SCHEMAS[name], name
    assert tables.invoices.height == 0 and tables.debt_products.height == 0
    assert tables.transactions.height == len(rows)
    assert tables.transactions["counterparty_id"].null_count() == len(rows)
    assert set(tables.transactions["category"].unique()) == {io.DASH_CATEGORY}
    assert tables.window.last_month == synthetic.last_month


def _dates(*days: date) -> pl.DataFrame:
    return pl.DataFrame({"date": list(days)}, schema={"date": pl.Date})


def test_window_is_derived_from_the_dates() -> None:
    none = _dates()
    window = io.derive_window(_dates(date(2025, 1, 14), date(2025, 6, 2)), none)
    assert window == io.Window(date(2025, 1, 1), date(2025, 5, 1), date(2025, 6, 2))
    # a month end closes its month, leap years included
    assert io.derive_window(_dates(date(2024, 1, 3), date(2024, 2, 29)), none).last_month == date(2024, 2, 1)
    assert io.derive_window(_dates(date(2025, 1, 3), date(2025, 2, 28)), none).last_month == date(2025, 2, 1)
    assert io.derive_window(_dates(date(2024, 11, 3), date(2025, 1, 1)), none).last_month == date(2024, 12, 1)
    # a later balance moves the extraction date
    late = io.derive_window(_dates(date(2025, 1, 14), date(2025, 6, 2)), _dates(date(2025, 6, 30)))
    assert (late.last_month, late.as_of) == (date(2025, 6, 1), date(2025, 6, 30))
    with pytest.raises(ValueError):
        io.derive_window(_dates(date(2025, 6, 2), date(2025, 6, 20)), none)  # no complete month
    with pytest.raises(ValueError):
        io.derive_window(none, _dates(date(2025, 6, 30)))


def test_window_of_the_synthetic_dataset(synthetic, tables) -> None:
    assert tables.window == io.Window(synthetic.first_month, synthetic.last_month, synthetic.as_of)


def test_shuffled_files_give_identical_frames(synthetic, datasets, tables, tmp_path) -> None:
    shuffled = datasets.shuffle(synthetic.path, tmp_path / "shuffled", seed=3)
    other = io.load_tables(shuffled, tmp_path / "cache")
    assert other.dataset_hash != tables.dataset_hash
    for name in io.TABLE_NAMES:
        assert getattr(other, name).equals(getattr(tables, name)), name
    assert tables.transactions["transaction_id"].is_sorted()
    assert tables.invoices["operation_id"].is_sorted()


def test_cache_is_reused_and_rebuilt_when_incomplete(synthetic, tmp_path) -> None:
    root = tmp_path / "cache"
    folder = io.build_cache(synthetic.path, root)
    assert folder == root / io.dataset_fingerprint(synthetic.path)
    assert sorted(path.name for path in folder.iterdir()) == sorted(
        [io.MANIFEST_FILE, *(f"{name}.parquet" for name in io.TABLE_NAMES)]
    )
    stamps = {path.name: path.stat().st_mtime_ns for path in folder.iterdir()}
    assert io.build_cache(synthetic.path, root) == folder
    assert {path.name: path.stat().st_mtime_ns for path in folder.iterdir()} == stamps  # untouched

    (folder / "invoices.parquet").unlink()  # incomplete: rebuilt
    io.build_cache(synthetic.path, root)
    assert (folder / "invoices.parquet").is_file()

    manifest = json.loads((folder / io.MANIFEST_FILE).read_text(encoding="utf-8"))
    (folder / io.MANIFEST_FILE).write_text(json.dumps(dict(manifest, cache_version=-1)), encoding="utf-8")
    io.build_cache(synthetic.path, root)  # another layout: rebuilt
    rebuilt = json.loads((folder / io.MANIFEST_FILE).read_text(encoding="utf-8"))
    assert rebuilt == manifest and rebuilt["cache_version"] == io.CACHE_VERSION


def test_broken_folders_are_refused(synthetic, tmp_path) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(synthetic.path, broken)
    (broken / "balances.csv").unlink()
    with pytest.raises(FileNotFoundError, match="balances.csv"):
        io.build_cache(broken, tmp_path / "cache")
    rows = _source(synthetic.path / "balances.csv")
    with (broken / "balances.csv").open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["product_id", "company_id", "date"], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="balance"):
        io.build_cache(broken, tmp_path / "cache")


@pytest.mark.dataset
def test_real_cache_holds_every_record(real_data_dir) -> None:
    tables = io.load_tables(real_data_dir, REAL_CACHE_DIR)
    folder = REAL_CACHE_DIR / tables.dataset_hash
    manifest = json.loads((folder / io.MANIFEST_FILE).read_text(encoding="utf-8"))
    for name, records in REAL_RECORDS.items():
        counts = manifest["tables"][name]
        assert counts["records"] == records == io.count_csv_records(real_data_dir / f"{name}.csv")
        assert counts["cached"] == records - counts["pending_dropped"] == getattr(tables, name).height
        rows = pl.scan_parquet(folder / f"{name}.parquet").select(pl.len()).collect().item()
        assert rows == counts["cached"], name
    assert manifest["tables"]["invoices"]["pending_dropped"] == 0
    assert 0 < manifest["tables"]["transactions"]["pending_dropped"] < 0.01 * REAL_RECORDS["transactions"]

    frame = tables.transactions
    assert frame["transaction_id"].n_unique() == frame.height and frame["transaction_id"].is_sorted()
    text = frame.select(
        nul=pl.col("description").str.contains("\x00", literal=True).sum(),
        multiline=pl.col("description").str.contains("\n", literal=True).sum(),
    ).row(0, named=True)
    assert text["nul"] == 0 and text["multiline"] > 10_000  # quoted newlines survive, NUL bytes do not
    assert b"\x00" in (real_data_dir / "transactions.csv").read_bytes()
    for name in io.TABLE_NAMES:
        assert dict(getattr(tables, name).schema) == io.CACHE_SCHEMAS[name], name
    assert tables.window == io.Window(date(2024, 9, 1), date(2026, 8, 1), date(2026, 9, 1))
