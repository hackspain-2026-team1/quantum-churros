"""Pillars read pre-aggregated as-of facts; what is not observable is None with a gate."""

from __future__ import annotations

import random
import re
from dataclasses import replace
from datetime import date

import pytest
from xray_engine.contracts import (
    GATE_TEXTS,
    PANEL_MONEY_COLUMNS,
    PILLAR_GATES,
    PILLAR_INPUT_KEYS,
    PILLAR_KEYS,
    SIZE_BANDS,
    Anchors,
    Evidence,
)
from xray_engine.pillars import (
    INFORMATIVE_GATES,
    NOTE_TEMPLATES,
    compute_pillars,
    format_es,
    liquidity_anchors,
    pillar_activity,
    pillar_collections,
    pillar_debt,
    pillar_liquidity,
    pillar_note,
    pillar_payments,
)

TOL = 1e-9
N_ROWS = 2_000
PERIOD = re.compile(r"^[0-9]{4}-[0-9]{2}(-[0-9]{2})?(\.\.[0-9]{4}-[0-9]{2}(-[0-9]{2})?)?$")
SOURCE_FILES = {"transactions.csv", "balances.csv", "invoices.csv", "debt_products.csv"}
UNITS = {"EUR", "días", "ratio", "cuota", "facturas", "meses"}


@pytest.fixture()
def row(panel_rows):
    """A healthy, fully observed month; every test bends one fact."""
    return panel_rows.random(
        random.Random(51), entity_kind="group", months_observed=24, size_band="small",
        cash_month_end=900.0, cash_intra_month_min=500.0, headroom=300.0, headroom_at_min=100.0,
        outflow_median_3m=600.0, outflow_median_12m=400.0, swept_subsidiary=False,
        op_in_sum_6m_w=3_300.0, outflow_sum_6m_w=3_000.0, months_in_6m_window=6,
        op_in_lfl_recent_mean=540.0, op_in_lfl_prior_mean=600.0, lfl_prior_months=6,
        no_external_revenue=False, op_in_sum_12m_w=6_000.0, debt_service_sum_12m_w=300.0,
        months_in_12m_window=12, has_debt_products=True, has_invoices=True,
        ap_n=40, ap_neff=12.0, ap_amount=5_000.0, ap_days_beyond_terms=7.5, ap_stamped_share=0.1,
        ap_open_share=0.2, ar_n=25, ar_neff=9.0, ar_amount=4_000.0, ar_days_beyond_terms=45.0,
        ar_stamped_share=0.0, ar_open_share=0.4,
    )


@pytest.fixture()
def banded(params):
    """Params whose size-band tables differ from the absolute one, as after fit-reference."""
    scores = params.liquidity.band_scores
    tables = {
        band: Anchors(((0.0, 0.0), *zip((step * (4 - index) for step in (2.0, 5.0, 10.0, 20.0, 40.0)), scores)))
        for index, band in enumerate(SIZE_BANDS)
    }
    return replace(params, liquidity=replace(params.liquidity, band_anchors=tables, band_anchors_fitted=True))


def test_every_pillar_reports_inputs_and_known_gates(panel_rows, params) -> None:
    rng = random.Random(52)
    gates_seen = set()
    for _ in range(1_500):
        row = panel_rows.random(rng)
        group_row = panel_rows.random(rng, entity_kind="group", swept_subsidiary=False)
        results = compute_pillars(row, params, group_row)
        assert list(results) == list(PILLAR_KEYS)
        for key, result in results.items():
            assert result.key == key and set(result.inputs) == set(PILLAR_INPUT_KEYS[key])
            assert set(result.gates) <= set(PILLAR_GATES), result.gates
            assert result.score is None or 0.0 <= result.score <= 100.0
            assert result.score is not None or result.gates  # never imputed, always explained
            gates_seen |= set(result.gates)
    assert gates_seen >= set(PILLAR_GATES) - {"carried_forward"}


