"""Frozen parameters: hand-set values of the spec, hash, validation."""

from __future__ import annotations

import dataclasses
import json
import re

import pytest
from xray_engine.contracts import ANCHOR_KEYS, DASH_LABELS, FLOW_CLASSES, PILLAR_KEYS, SIZE_BANDS
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
        (0.0, 0.0), (13.0, 35.0), (27.0, 60.0), (62.0, 85.0), (180.0, 100.0),
    )
    assert params.anchors["payments"].points == params.anchors["collections"].points == (
        (-10.0, 100.0), (0.0, 80.0), (15.0, 70.0), (30.0, 50.0), (60.0, 40.0), (90.0, 30.0),
    )
    assert params.anchors["activity_coverage"].points == (
        (0.70, 0.0), (0.85, 25.0), (0.95, 45.0), (1.00, 60.0), (1.10, 80.0), (1.25, 100.0),
    )
    assert params.anchors["activity_momentum"].points == (
        (0.4, 0.0), (0.6, 20.0), (0.8, 45.0), (1.0, 70.0), (1.2, 85.0), (1.5, 100.0),
    )
    assert params.anchors["debt_burden"].points == (
        (0.0, 100.0), (0.02, 75.0), (0.08, 50.0), (0.25, 25.0), (0.60, 0.0),
    )
    liquidity = params.liquidity
    assert (liquidity.month_end_weight, liquidity.intra_min_weight) == (0.6, 0.4)
    assert (liquidity.outflow_window_months, liquidity.outflow_fallback_months) == (3, 12)
    assert liquidity.segmented is True
    assert liquidity.band_quantiles == (0.10, 0.25, 0.50, 0.75, 0.90)
    assert liquidity.band_scores == (15.0, 35.0, 60.0, 85.0, 100.0)
    assert params.size_bands.upper_bounds_eur == (2e6, 10e6, 50e6)
    assert params.size_bands.window_months == 12
    invoices = params.invoices
    assert (invoices.window_days, invoices.clip_days) == (90, (-30.0, 90.0))
    assert (invoices.min_invoices, invoices.min_effective_n, invoices.stamped_share_max) == (10, 5.0, 0.5)
    activity = params.activity
    assert (activity.coverage_window_months, activity.recent_months, activity.prior_months) == (6, 3, 6)
    assert (activity.min_prior_months, activity.min_months_observed) == (4, 7)
    assert (params.debt.window_months, params.debt.min_months) == (12, 6)
    assert params.robust.monthly_winsor_multiple == 3.0
    assert (params.penalty.lam, params.penalty.tau) == (0.5, 45.0)
    caps = params.caps
    assert (caps.negative_liquidity_ceiling, caps.weak_payments_ceiling) == (40.0, 50.0)
    assert (caps.negative_liquidity_min_months, caps.negative_liquidity_window_months) == (3, 6)
    assert caps.weak_payments_threshold == 25.0
    assert dict(params.bands) == {"critical": 0.0, "watch": 40.0, "stable": 60.0, "solid": 80.0}
    feed = params.live_feed
    assert (feed.threshold, feed.recent_months, feed.base_from_months, feed.base_to_months) == (0.5, 3, 12, 4)
    assert feed.group_zero_row_month_is_stale is True
    assert params.abstention.min_months_observed == 4
    assert params.abstention.bank_pillars == ("liquidity", "activity")
    trajectory = params.trajectory
    assert (trajectory.horizon_months, trajectory.min_delta_points, trajectory.min_sigma_multiple) == (3, 6.0, 1.5)
    assert (trajectory.sigma_floor, trajectory.structural_consecutive_months) == (2.0, 2)
    assert (trajectory.min_scored_months, trajectory.bump_revert_months) == (6, 2)
    assert (trajectory.perimeter_shift_share, trajectory.perimeter_shift_window_months) == (0.2, 3)
    assert params.alerts.critical_score == 35.0
    profile = params.profile
    assert (profile.concentration_top1_share, profile.concentration_min_months,
            profile.concentration_window_months) == (0.2, 6, 12)
    mirror = params.mirror
    assert (mirror.min_amount_eur, mirror.max_day_gap, mirror.weekend_bridge_day_gap) == (100.0, 1, 3)
    assert mirror.weekend_bridge_weekdays == (4, 5) and mirror.reversal_max_day_gap == 1
    assert params.flows.sentinel_abs_balance == 9e8
    assert params.fx.rates["EUR"] == 1.0 and params.fx.rates["USD"] == 0.92
    flows = params.flows
    assert "interest_charge" in flows.debt_service_categories
    assert not set(flows.debt_service_categories) & set(flows.op_outflow_categories)
    assert flows.internal_categories == ("transfer",) and flows.dash_category == "-"


def test_amended_away_parameters_are_gone(params) -> None:
    names = {item.name for item in dataclasses.fields(params)}
    assert not names & {"ewma_alpha", "seasonality", "psi", "winsor"}
    assert not {"debt_dscr", "debt_utilisation", "activity"} & set(params.anchors)
    assert not hasattr(params.confidence, "abstain_below")
    assert not hasattr(params.debt, "neutral_score")
    assert not hasattr(params.caps, "lines_drawn_ceiling")


