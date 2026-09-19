"""Entity-month panel: perimeter, back-roll, trailing windows, as-of reading, cohort independence."""

from __future__ import annotations

import calendar
import csv
import random
import shutil
import statistics
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

import polars as pl
import pytest
from xray_engine import cleaning, invoices, io, panel, profile
from xray_engine.contracts import PANEL_COLUMNS, SIZE_BANDS

REAL_CACHE_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "cache"
KEYS = ["entity_kind", "entity_id", "month"]
TOL = 1e-9
SUMMED = (
    "op_inflow_1m", "op_outflow_1m", "debt_service_1m", "granted", "drawn", "headroom",
    "intragroup_in", "intragroup_out",
)
COUNTED = ("rows_month", "n_products", "n_cash_products", "n_credit_lines", "sentinel_balances_dropped")
SHARES = (
    "dash_share", "fx_excluded_share", "orphan_product_share", "no_cash_anchor_share",
    "zero_balance_account_share", "new_perimeter_inflow_share_3m", "cash_share_of_group",
    "ap_stamped_share", "ar_stamped_share",
)


def _build(path: Path, cache: Path, params) -> pl.DataFrame:
    return panel.build_panel(cleaning.clean(io.load_tables(path, cache), params), params)


@pytest.fixture(scope="module")
def clean(synthetic, params, tmp_path_factory):
    return cleaning.clean(io.load_tables(synthetic.path, tmp_path_factory.mktemp("panel-cache")), params)


@pytest.fixture(scope="module")
def frame(clean, params) -> pl.DataFrame:
    return panel.build_panel(clean, params)


def _rows(frame: pl.DataFrame, entity_id: str) -> dict[date, dict]:
    return {row["month"]: row for row in frame.filter(pl.col("entity_id") == entity_id).sort("month").to_dicts()}


def _eur(synthetic, params, product_id: str, month: date) -> float:
    rate = params.fx.rates["USD"] if product_id == synthetic.usd_product_id else 1.0
    return synthetic.month_end_balance_cents[(product_id, month)] / 100 * rate


# --------------------------------------------------------------------------
# shape
# --------------------------------------------------------------------------


def test_schema_blocks_and_round_trip(frame, clean, params) -> None:
    panel.validate_panel(frame)
    assert dict(frame.schema) == dict(PANEL_COLUMNS)
    kinds = frame["entity_kind"].to_list()
    assert kinds == sorted(kinds, key=("group", "company").index)  # groups first
    groups = panel.build_group_panel(clean, params)
    companies = panel.build_company_panel(clean, params)
    assert pl.concat([groups, companies]).equals(frame)
    for block in (groups, companies):
        assert block.select("entity_id", "month").equals(block.select("entity_id", "month").sort("entity_id", "month"))
    assert panel.rows_to_frame(list(panel.iter_rows(frame))).equals(frame)
    with pytest.raises(ValueError):
        panel.validate_panel(pl.concat([frame, frame.head(1)]))
    with pytest.raises(ValueError):
        panel.validate_panel(frame.drop("size_band"))


def test_an_entity_runs_from_its_first_booked_month_to_the_end(frame, synthetic, datasets) -> None:
    firsts = dict(synthetic.company_first_month)
    for group_id, members in synthetic.companies_by_group.items():
        firsts[group_id] = min(synthetic.company_first_month[company] for company in members)
    assert set(frame["entity_id"]) == set(firsts)
    for entity_id, first in firsts.items():
        rows = _rows(frame, entity_id)
        months = list(rows)
        assert months[0] == first and months[-1] == synthetic.last_month
        assert months == [datasets.month_add(first, step) for step in range(len(months))]
        assert [row["months_observed"] for row in rows.values()] == list(range(1, len(months) + 1))
    assert frame["size_band"].null_count() == 0 and set(frame["size_band"]) <= set(SIZE_BANDS)
    for name in SHARES:
        assert frame[name].drop_nulls().is_between(0, 1).all(), name
    groups = frame.filter(pl.col("entity_kind") == "group")
    assert not groups["swept_subsidiary"].any() and groups["cash_share_of_group"].null_count() == groups.height


# --------------------------------------------------------------------------
# perimeter
# --------------------------------------------------------------------------


