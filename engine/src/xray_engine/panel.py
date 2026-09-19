"""Entity-month panel: company and group rows with identical columns.

Rules that hold for every column of ``PANEL_COLUMNS``:
- complete months only, ``window.first_month..window.last_month``; an entity
  starts on the month of its first booked row and has one row per month from
  there to the end of the window, months without rows included;
- perimeter(g, m) = accounts whose first booked month is <= m, of members
  whose first booked month is <= m; ``created_at`` is never used. Products
  without any booked row (unused lines, loans, dormant accounts) follow the
  first booked month of their company. A perimeter change is a member or an
  account first seen in m, after the first month of the entity; events are
  deduped to (company, month);
- flows only read rows whose ``flow_class`` is op_in, op_out or debt_service
  and that are not ``fx_excluded``; legs of mirror pairs and reversals are
  ``internal`` for companies and groups alike. Cents are summed per (entity,
  month, currency) and converted with the static FX rate afterwards; group
  rows sum member flows, then take ratios;
- row counts (live feed, data-quality shares) include every booked row;
- trailing sums named ``*_w`` add monthly totals capped with ``winsorised``;
  windows only hold observed months (from the first month of the entity);
  there are no row-level caps and no epsilon floors: an undefined ratio is
  left to the pure core, which answers None with a gate;
- month t only uses rows dated <= the end of t. Snapshots are limited to the
  balance anchor of the back-roll, ``granted`` limits (assumed constant) and
  the list of debt products;
- a group row depends on the rows of that group and on ``Params`` only.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import polars as pl

from .cleaning import CleanTables
from .contracts import PANEL_COLUMNS, PANEL_KEY, PanelRow, Params

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


def build_perimeter(clean: CleanTables) -> pl.DataFrame:
    """One row per product with booked rows, as ``PERIMETER_COLUMNS``; sorted by product_id."""
    raise NotImplementedError


def backroll_balances(clean: CleanTables, params: Params) -> pl.DataFrame:
    """End-of-day balances per anchored product, as ``DAILY_BALANCE_COLUMNS``.

    Anchor = the latest balance row of the product that is not a sentinel
    (``|balance| >= params.flows.sentinel_abs_balance``), on its own date.
    ``balance(d) = anchor - sum(amount_cents of booked rows with d < date <=
    anchor_date)`` before the anchor and ``anchor + sum(rows with anchor_date <
    date <= d)`` after it. Every booked row of the product moves the balance,
    whatever its flow class. Covers cash products and revolving lines, for
    every day from the first month of the product in perimeter to the end of
    ``window.last_month``. Integer cents end to end.
    """
    raise NotImplementedError


def build_company_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Company-month rows with exactly ``PANEL_COLUMNS`` (order and dtypes).

    ``entity_kind = "company"``. Column by column:
      cash: sum of back-rolled cash products at month end and the minimum of
        the summed daily cash; ``headroom`` = sum over anchored revolving lines
        of ``max(0, |granted| - max(0, -balance))`` at month end and on the
        first day of the cash minimum; ``granted`` from the balance row, else
        from the debt product; ``limit_assumed_constant = granted > 0``;
      ``outflow_median_*``: median of monthly op_out + debt_service;
      ``op_in_lfl_*``: accounts with booked rows in both t-2..t and t-8..t-3,
        monthly op_in capped with ``winsorised`` over t-8..t, then the means;
      ``size_band``: ``size_band_of(op_in_sum_12m_w * 12 / months_in_12m_window)``;
      ``rows_base_median``: None below ``live_feed.min_base_months`` observed
        months inside the base window;
      ``swept_subsidiary`` (groups with more than one member), any of:
        zero_balance_account_share >= swept_zero_balance_share_min and
        cash_share_of_group <= swept_group_cash_share_max; sweep_pairs_12m >=
        swept_pairs_min and cash_share_of_group <= swept_pairs_cash_share_max;
        cash_share_of_group <= tiny_cash_share_max with a zero-balance account;
      invoices: ``invoices.days_beyond_terms_as_of`` for ``ap_*`` / ``ar_*``
        and ``features.invoice_states_as_of`` for the open and overdue stock.
    Sorted by ``PANEL_KEY``.
    """
    raise NotImplementedError


def build_group_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Group-month rows with exactly ``PANEL_COLUMNS``.

    ``entity_kind = "group"``, ``entity_id = group_id``. Same recipes as the
    company panel on the summed member rows; the like-for-like account set and
    the winsor caps are those of the group. Invoices pool every member.
    ``swept_subsidiary`` is false and ``cash_share_of_group`` null.
    Sorted by ``PANEL_KEY``.
    """
    raise NotImplementedError


def build_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Group rows followed by company rows; schema ``PANEL_COLUMNS``; sorted by ``PANEL_KEY``."""
    raise NotImplementedError


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
