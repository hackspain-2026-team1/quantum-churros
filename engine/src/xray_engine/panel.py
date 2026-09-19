"""Entity-month panel: company and group rows with identical columns.

Rules that hold for every column of ``PANEL_COLUMNS``:
- complete months only, ``window.first_month..window.last_month``; an entity
  starts on the month of its first booked row and has one row per month from
  there to the end of the window, months without rows included;
- perimeter(g, m) = accounts whose first booked month is <= m, of members
  whose first booked month is <= m; ``created_at`` is never used. An account
  without a booked row up to m is not in it, and neither is its balance: as
  of m nobody can tell a dormant account from one that is not connected yet,
  so reading it would rewrite past months once its first row arrives.
  Revolving lines and debt products are facilities of the member, not feeds:
  their limit, drawn balance and presence count from the first booked month
  of their company, whatever their own rows (most lines never book one). A
  perimeter change is a member or an account first seen in m, after the first
  month of the entity; events are deduped to (company, month): a company that
  joins is one event, not one per account it brings;
- flows only read rows whose ``flow_class`` is op_in, op_out or debt_service
  and that are not ``fx_excluded``; legs of mirror pairs and reversals are
  ``internal`` for companies and groups alike. Cents are summed per (entity,
  month, currency) and converted with the static FX rate afterwards; group
  rows sum member flows and balances, then take ratios: nothing is averaged
  over companies;
- row counts (live feed, data-quality shares) include every booked row;
- trailing sums named ``*_w`` add monthly totals capped with ``winsorised``;
  windows only hold observed months (from the first month of the entity);
  there are no row-level caps and no epsilon floors: an undefined ratio is
  left to the pure core, which answers None with a gate;
- month t only uses rows dated <= the end of t. Snapshots are limited to the
  balance anchor of the back-roll, ``granted`` limits (assumed constant) and
  the list of debt products;
- like-for-like momentum only reads accounts with booked rows in both windows
  that were already reporting on the first observed month of the prior
  window: an account connected half way would read as growth;
- the size band is sticky: a new band is adopted once the raw band has held
  ``size_bands.hold_months`` months in a row (past months only);
- a group row depends on the rows of that group and on ``Params`` only.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date

import polars as pl

from . import invoices as invoice_recipes
from .cleaning import CleanTables
from .contracts import PANEL_COLUMNS, PANEL_KEY, SIZE_BANDS, PanelRow, Params

PERIMETER_COLUMNS: dict[str, pl.DataType] = {
    "product_id": pl.String,
    "company_id": pl.String,
    "group_id": pl.String,
    "first_month": pl.Date,  # month of the first booked row
    "last_month": pl.Date,  # month of the last booked row
}
DAILY_BALANCE_COLUMNS: dict[str, pl.DataType] = {
    "product_id": pl.String,
    "company_id": pl.String,
    "group_id": pl.String,
    "product_type": pl.String,
    "date": pl.Date,
    "balance_cents": pl.Int64,  # end-of-day balance, account currency
    "currency": pl.String,
}

# Trailing months behind the data-quality shares, the sweep pairs, the
# zero-balance accounts and the external-revenue check.
TRAILING_YEAR = 12
_KEY = ["entity_id", "mi"]
_ROW_COLUMNS = (
    "transaction_id", "company_id", "group_id", "product_id", "date", "month", "amount_cents",
    "category", "currency", "fx_rate", "fx_excluded", "orphan_product", "reversal_id", "mirror_id",
    "mirror_scope", "flow_class",
)
# what ``profile.swept_subsidiaries`` reads: leaving the narratives out halves its cost
_SWEPT_COLUMNS = (
    "company_id", "product_id", "date", "month", "amount_cents", "group_id", "currency",
    "product_type", "fx_rate", "fx_excluded", "orphan_product", "mirror_id", "mirror_scope",
    "flow_class", "label", "counterparty_key",
)


def winsorised(monthly: Sequence[float], multiple: float) -> list[float]:
    """Monthly totals (>= 0) capped at ``multiple`` x the median positive month.

    The median skips empty months: a quarterly payment is not capped to zero.
    """
    positive = sorted(value for value in monthly if value > 0)
    if not positive:
        return [0.0 for _ in monthly]
    middle = len(positive) // 2
    median = positive[middle] if len(positive) % 2 else (positive[middle - 1] + positive[middle]) / 2
    cap = multiple * median
    return [float(min(max(value, 0.0), cap)) for value in monthly]


def winsorised_sum(monthly: Sequence[float], multiple: float) -> float:
    """Sum of ``winsorised``: the reference for every ``*_w`` column."""
    return float(sum(winsorised(monthly, multiple)))


# --------------------------------------------------------------------------
# shared pieces
# --------------------------------------------------------------------------


def _mi(column: str) -> pl.Expr:
    """Month as an integer, so windows are plain arithmetic."""
    value = pl.col(column)
    return (value.dt.year().cast(pl.Int32) * 12 + value.dt.month().cast(pl.Int32) - 1).alias("mi")


def _month_index(month: date) -> int:
    return month.year * 12 + month.month - 1


def _rates(params: Params) -> pl.DataFrame:
    rates = params.fx.rates
    return pl.DataFrame(
        {"currency": list(rates), "fx_rate": [float(rate) for rate in rates.values()]},
        schema={"currency": pl.String, "fx_rate": pl.Float64},
    )


def _eur(frame: pl.DataFrame, keys: list[str], columns: list[str]) -> pl.DataFrame:
    """Int64 cents per (keys, currency, fx_rate) -> EUR per keys.

    Rows without a rate are left out. Currencies are added in a fixed order,
    so a total never depends on the rest of the cohort or on the row order.
    """
    return (
        frame.filter(pl.col("fx_rate").is_not_null())
        .sort([*keys, "currency"])
        .group_by(keys, maintain_order=True)
        .agg([(pl.col(name) / 100 * pl.col("fx_rate")).sum().alias(name) for name in columns])
    )


def _booked(clean: CleanTables) -> pl.DataFrame:
    """Booked rows of the complete months, owners known; the columns the panel reads."""
    window = clean.window
    return clean.transactions.select(_ROW_COLUMNS).filter(
        pl.col("month").is_between(window.first_month, window.last_month)
        & pl.col("company_id").is_not_null()
        & pl.col("group_id").is_not_null()
    )


def build_perimeter(clean: CleanTables) -> pl.DataFrame:
    """One row per product with booked rows, as ``PERIMETER_COLUMNS``; sorted by product_id.

    The owner is the company of the earliest booked row of the product.
    """
    return (
        _booked(clean)
        .sort("date", "transaction_id")
        .group_by("product_id")
        .agg(
            pl.col("company_id").first(),
            pl.col("group_id").first(),
            pl.col("month").min().alias("first_month"),
            pl.col("month").max().alias("last_month"),
        )
        .select(pl.col(name).cast(dtype) for name, dtype in PERIMETER_COLUMNS.items())
        .sort("product_id")
    )


def _universe(clean: CleanTables, perimeter: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Every product of a company with booked rows: owner, type, rate and ``since_mi``,
    the month its balance facts start to count (module docstring): the first booked
    month of an account, the first month of the member for a revolving line, never
    (null) for an account without booked rows."""
    members = perimeter.group_by("company_id").agg(pl.col("first_month").min().alias("member_first"))
    is_line = pl.col("product_type").is_in(list(params.flows.revolving_product_types))
    master = clean.products.select(
        "product_id", pl.col("company_id").alias("master_company"),
        pl.col("group_id").alias("master_group"), "product_type", "product_family", "currency",
        pl.col("granted_cents").alias("product_granted_cents"),
    )
    return (
        master.join(perimeter, on="product_id", how="full", coalesce=True)
        .with_columns(
            pl.coalesce("company_id", "master_company").alias("company_id"),
            pl.coalesce("group_id", "master_group").alias("group_id"),
            pl.col("first_month").is_not_null().alias("has_rows"),
        )
        .join(members, on="company_id", how="inner")
        .join(_rates(params), on="currency", how="left")
        .filter(pl.col("group_id").is_not_null())
        .with_columns(
            pl.when(is_line.fill_null(False)).then("member_first").otherwise("first_month").alias("since_month")
        )
        .with_columns(
            _mi("first_month").alias("product_first_mi"), _mi("member_first").alias("member_first_mi"),
            _mi("since_month").alias("since_mi"),
        )
        .select(
            "product_id", "company_id", "group_id", "product_type", "product_family", "currency",
            "fx_rate", "product_granted_cents", "has_rows", "since_month", "product_first_mi",
            "member_first_mi", "since_mi",
        )
        .sort("product_id")
    )