def test_a_late_member_is_one_event_on_its_first_booked_month(frame, synthetic, datasets) -> None:
    joined = synthetic.late_member_first_month
    group = _rows(frame, synthetic.late_member_group_id)
    before = group[datasets.month_add(joined, -1)]
    assert not before["perimeter_changed"] and before["months_since_perimeter_change"] is None
    assert before["new_perimeter_inflow_share_3m"] == 0.0
    row = group[joined]
    assert (row["perimeter_changed"], row["members_joined"], row["products_connected"]) == (True, 1, 0)
    assert row["n_members"] == before["n_members"] + 1 and row["n_products"] == before["n_products"] + 1
    member = _rows(frame, synthetic.late_member_company_id)
    assert min(member) == joined  # never created_at, never an empty row before the first booked one
    assert not any(item["perimeter_changed"] for item in member.values())  # its first month is no change
    assert row["cash_month_end"] - before["cash_month_end"] > 0.9 * member[joined]["cash_month_end"] > 0
    for step in range(3):
        share = group[datasets.month_add(joined, step)]["new_perimeter_inflow_share_3m"]
        assert 0.05 < share < 0.6
    assert group[datasets.month_add(joined, 3)]["new_perimeter_inflow_share_3m"] == 0.0
    changes = [month for month, item in group.items() if item["perimeter_changed"]]
    assert changes == [joined]
    assert [group[datasets.month_add(joined, step)]["months_since_perimeter_change"] for step in range(4)] == [0, 1, 2, 3]


def test_an_account_connected_mid_window_counts_from_its_first_booked_row(frame, synthetic, datasets, params) -> None:
    connected, company = synthetic.mid_window_first_month, synthetic.mid_window_company_id
    rows = _rows(frame, company)
    before, row = rows[datasets.month_add(connected, -1)], rows[connected]
    assert (row["perimeter_changed"], row["members_joined"], row["products_connected"]) == (True, 0, 1)
    assert row["n_products"] == before["n_products"] + 1 and row["n_members"] == before["n_members"] == 1
    assert row["n_cash_products"] == before["n_cash_products"] + 1
    # its balance is unknown before it reports: only the first account makes the cash of May
    others = [
        product for product in synthetic.product_first_month
        if product != synthetic.mid_window_product_id and (product, connected) in synthetic.month_end_balance_cents
        and _owner(synthetic, frame, product) == company
    ]
    assert len(others) == 1
    month = datasets.month_add(connected, -1)
    assert before["cash_month_end"] == pytest.approx(_eur(synthetic, params, others[0], month), abs=TOL)
    both = _eur(synthetic, params, others[0], connected) + _eur(synthetic, params, synthetic.mid_window_product_id, connected)
    assert row["cash_month_end"] == pytest.approx(both, abs=1e-6)
    # like for like: the new account would read as +40 % growth; it only counts once it
    # has reported through the whole prior window
    peak = rows[datasets.month_add(connected, 2)]
    raw = sum(rows[datasets.month_add(connected, step)]["op_inflow_1m"] for step in range(3)) / sum(
        rows[datasets.month_add(connected, step)]["op_inflow_1m"] for step in range(-3, 0)
    )
    assert raw > 1.3
    assert peak["op_in_lfl_recent_mean"] / peak["op_in_lfl_prior_mean"] == pytest.approx(1.0, abs=0.12)
    span = params.activity.recent_months + params.activity.prior_months
    full = datasets.month_add(connected, span - 1)
    assert rows[full]["op_in_lfl_recent_mean"] > 1.25 * rows[datasets.month_add(full, -1)]["op_in_lfl_recent_mean"]
    assert rows[full]["op_in_lfl_recent_mean"] / rows[full]["op_in_lfl_prior_mean"] == pytest.approx(1.0, abs=0.12)


def _owner(synthetic, frame: pl.DataFrame, product_id: str) -> str:
    # synthetic product ids carry their company: PRODUCT ids are looked up in the source file
    owners = getattr(_owner, "cache", None)
    if owners is None:
        owners = {}
        for name in ("banking_products.csv", "debt_products.csv"):
            source = pl.read_csv(synthetic.path / name, infer_schema=False)
            owners.update(dict(zip(source["product_id"], source["company_id"])))
        _owner.cache = owners
    return owners[product_id]


# --------------------------------------------------------------------------
# balances
# --------------------------------------------------------------------------


def test_cash_is_the_ledger_of_the_cash_accounts_in_perimeter(frame, clean, synthetic, params) -> None:
    kinds = set(params.flows.cash_product_types)
    types = dict(zip(clean.products["product_id"], clean.products["product_type"]))
    unusable = {synthetic.sentinel_product_id, synthetic.fx_excluded_product_id}
    checked = 0
    for company_id in synthetic.company_ids:
        accounts = [
            product for product in synthetic.product_first_month
            if _owner(synthetic, frame, product) == company_id and types[product] in kinds and product not in unusable
        ]
        for month, row in _rows(frame, company_id).items():
            live = [product for product in accounts if synthetic.product_first_month[product] <= month]
            assert row["n_cash_products"] == len(live)
            if not live:
                assert row["cash_month_end"] is None and row["cash_intra_month_min"] is None
                continue
            expected = sum(_eur(synthetic, params, product, month) for product in live)
            assert row["cash_month_end"] == pytest.approx(expected, abs=1e-6), (company_id, month)
            assert row["cash_intra_month_min"] <= row["cash_month_end"] + 1e-9
            checked += 1
    assert checked > 100
    weak = _rows(frame, synthetic.deteriorating_company_id)[synthetic.last_month]
    assert weak["sentinel_balances_dropped"] == 1 and weak["no_cash_anchor_share"] == pytest.approx(0.5)
    foreign = _rows(frame, synthetic.stale_company_id)[synthetic.last_month]
    assert foreign["no_cash_anchor_share"] == pytest.approx(0.5)  # no rate, no usable anchor


