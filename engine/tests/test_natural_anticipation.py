"""Natural anticipation: portfolio AUC, injection calibration and rolling audit."""

from __future__ import annotations

import pytest
from xray_engine import io, natural_anticipation as na
from xray_engine import validation as v


@pytest.fixture(scope="module")
def scored(synthetic, params, tmp_path_factory) -> v.Scored:
    tables = io.load_tables(synthetic.path, tmp_path_factory.mktemp("anticipation-cache"))
    return v.score_core(tables, params)


def test_auc_handles_degenerate_classes_and_ties() -> None:
    assert na._auc([1.0, 2.0], [0, 0]) is None
    assert na._auc([1.0, 2.0], [1, 1]) is None
    assert na._auc([2.0, 1.0], [1, 0]) == pytest.approx(1.0)
    assert na._auc([1.0, 1.0], [1, 0]) == pytest.approx(0.5)


def test_anticipation_study_on_synthetic(scored) -> None:
    found = na.anticipation_study(scored)
    assert found["pass"] is None
    natural = found["natural"]
    assert natural["n_observations"] > 0
    assert natural["by_horizon"]["3"]["n_obs"] > natural["by_horizon"]["6"]["n_obs"]
    calibration = found["calibration_on_injection"]
    step = calibration["step"]
    ramp = calibration["ramp"]
    assert step["auc_h6"] >= 0.80
    assert ramp["auc_h6"] >= 0.70
    assert step["n_windows"] > 0 and ramp["n_windows"] == step["n_windows"]
    step_delay = step["detection_delay"]["median_months"]
    ramp_delay = ramp["detection_delay"]["median_months"]
    assert step_delay is not None and ramp_delay is not None and step_delay < ramp_delay
    assert step["structural_delay"]["median_months"] <= 3


def test_natural_anticipation_wired_in_validation() -> None:
    assert "natural_anticipation" in v.CHECK_KEYS
    assert "natural_anticipation" in v.QUICK_SKIPPED
    assert v.TITLES["natural_anticipation"] == "Anticipación natural"


def test_audit_rolling_origin_on_synthetic(scored) -> None:
    natural = na.natural_portfolio_study(scored, horizons=(6,))
    audit = na.audit_rolling_origin(scored, natural, horizon=6, epsilon=1.0)
    assert "cuts" in audit
