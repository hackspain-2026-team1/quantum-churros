"""Mechanics of every validation check, on the synthetic dataset."""

from __future__ import annotations

import json
import random
from dataclasses import replace
from datetime import date

import polars as pl
import pytest
from bundle_contract import load_schema, validate
from xray_engine import io, validation as v
from xray_engine.scoring import score_entity


@pytest.fixture(scope="module")
def scored(synthetic, params, tmp_path_factory) -> v.Scored:
    tables = io.load_tables(synthetic.path, tmp_path_factory.mktemp("validation-cache"))
    return v.score_core(tables, params)


# ---- comparisons and statistics ------------------------------------------------


def test_compare_scores_sees_numbers_labels_and_missing_rows(scored) -> None:
    frame = scored.frame
    assert v.compare_scores(frame, frame)["pass"]
    moved = frame.with_columns(pl.when(pl.int_range(pl.len()) == 0).then(pl.col("score") + 1e-6).otherwise(pl.col("score")).alias("score"))
    found = v.compare_scores(moved, frame)
    assert not found["pass"] and found["rows_beyond_tol"] == 1 and "score" in found["columns_differing"]
    assert found["max_abs_diff"] == pytest.approx(1e-6, rel=1e-3)
    assert v.compare_scores(moved, frame, tol=1e-5)["pass"]
    relabelled = frame.with_columns(pl.lit("other").alias("band"))
    assert v.compare_scores(relabelled, frame)["categorical_mismatches"] == frame.height
    short = v.compare_scores(frame.head(10), frame)
    assert not short["pass"] and short["missing_left"] == frame.height - 10


def test_compare_scores_flattens_structs_and_lists() -> None:
    left = pl.DataFrame({"entity_kind": ["group"], "entity_id": ["g"], "month": [date(2026, 1, 1)],
                         "parts": [{"a": 1.0, "b": None}], "tags": [["x", "y"]]})
    right = left.with_columns(pl.struct(a=pl.lit(1.5), b=pl.lit(None, dtype=pl.Float64)).alias("parts"))
    assert v.compare_scores(left, left)["pass"]
    found = v.compare_scores(left, right)
    assert list(found["columns_differing"]) == ["parts.a"] and found["max_abs_diff"] == 0.5


def test_spearman_and_eta_squared() -> None:
    assert v.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert v.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert v.spearman([1, 1, 1], [1, 2, 3]) is None
    assert v.eta_squared([1, 1, 5, 5], ["a", "a", "b", "b"]) == pytest.approx(1.0)
    assert v.eta_squared([1, 5, 1, 5], ["a", "a", "b", "b"]) == pytest.approx(0.0)
    rng = random.Random(3)
    values = [rng.gauss(50, 10) for _ in range(300)]
    noise = v.excess_eta_squared(values, [rng.randrange(4) for _ in values], draws=100)
    assert abs(noise["excess"]) < 0.03 and noise["cells"] == 4
    told = v.excess_eta_squared(values, [value > 50 for value in values], draws=100)
    assert told["excess"] > v.NEUTRALITY_FAIL


def test_conditional_rates() -> None:
    always = v.conditional_rates([[True] * 12, [False] * 12], lag=6)
    assert always["p_given_flag"] == 1.0 and always["p_given_clear"] == 0.0 and always["base_rate"] == 0.5
    assert always["pairs"] == 12 and always["flagged"] == 6
    gaps = v.conditional_rates([[True, None, False, None]], lag=2)
    assert gaps["pairs"] == 1 and gaps["p_given_flag"] == 0.0


# ---- tables in memory ------------------------------------------------------------


def test_subset_and_truncate_tables(scored, synthetic) -> None:
    group = synthetic.group_ids[0]
    sub = v.subset_tables(scored.tables, [group])
    members = set(synthetic.companies_by_group[group])
    assert set(sub.companies["company_id"]) == members
    assert set(sub.transactions["company_id"]) <= members and sub.transactions.height > 0
    cut_month = date(2026, 2, 1)
    cut = v.truncate_tables(scored.tables, cut_month, scored.params)
    assert cut.window.last_month == cut_month and cut.window.as_of == date(2026, 2, 28)
    assert cut.transactions["date"].max() <= date(2026, 2, 28)
    assert cut.balances["date"].max() <= date(2026, 2, 28)
    assert cut.balances.select("product_id", "date").is_duplicated().sum() == 0
    paid_later = cut.invoices.filter((pl.col("status") == "paid") & (pl.col("payment_date") > date(2026, 2, 28)))
    assert paid_later.is_empty()
    # the rolled anchor is the booked month-end balance of the oracle
    product = next(key[0] for key in synthetic.month_end_balance_cents if key[1] == cut_month)
    anchor = cut.balances.filter(pl.col("product_id") == product).sort("date")["balance_cents"][-1]
    if abs(anchor) / 100 < scored.params.flows.sentinel_abs_balance:
        assert anchor == synthetic.month_end_balance_cents[(product, cut_month)]