def test_the_intra_month_minimum_walks_every_day(frame, clean, synthetic, datasets) -> None:
    company = synthetic.companies_by_group["GROUP_0006"][0]
    accounts = [p for p in synthetic.product_first_month if _owner(synthetic, frame, p) == company]
    assert len(accounts) == 1
    moves = clean.transactions.filter(pl.col("product_id") == accounts[0]).select("date", "amount_cents")
    rows = _rows(frame, company)
    for month in (date(2025, 3, 1), date(2026, 5, 1), synthetic.last_month):
        opening = synthetic.month_end_balance_cents[(accounts[0], datasets.month_add(month, -1))]
        days = calendar.monthrange(month.year, month.month)[1]
        balances = [
            opening + moves.filter(pl.col("date").is_between(month, month.replace(day=day)))["amount_cents"].sum()
            for day in range(1, days + 1)
        ]
        assert rows[month]["cash_intra_month_min"] == pytest.approx(min(balances) / 100, abs=1e-6)
        assert rows[month]["cash_month_end"] == pytest.approx(balances[-1] / 100, abs=1e-6)


def test_a_credit_line_gives_drawn_and_headroom_per_month(frame, synthetic, params) -> None:
    line, granted = synthetic.credit_line_product_id, synthetic.credit_line_granted_cents / 100
    company = _rows(frame, synthetic.credit_line_company_id)
    group = _rows(frame, synthetic.late_member_group_id)
    seen = set()
    for month, row in company.items():
        drawn = max(0, -synthetic.month_end_balance_cents[(line, month)]) / 100
        assert row["drawn"] == pytest.approx(drawn, abs=1e-6)
        assert row["headroom"] == pytest.approx(max(0.0, granted - drawn), abs=1e-6)
        assert row["granted"] == pytest.approx(granted) and row["limit_assumed_constant"]
        assert 0.0 <= row["headroom_at_min"] <= granted and row["n_credit_lines"] == 1
        assert row["has_debt_products"]
        for name in ("drawn", "headroom", "granted"):
            assert group[month][name] == pytest.approx(row[name], abs=1e-6)  # the only line of the group
        assert 0.0 <= group[month]["headroom_at_min"] <= granted  # read on the day of the group minimum
        seen.add(round(drawn))
    assert len(seen) > 6  # rebuilt month by month, not the snapshot repeated
    last = company[synthetic.last_month]
    assert last["drawn"] == pytest.approx(synthetic.credit_line_drawn_cents / 100, abs=1e-6)
    # the line is an operating account, not cash
    assert last["n_cash_products"] == 3
    guarantee_only = _rows(frame, "GROUP_0006")[synthetic.last_month]
    assert not guarantee_only["has_debt_products"] and guarantee_only["granted"] == 0.0
    assert not guarantee_only["limit_assumed_constant"]
    assert _rows(frame, synthetic.no_invoice_group_id)[synthetic.last_month]["has_debt_products"]  # a loan


def _without_rows(source: Path, target: Path, headers, drop) -> Path:
    """Copy of a dataset folder that leaves out the transactions ``drop(row)`` selects."""
    target.mkdir(parents=True)
    for name in headers:
        if name != "transactions.csv":
            shutil.copy(source / name, target / name)
            continue
        with (source / name).open(newline="", encoding="utf-8") as handle:
            rows = [row for row in csv.DictReader(handle) if not drop(row)]
        with (target / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(headers[name]))
            writer.writeheader()
            writer.writerows(rows)
    return target


