"""Entity-month panel: company and group rows with identical columns.

Rules that hold for every column of ``PANEL_COLUMNS``:
- complete months only, ``window.first_month..window.last_month``; an entity
  starts on the month of its first observed booked row;
- perimeter of a month = products (and members) whose first observed row is
  <= that month; ``created_at`` is never used;
- cents are summed per (entity, month, currency) and converted with the static
  FX rate afterwards; group rows sum member flows, then take ratios;
- month t only uses rows dated <= the end of t. Snapshots are limited to the
  balance anchor of the back-roll and ``granted`` limits (assumed constant);
- a group row depends on the rows of that group and on ``Params`` only.
"""

from __future__ import annotations

from collections.abc import Iterator

import polars as pl

from .cleaning import CleanTables
from .contracts import PANEL_COLUMNS, PANEL_KEY, PanelRow, Params

PERIMETER_COLUMNS: dict[str, pl.DataType] = {
    "product_id": pl.String,
    "company_id": pl.String,
    "group_id": pl.String,
    "first_month": pl.Date,  # month of the first observed booked row
    "last_month": pl.Date,  # month of the last observed booked row
}
DAILY_CASH_COLUMNS: dict[str, pl.DataType] = {
    "product_id": pl.String,
    "company_id": pl.String,
    "group_id": pl.String,
    "date": pl.Date,
    "balance_cents": pl.Int64,  # end-of-day balance, account currency
    "currency": pl.String,
}


def build_perimeter(clean: CleanTables) -> pl.DataFrame:
    """One row per product with booked rows, as ``PERIMETER_COLUMNS``; sorted by product_id."""
    raise NotImplementedError


def backroll_balances(clean: CleanTables, params: Params) -> pl.DataFrame:
    """End-of-day balances per anchored product, as ``DAILY_CASH_COLUMNS``.

    ``balance(d) = anchor_balance - sum(amount_cents of booked rows with
    anchor_date >= date > d)``, anchored on the date of each balance row.
    Sentinel anchors (``|balance| >= params.flows.sentinel_abs_balance``) are
    dropped. Covers cash products and revolving lines, for every day from the
    first observed row of the product to ``window.last_month`` end. Integer
    cents end to end.
    """
    raise NotImplementedError


def build_company_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Company-month rows with exactly ``PANEL_COLUMNS`` (order and dtypes).

    ``entity_kind = "company"``. Intra-group mirror rows feed only
    ``intragroup_in/out``; intra-company mirror rows feed nothing but
    ``mirror_netted_1m``. Sorted by ``PANEL_KEY``.
    """
    raise NotImplementedError


def build_group_panel(clean: CleanTables, params: Params) -> pl.DataFrame:
    """Group-month rows with exactly ``PANEL_COLUMNS``.

    ``entity_kind = "group"``, ``entity_id = group_id``. Every mirror-netted row
    is excluded from operating flows. Invoice cohorts pool the invoices of all
    members. ``swept_subsidiary`` is false and ``cash_share_of_group`` null.
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