def test_liquidity_buffer_and_size_band_tables(row, params, banded) -> None:
    result = pillar_liquidity(row, banded)
    daily = 600.0 / 30.0
    end, low = (900.0 + 300.0) / daily, (500.0 + 100.0) / daily
    assert result.inputs["buffer_days_month_end"] == pytest.approx(end, abs=TOL)
    assert result.inputs["buffer_days_intra_min"] == pytest.approx(low, abs=TOL)
    assert result.inputs["monthly_outflow"] == 600.0
    table = banded.liquidity.band_anchors["small"]
    assert liquidity_anchors(row, banded) == (table, True)
    assert result.score == pytest.approx(0.6 * table(end) + 0.4 * table(low), abs=TOL)
    assert result.gates == ()
    # the same buffer reads differently by size band: larger entities run leaner cash
    by_band = [pillar_liquidity(replace(row, size_band=band), banded).score for band in SIZE_BANDS]
    assert by_band == sorted(by_band) and by_band[0] < by_band[-1]

    # the switch falls back to the absolute table 0->0, 13->35, 27->60, 62->85, 180->100
    flat = replace(banded, liquidity=replace(banded.liquidity, segmented=False))
    absolute = params.anchors["liquidity"]
    assert liquidity_anchors(row, flat) == (absolute, False)
    fallback = pillar_liquidity(row, flat)
    assert fallback.score == pytest.approx(0.6 * absolute(end) + 0.4 * absolute(low), abs=TOL)
    assert fallback.gates == ("absolute_anchors",)
    unknown = pillar_liquidity(replace(row, size_band=None), banded)
    assert unknown.score == pytest.approx(fallback.score, abs=TOL) and "absolute_anchors" in unknown.gates
    assert absolute(180.0) == 100.0 and absolute(120.0) < 100.0


def test_liquidity_denominator_and_missing_cash(row, params) -> None:
    fallback = pillar_liquidity(replace(row, outflow_median_3m=0.0), params)
    assert fallback.inputs["monthly_outflow"] == 400.0 and fallback.score is not None
    for empty in (dict(outflow_median_3m=0.0, outflow_median_12m=0.0),
                  dict(outflow_median_3m=None, outflow_median_12m=None)):
        undefined = pillar_liquidity(replace(row, **empty), params)
        assert undefined.score is None and undefined.gates == ("buffer_undefined",)  # never 100
    blind = pillar_liquidity(replace(row, cash_month_end=None, cash_intra_month_min=None), params)
    assert blind.score is None and blind.gates == ("no_cash_anchor",)
    overdrawn = pillar_liquidity(replace(row, cash_month_end=-5_000.0, cash_intra_month_min=-6_000.0), params)
    assert overdrawn.score == 0.0
    # headroom counts, at month end and at the minimum
    without = pillar_liquidity(replace(row, headroom=0.0, headroom_at_min=0.0), params)
    assert without.score < pillar_liquidity(row, params).score


def test_swept_subsidiary_inherits_the_group(row, panel_rows, params, banded) -> None:
    company = replace(row, entity_kind="company", swept_subsidiary=True, cash_month_end=1.0,
                      cash_intra_month_min=0.0, size_band="micro")
    group = replace(row, size_band="large")
    inherited = pillar_liquidity(company, banded, group)
    assert inherited.score == pytest.approx(pillar_liquidity(group, banded).score, abs=TOL)
    assert inherited.gates == ("inherited_from_group",)
    assert inherited.inputs["cash_month_end"] == group.cash_month_end
    alone = pillar_liquidity(company, banded)  # no group row: own figures
    assert alone.gates == () and alone.score < inherited.score
    own = pillar_liquidity(replace(company, swept_subsidiary=False), banded, group)
    assert own.gates == () and own.score == pytest.approx(alone.score, abs=TOL)


