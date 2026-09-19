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
from xray_engine.contracts import EntityMonth, PanelRow, Trajectory
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


def test_truncation_holds_when_a_rolled_balance_reaches_the_sentinel_magnitude(scored, params) -> None:
    # the sentinel rule reads snapshot rows only: a legitimately large balance at the cut,
    # rolled back from a small snapshot, stays the anchor of the cut run
    cut_month, cut = date(2026, 2, 1), date(2026, 2, 28)
    sentinel_cents = int(params.flows.sentinel_abs_balance * 100)
    cash = scored.clean.products.filter(pl.col("product_type").is_in(list(params.flows.cash_product_types)))
    reading = (
        scored.tables.balances.filter(
            (pl.col("date") > cut) & (pl.col("balance_cents").abs() < sentinel_cents // 2)
            & pl.col("product_id").is_in(cash["product_id"].to_list())
        ).sort("product_id", "date").group_by("product_id", maintain_order=True).last().row(0, named=True)
    )
    product = reading["product_id"]
    booked = scored.tables.transactions.filter(pl.col("product_id") == product).head(1)
    legs = [("T-HUGE-IN", date(2025, 12, 10), 2 * sentinel_cents), ("T-HUGE-OUT", date(2026, 3, 12), -2 * sentinel_cents)]
    huge = pl.concat([
        booked.with_columns(
            pl.lit(name).alias("transaction_id"), pl.lit(day).alias("date"), pl.lit(day.replace(day=1)).alias("month"),
            pl.lit(cents).cast(pl.Int64).alias("amount_cents"),
        )
        for name, day, cents in legs
    ])
    tables = replace(scored.tables, transactions=pl.concat([scored.tables.transactions, huge]).sort("transaction_id"))
    rolled, crossers = v.roll_balances(tables, cut, params)
    assert crossers == [product]
    marked = rolled.filter((pl.col("product_id") == product) & (pl.col("date") == cut))
    assert marked["rolled_back"].to_list() == [True] and abs(marked["balance_cents"][0]) >= sentinel_cents
    full = v.score_core(tables, params)
    owner = full.clean.products.filter(pl.col("product_id") == product)["company_id"][0]
    at_cut = full.panel.filter((pl.col("entity_id") == owner) & (pl.col("month") == cut_month))
    assert at_cut["cash_month_end"][0] >= params.flows.sentinel_abs_balance  # the back-rolled balance is kept
    found = v.check_truncation(full, months=[cut_month])
    assert found["pass"], found["summary"]
    assert found["accounts_rolled_over_sentinel"] == 1 and found["max_abs_diff"] <= 1e-9
    # without the mark the same reading is a placeholder: dropped, and the cut run differs
    unmarked = v.truncate_tables(tables, cut_month, params)
    unmarked = replace(unmarked, balances=unmarked.balances.drop("rolled_back"))
    dropped = v.score_core(unmarked, params).panel.filter((pl.col("entity_id") == owner) & (pl.col("month") == cut_month))
    assert dropped["sentinel_balances_dropped"][0] == at_cut["sentinel_balances_dropped"][0] + 1


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


def _verdict_months(score_parts, params, kind, entity_id, scores, verdicts, stale=()):
    """Hand-made months of one entity: ``verdicts`` maps an index to Trajectory fields
    (every other live month is stable); ``stale`` indexes are carried months."""
    first, months = date(2025, 1, 1), []
    for index, score in enumerate(scores):
        month = score_parts.month_add(first, index)
        if index in stale:
            parts = score_parts.stale(month, float(score), params, score=float(score), carried_from=first)
            verdict = Trajectory(available=False, reason="stale_feed")
        else:
            parts = score_parts.live(month, float(score), params)
            fields = dict(verdicts.get(index, {}))
            for name in ("shock_month", "compared_to"):
                if name in fields:
                    fields[name] = score_parts.month_add(first, fields[name])
            verdict = Trajectory(available=True, reason=None, **fields)
        row = PanelRow(entity_kind=kind, entity_id=entity_id, group_id="GROUP_A", month=month)
        months.append(EntityMonth(row, {}, parts, verdict))
    return months


def _verdict_cases(score_parts, params, swap: bool = False) -> list[EntityMonth]:
    pending, structural = ("structural", "shock_pending") if swap else ("shock_pending", "structural")
    fall = dict(direction="deteriorating", horizon="short")
    stays = _verdict_months(score_parts, params, "group", "GROUP_A", [70] * 4 + [50] * 8, {
        4: dict(fall, nature=pending, persistence_months=1), 5: dict(fall, nature=structural, persistence_months=2),
        6: dict(fall, nature=structural, persistence_months=3),
    })
    reverts = _verdict_months(score_parts, params, "group", "GROUP_B", [70] * 4 + [50] + [70] * 7, {
        4: dict(fall, nature=pending, persistence_months=1), 5: dict(nature="bump", shock_month=4),
    })
    drifts = _verdict_months(score_parts, params, "group", "GROUP_C", [80 - 0.9 * index for index in range(12)], {
        8: dict(direction="deteriorating", horizon="long", nature=structural, drift_months=9, persistence_months=2),
    })
    company = _verdict_months(score_parts, params, "company", "COMPANY_A", [70] * 4 + [50] * 8, {
        4: dict(fall, nature=structural, persistence_months=2),
    }, stale=(7,))
    return [*stays, *reverts, *drifts, *company]


def test_verdict_persistence_counts_by_hand(scored, score_parts, params) -> None:
    found = v.verdict_persistence(replace(scored, months=tuple(_verdict_cases(score_parts, params))), min_cases=1)
    assert (found["move_points"], found["horizon_months"], found["lags"]) == (6.0, 3, [3, 6])
    groups = found["by_kind"]["group"]
    base = groups["base_rate"]  # every month whose t - 3 is live and scored
    assert base["n"] == 27 and base["lag3"]["n"] == 18 and base["lag6"]["n"] == 9
    assert base["lag3"]["down"] == pytest.approx(4 / 18) and base["lag3"]["up"] == pytest.approx(1 / 18)
    assert base["lag3"]["persist"] is None
    structural = groups["classes"]["deteriorating/structural"]
    assert structural["n"] == 3 and structural["mean_move"] == pytest.approx((-20 - 20 - 2.7) / 3)
    assert structural["lag3"] == {"n": 3, "down": pytest.approx(2 / 3), "up": 0.0, "persist": pytest.approx(2 / 3)}
    assert structural["lag6"]["n"] == 1 and structural["lag6"]["persist"] == 1.0  # month t + 6 must exist
    split = structural["by_horizon"]
    assert (split["short"]["n"], split["short"]["lag3"]["persist"]) == (2, 1.0)
    # the drift alone: 5.4 points against t - 3, 9.9 against the first month of its nine-month window
    assert (split["long"]["lag3"]["persist"], split["long"]["mean_move"]) == (0.0, pytest.approx(-2.7))
    own = split["long"]["own_reference"]
    assert (own["n"], own["mean_move"], own["lag3"]["persist"]) == (1, pytest.approx(-7.2), 1.0)
    pending = groups["classes"]["deteriorating/shock_pending"]
    assert pending["lag3"]["persist"] == 0.5 and pending["lag6"]["persist"] == 0.5
    assert pending["by_age"]["first_month"]["n"] == 2 and "later_months" not in pending["by_age"]
    bump = groups["classes"]["stable/bump"]
    assert bump["lag3"]["persist"] is None and bump["lag3"]["down"] == 0.0  # no direction of its own
    assert bump["by_shock_direction"]["deteriorating"]["lag3"] == {"n": 1, "down": 0.0, "up": 0.0, "persist": 0.0}
    assert groups["classes"]["stable/none"]["n"] == 27 - 3 - 2 - 1
    # a carried month is no outcome: the company verdict has none at +3 and one at +6
    company = found["by_kind"]["company"]["classes"]["deteriorating/structural"]
    assert (company["n"], company["lag3"]["n"], company["lag3"]["persist"], company["lag6"]["persist"]) == (1, 0, None, 1.0)
    assert found["by_kind"]["company"]["base_rate"]["n"] == 7  # months 7 and 10 lack a live end

    falls = found["short_horizon_calls"]["group_falls"]
    assert falls["structural"]["lag3"] == {"n": 2, "persist": 1.0} and falls["pending"]["lag3"]["persist"] == 0.5
    assert falls["bump"]["lag3"]["persist"] == 0.0 and falls["base_rate"]["lag3"] == pytest.approx(4 / 18)
    assert (found["pass"], found["warning"]) == (True, False)
    assert all(0 < len(item["label"]) <= 400 and len(item["unit"]) <= 24 for item in found["metrics"])
    assert len(found["metrics"]) <= 24 and len(found["summary"]) <= 400


def test_verdict_persistence_grades_the_separation(scored, score_parts, params) -> None:
    cases = _verdict_cases(score_parts, params)
    few = v.verdict_persistence(replace(scored, months=tuple(cases)))
    assert (few["pass"], few["warning"]) == (None, False) and "insuficientes" in few["summary"]
    # the labels the other way round: what is called structural persists less than what is pending
    other_way = replace(scored, months=tuple(_verdict_cases(score_parts, params, swap=True)))
    swapped = v.verdict_persistence(other_way, min_cases=1)
    falls = swapped["short_horizon_calls"]["group_falls"]
    assert falls["structural"]["lag3"]["persist"] == 0.5 and falls["pending"]["lag3"]["persist"] == 1.0
    assert swapped["pass"] is False and "no discriminan" in swapped["summary"]
    assert v.check_status(swapped) == "fail"
    # it discriminates, short of a target: a warning, never a pass
    reverted = [
        replace(item, trajectory=replace(item.trajectory, nature="shock_pending", direction="deteriorating",
                                         horizon="short", persistence_months=2, shock_month=None))
        if item.trajectory.nature == "bump" else item
        for item in cases
    ]
    lower = [
        replace(item, parts=replace(item.parts, score=66.0))
        if item.row.entity_id == "GROUP_A" and item.row.month == date(2025, 10, 1) else item
        for item in reverted
    ]  # GROUP_A comes back for one month: the verdict of 2025-07 no longer persists at +3
    warned = v.verdict_persistence(replace(scored, months=tuple(lower)), min_cases=1)
    falls = warned["short_horizon_calls"]["group_falls"]
    assert falls["structural"]["lag3"]["persist"] == 0.5 and falls["pending"]["lag3"]["persist"] == pytest.approx(1 / 3)
    assert (warned["pass"], warned["warning"], v.check_status(warned)) == (None, True, "warn")


def test_verdict_persistence_on_the_scored_run(scored) -> None:
    found = v.verdict_persistence(scored)
    assert set(found["by_kind"]) == {"group", "company"}
    for kind, item in found["by_kind"].items():
        eligible = item["base_rate"]["n"]
        assert 0 < eligible and sum(cell["n"] for cell in item["classes"].values()) <= eligible
        for label, cell in item["classes"].items():
            direction, nature = label.split("/")
            assert direction in ("improving", "deteriorating", "stable", "perimeter_shift")
            for lag in ("lag3", "lag6"):
                assert cell[lag]["n"] <= cell["n"]
                for name in ("down", "up", "persist"):
                    assert cell[lag][name] is None or 0.0 <= cell[lag][name] <= 1.0
                assert (cell[lag]["persist"] is None) == (direction in ("stable", "perimeter_shift") or not cell[lag]["n"])
            if "by_horizon" in cell:
                assert sum(part["n"] for part in cell["by_horizon"].values()) == cell["n"]
    assert set(found["short_horizon_calls"]) == {"group_falls", "group_rises", "company_falls", "company_rises"}


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


def test_coverage_summary_counts_last_month(scored) -> None:
    found = v.coverage_summary(scored)
    groups = found["groups"]
    assert groups["total"] > 0
    assert 0 <= groups["scored_pct"] <= 1
    assert groups["scored"] + groups["abstained"] == groups["total"]
    assert "payments" in groups["pillars"]


def test_level_vs_slope_reports_autocorrelations(scored) -> None:
    found = v.level_vs_slope(scored, lag=3)
    assert found["n_level_pairs"] >= 0
    assert "Persistencia de nivel" in found["summary"]
    if found["n_level_pairs"] >= 3:
        assert found["level_autocorr_lag3"] is not None


def test_rolling_origin_matches_full_run_at_cuts(scored) -> None:
    found = v.rolling_origin(scored)
    assert found["pass"] is True
    assert found["min_spearman"] == pytest.approx(1.0, abs=1e-9)
    assert found["cuts"]


def test_build_kpis_groups_by_stage(scored) -> None:
    results = v.run_checks(scored, quick=True)
    coverage = v.coverage_summary(scored)
    kpis = v.build_kpis(
        scored,
        results,
        coverage=coverage,
        level_slope=results["level_vs_slope"],
        rolling=results["rolling_origin"],
    )
    assert set(kpis["by_stage"]) == {"reconcile", "normalize", "score"}
    assert kpis["by_stage"]["score"]["holdout_n_groups"] == results["isolation"]["n_groups"]


def test_run_validation_writes_kpis_and_coverage(scored, synthetic, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v.io, "load_source", lambda *_args, **_kwargs: scored.tables)
    monkeypatch.setattr(v, "score_core", lambda *_args, **_kwargs: scored)
    out = tmp_path / "validation.json"
    document = v.run_validation(synthetic.path, scored.params, out, quick=True)
    assert "kpis" in document and "coverage" in document
    assert document["kpis"]["by_stage"]["score"]["holdout_n_groups"] == document["isolation"]["n_groups"]
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["level_vs_slope"]["summary"]
