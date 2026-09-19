"""Cohort independence: a group scored alone equals the same group in a full run."""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

import polars as pl
import pytest
from xray_engine import io
from xray_engine.scoring import score_dataset

TOL = 1e-9
KEYS = ["entity_kind", "entity_id", "month"]
CATEGORICALS = [
    "band", "size_band", "branch", "caps_fired", "flags", "abstained", "abstain_reason",
    "feed_live", "carried_from", "confidence_label", "trend", "persistence_months",
    "detected_since", "gates",
]
VERDICT = ["available", "reason", "direction", "nature", "horizon", "shock_month", "pillars_moved"]


def categoricals(snapshots: pl.DataFrame) -> pl.DataFrame:
    """Everything on a snapshot that is a label, not a number: equal, not close."""
    call = [pl.col("trajectory").struct.field(name).alias(f"trajectory_{name}") for name in VERDICT]
    return snapshots.sort(KEYS).select(*KEYS, *CATEGORICALS, *call)


@pytest.mark.parametrize(
    "groups",
    [["GROUP_0001"], ["GROUP_0004"], ["GROUP_0002", "GROUP_0005"], ["GROUP_0003", "GROUP_0006", "GROUP_0008"]],
)
def test_groups_scored_alone_equal_the_full_run(
    datasets, params, same_frames, tmp_path_factory, groups
) -> None:
    root = tmp_path_factory.mktemp("isolation")
    full_dir = datasets.make(root / "full", n_groups=9, seed=7).path
    full = score_dataset(full_dir, params, cache_dir=root / "cache")
    alone_dir = datasets.filter(full_dir, root / "alone", groups)
    alone = score_dataset(alone_dir, params, cache_dir=root / "cache")

    expected = full.snapshots.filter(pl.col("group_id").is_in(groups))
    assert expected.height > 0 and set(alone.snapshots["group_id"]) == set(groups)
    same_frames(alone.snapshots, expected, keys=KEYS, tol=TOL, ignore=("dataset_hash",))
    same_frames(
        alone.panel, full.panel.filter(pl.col("group_id").is_in(groups)), keys=KEYS, tol=TOL
    )
    wanted = [alert for alert in full.alerts if alert.group_id in groups]
    assert list(alone.alerts) == wanted
    assert {key: card for key, card in full.profiles.items() if card.group_id in groups} == dict(
        alone.profiles
    )
    assert alone.params.sha256 == full.params.sha256


class _Tap:
    """Feeds the csv reader NUL-free lines and keeps the raw ones it consumed."""

    def __init__(self, source) -> None:
        self.source, self.raw = source, []

    def __iter__(self) -> "_Tap":
        return self

    def __next__(self) -> str:
        line = next(self.source)
        self.raw.append(line)
        return line.replace("\x00", "")


def filter_csv(source: Path, target: Path, column: str, keep: set[str]) -> tuple[int, int]:
    """Copies the records whose ``column`` is in ``keep``; (records read, kept).

    The stdlib reader finds the records (quoted newlines included) and their
    key; a kept record is written as its raw text, so quoting, NUL bytes and
    line endings are those of the source file.
    """
    limit = csv.field_size_limit(sys.maxsize)
    try:
        with source.open(newline="", encoding="utf-8") as raw, target.open(
            "w", newline="", encoding="utf-8"
        ) as out:
            tap = _Tap(raw)
            reader = csv.reader(tap)
            header = next(reader)
            out.write("".join(tap.raw))
            tap.raw.clear()
            index = [name.lstrip("\ufeff") for name in header].index(column)
            read = kept = 0
            for record in reader:
                text = "".join(tap.raw)
                tap.raw.clear()
                if not record:
                    continue
                read += 1
                if record[index] in keep:
                    out.write(text)
                    kept += 1
    finally:
        csv.field_size_limit(limit)
    return read, kept


def subset_folder(source: Path, target: Path, groups: set[str]) -> Path:
    """Folder with the eight CSVs of ``groups`` only, filtered at file level."""
    target.mkdir(parents=True, exist_ok=True)
    with (source / "companies.csv").open(newline="", encoding="utf-8-sig") as handle:
        members = {row["company_id"] for row in csv.DictReader(handle) if row["group_id"] in groups}
    for name in io.TABLE_NAMES:
        by_group = name in ("groups", "companies")
        filter_csv(
            source / f"{name}.csv", target / f"{name}.csv",
            "group_id" if by_group else "company_id", groups if by_group else members,
        )
    return target


def test_file_level_filter_keeps_the_raw_records(tmp_path) -> None:
    source = tmp_path / "source.csv"
    text = (
        'transaction_id,company_id,description\r\n'
        'T1,C1,"two\nlines, ""quoted"""\r\n'
        'T2,C2,plain\r\n'
        'T3,C1,"nul\x00 inside"\r\n'
        '"T4","C1",""\r\n'
    )
    source.write_text(text, encoding="utf-8", newline="")
    assert filter_csv(source, tmp_path / "kept.csv", "company_id", {"C1"}) == (4, 3)
    kept = (tmp_path / "kept.csv").read_bytes().decode("utf-8")
    assert kept == text.replace("T2,C2,plain\r\n", "")
    assert io.count_csv_records(tmp_path / "kept.csv") == 3


def test_a_filtered_folder_scores_like_the_full_run(datasets, params, same_frames, tmp_path) -> None:
    full_dir = datasets.make(tmp_path / "full", n_groups=9, seed=11).path
    groups = {"GROUP_0002", "GROUP_0007"}
    alone_dir = subset_folder(full_dir, tmp_path / "alone", groups)
    full = score_dataset(full_dir, params, cache_dir=tmp_path / "cache")
    alone = score_dataset(alone_dir, params, cache_dir=tmp_path / "cache")
    expected = full.snapshots.filter(pl.col("group_id").is_in(groups))
    same_frames(alone.snapshots, expected, keys=KEYS, tol=TOL, ignore=("dataset_hash",))
    assert categoricals(alone.snapshots).equals(categoricals(expected))


@pytest.mark.dataset
def test_sixty_real_groups_scored_alone(real_data_dir, params, same_frames, tmp_path) -> None:
    with (real_data_dir / "groups.csv").open(newline="", encoding="utf-8-sig") as handle:
        every = sorted({row["group_id"] for row in csv.DictReader(handle)})
    groups = set(random.Random(7).sample(every, 60))
    subset = subset_folder(real_data_dir, tmp_path / "subset", groups)
    assert io.count_csv_records(subset / "groups.csv") == 60

    full = score_dataset(real_data_dir, params)
    alone = score_dataset(subset, params, cache_dir=tmp_path / "cache")
    assert set(alone.snapshots["group_id"]) <= groups
    assert alone.snapshots.filter(pl.col("entity_kind") == "group")["entity_id"].n_unique() == 60

    expected = full.snapshots.filter(pl.col("group_id").is_in(groups))
    same_frames(alone.snapshots, expected, keys=KEYS, tol=TOL, ignore=("dataset_hash",))
    # bands, calls, flags and caps are equal, not just close
    assert categoricals(alone.snapshots).equals(categoricals(expected))
    same_frames(alone.panel, full.panel.filter(pl.col("group_id").is_in(groups)), keys=KEYS, tol=TOL)
    assert list(alone.alerts) == [alert for alert in full.alerts if alert.group_id in groups]
    assert alone.params.sha256 == full.params.sha256 == params.sha256