def test_punctuality_is_as_of_dbt_with_gates(row, params) -> None:
    payments, collections = pillar_payments(row, params), pillar_collections(row, params)
    assert payments.score == pytest.approx(75.0, abs=TOL)  # 7.5 days: halfway 80 -> 70
    assert collections.score == pytest.approx(45.0, abs=TOL)  # 45 days: halfway 50 -> 40
    assert payments.inputs["days_beyond_terms"] == 7.5 and payments.inputs["neff"] == 12.0
    assert pillar_payments(replace(row, ap_days_beyond_terms=-30.0), params).score == 100.0
    assert pillar_payments(replace(row, ap_days_beyond_terms=90.0), params).score == 30.0  # reachable floor

    def gates(**changes: object) -> tuple[str, ...]:
        result = pillar_payments(replace(row, **changes), params)
        assert result.score is None  # never a neutral 50
        return result.gates

    assert gates(ap_n=9) == ("few_invoices",)
    assert gates(ap_neff=4.99) == ("low_effective_n",)
    assert gates(ap_stamped_share=0.5) == ("stamped_regime",)
    assert gates(ap_stamped_share=0.9, ap_n=3, ap_neff=1.0) == (
        "stamped_regime", "few_invoices", "low_effective_n",
    )
    nothing = dict(ap_n=0, ap_neff=None, ap_days_beyond_terms=None, ap_stamped_share=None, ap_open_share=None)
    assert gates(**nothing) == ("no_invoices",)
    assert pillar_payments(replace(row, ap_n=10, ap_neff=5.0, ap_stamped_share=0.49), params).score is not None
    # AP and AR never mix
    assert pillar_collections(replace(row, **nothing), params).score == collections.score
    assert pillar_payments(replace(row, ar_n=0, ar_neff=None), params).score == payments.score


def test_activity_is_the_mean_of_coverage_and_momentum(row, params) -> None:
    coverage = params.anchors["activity_coverage"](1.1)
    momentum = params.anchors["activity_momentum"](0.9)
    assert (coverage, momentum) == (pytest.approx(80.0), pytest.approx(57.5))
    both = pillar_activity(row, params)
    assert both.score == pytest.approx((80.0 + 57.5) / 2, abs=TOL) and both.gates == ()
    assert both.inputs["coverage"] == pytest.approx(1.1) and both.inputs["momentum"] == pytest.approx(0.9)

    young = pillar_activity(replace(row, months_observed=6), params)
    assert young.score == pytest.approx(80.0, abs=TOL) and young.gates == ("short_history", "coverage_only")
    for change in (dict(lfl_prior_months=3), dict(op_in_lfl_prior_mean=0.0), dict(op_in_lfl_prior_mean=None),
                   dict(op_in_lfl_recent_mean=None)):
        result = pillar_activity(replace(row, **change), params)
        assert result.score == pytest.approx(80.0, abs=TOL) and result.gates == ("no_base", "coverage_only")
    for change in (dict(outflow_sum_6m_w=0.0), dict(months_in_6m_window=2)):
        result = pillar_activity(replace(row, **change), params)
        assert result.score == pytest.approx(57.5, abs=TOL)
        assert result.gates == ("coverage_undefined", "momentum_only")
    neither = pillar_activity(replace(row, outflow_sum_6m_w=0.0, months_observed=3), params)
    assert neither.score is None and neither.gates == ("coverage_undefined", "short_history")
    captive = pillar_activity(replace(row, no_external_revenue=True, op_in_sum_6m_w=0.0), params)
    assert captive.score is None and captive.gates == ("no_external_revenue",)  # never a 0 score


def test_debt_is_burden_and_absence_is_not_imputed(row, params) -> None:
    result = pillar_debt(row, params)
    assert result.inputs["burden"] == pytest.approx(0.05)
    assert result.score == pytest.approx(62.5, abs=TOL)  # halfway 0.02 -> 75 and 0.08 -> 50
    assert pillar_debt(replace(row, debt_service_sum_12m_w=0.0), params).score == 100.0
    assert pillar_debt(replace(row, debt_service_sum_12m_w=6_000.0), params).score == 0.0

    none = pillar_debt(replace(row, has_debt_products=False, debt_service_sum_12m_w=0.0), params)
    assert none.score is None and none.gates == ("no_debt",)  # not a neutral 75
    unlisted = pillar_debt(replace(row, has_debt_products=False), params)
    assert unlisted.score == pytest.approx(62.5, abs=TOL)  # service without a product still counts
    young = pillar_debt(replace(row, months_in_12m_window=5), params)
    assert young.score is None and young.gates == ("short_history",)
    assert pillar_debt(replace(row, months_in_12m_window=6), params).score is not None
    dry = pillar_debt(replace(row, op_in_sum_12m_w=0.0), params)
    assert dry.score is None and dry.gates == ("burden_undefined",)