def test_a_line_is_a_facility_and_a_silent_account_is_not_in_the_perimeter(
    frame, synthetic, datasets, params, same_frames, tmp_path
) -> None:
    line, silent = synthetic.credit_line_product_id, synthetic.own_date_anchor_product_id
    first_use = date(2025, 10, 1)

    def drop(row: dict) -> bool:
        early = row["product_id"] == line and row["date"][:10] < first_use.isoformat()
        return early or row["product_id"] == silent

    folder = _without_rows(synthetic.path, tmp_path / "quiet", datasets.headers, drop)
    quiet = _build(folder, tmp_path / "cache", params)
    # the line books its first row in October: limit and drawn balance count from the first
    # month of its company all the same, the account event comes with the first row
    rows, full = _rows(quiet, synthetic.credit_line_company_id), _rows(frame, synthetic.credit_line_company_id)
    granted = synthetic.credit_line_granted_cents / 100
    unused = [row for month, row in rows.items() if month < first_use]
    assert len(unused) == 13 and {row["n_credit_lines"] for row in unused} == {1}
    assert {row["granted"] for row in unused} == {granted} and all(row["limit_assumed_constant"] for row in unused)
    assert len({row["drawn"] for row in unused}) == 1 and 0 < unused[0]["drawn"] < granted
    assert all(row["headroom"] == pytest.approx(granted - row["drawn"]) for row in unused)
    assert all(row["n_products"] == full[row["month"]]["n_products"] - 1 for row in unused)
    assert not any(row["perimeter_changed"] for row in unused)
    assert rows[first_use]["perimeter_changed"] and rows[first_use]["products_connected"] == 1
    assert rows[first_use]["n_products"] == full[first_use]["n_products"]
    assert rows[synthetic.last_month]["drawn"] == pytest.approx(full[synthetic.last_month]["drawn"], abs=1e-6)
    # an account that never books a row: nobody can date it, so its balance is not read
    stamped, before = _rows(quiet, synthetic.stamped_company_id), _rows(frame, synthetic.stamped_company_id)
    assert {row["n_cash_products"] for row in stamped.values()} == {1}
    assert {row["n_products"] for row in stamped.values()} == {1}
    assert before[synthetic.last_month]["n_cash_products"] == 2
    gap = before[synthetic.last_month]["cash_month_end"] - stamped[synthetic.last_month]["cash_month_end"]
    assert gap == pytest.approx(synthetic.month_end_balance_cents[(silent, synthetic.last_month)] / 100, abs=1e-6)
    # which is what keeps the past still: cut before the first row of the line, same rows
    month = date(2025, 5, 1)
    cut = _build(datasets.truncate(folder, tmp_path / "quiet-cut", month), tmp_path / "cache", params)
    same_frames(cut, quiet.filter(pl.col("month") <= month), keys=KEYS, tol=TOL)


def test_swept_subsidiaries_are_read_as_of_every_month(frame, clean, synthetic, params) -> None:
    swept = _rows(frame, synthetic.swept_company_id)
    last = swept[synthetic.last_month]
    assert last["swept_subsidiary"] and last["zero_balance_account_share"] == 1.0
    assert last["sweep_pairs_12m"] > 50 and last["cash_share_of_group"] <= 0.05 and last["intragroup_out"] > 0
    companies = frame.filter(pl.col("entity_kind") == "company")
    for month in (date(2024, 12, 1), date(2025, 9, 1), synthetic.last_month):
        expected = profile.swept_subsidiaries(clean, clean, params, month=month)
        found = set(companies.filter((pl.col("month") == month) & pl.col("swept_subsidiary"))["entity_id"])
        assert found == {company for company in expected if month in _rows(frame, company)}
    assert not any(row["swept_subsidiary"] for row in _rows(frame, synthetic.treasury_company_id).values())
    assert not frame.filter(pl.col("entity_kind") == "group")["swept_subsidiary"].any()
    single = companies.join(
        companies.group_by("group_id").agg(pl.col("entity_id").n_unique().alias("members")), on="group_id"
    ).filter(pl.col("members") == 1)
    assert not single["swept_subsidiary"].any()


# --------------------------------------------------------------------------
# invoices
# --------------------------------------------------------------------------


def test_a_group_without_invoices_has_no_invoice_facts(frame, synthetic) -> None:
    for row in _rows(frame, synthetic.no_invoice_group_id).values():
        assert not row["has_invoices"]
        for side in ("ap", "ar"):
            assert row[f"{side}_n"] == row[f"{side}_aged_n"] == row[f"{side}_aged_open_n"] == 0
            assert row[f"{side}_amount"] == row[f"{side}_open"] == row[f"{side}_overdue"] == 0.0
            for name in ("neff", "days_beyond_terms", "stamped_share", "open_share"):
                assert row[f"{side}_{name}"] is None


def test_invoice_columns_are_the_as_of_aggregates(frame, clean, params) -> None:
    months = sorted(frame["month"].unique())
    dbt = invoices.days_beyond_terms_as_of(clean.invoices, months, params)
    evidence = invoices.window_evidence_as_of(clean.invoices, months, params)
    facts = dbt.join(
        evidence.select("entity_kind", "entity_id", "side", "month", "aged_n", "aged_open_n"),
        on=["entity_kind", "entity_id", "side", "month"],
    )
    assert facts.height > 100
    lookup = {(row["entity_kind"], row["entity_id"], row["month"]): row for row in frame.to_dicts()}
    matched = 0
    for fact in facts.to_dicts():
        row = lookup.get((fact["entity_kind"], fact["entity_id"], fact["month"]))
        if row is None:  # invoices before the first booked row: no entity-month yet
            continue
        side = fact["side"].lower()
        assert row["has_invoices"]
        for source, target in (("n", "n"), ("neff", "neff"), ("amount", "amount"), ("aged_n", "aged_n"),
                               ("days_beyond_terms", "days_beyond_terms"), ("stamped_share", "stamped_share"),
                               ("open_share", "open_share"), ("aged_open_n", "aged_open_n")):
            assert row[f"{side}_{target}"] == fact[source], (fact["entity_id"], fact["month"], target)
        matched += 1
    assert matched > 100
    dated = frame.filter(pl.col("has_invoices"))
    assert (dated["ap_open"] >= dated["ap_overdue"]).all() and (dated["ar_open"] >= dated["ar_overdue"]).all()
    assert dated["ap_open"].max() > 0 and dated["ar_overdue"].max() > 0
    # once an entity has an invoice it keeps the flag
    for rows in frame.sort("month").group_by("entity_id", maintain_order=True).agg("has_invoices")["has_invoices"]:
        flags = rows.to_list()
        assert flags == sorted(flags)


