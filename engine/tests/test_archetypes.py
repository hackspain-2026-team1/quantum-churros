"""End to end on the synthetic dataset: every archetype lands where the rules say."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from xray_engine.contracts import CARRIED_GATE, SIZE_BANDS
from xray_engine.scoring import score_dataset

pytestmark = pytest.mark.xfail(
    raises=NotImplementedError, strict=False, reason="engine modules are stubs"
)


@pytest.fixture(scope="module")
def run(synthetic, params, tmp_path_factory):
    return score_dataset(synthetic.path, params, cache_dir=tmp_path_factory.mktemp("archetypes"),
                         industry_override={})


def _snapshots(run, entity_id: str) -> dict[date, dict]:
    frame = run.snapshots.filter(pl.col("entity_id") == entity_id).sort("month")
    return {row["month"]: row for row in frame.to_dicts()}


def _panel(run, entity_id: str) -> dict[date, dict]:
    frame = run.panel.filter(pl.col("entity_id") == entity_id).sort("month")
    return {row["month"]: row for row in frame.to_dicts()}


def test_every_entity_has_a_row_per_month_from_its_first_one(run, synthetic) -> None:
    for company_id, first in synthetic.company_first_month.items():
        months = sorted(_snapshots(run, company_id))
        assert months[0] == first and months[-1] == synthetic.last_month
        assert len(months) == (synthetic.last_month.year - first.year) * 12 + (
            synthetic.last_month.month - first.month
        ) + 1
    assert set(run.snapshots["band"].unique()) <= {"critical", "watch", "stable", "solid"}
    assert set(run.panel["size_band"].drop_nulls().unique()) <= set(SIZE_BANDS)
    assert run.panel["size_band"].null_count() == 0 and run.panel["size_band"].n_unique() >= 2
    scores = run.snapshots.select("score", "level")
    assert scores.filter(pl.col("score").is_between(0, 100).not_()).height == 0


def test_a_company_funded_by_its_group_has_no_activity_pillar(run, synthetic) -> None:
    company = synthetic.no_external_revenue_company_id
    row = _panel(run, company)[synthetic.last_month]
    assert row["no_external_revenue"] and row["op_in_sum_12m_w"] == 0.0 and row["intragroup_in"] > 0
    last = _snapshots(run, company)[synthetic.last_month]
    assert last["pillars"]["activity"] is None and last["gates"]["activity"] == ["no_external_revenue"]
    assert "no_external_revenue" in last["flags"]
    assert last["pillars"]["liquidity"] is not None and not last["abstained"]  # never a zero score


def test_a_feed_that_stops_is_carried_forward(run, synthetic, datasets) -> None:
    company = synthetic.stale_company_id
    last_active = synthetic.stale_company_last_active_month
    last_live = datasets.month_add(last_active, 1)  # two of the three trailing months still report
    snapshots = _snapshots(run, company)
    for month, row in snapshots.items():
        assert row["feed_live"] == (month <= last_live), month
    frozen = snapshots[last_live]
    for month in (datasets.month_add(last_live, 1), synthetic.last_month):
        row = snapshots[month]
        assert row["carried_from"] == last_live and row["score"] == frozen["score"]
        assert row["pillars"] == frozen["pillars"] and row["contributions"] == frozen["contributions"]
        assert row["abstained"] and row["abstain_reason"] == "stale_feed" and "stale_feed" in row["flags"]
        assert all(CARRIED_GATE in gates for gates in row["gates"].values())
        assert row["trajectory"]["available"] is False and row["trajectory"]["reason"] == "stale_feed"
        assert row["delta"] == 0.0 or month == datasets.month_add(last_live, 1)
    kinds = [(alert.month, alert.kind, alert.state) for alert in run.alerts
             if alert.entity_id == company and alert.month > last_live]
    assert kinds == [(datasets.month_add(last_live, 1), "stale_feed", "fired")]
    group = _snapshots(run, "GROUP_0005")
    assert all(row["feed_live"] for row in group.values())  # the rest of the group keeps reporting


def test_perimeter_changes_are_dated_by_first_booked_rows(run, synthetic, datasets) -> None:
    group = _panel(run, synthetic.late_member_group_id)
    joined = synthetic.late_member_first_month
    assert group[joined]["perimeter_changed"] and group[joined]["members_joined"] == 1
    assert group[joined]["months_since_perimeter_change"] == 0
    assert group[datasets.month_add(joined, 1)]["months_since_perimeter_change"] == 1
    assert not group[synthetic.first_month]["perimeter_changed"]  # the first month is not a change
    assert group[synthetic.first_month]["n_members"] + 1 == group[joined]["n_members"]

    solo = synthetic.mid_window_company_id
    connected = synthetic.mid_window_first_month
    rows = _panel(run, solo)
    assert rows[connected]["perimeter_changed"] and rows[connected]["products_connected"] == 1
    peak = datasets.month_add(connected, 2)  # three months of the new account: about 29 % of the inflow
    assert rows[peak]["new_perimeter_inflow_share_3m"] == pytest.approx(0.29, abs=0.03)
    assert rows[datasets.month_add(connected, 3)]["new_perimeter_inflow_share_3m"] == 0.0
    snapshot = _snapshots(run, solo)[peak]
    assert "perimeter_shift" in snapshot["flags"]
    assert snapshot["trajectory"]["direction"] == "perimeter_shift" and snapshot["trend"] == "stable"
    structural = [alert for alert in run.alerts if alert.entity_id == solo and alert.month == peak
                  and alert.kind.endswith("_structural")]
    assert structural == []


def test_swept_subsidiary_reads_the_liquidity_of_its_group(run, synthetic) -> None:
    company = _snapshots(run, synthetic.swept_company_id)[synthetic.last_month]
    group = _snapshots(run, "GROUP_0001")[synthetic.last_month]
    assert _panel(run, synthetic.swept_company_id)[synthetic.last_month]["swept_subsidiary"]
    assert "inherited_from_group" in company["gates"]["liquidity"]
    assert "inherited_from_group" in company["flags"]
    assert company["pillars"]["liquidity"] == pytest.approx(group["pillars"]["liquidity"], abs=1e-9)
    treasury = _snapshots(run, synthetic.treasury_company_id)[synthetic.last_month]
    assert "inherited_from_group" not in treasury["gates"]["liquidity"]


def test_invoice_pillars_are_missing_rather_than_neutral(run, synthetic) -> None:
    bank_only = _snapshots(run, synthetic.no_invoice_group_id)[synthetic.last_month]
    for key in ("payments", "collections"):
        assert bank_only["pillars"][key] is None and bank_only["gates"][key] == ["no_invoices"]
    assert "payments" not in bank_only["branch"] and bank_only["weights_effective"]["payments"] is None
    stamped = _snapshots(run, synthetic.stamped_company_id)[synthetic.last_month]
    for key in ("payments", "collections"):
        assert stamped["pillars"][key] is None and "stamped_regime" in stamped["gates"][key]
    dated = _snapshots(run, synthetic.non_stamped_company_id)[synthetic.last_month]
    assert dated["pillars"]["payments"] is not None and dated["pillars"]["collections"] is not None
    assert "payments" in dated["branch"].split("+")


def test_debt_pillar_needs_debt(run, synthetic) -> None:
    for group in (synthetic.no_debt_group_id, "GROUP_0006"):  # nothing, and a guarantee only
        last = _snapshots(run, group)[synthetic.last_month]
        assert last["pillars"]["debt"] is None and last["gates"]["debt"] == ["no_debt"]
    indebted = _snapshots(run, synthetic.no_invoice_group_id)[synthetic.last_month]
    assert indebted["pillars"]["debt"] is not None and "debt_snapshot" in indebted["flags"]
    assert indebted["series"]["debt_burden"] == pytest.approx(210_000 / 8_500_000, rel=0.1)


def test_short_history_abstains_then_scores(run, synthetic, datasets) -> None:
    snapshots = _snapshots(run, synthetic.short_history_group_id)
    first = min(snapshots)
    for offset in range(3):
        row = snapshots[datasets.month_add(first, offset)]
        assert row["abstained"] and row["abstain_reason"] == "short_history" and row["unlock_hint"]
        assert 0.0 <= row["score"] <= 100.0  # the number is still there
    fourth = snapshots[datasets.month_add(first, 3)]
    assert not fourth["abstained"] and fourth["abstain_reason"] is None
    assert all(row["trajectory"]["reason"] == "short_history" for row in snapshots.values())
    assert all("short_history" in row["flags"] for row in snapshots.values())


def test_rows_without_value_only_lower_the_data_quality(run, synthetic) -> None:
    foreign = _panel(run, synthetic.stale_company_id)[synthetic.stale_company_last_active_month]
    assert foreign["fx_excluded_share"] == pytest.approx(1 / 8)  # one forint row in eight
    weak = _panel(run, synthetic.deteriorating_company_id)
    assert weak[date(2026, 2, 1)]["orphan_product_share"] > 0
    assert weak[date(2025, 4, 1)]["orphan_product_share"] == 0.0
    flagged = _snapshots(run, synthetic.deteriorating_company_id)[date(2026, 2, 1)]
    assert "orphan_products" in flagged["flags"]
    # the account holds of January are no cash flow: the month looks like its neighbours
    january, december = weak[date(2026, 1, 1)], weak[date(2025, 12, 1)]
    assert january["op_inflow_1m"] < 2 * december["op_inflow_1m"]
    assert january["op_outflow_1m"] < 2 * december["op_outflow_1m"]
    assert _panel(run, synthetic.deteriorating_company_id)[synthetic.last_month]["sentinel_balances_dropped"] == 1