def test_roll_balances_names_an_anchor_rolled_over_the_sentinel(scored, params) -> None:
    cut = date(2026, 2, 28)
    balances, crossers = v.roll_balances(scored.tables, cut, params)
    assert crossers == [] and balances["date"].max() <= cut
    sentinel_cents = int(params.flows.sentinel_abs_balance * 100)
    reading = (
        scored.tables.balances.filter((pl.col("date") > cut) & (pl.col("balance_cents").abs() < sentinel_cents // 2))
        .sort("product_id", "date").group_by("product_id", maintain_order=True).last().row(0, named=True)
    )
    booked = scored.tables.transactions.filter(pl.col("product_id") == reading["product_id"]).head(1)
    huge = booked.with_columns(
        pl.lit("T-HUGE").alias("transaction_id"), pl.lit(date(2026, 3, 2)).alias("date"),
        pl.lit(date(2026, 3, 1)).alias("month"), pl.lit(-2 * sentinel_cents).cast(pl.Int64).alias("amount_cents"),
    )
    tables = replace(scored.tables, transactions=pl.concat([scored.tables.transactions, huge]))
    rolled, crossers = v.roll_balances(tables, cut, params)
    assert crossers == [reading["product_id"]]
    at_cut = (pl.col("product_id") == reading["product_id"]) & (pl.col("date") == cut)
    assert rolled.filter(at_cut)["balance_cents"][0] == balances.filter(at_cut)["balance_cents"][0] + 2 * sentinel_cents


def test_isolation_truncation_determinism_pass(scored) -> None:
    isolation = v.check_isolation(scored, n_groups=3)
    assert isolation["pass"] and isolation["n_groups"] == 3 and isolation["max_abs_diff"] <= 1e-9
    truncation = v.check_truncation(scored, months=[date(2026, 2, 1)])
    assert truncation["pass"] and list(truncation["cuts"]) == ["2026-02"]
    assert truncation["snapshot_exceptions"]
    determinism = v.check_determinism(scored, group_ids=v.pick_groups(scored, 2))
    assert determinism["pass"] and determinism["second_run_equal"] and determinism["shuffled_equal"]


def test_truncation_reports_a_future_leak(scored) -> None:
    # a "full run" whose past moved must fail and name the column
    leaked = replace(scored, frame=scored.frame.with_columns(pl.col("score") + 0.5))
    found = v.check_truncation(leaked, months=[date(2026, 2, 1)])
    assert found["pass"] is False and found["max_abs_diff"] == pytest.approx(0.5)
    assert "score" in found["cuts"]["2026-02"]["columns_differing"]


def test_pick_groups_is_seeded(scored, synthetic) -> None:
    assert v.pick_groups(scored, 3, seed=1) == v.pick_groups(scored, 3, seed=1)
    assert set(v.pick_groups(scored, 99)) == set(synthetic.group_ids)


# ---- checks on the scored result ---------------------------------------------------


def test_additivity_passes_and_catches_a_broken_identity(scored) -> None:
    assert v.check_additivity(scored)["pass"]
    first = scored.months[0]
    broken = replace(first, parts=replace(first.parts, penalty=first.parts.penalty + 1.0))
    found = v.check_additivity(replace(scored, months=(broken, *scored.months[1:])))
    assert found["pass"] is False and found["max_abs_residual"] == pytest.approx(1.0)


def test_scale_invariance(scored) -> None:
    found = v.check_scale_invariance(scored, factor=1024.0)
    assert found["pass"] and found["n"] == len(scored.months)


def test_paired_ablation_removes_the_invoice_pillars(scored, synthetic) -> None:
    found = v.paired_ablation(scored)
    with_invoices = sum(
        any(item.parts.pillar_scores[key] is not None for key in ("payments", "collections"))
        for item in v._last_live(scored)
    )
    assert found["invoices"]["n"] == with_invoices > 0
    assert found["invoices"]["mean_abs_shift"] >= abs(found["invoices"]["mean_shift"])
    item = next(i for i in v._last_live(scored) if i.parts.pillar_scores["payments"] is not None)
    pillars = v._without(item, ("payments", "collections"))
    assert pillars["payments"].score is None and pillars["liquidity"] is item.pillars["liquidity"]


def test_neutrality_and_penalty_by_branch(scored) -> None:
    found = v.neutrality(scored, draws=20)
    assert set(found["dimensions"]) == set(v.NEUTRALITY_DIMENSIONS)
    assert found["pass"] is None  # too few groups for a verdict
    attributes = v.group_attributes(scored)
    assert all({"erp_tier", "main_bank"} <= set(item) for item in attributes.values())
    penalties = v.penalty_by_branch(scored)
    assert sum(item["n"] for item in penalties["branches"].values()) == penalties["n"] > 0
    assert all(0 <= item["penalised_share"] <= 1 for item in penalties["branches"].values())


def test_rank_stability(scored, params) -> None:
    found = v.rank_stability(scored, draws=12)
    assert found["draws"] <= 12 and -1 <= found["spearman_min"] <= found["spearman_median"] <= 1
    still = v.rank_stability(scored, draws=3, lambdas=(params.penalty.lam,), seed=1)
    assert still["n_groups"] == len(v._last_live(scored))
    moved = v.perturbed_params(params, random.Random(1), 0.3)
    assert sum(moved.weights.values()) == pytest.approx(1.0) and moved.penalty.lam == 0.3
    assert all(abs(moved.weights[key] - params.weights[key]) < 0.15 for key in params.weights)


def test_history_truncation(scored) -> None:
    found = v.history_truncation(scored, lengths=(6, 12))
    assert found["n_groups"] > 0 and set(found["by_length"]) == {"6", "12"}
    assert all(item["median_abs_diff"] >= 0 and item["n"] <= found["n_groups"] for item in found["by_length"].values())


def test_persistence(scored) -> None:
    found = v.persistence(scored)
    assert found["low_score"]["pairs"] > 0 and found["lag_months"] == 6
    for rates in (found["low_score"], found["negative_cash"]):
        assert all(rates[key] is None or 0 <= rates[key] <= 1 for key in ("p_given_flag", "p_given_clear", "base_rate"))


def test_netting_placebo_finds_the_real_pairs_only(scored, synthetic) -> None:
    found = v.netting_placebo(scored)
    assert found["real"]["pairs"] >= len([pair for pair in synthetic.mirror_pairs if not pair.ambiguous]) > 0
    assert found["placebo"]["pairs"] < found["real"]["pairs"] and found["pass"]


# ---- injection -------------------------------------------------------------------


def _rows(scored, group_id):
    return [item.row for item in v._groups(scored)[group_id]]


def _full_history_group(scored) -> str:
    window = scored.tables.window
    return next(
        group_id for group_id, items in v._groups(scored).items()
        if items[0].row.month == window.first_month and items[-1].row.month == window.last_month
        and items[-1].row.op_inflow_1m > 0
    )


def test_inject_keeps_the_past_and_books_the_cash(scored, params) -> None:
    rows = _rows(scored, _full_history_group(scored))
    start = rows[-10].month
    first = len(rows) - 10
    for kind in v.INJECTION_KINDS:
        changed = v.inject(rows, kind, start, params)
        assert changed[:first] == rows[:first] and len(changed) == len(rows)
        assert [row.month for row in changed] == [row.month for row in rows]
    step = v.inject(rows, "step", start, params)
    lost = 0.0
    for before, after in zip(rows[first:], step[first:]):
        assert after.op_inflow_1m == pytest.approx(0.7 * before.op_inflow_1m)
        lost += before.op_inflow_1m - after.op_inflow_1m
        if before.cash_month_end is not None:
            assert after.cash_month_end == pytest.approx(before.cash_month_end - lost)
        assert after.op_in_sum_6m_w <= before.op_in_sum_6m_w + 1e-9
        assert after.op_outflow_1m == before.op_outflow_1m and after.ap_n == before.ap_n
    ramp = v.inject(rows, "ramp", start, params)
    assert ramp[first].op_inflow_1m == pytest.approx(rows[first].op_inflow_1m * 0.95)
    assert ramp[first + 5].op_inflow_1m == pytest.approx(rows[first + 5].op_inflow_1m * 0.70)
    assert ramp[-1].op_inflow_1m == pytest.approx(rows[-1].op_inflow_1m * 0.70)
    spike = v.inject(rows, "spike", start, params)
    assert spike[first].op_outflow_1m > rows[first].op_outflow_1m
    assert sum(row.op_outflow_1m for row in spike) == pytest.approx(sum(row.op_outflow_1m for row in rows))
    if rows[first].cash_month_end is not None:
        assert spike[first].cash_month_end < rows[first].cash_month_end
        assert spike[-1].cash_month_end == pytest.approx(rows[-1].cash_month_end)
    with pytest.raises(ValueError):
        v.inject(rows, "flood", start, params)


def test_a_step_lowers_the_score_and_the_study_counts_it(scored, params) -> None:
    rows = _rows(scored, _full_history_group(scored))
    start = rows[-10].month
    base = score_entity(rows, params)
    hit = score_entity(v.inject(rows, "step", start, params, drop=0.6), params)
    assert [item.parts.score for item in hit[:-10]] == [item.parts.score for item in base[:-10]]
    assert hit[-1].parts.score < base[-1].parts.score
    study = v.injection_study(scored, min_score=0.0)
    assert study["n_injections"] > 0 and set(study["by_kind"]) == set(v.INJECTION_KINDS)
    for item in study["by_kind"].values():
        assert item["n"] == study["n_injections"]
        assert sum(item["verdict_delay_distribution"].values()) == item["n"]
        assert 0 <= item["p_structural"] <= item["p_verdict"] <= 1
        assert sum(band["n"] for band in item["by_size_band"].values()) == item["n"]
        assert all({"median_verdict_delay", "median_alert_delay", "p_alert"} <= set(band) for band in item["by_size_band"].values())
        # windows without a deterioration verdict of their own: same subset for every kind
        assert item["quiet_base"]["n"] == study["untouched"]["quiet_windows"] <= item["n"]
        assert item["quiet_base"]["structural_in_month_0"] <= item["quiet_base"]["n"]
    assert study["untouched"]["group_years"] > 0
    assert v.injection_study(scored, min_score=101.0)["pass"] is None


# ---- document ---------------------------------------------------------------------


def test_run_validation_writes_a_contract_receipt(synthetic, params, tmp_path) -> None:
    out = tmp_path / "artifacts" / "validation.json"
    document = v.run_validation(synthetic.path, params, out, cache_dir=tmp_path / "cache", quick=True)
    assert json.loads(out.read_text(encoding="utf-8")) == document
    assert document["params_hash"] == params.sha256 and document["quick"] is True
    schema = load_schema()
    assert validate(document["receipt"], schema["$defs"]["receipt"], schema) == []
    checks = {item["key"]: item for item in document["receipt"]["checks"]}
    assert list(checks) == list(v.CHECK_KEYS) and document["checks"] == document["receipt"]["checks"]
    for key in v.QUICK_SKIPPED:
        assert checks[key]["status"] == "not_run" and key not in document
    for key in ("isolation", "truncation", "additivity", "scale", "determinism"):
        assert checks[key]["status"] == "pass", checks[key]["summary"]
        assert document[key]["pass"] is True and document[key]["status"] == "ok"
    ran = [key for key in v.CHECK_KEYS if key not in v.QUICK_SKIPPED]
    assert sum(document["status_counts"].values()) == len(ran)
    assert document["status_counts"]["fail"] == sum(document[key]["status"] == "fail" for key in ran)
    zero = {item["name"] for item in document["receipt"]["signals"] if item["weight"] == 0}
    assert {"industry", "customer_concentration", "seasonality"} <= zero
    assert sum(item["weight"] for item in document["receipt"]["signals"]) == pytest.approx(1.0)
    abstained = {item["entity_id"] for item in document["receipt"]["abstentions"]}
    assert synthetic.short_history_company_id in abstained or synthetic.stale_company_id in abstained


def test_receipt_check_maps_status_and_bars() -> None:
    assert v.receipt_check("isolation", None)["status"] == "not_run"
    failing = v.receipt_check("injection", {
        "pass": False, "summary": "x" * 900, "metrics": [v._metric("a", float("nan"), "u" * 40)],
        "bars": [{"label": "mes +0", "value": 3}],
    })
    assert failing["status"] == "fail" and len(failing["summary"]) == 400
    assert failing["metrics"][0] == {"label": "a", "value": None, "unit": "u" * 24}
    assert failing["bars"] == [{"label": "mes +0", "value": 3.0}]
    assert v.receipt_check("ablation", {"pass": None, "summary": "s"})["status"] == "info"
    # ok | warn | fail | info on the raw result; the contract enum has no "warn"
    assert v.check_status({"pass": True}) == "ok" and v.check_status({"pass": None}) == "info"
    assert v.check_status({"pass": False, "warning": True}) == "fail"
    warned = {"pass": None, "warning": True, "summary": "Aviso"}
    assert v.check_status(warned) == "warn" and v.receipt_check("neutrality", warned)["status"] == "info"


def test_a_broken_check_is_reported_not_raised(scored, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(v, "penalty_by_branch", boom)
    results = v.run_checks(scored, quick=True)
    assert results["penalty_by_branch"]["pass"] is False and "boom" in results["penalty_by_branch"]["error"]
    assert results["additivity"]["pass"] is True