# --------------------------------------------------------------------------
# trailing windows
# --------------------------------------------------------------------------


def test_trailing_columns_follow_the_pure_reference(frame, params) -> None:
    multiple = params.robust.monthly_winsor_multiple
    feed, caps = params.live_feed, params.caps
    six, year = params.activity.coverage_window_months, params.debt.window_months
    short, long = params.liquidity.outflow_window_months, params.liquidity.outflow_fallback_months
    checked = 0
    for entity_id in sorted(set(frame["entity_id"])):
        rows = list(_rows(frame, entity_id).values())
        inflow = [row["op_inflow_1m"] for row in rows]
        debt = [row["debt_service_1m"] for row in rows]
        outflow = [row["op_outflow_1m"] + row["debt_service_1m"] for row in rows]
        counts = [row["rows_month"] for row in rows]
        negative = [
            row["cash_month_end"] is not None and row["cash_month_end"] + row["headroom"] < 0 for row in rows
        ]
        for index, row in enumerate(rows):
            def last(values: list, months: int, index: int = index) -> list:
                return values[max(0, index - months + 1): index + 1]

            assert row["op_in_sum_6m_w"] == pytest.approx(panel.winsorised_sum(last(inflow, six), multiple), rel=1e-12, abs=1e-9)
            assert row["outflow_sum_6m_w"] == pytest.approx(panel.winsorised_sum(last(outflow, six), multiple), rel=1e-12, abs=1e-9)
            assert row["op_in_sum_12m_w"] == pytest.approx(panel.winsorised_sum(last(inflow, year), multiple), rel=1e-12, abs=1e-9)
            assert row["debt_service_sum_12m_w"] == pytest.approx(panel.winsorised_sum(last(debt, year), multiple), rel=1e-12, abs=1e-9)
            assert row["months_in_6m_window"] == min(six, index + 1)
            assert row["months_in_12m_window"] == min(year, index + 1)
            assert row["outflow_median_3m"] == pytest.approx(statistics.median(last(outflow, short)), abs=1e-9)
            assert row["outflow_median_12m"] == pytest.approx(statistics.median(last(outflow, long)), abs=1e-9)
            assert row["rows_3m"] == sum(last(counts, feed.recent_months))
            assert row["zero_row_month"] == (row["rows_month"] == 0)
            base = counts[max(0, index - feed.base_from_months): max(0, index - feed.base_to_months + 1)]
            assert row["rows_base_months"] == len(base)
            if len(base) >= feed.min_base_months:
                assert row["rows_base_median"] == pytest.approx(statistics.median(base))
            else:
                assert row["rows_base_median"] is None
            assert row["neg_liquidity_months_6m"] == sum(last(negative, caps.negative_liquidity_window_months))
            assert row["lfl_prior_months"] == max(
                0, min(params.activity.prior_months, index + 1 - params.activity.recent_months)
            )
            checked += 1
    assert checked == frame.height


def test_a_short_history_has_short_windows_and_no_base(frame, synthetic, params) -> None:
    for entity_id in (synthetic.short_history_company_id, synthetic.short_history_group_id):
        rows = list(_rows(frame, entity_id).values())
        assert 1 < len(rows) < 6
        for index, row in enumerate(rows, start=1):
            assert row["months_observed"] == row["months_in_6m_window"] == row["months_in_12m_window"] == index
            assert row["rows_base_median"] is None and row["rows_month"] > 0
            assert row["outflow_median_3m"] > 0 and row["size_band"] in SIZE_BANDS
            assert row["lfl_prior_months"] == max(0, index - params.activity.recent_months)
            assert (row["op_in_lfl_prior_mean"] is None) == (row["lfl_prior_months"] == 0)
        assert not any(row["perimeter_changed"] for row in rows)