def test_both_liquidity_gates_are_reported(row, params) -> None:
    nothing = replace(row, cash_month_end=None, cash_intra_month_min=None,
                      outflow_median_3m=0.0, outflow_median_12m=None)
    result = pillar_liquidity(nothing, params)
    assert result.score is None and result.gates == ("no_cash_anchor", "buffer_undefined")
    assert result.inputs["headroom"] == row.headroom and result.inputs["monthly_outflow"] is None
    half = pillar_liquidity(replace(row, cash_intra_month_min=None), params)  # both figures or none
    assert half.score is None and half.gates == ("no_cash_anchor",)


# (pillar, column, better value) with step = a share of the monthly outflow of the row
IMPROVEMENTS = [
    ("liquidity", "cash_month_end", lambda value, step: value + step),
    ("liquidity", "cash_intra_month_min", lambda value, step: value + step),
    ("liquidity", "headroom", lambda value, step: value + step),
    ("liquidity", "headroom_at_min", lambda value, step: value + step),
    ("liquidity", "outflow_median_3m", lambda value, step: value * 0.7),
    ("liquidity", "outflow_median_12m", lambda value, step: value * 0.7),
    ("payments", "ap_days_beyond_terms", lambda value, step: value - 7.0),
    ("collections", "ar_days_beyond_terms", lambda value, step: value - 7.0),
    ("activity", "op_in_sum_6m_w", lambda value, step: value * 1.2),
    ("activity", "outflow_sum_6m_w", lambda value, step: value * 0.8),
    ("activity", "op_in_lfl_recent_mean", lambda value, step: value * 1.2),
    ("debt", "debt_service_sum_12m_w", lambda value, step: value * 0.8),
    ("debt", "op_in_sum_12m_w", lambda value, step: value * 1.2),
]


