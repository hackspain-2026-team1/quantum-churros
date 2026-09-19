"""Same input, same bytes: across runs, row order and thread count."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import polars as pl
from xray_engine.export import export_bundle
from xray_engine.scoring import score_dataset


def _tree_hash(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in folder.rglob("*") if item.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_two_runs_are_identical(synthetic, params, tmp_path) -> None:
    first = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache-a")
    second = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache-b")
    cached = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache-a")
    assert first.snapshots.equals(second.snapshots) and first.snapshots.equals(cached.snapshots)
    assert first.panel.equals(second.panel)
    assert first.alerts == second.alerts and first.profiles == second.profiles
    export_bundle(first, tmp_path / "bundle-a")
    export_bundle(second, tmp_path / "bundle-b")
    assert _tree_hash(tmp_path / "bundle-a") == _tree_hash(tmp_path / "bundle-b")


def test_row_order_of_the_files_does_not_matter(synthetic, datasets, params, tmp_path) -> None:
    shuffled_dir = datasets.shuffle(synthetic.path, tmp_path / "shuffled", seed=5)
    base = score_dataset(synthetic.path, params, cache_dir=tmp_path / "cache")
    shuffled = score_dataset(shuffled_dir, params, cache_dir=tmp_path / "cache")
    # the fingerprint covers the bytes of the files, so only that column may differ
    assert base.dataset_hash != shuffled.dataset_hash
    assert base.snapshots.drop("dataset_hash").equals(shuffled.snapshots.drop("dataset_hash"))
    assert base.panel.equals(shuffled.panel)
    assert base.alerts == shuffled.alerts


def _predict(data: Path, out: Path, threads: str | None) -> None:
    env = {key: value for key, value in os.environ.items() if key != "POLARS_MAX_THREADS"}
    if threads:
        env["POLARS_MAX_THREADS"] = threads
    command = [
        sys.executable, "-m", "xray_engine.cli", "predict", str(data), "--out", str(out / "artifacts"),
        "--export-dir", str(out / "bundle"), "--cache-dir", str(out / "cache"),
    ]
    done = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-2000:]


def test_thread_count_does_not_matter(synthetic, tmp_path) -> None:
    _predict(synthetic.path, tmp_path / "default", None)
    _predict(synthetic.path, tmp_path / "single", "1")
    default = pl.read_parquet(tmp_path / "default" / "artifacts" / "scores.parquet")
    single = pl.read_parquet(tmp_path / "single" / "artifacts" / "scores.parquet")
    assert default.equals(single)
    for name in ("scores_groups.csv", "scores_companies.csv"):
        assert (tmp_path / "default" / "artifacts" / name).read_bytes() == (
            tmp_path / "single" / "artifacts" / name
        ).read_bytes()
    assert _tree_hash(tmp_path / "default" / "bundle") == _tree_hash(tmp_path / "single" / "bundle")