def test_the_size_band_waits_before_it_moves(params) -> None:
    bound = params.size_bands.upper_bounds_eur[0]
    hold = params.size_bands.hold_months
    assert hold == 3
    low, high = bound * 0.5, bound * 2.0
    annual = [low, low, high, high, low, high, high, high, high, low, low, low]
    flows = pl.DataFrame({
        "entity_id": ["E"] * len(annual), "mi": list(range(len(annual))),
        "band_inflow": annual, "band_months": [12] * len(annual),
    }, schema_overrides={"mi": pl.Int32})
    bands = panel._size_band(flows, params)["size_band"].to_list()
    small, medium = SIZE_BANDS[0], SIZE_BANDS[1]
    assert bands == [small] * 7 + [medium] * 4 + [small]
    # the first month takes its own band, and a lone entity never reads its neighbour
    late = flows.with_columns(pl.lit("F").alias("entity_id"), (high + pl.col("band_inflow") * 0).alias("band_inflow"))
    both = panel._size_band(pl.concat([flows, late]), params)
    assert both.filter(pl.col("entity_id") == "F")["size_band"].to_list() == [medium] * len(annual)
    assert both.filter(pl.col("entity_id") == "E")["size_band"].to_list() == bands


def test_a_company_funded_by_its_group_shows_it(frame, synthetic) -> None:
    row = _rows(frame, synthetic.no_external_revenue_company_id)[synthetic.last_month]
    assert row["no_external_revenue"] and row["op_in_sum_12m_w"] == 0.0
    assert row["intragroup_in"] > 0 and row["mirror_netted_1m"] == pytest.approx(row["intragroup_in"])
    assert row["op_outflow_1m"] > 0  # its payroll is real
    assert not _rows(frame, synthetic.treasury_company_id)[synthetic.last_month]["no_external_revenue"]


# --------------------------------------------------------------------------
# groups
# --------------------------------------------------------------------------


def test_groups_add_their_members_then_take_ratios(frame) -> None:
    companies = frame.filter(pl.col("entity_kind") == "company")
    groups = frame.filter(pl.col("entity_kind") == "group")
    members = companies.group_by("group_id", "month").agg(
        pl.col(*SUMMED, *COUNTED).sum(), pl.len().alias("members"),
        pl.col("cash_month_end").sum().alias("cash"), pl.col("cash_month_end").is_null().all().alias("no_cash"),
        pl.col("mirror_netted_1m").sum().alias("netted_by_members"),
        pl.col("sweep_pairs_12m").sum().alias("pair_legs"),
    )
    joined = groups.join(members, left_on=["entity_id", "month"], right_on=["group_id", "month"], suffix="_members")
    assert joined.height == groups.height
    for name in SUMMED:
        assert (joined[name] - joined[f"{name}_members"]).abs().max() < 1e-6, name
    for name in COUNTED:
        assert (joined[name] == joined[f"{name}_members"]).all(), name
    assert (joined["n_members"] == joined["members"]).all()
    known = joined.filter(~pl.col("no_cash"))
    assert (known["cash_month_end"] - known["cash"]).abs().max() < 1e-6
    # both legs of an intra-group pair sit in the group: they cancel, and the pair counts once
    assert (groups["intragroup_in"] - groups["intragroup_out"]).abs().max() < 1e-6
    assert (joined["mirror_netted_1m"] <= joined["netted_by_members"] + 1e-6).all()
    assert (joined["sweep_pairs_12m"] * 2 == joined["pair_legs"]).all()
    shared = joined.filter(pl.col("members") > 1)
    assert (shared["mirror_netted_1m"] < shared["netted_by_members"]).any()


# --------------------------------------------------------------------------
# as-of reading, cohort independence, determinism
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wide(datasets, params, tmp_path_factory):
    root = tmp_path_factory.mktemp("panel-wide")
    dataset = datasets.make(root / "full", n_groups=9, seed=7)
    return root, dataset, _build(dataset.path, root / "cache", params)


# before the late member, before the account connected mid-window (and the first row of a
# savings account), on the connection month, before the short-history group exists
@pytest.mark.parametrize("month", [date(2024, 11, 1), date(2025, 3, 1), date(2025, 6, 1), date(2026, 3, 1)])
def test_later_rows_never_change_an_earlier_month(wide, datasets, params, same_frames, month) -> None:
    root, dataset, full = wide
    cut_dir = datasets.truncate(dataset.path, root / f"cut-{month}", month)
    tables = io.load_tables(cut_dir, root / "cache")
    assert tables.window.last_month == month
    cut = panel.build_panel(cleaning.clean(tables, params), params)
    expected = full.filter(pl.col("month") <= month)
    assert 0 < expected.height < full.height
    same_frames(cut, expected, keys=KEYS, tol=TOL)


@pytest.mark.parametrize("groups", [["GROUP_0001"], ["GROUP_0003", "GROUP_0005", "GROUP_0008"]])
def test_a_group_alone_gives_the_rows_of_the_full_run(wide, datasets, params, same_frames, groups) -> None:
    root, dataset, full = wide
    alone_dir = datasets.filter(dataset.path, root / ("alone-" + "-".join(groups)), groups)
    alone = _build(alone_dir, root / "cache", params)
    assert set(alone["group_id"]) == set(groups)
    same_frames(alone, full.filter(pl.col("group_id").is_in(groups)), keys=KEYS, tol=TOL)


