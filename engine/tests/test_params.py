"""Frozen parameters: hand-set values of the spec, hash, validation."""

from __future__ import annotations

import dataclasses
import json
import re

import pytest
from xray_engine.contracts import ANCHOR_KEYS, DASH_LABELS, PILLAR_KEYS
from xray_engine.params import (
    DEFAULT_PARAMS_PATH,
    PARAMS_ENV,
    ParamsError,
    canonical_dump,
    default_params_path,
    load_params,
    params_from_dict,
    params_hash,
    params_to_dict,
    write_params,
)


def test_reference_file_is_valid_and_stamped(params) -> None:
    assert DEFAULT_PARAMS_PATH.name == "reference_v1.json"
    assert params.version == "reference_v1"
    assert params.sha256 == params_hash(params) and len(params.sha256) == 64


def test_hand_set_values_follow_the_spec(params) -> None:
    assert dict(params.weights) == {
        "liquidity": 0.30, "payments": 0.20, "collections": 0.15, "activity": 0.20, "debt": 0.15,
    }
    assert set(params.anchors) == set(ANCHOR_KEYS)
    assert params.anchors["liquidity"].points == (
        (0.0, 0.0), (13.0, 35.0), (27.0, 60.0), (62.0, 85.0), (120.0, 100.0),
    )
    assert params.anchors["payments"].points == params.anchors["collections"].points == (
        (-10.0, 100.0), (0.0, 80.0), (15.0, 70.0), (30.0, 50.0), (60.0, 40.0), (90.0, 30.0),
        (120.0, 20.0),
    )
    assert params.anchors["activity"].points[0] == (0.4, 0.0)
    assert params.anchors["activity"].points[-1] == (1.5, 100.0)
    assert params.anchors["debt_dscr"].points == (
        (0.8, 10.0), (1.0, 35.0), (1.25, 60.0), (2.0, 90.0), (3.0, 100.0),
    )
    assert params.anchors["debt_utilisation"].points == (
        (0.0, 100.0), (0.5, 75.0), (0.8, 50.0), (0.95, 25.0), (1.0, 10.0),
    )
    assert (params.liquidity.month_end_weight, params.liquidity.intra_min_weight) == (0.6, 0.4)
    assert (params.penalty.lam, params.penalty.tau) == (0.5, 45.0)
    assert params.ewma_alpha == 0.5
    caps = params.caps
    assert (caps.negative_liquidity_ceiling, caps.lines_drawn_ceiling, caps.weak_pillar_ceiling) == (
        40.0, 60.0, 50.0,
    )
    assert (caps.negative_liquidity_min_months, caps.negative_liquidity_window_months) == (3, 6)
    assert caps.lines_drawn_threshold == 0.98 and caps.weak_pillar_threshold == 25.0
    assert caps.weak_pillars == ("liquidity", "payments")
    assert params.live_feed.threshold == 0.8
    assert params.confidence.abstain_below == 0.5
    assert params.debt.neutral_score == 75.0
    assert params.invoices.min_settlements == 10 and params.invoices.pooled_cohorts == 3
    assert params.invoices.settled_clip_days == (-30.0, 120.0)
    assert (params.activity.min_base_months, params.activity.min_months_observed) == (4, 7)
    trajectory = params.trajectory
    assert (trajectory.min_delta_points, trajectory.min_sigma_multiple, trajectory.sigma_floor) == (
        6.0, 1.5, 2.0,
    )
    assert (trajectory.min_months_observed, trajectory.perimeter_quiet_months) == (6, 2)
    assert params.alerts.critical_score == 35.0
    assert params.mirror.day_offsets == (0, 1, -1, 2, -2)
    assert params.flows.sentinel_abs_balance == 9e8
    assert params.fx.rates["EUR"] == 1.0 and params.fx.rates["USD"] == 0.92
    assert "interest_charge" in params.flows.op_outflow_categories
    assert "interest_charge" in params.flows.debt_service_categories
    assert "debt_repayment" not in params.flows.op_outflow_categories


def test_placeholders_are_flagged_as_not_fitted(params) -> None:
    assert params.fitted is False and params.fitted_on is None
    assert dict(params.reference.medians) == {key: 60.0 for key in PILLAR_KEYS}
    assert params.reference.fitted is False
    assert params.seasonality.fitted is False and params.seasonality.month_factors == (1.0,) * 12
    assert params.psi.fitted is False
    assert all(rule.precision is None for rule in params.dash_rules)


def test_dash_rules_cover_every_label(params) -> None:
    assert {rule.label for rule in params.dash_rules} == set(DASH_LABELS)
    by_label = {rule.label: rule for rule in params.dash_rules}
    installment = by_label["debt_installment"]
    assert installment.sign == "negative"
    assert re.search(installment.pattern, "LIQU.PTMO. 0355 [NUM].051.1", re.IGNORECASE)
    assert re.search(installment.pattern, "CARGO POR AMORTIZACION ANTICIPADA DE [COMPANY]", re.IGNORECASE)
    assert re.search(installment.exclude, "CUOTA TARJETA DEBITO", re.IGNORECASE)
    drawdown = by_label["debt_drawdown"]
    assert drawdown.sign == "positive"
    assert re.search(drawdown.pattern, "[ACCOUNT] ABONO POR DISPOSICION DE [COMPANY]/CREDITO", re.IGNORECASE)


def test_hash_ignores_formatting_but_not_content(tmp_path, params) -> None:
    data = json.loads(DEFAULT_PARAMS_PATH.read_text(encoding="utf-8"))
    compact = tmp_path / "compact.json"
    compact.write_text(json.dumps(data), encoding="utf-8")
    assert load_params(compact) == params

    data["penalty"]["lam"] = 0.4
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ParamsError, match="sha256"):
        load_params(tampered)
    edited = load_params(tampered, verify=False)
    assert params_hash(edited) != params.sha256

    stamped = write_params(edited, tmp_path / "stamped.json")
    assert load_params(tmp_path / "stamped.json") == stamped
    assert stamped.sha256 == params_hash(edited)
    assert canonical_dump(stamped) == canonical_dump(edited)


def test_round_trip_and_strict_parsing(params) -> None:
    data = params_to_dict(params)
    assert params_from_dict(data) == params
    with pytest.raises(ParamsError, match="unknown keys"):
        params_from_dict({**data, "surprise": 1})
    broken = {key: value for key, value in data.items() if key != "caps"}
    with pytest.raises(ParamsError, match="missing keys"):
        params_from_dict(broken)
    with pytest.raises(ParamsError, match="sum to 1"):
        params_from_dict({**data, "weights": {**data["weights"], "debt": 0.5}})
    with pytest.raises(ParamsError, match="strictly increasing"):
        params_from_dict({**data, "anchors": {**data["anchors"], "activity": [[1, 0], [1, 50]]}})
    with pytest.raises(ParamsError, match="bad regex"):
        rules = [dict(data["dash_rules"][0], pattern="(")] + data["dash_rules"][1:]
        params_from_dict({**data, "dash_rules": rules})
    assert dataclasses.replace(params, ewma_alpha=1.0).ewma_alpha == 1.0


def test_environment_override(monkeypatch, tmp_path) -> None:
    assert default_params_path() == DEFAULT_PARAMS_PATH
    monkeypatch.setenv(PARAMS_ENV, str(tmp_path / "other.json"))
    assert default_params_path() == tmp_path / "other.json"
    with pytest.raises(ParamsError, match="not found"):
        load_params()
