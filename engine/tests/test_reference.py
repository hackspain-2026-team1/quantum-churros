"""fit-reference: the only cohort-level step. Frozen output, aggregates only."""

from __future__ import annotations

import json
from dataclasses import replace

import polars as pl
import pytest
from xray_engine import reference
from xray_engine.contracts import PILLAR_KEYS, SERIES_KEYS, SIZE_BANDS, SNAPSHOT_SCHEMA
from xray_engine.params import DEFAULT_PARAMS_PATH, load_params, params_hash
from xray_engine.scoring import score_dataset


def test_quantile_is_linear_interpolation() -> None:
    values = [0.0, 10.0, 20.0, 30.0, 40.0]
    assert reference.quantile(values, 0.5) == 20.0
    assert reference.quantile(values, 0.1) == pytest.approx(4.0)
    assert reference.quantile(values, 1.0) == 40.0 and reference.quantile([7.0], 0.25) == 7.0
    with pytest.raises(ValueError):
        reference.quantile([], 0.5)


def test_a_thin_band_joins_its_thinner_neighbour() -> None:
    alone = {band: (band,) for band in SIZE_BANDS}
    assert reference.band_pools({"micro": 900, "small": 800, "medium": 1300, "large": 800}) == alone
    # large is thin: it joins medium, and both read the pooled table
    pooled = reference.band_pools({"micro": 900, "small": 800, "medium": 1300, "large": 40})
    assert pooled["large"] == pooled["medium"] == ("medium", "large")
    assert pooled["micro"] == ("micro",) and pooled["small"] == ("small",)
    # a thin band in the middle picks the thinner side
    middle = reference.band_pools({"micro": 900, "small": 100, "medium": 200, "large": 800})
    assert middle["small"] == middle["medium"] == ("small", "medium")
    # pooling goes on until the pool is thick enough
    chain = reference.band_pools({"micro": 60, "small": 60, "medium": 60, "large": 800})
    assert chain["micro"] == chain["small"] == chain["medium"] == ("micro", "small", "medium")
    everything = reference.band_pools({"micro": 10, "small": 10, "medium": 10, "large": 10})
    assert set(everything.values()) == {tuple(SIZE_BANDS)}


def _scores(rows: list[dict]) -> pl.DataFrame:
    """A snapshot-shaped frame with only the columns the fit reads."""
    records = []
    for row in rows:
        records.append({
            "entity_kind": row.get("entity_kind", "group"),
            "feed_live": row.get("feed_live", True),
            "pillars": {key: row.get(key) for key in PILLAR_KEYS},
            "series": {key: row.get(f"raw_{key}") for key in SERIES_KEYS},
        })
    schema = {name: SNAPSHOT_SCHEMA[name] for name in ("entity_kind", "feed_live", "pillars", "series")}
    return pl.DataFrame(records, schema=schema)


def test_medians_read_live_group_rows_only() -> None:
    frame = _scores(
        [{"liquidity": 10.0 * step, "activity": 50.0} for step in range(1, 6)]
        + [{"liquidity": 0.0, "feed_live": False}, {"liquidity": 0.0, "entity_kind": "company"}]
    )
    medians = reference.fit_reference_medians(frame)
    assert medians == {"liquidity": 30.0, "activity": 50.0}  # a pillar nobody has is left out


def test_calibration_review_accepts_and_rejects(params) -> None:
    centred = _scores([{"raw_activity_coverage": 0.9 + 0.002 * step} for step in range(101)])
    table = reference.check_anchor_calibration(centred, params)["tables"]["activity_coverage"]
    assert table["acceptable"] is True and table["at_0_share"] == 0.0 and table["at_100_share"] == 0.0
    assert table["median_score"] == pytest.approx(params.anchors["activity_coverage"](1.0))
    assert list(table["raw_quantiles"]) == ["p10", "p25", "p50", "p75", "p90"]

    saturated = _scores(
        [{"raw_activity_coverage": 1.0}] * 70 + [{"raw_activity_coverage": 0.1}] * 15
        + [{"raw_activity_coverage": 9.0}] * 15
    )
    table = reference.check_anchor_calibration(saturated, params)["tables"]["activity_coverage"]
    assert (table["at_0_share"], table["at_100_share"]) == (0.15, 0.15)
    assert table["acceptable"] is False  # the median is fine, 30% of the rows saturate

    generous = _scores([{"raw_debt_burden": 0.001}] * 50)
    table = reference.check_anchor_calibration(generous, params)["tables"]["debt_burden"]
    assert table["median_score"] > 75.0 and table["acceptable"] is False
    empty = reference.check_anchor_calibration(generous, params)["tables"]["activity_momentum"]
    assert empty == {"group_months": 0, "acceptable": None}