def test_row_order_of_the_files_does_not_matter(wide, datasets, params, clean, frame) -> None:
    root, dataset, full = wide
    shuffled = _build(datasets.shuffle(dataset.path, root / "shuffled", seed=11), root / "cache", params)
    assert shuffled.equals(full)
    assert panel.build_panel(clean, params).equals(frame)
    mixed = replace(
        clean,
        transactions=clean.transactions.sample(fraction=1.0, shuffle=True, seed=5),
        invoices=clean.invoices.sample(fraction=1.0, shuffle=True, seed=5),
        balances=clean.balances.sample(fraction=1.0, shuffle=True, seed=5),
        products=clean.products.sample(fraction=1.0, shuffle=True, seed=5),
    )
    assert panel.build_panel(mixed, params).equals(frame)


# --------------------------------------------------------------------------
# real dataset: aggregate invariants only
# --------------------------------------------------------------------------


def _truncated(tables: io.Tables, month: date, sentinel_cents: int) -> io.Tables:
    """The cached tables as extracted at the end of ``month`` (same rules as ``datasets.truncate``)."""
    cut = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    reopened = ((pl.col("status") == "paid") & (pl.col("payment_date") > cut)).fill_null(False)
    state = pl.when(pl.col("due_date") <= cut).then(pl.lit("overdue")).otherwise(pl.lit("pending"))
    kept = tables.invoices.filter(pl.col("issuance_date") <= cut).with_columns(
        pl.when(reopened).then(state).otherwise("status").alias("status"),
        pl.when(reopened).then("amount_cents").otherwise("pending_cents").alias("pending_cents"),
        pl.when(reopened).then("due_date").otherwise("payment_date").alias("payment_date"),
    )
    later = tables.transactions.filter(pl.col("date") > cut).select(
        "product_id", pl.col("date").alias("booked"), "amount_cents"
    )
    balances = tables.balances.with_row_index("row")
    moved = (
        balances.filter(pl.col("date") > cut).select("row", "product_id", "date")
        .join(later, on="product_id").filter(pl.col("booked") <= pl.col("date"))
        .group_by("row").agg(pl.col("amount_cents").sum().alias("moved"))
    )
    after = pl.col("date") > cut
    real = (pl.col("balance_cents").abs() < sentinel_cents).fill_null(False)
    balances = balances.join(moved, on="row", how="left").with_columns(
        pl.when(after & real).then(pl.col("balance_cents") - pl.col("moved").fill_null(0))
        .otherwise("balance_cents").alias("balance_cents"),
        pl.when(after).then(pl.lit(cut)).otherwise("date").alias("date"),
    ).drop("row", "moved")
    transactions = tables.transactions.filter(pl.col("date") <= cut)
    return replace(
        tables, transactions=transactions, invoices=kept, balances=balances,
        window=io.derive_window(transactions, balances),
    )