def _anchors(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Latest balance row per product that is not a sentinel, on its own date."""
    sentinel = pl.col("balance_cents").abs() / 100 >= params.flows.sentinel_abs_balance
    return (
        clean.balances.filter(pl.col("balance_cents").is_not_null() & ~sentinel)
        .sort("product_id", "date")
        .group_by("product_id", maintain_order=True)
        .agg(
            pl.col("date").last().alias("anchor_date"),
            pl.col("balance_cents").last().alias("anchor_cents"),
            pl.col("granted_cents").last().alias("anchor_granted_cents"),
        )
    )


def _daily(clean: CleanTables, universe: pl.DataFrame, anchors: pl.DataFrame, params: Params) -> pl.DataFrame:
    """End-of-day balance and turnover per anchored cash product and revolving line."""
    flows = params.flows
    kinds = [*flows.cash_product_types, *flows.revolving_product_types]
    targets = universe.filter(pl.col("product_type").is_in(kinds) & pl.col("since_month").is_not_null()).join(
        anchors, on="product_id", how="inner"
    )
    moves = (
        clean.transactions.select("product_id", "date", "amount_cents")
        .join(targets.select("product_id", "anchor_date"), on="product_id", how="inner")
        .group_by("product_id", "date")
        .agg(
            pl.col("amount_cents").sum().alias("net"),
            pl.col("amount_cents").abs().sum().alias("turnover"),
            pl.col("anchor_date").first(),
        )
    )
    # balance(d) = anchor - rows in (d, anchor date] = opening + rows up to d
    booked_by_anchor = moves.group_by("product_id").agg(
        pl.col("net").filter(pl.col("date") <= pl.col("anchor_date")).sum().alias("booked_by_anchor")
    )
    window = clean.window
    days = pl.select(
        pl.date_range(window.first_month, pl.lit(window.last_month).dt.month_end(), interval="1d").alias("date")
    )
    return (
        targets.join(booked_by_anchor, on="product_id", how="left")
        .select(
            "product_id", "since_month",
            (pl.col("anchor_cents") - pl.col("booked_by_anchor").fill_null(0)).alias("opening"),
        )
        .join(days, how="cross")
        .filter(pl.col("date") >= pl.col("since_month"))
        .join(moves.select("product_id", "date", "net", "turnover"), on=["product_id", "date"], how="left")
        .with_columns(pl.col("net").fill_null(0), pl.col("turnover").fill_null(0))
        .sort("product_id", "date")
        .with_columns((pl.col("opening") + pl.col("net").cum_sum().over("product_id")).alias("balance_cents"))
        .select("product_id", "date", "balance_cents", "turnover")
    )


def backroll_balances(clean: CleanTables, params: Params) -> pl.DataFrame:
    """End-of-day balances per anchored product, as ``DAILY_BALANCE_COLUMNS``.

    Anchor = the latest balance row of the product that is not a sentinel
    (``|balance| >= params.flows.sentinel_abs_balance``), on its own date.
    ``balance(d) = anchor - sum(amount_cents of booked rows with d < date <=
    anchor_date)`` before the anchor and ``anchor + sum(rows with anchor_date <
    date <= d)`` after it. Every booked row of the product moves the balance,
    whatever its flow class. Covers cash accounts from their first booked month
    (none for an account without booked rows) and revolving lines from the
    first booked month of their company, up to the end of
    ``window.last_month``. Integer cents end to end.
    """
    universe = _universe(clean, build_perimeter(clean), params)
    facts = universe.select("product_id", "company_id", "group_id", "product_type", "currency")
    return (
        _daily(clean, universe, _anchors(clean, params), params)
        .join(facts, on="product_id", how="left")
        .select(pl.col(name).cast(dtype) for name, dtype in DAILY_BALANCE_COLUMNS.items())
        .sort("product_id", "date")
    )


@dataclass(frozen=True)
class _Base:
    """Everything both entity kinds share; nothing here looks across groups."""

    months: pl.DataFrame  # month, mi
    last_mi: int
    universe: pl.DataFrame
    product_months: pl.DataFrame  # integer facts per (product, month)
    netted: pl.DataFrame  # one row per leg of a mirror pair or reversal
    daily: pl.DataFrame  # product_id, date, balance_cents, turnover, product facts
    line_limits: pl.DataFrame  # product_id, limit_cents: |granted| of the balance row, else of the product
    sentinels: pl.DataFrame  # product_id, sentinel_rows
    invoices: pl.DataFrame  # days beyond terms and gate inputs, both kinds
    invoice_stock: pl.DataFrame  # company_id, group_id, side, month, open, overdue (cents by currency)
    first_invoice: pl.DataFrame  # company_id, group_id, first issuance date
    swept: pl.DataFrame  # company_id, month


def _product_months(rows: pl.DataFrame, params: Params) -> pl.DataFrame:
    flows = params.flows
    cents, valued = pl.col("amount_cents"), ~pl.col("fx_excluded")
    intragroup = (pl.col("mirror_scope") == "intra_group").fill_null(False)

    def total(flag: pl.Expr, sign: int = 1) -> pl.Expr:
        return (cents.filter(flag & valued).sum() * sign).cast(pl.Int64)

    return (
        rows.group_by("company_id", "group_id", "product_id", "currency", "fx_rate", "month")
        .agg(
            pl.len().cast(pl.Int64).alias("rows"),
            (pl.col("category") == flows.dash_category).sum().cast(pl.Int64).alias("dash_rows"),
            (pl.col("fx_excluded") & ~pl.col("orphan_product")).sum().cast(pl.Int64).alias("fx_rows"),
            pl.col("orphan_product").sum().cast(pl.Int64).alias("orphan_rows"),
            ((cents > 0) & valued).sum().cast(pl.Int64).alias("inflow_rows"),
            intragroup.sum().cast(pl.Int64).alias("pair_legs"),
            (intragroup & (cents < 0)).sum().cast(pl.Int64).alias("pairs_paid"),
            total(pl.col("flow_class") == "op_in").alias("op_in"),
            total(pl.col("flow_class") == "op_out", -1).alias("op_out"),
            total(pl.col("flow_class") == "debt_service", -1).alias("debt_service"),
            total(intragroup & (cents > 0)).alias("intragroup_in"),
            total(intragroup & (cents < 0), -1).alias("intragroup_out"),
        )
        .with_columns(_mi("month"))
        .sort("product_id", "month")
    )


def _swept_months(clean: CleanTables, params: Params, months: Sequence[date]) -> pl.DataFrame:
    """(company_id, month) of the swept subsidiaries, one as-of reading per month."""
    from . import profile  # profile imports this module for the winsorised sums

    # a company alone in its group is never swept: groups of one are left out
    sizes = clean.transactions.group_by("group_id").agg(pl.col("company_id").n_unique().alias("members"))
    shared = sizes.filter(pl.col("members") > 1).select("group_id")
    rows = clean.transactions.select(_SWEPT_COLUMNS).join(shared, on="group_id", how="semi")
    found = [
        {"company_id": company_id, "month": month}
        for month in months
        for company_id in (sorted(profile.swept_subsidiaries(clean, rows, params, month=month)) if rows.height else [])
    ]
    return pl.DataFrame(found, schema={"company_id": pl.String, "month": pl.Date})


def _invoice_facts(clean: CleanTables, params: Params, months: Sequence[date]) -> pl.DataFrame:
    keys = ["entity_kind", "entity_id", "side", "month"]
    dbt = invoice_recipes.days_beyond_terms_as_of(clean.invoices, months, params)
    evidence = invoice_recipes.window_evidence_as_of(clean.invoices, months, params)
    return dbt.drop("group_id").join(evidence.select(*keys, "aged_n", "aged_open_n"), on=keys, how="left")


def _prepare(clean: CleanTables, params: Params) -> _Base:
    window = clean.window
    months = pl.DataFrame(
        {"month": pl.date_range(window.first_month, window.last_month, interval="1mo", eager=True)}
    ).with_columns(_mi("month"))
    month_list = months["month"].to_list()
    rows = _booked(clean)
    perimeter = build_perimeter(clean)
    universe = _universe(clean, perimeter, params)

    legs = rows.filter(
        (pl.col("mirror_id").is_not_null() | pl.col("reversal_id").is_not_null()) & ~pl.col("fx_excluded")
    ).select(
        "company_id", "group_id", "month", "currency", "fx_rate",
        pl.coalesce("mirror_id", "reversal_id").alias("pair_id"),
        pl.col("amount_cents").abs().alias("netted"),
    )
    sentinel = pl.col("balance_cents").abs() / 100 >= params.flows.sentinel_abs_balance
    sentinels = clean.balances.filter(sentinel).group_by("product_id").agg(
        pl.len().cast(pl.Int64).alias("sentinel_rows")
    )
    facts = universe.select("product_id", "company_id", "group_id", "product_type", "currency", "fx_rate")
    anchors = _anchors(clean, params)
    limits = universe.join(anchors, on="product_id", how="left").select(
        "product_id",
        pl.coalesce("anchor_granted_cents", "product_granted_cents").abs().fill_null(0).alias("limit_cents"),
    )
    members = clean.companies.select("company_id", "group_id").unique("company_id", keep="first")
    stock = (
        invoice_recipes.invoice_states_as_of(clean.invoices, window.last_month)
        .join(members, on="company_id", how="left")
        .join(_rates(params), on="currency", how="left")
        .select("company_id", "group_id", "side", "month", "currency", "fx_rate",
                pl.col("open_cents").alias("open"), pl.col("overdue_cents").alias("overdue"))
    )
    first_invoice = clean.invoices.group_by("company_id", "group_id").agg(
        pl.col("issuance_date").min().alias("first_issued")
    )
    return _Base(
        months=months,
        last_mi=_month_index(window.last_month),
        universe=universe,
        product_months=_product_months(rows, params),
        netted=legs,
        daily=_daily(clean, universe, anchors, params).join(facts, on="product_id", how="left"),
        line_limits=limits,
        sentinels=sentinels,
        invoices=_invoice_facts(clean, params, month_list),
        invoice_stock=stock,
        first_invoice=first_invoice,
        swept=_swept_months(clean, params, month_list),
    )


# --------------------------------------------------------------------------
# one entity kind
# --------------------------------------------------------------------------


def _skeleton(base: _Base, entity: str) -> pl.DataFrame:
    """One row per entity and observed month: entity_id, group_id, month, mi, first_mi."""
    first = base.product_months.group_by(pl.col(entity).alias("entity_id")).agg(
        pl.col("group_id").min(), pl.col("mi").min().alias("first_mi")
    )
    return (
        first.join(base.months, how="cross")
        .filter(pl.col("mi") >= pl.col("first_mi"))
        .with_columns((pl.col("mi") - pl.col("first_mi") + 1).cast(pl.Int64).alias("months_observed"))
        .sort("entity_id", "mi")
    )


def _monthly(base: _Base, skeleton: pl.DataFrame, entity: str) -> pl.DataFrame:
    """Complete entity-month grid: row counts and EUR flows, zeros where nothing was booked."""
    own = base.product_months.with_columns(pl.col(entity).alias("entity_id"))
    counts = own.group_by(_KEY).agg(
        pl.col("rows", "dash_rows", "fx_rows", "orphan_rows", "inflow_rows").sum(),
        pl.col("op_in").sum().alias("op_in_cents"),
        # a pair between two members is one pair for the group and one for each company
        pl.col("pairs_paid" if entity == "group_id" else "pair_legs").sum().alias("pairs"),
    )
    money = ["op_in", "op_out", "debt_service", "intragroup_in", "intragroup_out"]
    by_currency = own.group_by([*_KEY, "currency", "fx_rate"]).agg(pl.col(money).sum())
    netted = (
        base.netted.with_columns(pl.col(entity).alias("entity_id"), _mi("month"))
        .unique([*_KEY, "pair_id"])  # both legs inside the entity: the pair counts once
        .group_by([*_KEY, "currency", "fx_rate"])
        .agg(pl.col("netted").sum())
    )
    integers = ["rows", "dash_rows", "fx_rows", "orphan_rows", "inflow_rows", "op_in_cents", "pairs"]
    return (
        skeleton.select("entity_id", "mi", "first_mi")
        .join(counts, on=_KEY, how="left")
        .join(_eur(by_currency, _KEY, money), on=_KEY, how="left")
        .join(_eur(netted, _KEY, ["netted"]), on=_KEY, how="left")
        .with_columns(pl.col(integers).fill_null(0), pl.col([*money, "netted"]).fill_null(0.0))
        .with_columns((pl.col("op_out") + pl.col("debt_service")).alias("outflow"))
        .sort(_KEY)
    )


def _windows(monthly: pl.DataFrame, reach: int) -> pl.DataFrame:
    """Every observed month m = t - k, k in 0..reach, next to its entity-month t."""
    offsets = pl.DataFrame({"k": pl.int_range(0, reach + 1, eager=True, dtype=pl.Int32)})
    values = monthly.drop("first_mi").rename({"mi": "m"})
    return (
        monthly.select("entity_id", "mi", "first_mi")
        .join(offsets, how="cross")
        .with_columns((pl.col("mi") - pl.col("k")).alias("m"))
        .filter(pl.col("m") >= pl.col("first_mi"))
        .join(values, on=["entity_id", "m"], how="left")
        .sort("entity_id", "mi", "m")
    )


def _capped_sum(name: str, months: int, multiple: float) -> pl.Expr:
    """``winsorised_sum`` of column ``name`` over k < months (needs the ``cap`` columns)."""
    value = pl.col(name).filter(pl.col("k") < months)
    cap = pl.col(f"{name}_cap_{months}").filter(pl.col("k") < months)
    return pl.min_horizontal(value.clip(lower_bound=0.0), cap * multiple).sum().fill_null(0.0)


def _flows(monthly: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Trailing facts per entity-month; every window only holds observed months."""
    feed, liquidity, activity = params.live_feed, params.liquidity, params.activity
    multiple = params.robust.monthly_winsor_multiple
    six, year, band = activity.coverage_window_months, params.debt.window_months, params.size_bands.window_months
    reach = max(feed.base_from_months, year, band, TRAILING_YEAR - 1, liquidity.outflow_fallback_months - 1)
    k = pl.col("k")
    base = (k >= feed.base_to_months) & (k <= feed.base_from_months)
    capped = [("op_in", six), ("outflow", six), ("op_in", year), ("debt_service", year), ("op_in", band)]
    caps = {
        f"{name}_cap_{months}": pl.col(name).filter((k < months) & (pl.col(name) > 0)).median().over(_KEY)
        for name, months in capped
    }
    quality = k < TRAILING_YEAR
    windows = _windows(monthly, reach).with_columns(**caps)
    return windows.group_by(_KEY, maintain_order=True).agg(
        pl.col("rows").filter(k == 0).sum().alias("rows_month"),
        pl.col("rows").filter(k < feed.recent_months).sum().alias("rows_3m"),
        pl.col("rows").filter(base).median().alias("rows_base_median"),
        base.sum().cast(pl.Int64).alias("rows_base_months"),
        pl.col("op_in").filter(k == 0).sum().alias("op_inflow_1m"),
        pl.col("op_out").filter(k == 0).sum().alias("op_outflow_1m"),
        pl.col("debt_service").filter(k == 0).sum().alias("debt_service_1m"),
        pl.col("intragroup_in").filter(k == 0).sum().alias("intragroup_in"),
        pl.col("intragroup_out").filter(k == 0).sum().alias("intragroup_out"),
        pl.col("netted").filter(k == 0).sum().alias("mirror_netted_1m"),
        pl.col("outflow").filter(k < liquidity.outflow_window_months).median().alias("outflow_median_3m"),
        pl.col("outflow").filter(k < liquidity.outflow_fallback_months).median().alias("outflow_median_12m"),
        _capped_sum("op_in", six, multiple).alias("op_in_sum_6m_w"),
        _capped_sum("outflow", six, multiple).alias("outflow_sum_6m_w"),
        (k < six).sum().cast(pl.Int64).alias("months_in_6m_window"),
        _capped_sum("op_in", year, multiple).alias("op_in_sum_12m_w"),
        _capped_sum("debt_service", year, multiple).alias("debt_service_sum_12m_w"),
        (k < year).sum().cast(pl.Int64).alias("months_in_12m_window"),
        _capped_sum("op_in", band, multiple).alias("band_inflow"),
        (k < band).sum().alias("band_months"),
        pl.col("pairs").filter(quality).sum().alias("sweep_pairs_12m"),
        pl.col("rows").filter(quality).sum().alias("rows_year"),
        pl.col("dash_rows").filter(quality).sum().alias("dash_year"),
        pl.col("fx_rows").filter(quality).sum().alias("fx_year"),
        pl.col("orphan_rows").filter(quality).sum().alias("orphan_year"),
        pl.col("inflow_rows").filter(quality).sum().alias("inflow_rows_year"),
        pl.col("op_in_cents").filter(quality).sum().alias("op_in_cents_year"),
    ).with_columns(
        pl.when(pl.col("rows_base_months") >= feed.min_base_months).then(pl.col("rows_base_median")).alias("rows_base_median"),
        (pl.col("rows_month") == 0).alias("zero_row_month"),
        ((pl.col("inflow_rows_year") > 0) & (pl.col("op_in_cents_year") == 0)).alias("no_external_revenue"),
        *[
            pl.when(pl.col("rows_year") > 0).then(pl.col(source) / pl.col("rows_year")).alias(target)
            for source, target in (("dash_year", "dash_share"), ("fx_year", "fx_excluded_share"),
                                   ("orphan_year", "orphan_product_share"))
        ],
    )


def _size_band(flows: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Sticky band: the raw band of the first month, then a new one once it has
    held ``hold_months`` months in a row. Only reads months up to t."""
    bounds, hold = params.size_bands.upper_bounds_eur, params.size_bands.hold_months
    annual = pl.col("band_inflow") * 12 / pl.col("band_months")
    raw = pl.lit(SIZE_BANDS[-1])
    for key, bound in reversed(list(zip(SIZE_BANDS, bounds))):
        raw = pl.when(annual < bound).then(pl.lit(key)).otherwise(raw)
    held = pl.all_horizontal(
        [pl.col("raw") == pl.col("raw").shift(step).over("entity_id") for step in range(1, hold)] or [pl.lit(True)]
    )
    return (
        flows.sort(_KEY)
        .with_columns(raw.alias("raw"))
        .with_columns(pl.when(held).then(pl.col("raw")).alias("settled"))
        .select(
            *_KEY,
            pl.coalesce(
                pl.col("settled").forward_fill().over("entity_id"), pl.col("raw").first().over("entity_id")
            ).alias("size_band"),
        )
    )


def _perimeter_facts(base: _Base, skeleton: pl.DataFrame, entity: str, params: Params) -> pl.DataFrame:
    """Members, accounts, change events and the inflow share of new accounts."""
    products = base.universe.with_columns(pl.col(entity).alias("entity_id")).join(
        skeleton.select("entity_id", "first_mi").unique(), on="entity_id", how="inner"
    )
    # events, deduped to (company, month): a joining member, or an account of a known member
    first_rows = products.filter(pl.col("has_rows")).select(
        "entity_id", "company_id", "member_first_mi", "first_mi", pl.col("product_first_mi").alias("mi")
    ).unique(["entity_id", "company_id", "mi"])
    joined = (
        first_rows.unique(["entity_id", "company_id"]).filter(pl.col("member_first_mi") > pl.col("first_mi"))
        .select("entity_id", pl.col("member_first_mi").alias("mi"), pl.lit(1).alias("members_joined"))
    )
    connected = first_rows.filter(pl.col("mi") > pl.col("member_first_mi")).select(
        "entity_id", "mi", pl.lit(1).alias("products_connected")
    )
    events = pl.concat([joined, connected], how="diagonal").group_by(_KEY).agg(
        pl.col("members_joined").sum().fill_null(0), pl.col("products_connected").sum().fill_null(0)
    )
    arrivals = pl.concat(
        [
            products.select("entity_id", pl.col("product_first_mi").alias("since"), pl.lit(1).alias("n_products")),
            products.unique(["entity_id", "company_id"]).select(
                "entity_id", pl.col("member_first_mi").alias("since"), pl.lit(1).alias("n_members")
            ),
        ],
        how="diagonal",
    ).group_by("entity_id", "since").agg(pl.col("n_products", "n_members").sum().fill_null(0))
    counts = (
        skeleton.select(*_KEY).join(arrivals, on="entity_id", how="left")
        .filter(pl.col("since") <= pl.col("mi"))
        .group_by(_KEY).agg(pl.col("n_products", "n_members").sum())
    )

    span = params.trajectory.perimeter_shift_window_months
    offsets = pl.DataFrame({"k": pl.int_range(0, span, eager=True, dtype=pl.Int32)})
    is_new = (pl.col("product_first_mi") > pl.col("mi") - span) & (pl.col("product_first_mi") > pl.col("first_mi"))
    inflow = (
        base.product_months.filter(pl.col("op_in") > 0)
        .select(pl.col(entity).alias("entity_id"), "product_id", "currency", "fx_rate", "op_in", pl.col("mi").alias("m"))
        .join(products.select("entity_id", "product_id", "product_first_mi", "first_mi"), on=["entity_id", "product_id"])
        .join(offsets, how="cross")
        .with_columns((pl.col("m") + pl.col("k")).alias("mi"))
        .filter(pl.col("mi") <= base.last_mi)
        .group_by([*_KEY, "currency", "fx_rate"])
        .agg(pl.col("op_in").sum().alias("inflow"), pl.col("op_in").filter(is_new).sum().alias("new_inflow"))
    )
    share = _eur(inflow, _KEY, ["inflow", "new_inflow"]).select(
        *_KEY,
        pl.when(pl.col("inflow") > 0).then(pl.col("new_inflow") / pl.col("inflow")).alias("new_perimeter_inflow_share_3m"),
    )
    return (
        skeleton.select(*_KEY)
        .join(counts, on=_KEY, how="left")
        .join(events, on=_KEY, how="left")
        .join(share, on=_KEY, how="left")
        .with_columns(pl.col("n_products", "n_members", "members_joined", "products_connected").fill_null(0))
        .sort(_KEY)
        .with_columns((pl.col("members_joined") + pl.col("products_connected") > 0).alias("perimeter_changed"))
        .with_columns(
            (pl.col("mi") - pl.when(pl.col("perimeter_changed")).then(pl.col("mi")).forward_fill().over("entity_id"))
            .cast(pl.Int64).alias("months_since_perimeter_change")
        )
    )


def _like_for_like(base: _Base, skeleton: pl.DataFrame, entity: str, params: Params) -> pl.DataFrame:
    """Momentum inputs on the accounts that report in both windows."""
    activity, multiple = params.activity, params.robust.monthly_winsor_multiple
    recent, span = activity.recent_months, activity.recent_months + activity.prior_months
    offsets = pl.DataFrame({"k": pl.int_range(0, span, eager=True, dtype=pl.Int32)})
    k = pl.col("k")
    prior_months = (
        pl.min_horizontal(pl.lit(activity.prior_months), pl.col("mi") - recent - pl.col("first_mi") + 1)
        .clip(lower_bound=0).cast(pl.Int64).alias("lfl_prior_months")
    )
    spread = (
        base.product_months.select(
            pl.col(entity).alias("entity_id"), "product_id", "currency", "fx_rate", "rows", "op_in",
            pl.col("mi").alias("m"),
        )
        .join(offsets, how="cross")
        .with_columns((pl.col("m") + k).alias("mi"))
        .join(skeleton.select(*_KEY, "first_mi"), on=_KEY, how="inner")
        .join(base.universe.select("product_id", "product_first_mi"), on="product_id", how="inner")
    )
    # reporting in both windows, and from the first observed month of the prior one
    since = pl.max_horizontal(pl.col("mi") - (span - 1), pl.col("first_mi"))
    account = [*_KEY, "product_id"]
    same = (
        (pl.col("rows").filter(k < recent).sum().over(account) > 0)
        & (pl.col("rows").filter(k >= recent).sum().over(account) > 0)
        & (pl.col("product_first_mi") <= since)
    )
    by_currency = spread.filter(same).group_by([*_KEY, "m", "k", "currency", "fx_rate"]).agg(pl.col("op_in").sum())
    months = _eur(by_currency, [*_KEY, "m", "k"], ["op_in"]).sort(*_KEY, "m")
    cap = pl.col("op_in").filter(pl.col("op_in") > 0).median().over(_KEY) * multiple
    sums = (
        months.with_columns(pl.min_horizontal(pl.col("op_in"), cap).alias("capped"))
        .group_by(_KEY, maintain_order=True)
        .agg(
            pl.col("capped").filter(k < recent).sum().alias("recent_sum"),
            pl.col("capped").filter(k >= recent).sum().alias("prior_sum"),
        )
    )
    # accounts without any valued inflow still make the set: their means are zero
    members = spread.filter(same & pl.col("fx_rate").is_not_null()).select(_KEY).unique()
    return (
        skeleton.select(*_KEY, "first_mi").with_columns(prior_months)
        .join(members.with_columns(pl.lit(True).alias("has_accounts")), on=_KEY, how="left")
        .join(sums, on=_KEY, how="left")
        .select(
            *_KEY, "lfl_prior_months",
            pl.when(pl.col("has_accounts")).then(pl.col("recent_sum").fill_null(0.0) / recent).alias("op_in_lfl_recent_mean"),
            pl.when(pl.col("has_accounts") & (pl.col("lfl_prior_months") > 0))
            .then(pl.col("prior_sum").fill_null(0.0) / pl.col("lfl_prior_months")).alias("op_in_lfl_prior_mean"),
        )
    )


def _zero_balance_accounts(base: _Base, cash: pl.DataFrame, params: Params) -> pl.DataFrame:
    """(product_id, mi) of the active cash accounts that sit at zero over t-11..t.

    Scale of an account = the larger p95 of its daily |balance| and of its
    daily turnover over the same days, so the rule is free of the money scale.
    """
    rule = params.liquidity
    level = pl.col("balance_cents").abs()
    scale = pl.max_horizontal(
        level.quantile(0.95), pl.col("turnover").filter(pl.col("turnover") > 0).quantile(0.95).fill_null(0)
    )
    found = []
    for month, mi in base.months.iter_rows():
        start = pl.lit(month).dt.offset_by(f"-{TRAILING_YEAR - 1}mo")
        days = cash.filter(pl.col("date").is_between(start, pl.lit(month).dt.month_end()))
        verdict = days.group_by("product_id").agg(
            (level <= rule.zero_balance_relative * scale).mean().alias("share"),
            pl.col("turnover").sum().alias("turnover"),
        )
        found.append(
            verdict.filter(pl.col("turnover") > 0).select(
                "product_id", pl.lit(mi, dtype=pl.Int32).alias("mi"),
                (pl.col("share") >= rule.zero_balance_days_share).alias("zero_balance"),
            )
        )
    return pl.concat(found)


def _liquidity(base: _Base, skeleton: pl.DataFrame, entity: str, params: Params, zero: pl.DataFrame) -> pl.DataFrame:
    """Cash, lines, anchors and sentinels per entity-month."""
    flows = params.flows
    valued = pl.col("fx_rate").is_not_null()
    is_cash = pl.col("product_type").is_in(list(flows.cash_product_types))
    is_line = pl.col("product_type").is_in(list(flows.revolving_product_types))
    daily = base.daily.filter(valued).with_columns(pl.col(entity).alias("entity_id"))
    month_of = pl.col("date").dt.truncate("1mo")

    cash_days = _eur(
        daily.filter(is_cash).group_by("entity_id", "date", "currency", "fx_rate").agg(pl.col("balance_cents").sum()),
        ["entity_id", "date"], ["balance_cents"],
    ).sort("entity_id", "date")
    cash = cash_days.group_by("entity_id", month_of.alias("month"), maintain_order=True).agg(
        pl.col("balance_cents").last().alias("cash_month_end"),
        pl.col("balance_cents").min().alias("cash_intra_month_min"),
        pl.col("date").get(pl.col("balance_cents").arg_min()).alias("min_day"),
    )

    drawn = pl.max_horizontal(pl.lit(0), -pl.col("balance_cents"))
    line_days = _eur(
        daily.filter(is_line).join(base.line_limits, on="product_id", how="left")
        .with_columns(drawn.alias("drawn"))
        .with_columns(pl.max_horizontal(pl.lit(0), pl.col("limit_cents") - pl.col("drawn")).alias("headroom"))
        .group_by("entity_id", "date", "currency", "fx_rate").agg(pl.col("drawn", "headroom").sum()),
        ["entity_id", "date"], ["drawn", "headroom"],
    )
    month_ends = line_days.filter(pl.col("date") == pl.col("date").dt.month_end()).select(
        "entity_id", month_of.alias("month"), "drawn", "headroom"
    )
    at_min = line_days.select("entity_id", pl.col("date").alias("min_day"), pl.col("headroom").alias("headroom_at_min"))

    # facts of the products in perimeter: counted from the month they enter it
    products = base.universe.with_columns(pl.col(entity).alias("entity_id")).join(
        base.daily.select("product_id").unique().with_columns(pl.lit(True).alias("anchored")), on="product_id", how="left"
    ).join(base.sentinels, on="product_id", how="left").join(base.line_limits, on="product_id", how="left")
    usable = pl.col("anchored").fill_null(False) & valued
    arrivals = products.select(
        "entity_id", pl.col("since_mi").alias("since"), "currency", "fx_rate",
        (is_cash & usable).cast(pl.Int64).alias("n_cash_products"),
        is_line.cast(pl.Int64).alias("n_credit_lines"),
        (is_cash & pl.col("has_rows")).cast(pl.Int64).alias("cash_booked"),
        (is_cash & pl.col("has_rows") & ~usable).cast(pl.Int64).alias("cash_unanchored"),
        pl.when(is_cash | is_line).then(pl.col("sentinel_rows")).fill_null(0).alias("sentinel_balances_dropped"),
        pl.when(is_line).then(pl.col("limit_cents")).fill_null(0).alias("granted"),
    )
    in_perimeter = (
        skeleton.select(*_KEY).join(arrivals, on="entity_id", how="inner").filter(pl.col("since") <= pl.col("mi"))
    )
    integers = ["n_cash_products", "n_credit_lines", "cash_booked", "cash_unanchored", "sentinel_balances_dropped"]
    counts = in_perimeter.group_by(_KEY).agg(pl.col(integers).sum())
    granted = _eur(
        in_perimeter.group_by([*_KEY, "currency", "fx_rate"]).agg(pl.col("granted").sum()), _KEY, ["granted"]
    )
    debts = (
        skeleton.select(*_KEY)
        .join(
            products.filter(
                (pl.col("product_family") == "debt") & ~pl.col("product_type").is_in(list(flows.excluded_debt_types))
            ).select("entity_id", "member_first_mi"),
            on="entity_id", how="inner",
        )
        .filter(pl.col("member_first_mi") <= pl.col("mi"))
        .select(*_KEY, pl.lit(True).alias("has_debt_products")).unique()
    )
    zero_share = (
        zero.join(products.filter(is_cash & usable).select("entity_id", "product_id"), on="product_id", how="inner")
        .group_by(_KEY).agg(pl.col("zero_balance").mean().alias("zero_balance_account_share"))
    )
    window = params.caps.negative_liquidity_window_months
    return (
        skeleton.select(*_KEY, "month")
        .join(cash, on=["entity_id", "month"], how="left")
        .join(month_ends, on=["entity_id", "month"], how="left")
        .join(at_min, on=["entity_id", "min_day"], how="left")
        .join(counts, on=_KEY, how="left")
        .join(granted, on=_KEY, how="left")
        .join(debts, on=_KEY, how="left")
        .join(zero_share, on=_KEY, how="left")
        .with_columns(
            pl.col(integers).fill_null(0), pl.col("drawn", "headroom", "granted").fill_null(0.0),
            pl.col("has_debt_products").fill_null(False),
        )
        .with_columns(
            # without a cash series there is no minimum day: the month-end headroom stands
            pl.coalesce("headroom_at_min", "headroom").alias("headroom_at_min"),
            (pl.col("granted") > 0).alias("limit_assumed_constant"),
            pl.when(pl.col("cash_booked") > 0).then(pl.col("cash_unanchored") / pl.col("cash_booked")).alias("no_cash_anchor_share"),
            (pl.col("cash_month_end") + pl.col("headroom") < 0).fill_null(False).cast(pl.Int64).alias("negative"),
        )
        .sort(_KEY)
        .with_columns(
            pl.col("negative").rolling_sum(window, min_samples=1).over("entity_id").alias("neg_liquidity_months_6m")
        )
        .drop("month", "min_day", "negative", "cash_booked", "cash_unanchored")
    )


def _invoices(base: _Base, skeleton: pl.DataFrame, kind: str, entity: str) -> pl.DataFrame:
    """``ap_*`` / ``ar_*`` columns and ``has_invoices``; invoices pool every member company."""
    facts = base.invoices.filter(pl.col("entity_kind") == kind)
    stock = _eur(
        base.invoice_stock.filter(pl.col(entity).is_not_null())
        .group_by(pl.col(entity).alias("entity_id"), "side", "month", "currency", "fx_rate")
        .agg(pl.col("open", "overdue").sum()),
        ["entity_id", "side", "month"], ["open", "overdue"],
    )
    first = base.first_invoice.filter(pl.col(entity).is_not_null()).group_by(pl.col(entity).alias("entity_id")).agg(
        pl.col("first_issued").min()
    )
    frame = skeleton.select(*_KEY, "month").join(first, on="entity_id", how="left").with_columns(
        (pl.col("first_issued") <= pl.col("month").dt.month_end()).fill_null(False).alias("has_invoices")
    )
    for side in ("ap", "ar"):
        own = facts.filter(pl.col("side") == side.upper()).select(
            "entity_id", "month",
            pl.col("n").alias(f"{side}_n"), pl.col("neff").alias(f"{side}_neff"),
            pl.col("amount").alias(f"{side}_amount"),
            pl.col("days_beyond_terms").alias(f"{side}_days_beyond_terms"),
            pl.col("stamped_share").alias(f"{side}_stamped_share"),
            pl.col("open_share").alias(f"{side}_open_share"),
            pl.col("aged_n").alias(f"{side}_aged_n"), pl.col("aged_open_n").alias(f"{side}_aged_open_n"),
        )
        held = stock.filter(pl.col("side") == side.upper()).select(
            "entity_id", "month", pl.col("open").alias(f"{side}_open"), pl.col("overdue").alias(f"{side}_overdue")
        )
        frame = (
            frame.join(own, on=["entity_id", "month"], how="left")
            .join(held, on=["entity_id", "month"], how="left")
            .with_columns(
                pl.col(f"{side}_n", f"{side}_aged_n", f"{side}_aged_open_n").fill_null(0),
                pl.col(f"{side}_amount", f"{side}_open", f"{side}_overdue").fill_null(0.0),
            )
        )
    return frame.drop("month", "first_issued")


def _entity_panel(base: _Base, kind: str, entity: str, params: Params, zero: pl.DataFrame) -> pl.DataFrame:
    skeleton = _skeleton(base, entity)
    flows = _flows(_monthly(base, skeleton, entity), params)
    frame = (
        skeleton.join(flows, on=_KEY, how="left")
        .join(_size_band(flows, params), on=_KEY, how="left")
        .join(_perimeter_facts(base, skeleton, entity, params), on=_KEY, how="left")
        .join(_like_for_like(base, skeleton, entity, params), on=_KEY, how="left")
        .join(_liquidity(base, skeleton, entity, params, zero), on=_KEY, how="left")
        .join(_invoices(base, skeleton, kind, entity), on=_KEY, how="left")
    )
    if kind == "company":
        frame = frame.join(
            base.swept.select(pl.col("company_id").alias("entity_id"), "month", pl.lit(True).alias("swept_subsidiary")),
            on=["entity_id", "month"], how="left",
        ).with_columns(pl.col("swept_subsidiary").fill_null(False))
    else:
        frame = frame.with_columns(pl.lit(False).alias("swept_subsidiary"))
    return frame.with_columns(pl.lit(kind).alias("entity_kind"))


def _finish(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.select(pl.col(name).cast(dtype) for name, dtype in PANEL_COLUMNS.items()).sort(
        "entity_id", "month"
    )


def _build(clean: CleanTables, params: Params, kinds: Sequence[str]) -> dict[str, pl.DataFrame]:
    base = _prepare(clean, params)
    is_cash = pl.col("product_type").is_in(list(params.flows.cash_product_types))
    zero = _zero_balance_accounts(base, base.daily.filter(is_cash & pl.col("fx_rate").is_not_null()), params)
    groups = _entity_panel(base, "group", "group_id", params, zero).with_columns(
        pl.lit(None, dtype=pl.Float64).alias("cash_share_of_group")
    )
    found = {"group": _finish(groups)}
    if "company" in kinds:
        pooled = groups.select(pl.col("entity_id").alias("group_id"), "mi", pl.col("cash_month_end").alias("group_cash"))
        # a share: an overdrawn member holds none of the group cash, nobody holds more than all of it
        share = pl.when(pl.col("group_cash") > 0).then((pl.col("cash_month_end") / pl.col("group_cash")).clip(0.0, 1.0))
        companies = (
            _entity_panel(base, "company", "company_id", params, zero)
            .join(pooled, on=["group_id", "mi"], how="left")
            .with_columns(share.alias("cash_share_of_group"))
        )
        found["company"] = _finish(companies)
    return found


def build_company_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Company-month rows with exactly ``PANEL_COLUMNS`` (order and dtypes).

    ``entity_kind = "company"``. Column by column:
      cash: sum of the back-rolled cash accounts in perimeter at month end and
        the minimum of the summed daily cash; ``headroom`` = sum over the
        anchored revolving lines of the members in perimeter of
        ``max(0, |granted| - max(0, -balance))`` at month end and on the
        first day of the cash minimum; ``granted`` from the balance row, else
        from the debt product; ``limit_assumed_constant = granted > 0``. A
        cash product in a currency outside the FX table has no usable anchor;
      ``outflow_median_*``: median of monthly op_out + debt_service;
      ``op_in_lfl_*``: accounts with booked rows in both t-2..t and t-8..t-3,
        first seen by the first observed month of t-8..t-3; monthly op_in
        capped with ``winsorised`` over t-8..t, then the means;
      ``size_band``: ``size_band_of(op_in_sum_12m_w * 12 / months_in_12m_window)``
        made sticky with ``size_bands.hold_months``;
      ``rows_base_median``: None below ``live_feed.min_base_months`` observed
        months inside the base window;
      ``swept_subsidiary``: ``profile.swept_subsidiaries`` read as of every
        month (needs a pair paid by the company inside its group);
        ``cash_share_of_group``, ``zero_balance_account_share`` and
        ``sweep_pairs_12m`` are context next to it;
      ``mirror_netted_1m``: every mirror pair and reversal with a leg in the
        entity counts once, at the value of one leg;
      invoices: ``invoices.days_beyond_terms_as_of`` for ``ap_*`` / ``ar_*``,
        ``invoices.window_evidence_as_of`` for the aged counts and
        ``invoices.invoice_states_as_of`` for the open and overdue stock.
    Sorted by (entity_id, month).
    """
    return _build(clean, params, ("group", "company"))["company"]


def build_group_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Group-month rows with exactly ``PANEL_COLUMNS``.

    ``entity_kind = "group"``, ``entity_id = group_id``. Same recipes as the
    company panel on the summed member rows; the like-for-like account set and
    the winsor caps are those of the group. Invoices pool every member.
    ``swept_subsidiary`` is false and ``cash_share_of_group`` null.
    Sorted by (entity_id, month).
    """
    return _build(clean, params, ("group",))["group"]


def build_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Group rows followed by company rows; schema ``PANEL_COLUMNS``; each block sorted by (entity_id, month)."""
    found = _build(clean, params, ("group", "company"))
    return pl.concat([found["group"], found["company"]])


def validate_panel(panel: pl.DataFrame) -> None:
    """Raises ValueError unless the schema equals ``PANEL_COLUMNS`` and ``PANEL_KEY`` is unique."""
    expected = dict(PANEL_COLUMNS)
    actual = dict(panel.schema)
    if list(actual) != list(expected) or any(
        actual[name] != dtype for name, dtype in expected.items()
    ):
        raise ValueError("Panel schema differs from PANEL_COLUMNS")
    if panel.select(PANEL_KEY).is_duplicated().any():
        raise ValueError("Panel has duplicated entity-months")


def iter_rows(panel: pl.DataFrame) -> Iterator[PanelRow]:
    """Panel frame -> ``PanelRow`` objects, in frame order."""
    for values in panel.iter_rows(named=True):
        yield PanelRow.from_mapping(values)


def rows_to_frame(rows: list[PanelRow]) -> pl.DataFrame:
    """``PanelRow`` objects -> frame with schema ``PANEL_COLUMNS``."""
    return pl.DataFrame([row.to_mapping() for row in rows], schema=PANEL_COLUMNS)