def test_improving_one_input_never_lowers_its_pillar(panel_rows, params) -> None:
    rng = random.Random(53)
    functions = {"liquidity": pillar_liquidity, "payments": pillar_payments,
                 "collections": pillar_collections, "activity": pillar_activity, "debt": pillar_debt}
    raised = dict.fromkeys(PILLAR_KEYS, 0)
    for _ in range(N_ROWS):
        row = panel_rows.random(rng)
        step = 0.3 * row.op_outflow_1m
        before = {key: function(row, params) for key, function in functions.items()}
        for key, column, better in IMPROVEMENTS:
            value = getattr(row, column)
            if value is None:
                continue
            after = functions[key](replace(row, **{column: better(value, step)}), params)
            assert after.gates == before[key].gates, (key, column)  # availability does not move
            if after.score is None:
                continue
            assert after.score >= before[key].score - TOL, (key, column)
            raised[key] += after.score > before[key].score + TOL
    assert all(count > 100 for count in raised.values()), raised  # the property is not vacuous

    # through the inheritance too: a richer group never lowers the liquidity of a swept subsidiary
    for _ in range(N_ROWS // 10):
        company = panel_rows.random(rng, entity_kind="company", swept_subsidiary=True)
        group = panel_rows.random(rng, entity_kind="group", cash_month_end=rng.uniform(-1e5, 1e6),
                                  cash_intra_month_min=-2e5, outflow_median_3m=3e5)
        richer = replace(group, cash_month_end=group.cash_month_end + 2e5, cash_intra_month_min=0.0)
        before, after = pillar_liquidity(company, params, group), pillar_liquidity(company, params, richer)
        assert after.gates == before.gates and after.gates[0] == "inherited_from_group"
        assert after.score >= before.score - TOL


def test_pillars_are_deterministic(panel_rows, params) -> None:
    one, other = random.Random(54), random.Random(54)
    for _ in range(300):
        row, again = panel_rows.random(one), panel_rows.random(other)
        group, group_again = panel_rows.random(one, entity_kind="group"), panel_rows.random(other, entity_kind="group")
        assert compute_pillars(row, params, group) == compute_pillars(again, params, group_again)


def test_evidence_rows_are_aggregates(panel_rows, params) -> None:
    rng = random.Random(55)
    units_seen, scored = set(), dict.fromkeys(PILLAR_KEYS, 0)
    for _ in range(N_ROWS // 4):
        row = panel_rows.random(rng)
        group_row = panel_rows.random(rng, entity_kind="group", swept_subsidiary=False)
        results = compute_pillars(row, params, group_row)
        scaled = compute_pillars(panel_rows.scale(row, 8.0), params, panel_rows.scale(group_row, 8.0))
        money = {getattr(source, name) for source in (row, group_row) for name in PANEL_MONEY_COLUMNS}
        for key, result in results.items():
            assert isinstance(result.evidence, tuple)
            if result.score is not None:
                scored[key] += 1
                assert len(result.evidence) >= 3, key
            assert len(scaled[key].evidence) == len(result.evidence)
            for fact, bigger in zip(result.evidence, scaled[key].evidence):
                assert isinstance(fact, Evidence) and fact.value is not None
                assert 1 <= len(fact.label) <= 120 and fact.unit in UNITS
                assert PERIOD.match(fact.period), fact.period
                assert fact.source_file in SOURCE_FILES
                assert fact.n_rows is None or (isinstance(fact.n_rows, int) and fact.n_rows >= 0)
                assert not isinstance(fact.value, str)  # numbers only: never a description
                same = (bigger.label, bigger.unit, bigger.period, bigger.source_file, bigger.n_rows)
                assert same == (fact.label, fact.unit, fact.period, fact.source_file, fact.n_rows)
                if fact.unit == "EUR":  # a column of the row, never a derived amount
                    assert fact.value in money and bigger.value == fact.value * 8.0
                else:
                    assert bigger.value == pytest.approx(fact.value, abs=TOL)
                units_seen.add(fact.unit)
    assert units_seen == UNITS and all(scored.values())


def test_evidence_periods_follow_the_windows(row, params) -> None:
    row = replace(row, month=date(2026, 3, 1))
    periods = {
        key: {fact.label: fact.period for fact in result.evidence}
        for key, result in compute_pillars(row, params).items()
    }
    assert periods["liquidity"]["Caja a fin de mes"] == "2026-03"
    assert periods["liquidity"]["Mediana mensual de pagos operativos y deuda"] == "2026-01..2026-03"
    fallback = pillar_liquidity(replace(row, outflow_median_3m=0.0), params)
    assert {fact.period for fact in fallback.evidence} == {"2026-03", "2025-04..2026-03"}
    young = pillar_liquidity(replace(row, months_observed=2), params)  # only observed months
    assert "2026-02..2026-03" in {fact.period for fact in young.evidence}
    # invoices due in (t - 90 days, t], t = month end
    assert set(periods["payments"].values()) == {"2026-01-01..2026-03-31"}
    assert set(periods["collections"].values()) == {"2026-01-01..2026-03-31"}
    assert periods["activity"]["Cobros operativos sobre pagos operativos y deuda"] == "2025-10..2026-03"
    assert periods["activity"]["Media mensual de cobros recientes, mismas cuentas"] == "2026-01..2026-03"
    assert periods["activity"]["Media mensual de cobros de los meses previos, mismas cuentas"] == "2025-07..2025-12"
    assert set(periods["debt"].values()) == {"2025-04..2026-03"}
    days = pillar_payments(row, params).evidence[0]
    assert (days.value, days.unit, days.n_rows, days.source_file) == (7.5, "días", 40, "invoices.csv")


def test_inherited_evidence_names_the_group(row, params) -> None:
    company = replace(row, entity_kind="company", swept_subsidiary=True)
    inherited = pillar_liquidity(company, params, replace(row, cash_month_end=7_777.0))
    assert all("del grupo" in fact.label for fact in inherited.evidence)
    assert inherited.evidence[0].value == 7_777.0
    assert not any("del grupo" in fact.label for fact in pillar_liquidity(company, params).evidence)


def test_notes_are_one_spanish_sentence(row, panel_rows, params) -> None:
    results = compute_pillars(row, params)
    assert pillar_note(results["liquidity"], params) == (
        "Colchón de 60 días de salidas entre caja y líneas disponibles (30 días en el mínimo del mes)."
    )
    assert pillar_note(results["payments"], params) == (
        "Paga a proveedores 8 días después del vencimiento, ponderado por importe."
    )
    assert pillar_note(results["collections"], params) == (
        "Cobra de clientes 45 días después del vencimiento, ponderado por importe."
    )
    assert pillar_note(results["activity"], params) == (
        "Los cobros operativos cubren 1,10 veces los pagos de los últimos 6 meses "
        "y los cobros recientes son 0,90 veces los de los meses previos."
    )
    assert pillar_note(results["debt"], params) == (
        "El servicio de la deuda consume el 5,0 % de los cobros de 12 meses."
    )
    early = pillar_payments(replace(row, ap_days_beyond_terms=-1.0), params)
    assert pillar_note(early, params) == "Paga a proveedores 1 día antes del vencimiento, ponderado por importe."
    overdrawn = pillar_liquidity(replace(row, cash_month_end=-5_000.0, cash_intra_month_min=-6_000.0), params)
    assert pillar_note(overdrawn, params) == NOTE_TEMPLATES["liquidity_negative"]
    idle = pillar_liquidity(replace(row, outflow_median_3m=1.0, cash_intra_month_min=-0.04), params)
    assert pillar_note(idle, params) == (
        "Colchón de más de 365 días de salidas entre caja y líneas disponibles "
        "(más de 365 días en el mínimo del mes)."
    )
    tight = pillar_liquidity(replace(row, cash_intra_month_min=-200.0), params)  # (-200 + 100) / 20
    assert "(-5 días en el mínimo del mes)" in pillar_note(tight, params)
    company = replace(row, entity_kind="company", swept_subsidiary=True)
    inherited = pillar_note(pillar_liquidity(company, params, row), params)
    assert inherited.startswith("Liquidez del grupo: colchón de 60 días")
    young = pillar_activity(replace(row, months_observed=6), params)
    assert pillar_note(young, params) == (
        "Los cobros operativos cubren 1,10 veces los pagos de los últimos 6 meses."
    )
    # without a score the sentence is the text of the gate that blocks it
    assert pillar_note(pillar_payments(replace(row, ap_n=9), params), params) == GATE_TEXTS["few_invoices"]
    blocked = pillar_activity(replace(row, outflow_sum_6m_w=0.0, months_observed=3), params)
    assert pillar_note(blocked, params) == GATE_TEXTS["coverage_undefined"]
    # a carried month keeps the sentence of the month it copies
    carried = replace(results["debt"], gates=(*results["debt"].gates, "carried_forward"))
    assert pillar_note(carried, params) == pillar_note(results["debt"], params)
    assert "carried_forward" in INFORMATIVE_GATES and set(INFORMATIVE_GATES) <= set(PILLAR_GATES)

    rng = random.Random(56)
    for _ in range(500):
        other = panel_rows.random(rng)
        group_row = panel_rows.random(rng, entity_kind="group")
        notes = {key: pillar_note(result, params) for key, result in compute_pillars(other, params, group_row).items()}
        scaled = compute_pillars(panel_rows.scale(other, 1024.0), params, panel_rows.scale(group_row, 1024.0))
        for key, note in notes.items():
            assert 1 <= len(note) <= 400 and note.endswith(".") and "None" not in note and "nan" not in note
            assert pillar_note(scaled[key], params) == note  # days, ratios and shares only


def test_numbers_use_the_decimal_comma() -> None:
    assert format_es(1.1, 2) == "1,10" and format_es(1234.56, 1) == "1234,6" and format_es(61.4) == "61"
    assert format_es(-0.04, 1) == "0,0" and format_es(-2.5, 1) == "-2,5"