def test_placeholders_are_flagged_as_not_fitted(params) -> None:
    assert params.fitted is False and params.fitted_on is None
    assert dict(params.reference.medians) == {key: 60.0 for key in PILLAR_KEYS}
    assert params.reference.fitted is False
    liquidity = params.liquidity
    assert liquidity.band_anchors_fitted is False and set(liquidity.band_anchors) == set(SIZE_BANDS)
    absolute = params.anchors["liquidity"]
    for table in liquidity.band_anchors.values():
        assert table.points[0] == (0.0, 0.0)
        assert tuple(y for _, y in table.points[1:]) == liquidity.band_scores
        # until fit-reference runs, a band table is the absolute curve
        for days in (-5.0, 0.0, 3.0, 5.6, 10.0, 20.0, 45.0, 100.0, 180.0, 400.0):
            assert table(days) == pytest.approx(absolute(days), abs=1e-9)


def test_dash_rules_are_the_high_precision_table(params) -> None:
    rules = {rule.id: rule for rule in params.dash_rules}
    assert {rule.flow_class for rule in rules.values()} == {
        "adjustment", "internal", "debt_service", "op_out", "op_in",
    }
    assert all(rule.flow_class in FLOW_CLASSES and rule.label in DASH_LABELS for rule in rules.values())
    scored = [rule for rule in rules.values() if rule.flow_class != "adjustment"]
    assert len(scored) == 11 and all(rule.precision >= 0.8 for rule in scored)
    assert rules["retention_adjustment"].precision is None
    assert params.dash_rules[0].id == "retention_adjustment"  # whales leave before anything else

    def fires(rule_id: str, text: str) -> bool:
        rule = rules[rule_id]
        vetoed = rule.exclude and re.search(rule.exclude, text, re.IGNORECASE)
        return bool(re.search(rule.pattern, text, re.IGNORECASE)) and not vetoed

    assert fires("loan_instalment", "LIQUID. CUOTA PTMO 0355 [NUM]")
    assert fires("amortisation_charge", "CARGO POR AMORTIZACION ANTICIPADA DE [COMPANY]")
    assert fires("amortisation", "AMORTIZ.PTMO [NUM]") and not fires("amortisation", "COMISION AMORTIZACION")
    assert fires("retention_adjustment", "AP.RET.DST: [ACCOUNT] MV#")
    assert fires("retention_adjustment", "MANUAL QUITAR RETENCION")
    assert fires("social_security", "TGSS COTIZACION") and fires("social_security", "SEG.SOCIAL [NUM]")
    assert fires("fee", "MONTHLY FEE") and not fires("fee", "COFFEE SHOP")
    assert rules["sepa_overboeking"].sign == "positive" and rules["loan_instalment"].sign == "negative"
    # measured below the bar: none of these may appear in a pattern
    patterns = " ".join(rule.pattern for rule in params.dash_rules)
    for banned in ("CUOTA NUMERO", "NOMINA", "N[OÓ]MINA", "TARJETA", "VISA", "INTERES", "DISPOSICI",
                   "RECIBO", "PRES", "LIQUIDACION PERIODICA", "TRASPASO"):
        assert banned not in patterns, banned


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
        params_from_dict({**data, "anchors": {**data["anchors"], "debt_burden": [[1, 0], [1, 50]]}})
    with pytest.raises(ParamsError, match="bad regex"):
        rules = [dict(data["dash_rules"][0], pattern="(")] + data["dash_rules"][1:]
        params_from_dict({**data, "dash_rules": rules})
    with pytest.raises(ParamsError, match="flow_class"):
        rules = [dict(data["dash_rules"][0], flow_class="salary")] + data["dash_rules"][1:]
        params_from_dict({**data, "dash_rules": rules})
    with pytest.raises(ParamsError, match="bands"):
        params_from_dict({**data, "bands": {**data["bands"], "watch": 70.0}})
    with pytest.raises(ParamsError, match="band_anchors"):
        tables = {key: value for key, value in data["liquidity"]["band_anchors"].items() if key != "large"}
        params_from_dict({**data, "liquidity": {**data["liquidity"], "band_anchors": tables}})
    with pytest.raises(ParamsError, match="one point per band score"):
        tables = {**data["liquidity"]["band_anchors"], "micro": [[0, 0], [10, 50], [20, 100]]}
        params_from_dict({**data, "liquidity": {**data["liquidity"], "band_anchors": tables}})
    flipped = dataclasses.replace(params, liquidity=dataclasses.replace(params.liquidity, segmented=False))
    assert params_from_dict(params_to_dict(flipped)).liquidity.segmented is False


def test_environment_override(monkeypatch, tmp_path) -> None:
    assert default_params_path() == DEFAULT_PARAMS_PATH
    monkeypatch.setenv(PARAMS_ENV, str(tmp_path / "other.json"))
    assert default_params_path() == tmp_path / "other.json"
    with pytest.raises(ParamsError, match="not found"):
        load_params()