@pytest.fixture(scope="module")
def fitted(datasets, tmp_path_factory):
    root = tmp_path_factory.mktemp("fit")
    data = datasets.make(root / "data", n_groups=9, seed=3).path
    base = load_params()
    out, report = root / "fitted.json", root / "report.json"
    stamped = reference.fit_reference(data, out, base=base, cache_dir=root / "cache", report_path=report)
    return dict(root=root, data=data, base=base, out=out, report=report, stamped=stamped)


def test_fit_writes_a_verified_frozen_file(fitted) -> None:
    stamped, base = fitted["stamped"], fitted["base"]
    loaded = load_params(fitted["out"])  # verifies the sha256
    assert loaded == stamped and stamped.sha256 == params_hash(stamped)
    assert stamped.fitted and stamped.reference.fitted and len(stamped.fitted_on) == 64
    assert set(stamped.reference.medians) == set(PILLAR_KEYS)
    # hand-set values are never touched by the fit
    assert stamped.anchors == base.anchors and stamped.weights == base.weights
    assert (stamped.penalty, stamped.caps, stamped.bands, stamped.trajectory) == (
        base.penalty, base.caps, base.bands, base.trajectory
    )
    assert [rule.pattern for rule in stamped.dash_rules] == [rule.pattern for rule in base.dash_rules]
    for table in stamped.liquidity.band_anchors.values():
        assert table.points[0] == (0.0, 0.0)
        assert tuple(y for _, y in table.points[1:]) == stamped.liquidity.band_scores


def test_fit_is_idempotent_and_cohort_level_only(fitted) -> None:
    again = reference.fit_reference(
        fitted["data"], fitted["root"] / "again.json", base=fitted["stamped"],
        cache_dir=fitted["root"] / "cache",
    )
    assert again.sha256 == fitted["stamped"].sha256
    report = fitted["report"].read_text(encoding="utf-8")
    document = json.loads(report)
    assert document["params_hash"] == fitted["stamped"].sha256
    assert set(document["liquidity_bands"]) == set(SIZE_BANDS)
    assert set(document["calibration"]["tables"]) == set(reference.REVIEWED_TABLES)
    # aggregates only: no entity of the cohort is named
    assert "GROUP_" not in report and "COMPANY_" not in report
    assert "GROUP_" not in fitted["out"].read_text(encoding="utf-8")


def test_small_bands_are_pooled_or_keep_the_base_tables(fitted) -> None:
    bands = json.loads(fitted["report"].read_text(encoding="utf-8"))["liquidity_bands"]
    for band, item in bands.items():
        assert item["pooled_group_months"] >= item["group_months"]
        if item["fitted"]:
            assert item["pooled_group_months"] >= reference.MIN_BAND_OBSERVATIONS
        else:
            kept = fitted["base"].liquidity.band_anchors[band]
            assert item["anchors"] == [list(point) for point in kept.points]


def test_predict_with_the_fitted_file_stamps_its_hash(fitted) -> None:
    stamped = fitted["stamped"]
    result = score_dataset(fitted["data"], stamped, cache_dir=fitted["root"] / "cache")
    assert set(result.snapshots["params_hash"]) == {stamped.sha256}
    moved = replace(stamped, reference=replace(stamped.reference, medians={
        key: value + 1.0 for key, value in stamped.reference.medians.items()
    }))
    shifted = score_dataset(fitted["data"], moved, cache_dir=fitted["root"] / "cache")
    # B_k only moves the explanation (base, contributions), never the score
    assert shifted.snapshots["score"].equals(result.snapshots["score"])
    assert not shifted.snapshots["base"].equals(result.snapshots["base"])


@pytest.mark.dataset
def test_the_frozen_file_is_the_fit_of_the_real_dataset(real_data_dir, params, tmp_path) -> None:
    assert DEFAULT_PARAMS_PATH.is_file()
    report = tmp_path / "report.json"
    again = reference.fit_reference(real_data_dir, tmp_path / "refit.json", base=params, report_path=report)
    assert again.sha256 == params.sha256 and again.fitted_on == params.fitted_on
    document = json.loads(report.read_text(encoding="utf-8"))
    for band, item in document["liquidity_bands"].items():
        assert item["fitted"] and item["pooled_group_months"] >= reference.MIN_BAND_OBSERVATIONS, band
    for name, item in document["calibration"]["tables"].items():
        assert item["acceptable"] is True, name
        assert item["at_0_share"] + item["at_100_share"] <= reference.REVIEW_MAX_SATURATED
    assert "GROUP_" not in report.read_text(encoding="utf-8")
