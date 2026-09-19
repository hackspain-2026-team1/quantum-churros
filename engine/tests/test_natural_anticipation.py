"""Natural anticipation: portfolio AUC, injection calibration and rolling audit."""

from __future__ import annotations

import pytest
from xray_engine import io, natural_anticipation as na
from xray_engine import validation as v


@pytest.fixture(scope="module")
def scored(synthetic, params, tmp_path_factory) -> v.Scored:
    tables = io.load_tables(synthetic.path, tmp_path_factory.mktemp("anticipation-cache"))
    return v.score_core(tables, params)


def test_auc_handles_degenerate_classes() -> None:
    assert na._auc([1.0, 2.0], [0, 0]) is None
    assert na._auc([1.0, 2.0], [1, 1]) is None
    assert na._auc([2.0, 1.0], [1, 0]) == pytest.approx(1.0)


def test_anticipation_study_on_synthetic(scored) -> None:
    found = na.anticipation_study(scored)
    assert found["pass"] is None
    assert "natural" in found and "calibration_on_injection" in found
    natural = found["natural"]
    assert natural["n_observations"] > 0
    step = found["calibration_on_injection"].get("step") or {}
    assert step.get("auc_h6") is not None
    assert step["n_observations"] > 0
    lead = (step.get("lead_time") or {}).get("median_months")
    assert lead is not None and lead >= 0


def test_natural_anticipation_wired_in_validation(scored) -> None:
    results = v.run_checks(scored, quick=True)
    assert "natural_anticipation" in results
    item = results["natural_anticipation"]
    assert item["pass"] is not False
    assert item.get("calibration_on_injection")


def test_audit_rolling_origin_on_synthetic(scored) -> None:
    natural = na.natural_portfolio_study(scored, horizons=(6,))
    audit = na.audit_rolling_origin(scored, natural, horizon=6, epsilon=1.0)
    assert "cuts" in audit
