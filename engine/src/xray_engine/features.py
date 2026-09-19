"""Frame helpers shared by the panel: the month grid and the as-of invoice stock."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl


def _required(input_dir: Path, name: str) -> Path:
    path = input_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Required dataset file not found: {path}")
    return path


def _monthly_grid(
    companies: pl.DataFrame, minimum: object, maximum: object
) -> pl.DataFrame:
    months = pl.DataFrame(
        {
            "month": pl.date_range(
                minimum,
                maximum,
                interval="1mo",
                eager=True,
            )
        }
    )
    return companies.join(months, how="cross")


def invoice_states_as_of(invoices: pl.DataFrame, last_month: date) -> pl.DataFrame:
    """Open and overdue invoice stock at every month end, without look-ahead.

    ``invoices`` follows ``cleaning.CLEAN_INVOICE_COLUMNS``. An invoice is open
    at the end of month m when it was issued by then and ``settled_date`` is
    null or later than that month end; it is overdue when open and past due.
    Returns one row per (company_id, side, currency, month) with ``open_cents``,
    ``overdue_cents``, ``open_n`` and ``overdue_n``; months up to ``last_month``.
    """
    # an invoice can only be open from its issuance month to the month before
    # it settles, so only those months are materialised
    last_open = (
        pl.when(pl.col("settled_date").is_null())
        .then(pl.lit(last_month))
        .otherwise(
            pl.min_horizontal(
                pl.col("settled_date").dt.truncate("1mo").dt.offset_by("-1mo"),
                pl.lit(last_month),
            )
        )
    )
    return (
        invoices.with_columns(
            pl.col("issuance_date").dt.truncate("1mo").alias("issuance_month"),
            last_open.alias("last_open_month"),
        )
        .filter(pl.col("issuance_month") <= pl.col("last_open_month"))
        .with_columns(
            pl.date_ranges(
                pl.col("issuance_month"),
                pl.col("last_open_month"),
                interval="1mo",
                closed="both",
            ).alias("month")
        )
        .explode("month", empty_as_null=False)
        .with_columns(
            pl.col("month").dt.offset_by("1mo").dt.offset_by("-1d").alias("month_end")
        )
        .with_columns((pl.col("due_date") < pl.col("month_end")).alias("is_overdue"))
        .group_by("company_id", "side", "currency", "month")
        .agg(
            pl.col("amount_cents").sum().alias("open_cents"),
            pl.col("amount_cents").filter(pl.col("is_overdue")).sum().alias("overdue_cents"),
            pl.len().cast(pl.Int64).alias("open_n"),
            pl.col("is_overdue").sum().cast(pl.Int64).alias("overdue_n"),
        )
        .sort("company_id", "side", "currency", "month")
    )