@pytest.mark.dataset
def test_real_panel_invariants(real_data_dir, params, same_frames) -> None:
    tables = io.load_tables(real_data_dir, REAL_CACHE_DIR)
    clean = cleaning.clean(tables, params)
    started = time.perf_counter()
    frame = panel.build_panel(clean, params)
    assert time.perf_counter() - started < 90
    panel.validate_panel(frame)
    groups = frame.filter(pl.col("entity_kind") == "group")
    companies = frame.filter(pl.col("entity_kind") == "company")
    window = tables.window
    assert (frame["month"].min(), frame["month"].max()) == (window.first_month, window.last_month)

    # verified headline numbers of the perimeter
    assert groups["entity_id"].n_unique() == 250
    assert groups.filter(pl.col("month") == window.first_month).height == 95
    active = groups.group_by("entity_id").agg((~pl.col("zero_row_month")).sum().alias("months"))
    assert active.filter(pl.col("months") == 24).height == 86  # a row every month of the window
    assert groups.filter(pl.col("members_joined") > 0)["entity_id"].n_unique() == 110
    assert 0.15 < groups["perimeter_changed"].mean() < 0.35
    spans = frame.group_by("entity_id").agg(
        pl.len().alias("rows"), pl.col("months_observed").max().alias("observed"), pl.col("month").max().alias("last")
    )
    assert (spans["rows"] == spans["observed"]).all() and (spans["last"] == window.last_month).all()

    # groups add their members, then take ratios
    members = companies.group_by("group_id", "month").agg(
        pl.col(*SUMMED, *COUNTED).sum(), pl.len().alias("members"),
        pl.col("cash_month_end").sum().alias("cash"), pl.col("cash_month_end").is_null().all().alias("no_cash"),
    )
    joined = groups.join(members, left_on=["entity_id", "month"], right_on=["group_id", "month"], suffix="_members")
    assert joined.height == groups.height and (joined["n_members"] == joined["members"]).all()
    for name in SUMMED:
        scale = pl.max_horizontal(joined[name].abs(), pl.lit(1.0))
        assert joined.select(((pl.col(name) - pl.col(f"{name}_members")).abs() / scale).max()).item() < 1e-9, name
    for name in COUNTED:
        assert (joined[name] == joined[f"{name}_members"]).all(), name
    known = joined.filter(~pl.col("no_cash"))
    assert known.select(
        ((pl.col("cash_month_end") - pl.col("cash")).abs() / pl.max_horizontal(pl.col("cash").abs(), pl.lit(1.0))).max()
    ).item() < 1e-9
    assert groups.select(
        ((pl.col("intragroup_in") - pl.col("intragroup_out")).abs()
         / pl.max_horizontal(pl.col("intragroup_in"), pl.lit(1.0))).max()
    ).item() < 1e-9

    # ranges
    for name in SHARES:
        assert frame[name].drop_nulls().is_between(0, 1).all(), name
    cash = frame.filter(pl.col("cash_month_end").is_not_null())
    assert (cash["cash_intra_month_min"] <= cash["cash_month_end"] + 1e-6).all()
    assert cash.height > 0.95 * frame.height
    assert (frame["headroom"] <= frame["granted"] + 1e-6).all() and (frame["headroom"] >= 0).all()
    assert (frame["drawn"] >= 0).all() and frame["size_band"].null_count() == 0
    assert set(frame["size_band"].unique()) == set(SIZE_BANDS)
    for name in ("op_inflow_1m", "op_outflow_1m", "debt_service_1m", "op_in_sum_6m_w", "outflow_sum_6m_w",
                 "op_in_sum_12m_w", "debt_service_sum_12m_w", "mirror_netted_1m", "ap_open", "ar_open"):
        assert (frame[name] >= 0).all(), name
    last = companies.filter(pl.col("month") == window.last_month)
    assert 150 <= last["swept_subsidiary"].sum() <= 240  # the paid-pair rule, not the loose one
    assert not groups["swept_subsidiary"].any()

    # the vectorised windows equal the pure reference on a sample of entities
    multiple = params.robust.monthly_winsor_multiple
    sample = random.Random(5).sample(sorted(set(frame["entity_id"])), 40)
    for entity_id in sample:
        rows = frame.filter(pl.col("entity_id") == entity_id).sort("month").to_dicts()
        inflow = [row["op_inflow_1m"] for row in rows]
        outflow = [row["op_outflow_1m"] + row["debt_service_1m"] for row in rows]
        for index, row in enumerate(rows):
            assert row["op_in_sum_12m_w"] == pytest.approx(
                panel.winsorised_sum(inflow[max(0, index - 11): index + 1], multiple), rel=1e-9, abs=1e-6)
            assert row["outflow_sum_6m_w"] == pytest.approx(
                panel.winsorised_sum(outflow[max(0, index - 5): index + 1], multiple), rel=1e-9, abs=1e-6)
            assert row["outflow_median_3m"] == pytest.approx(
                statistics.median(outflow[max(0, index - 2): index + 1]), rel=1e-9, abs=1e-6)

    # cohort independence: sixty groups alone
    chosen = random.Random(7).sample(sorted(groups["entity_id"].unique()), 60)
    owned = tables.companies.filter(pl.col("group_id").is_in(chosen))["company_id"].to_list()
    subset = replace(
        tables,
        groups=tables.groups.filter(pl.col("group_id").is_in(chosen)),
        **{
            name: getattr(tables, name).filter(pl.col("company_id").is_in(owned))
            for name in ("companies", "banking_products", "debt_products", "debt_schedule_config",
                         "transactions", "invoices", "balances")
        },
    )
    alone = panel.build_panel(cleaning.clean(subset, params), params)
    same_frames(alone, frame.filter(pl.col("group_id").is_in(chosen)), keys=KEYS, tol=1e-6)

    # as-of reading: the panel of the data cut at t equals the rows up to t. A rolled-back
    # balance that crosses the sentinel threshold is dropped by the cut run only: left out
    month = date(2025, 11, 1)
    sentinel_cents = int(params.flows.sentinel_abs_balance * 100)
    cut_tables = _truncated(tables, month, sentinel_cents)
    assert cut_tables.window.last_month == month
    crossed = cut_tables.balances.join(
        tables.balances.select("product_id", pl.col("balance_cents").alias("declared")), on="product_id"
    ).filter((pl.col("balance_cents").abs() >= sentinel_cents) & (pl.col("declared").abs() < sentinel_cents))
    owners = crossed["company_id"].to_list()
    skipped = tables.companies.filter(pl.col("company_id").is_in(owners))["group_id"].unique().to_list()
    assert len(skipped) <= 5
    cut = panel.build_panel(cleaning.clean(cut_tables, params), params)
    same_frames(
        cut.filter(~pl.col("group_id").is_in(skipped)),
        frame.filter((pl.col("month") <= month) & ~pl.col("group_id").is_in(skipped)),
        keys=KEYS, tol=1e-6,
    )
