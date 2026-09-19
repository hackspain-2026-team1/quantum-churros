"""Cohort independence: a group scored alone equals the same group in a full run."""

from __future__ import annotations

import random

import polars as pl
import pytest
from xray_engine import io
from xray_engine.scoring import score_dataset

TOL = 1e-9
KEYS = ["entity_kind", "entity_id", "month"]

pytestmark = pytest.mark.xfail(
    raises=NotImplementedError, strict=False, reason="engine modules are stubs"
)


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


@pytest.mark.dataset
def test_sixty_real_groups_scored_alone(real_data_dir, params, same_frames, tmp_path) -> None:
    companies = pl.read_csv(real_data_dir / "companies.csv", schema_overrides=io.SCHEMAS["companies"])
    groups = random.Random(7).sample(sorted(companies["group_id"].unique().to_list()), 60)
    members = companies.filter(pl.col("group_id").is_in(groups))["company_id"].to_list()
    subset = tmp_path / "subset"
    subset.mkdir()
    for name in io.TABLE_NAMES:
        frame = pl.scan_csv(real_data_dir / f"{name}.csv", schema_overrides=io.SCHEMAS[name])
        keep = (
            pl.col("group_id").is_in(groups) if name == "groups" else pl.col("company_id").is_in(members)
        )
        if name == "companies":
            keep = pl.col("group_id").is_in(groups)
        frame.filter(keep).collect().write_csv(subset / f"{name}.csv")

    full = score_dataset(real_data_dir, params, cache_dir=tmp_path / "cache")
    alone = score_dataset(subset, params, cache_dir=tmp_path / "cache")
    expected = full.snapshots.filter(pl.col("group_id").is_in(groups))
    same_frames(alone.snapshots, expected, keys=KEYS, tol=TOL, ignore=("dataset_hash",))
