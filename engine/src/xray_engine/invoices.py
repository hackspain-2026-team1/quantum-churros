"""Invoices: cleaning and as-of days beyond terms for payments (AP) and collections (AR).

Every figure of month t is read at the end of t: a payment dated after t does
not exist yet, so the invoice is still open and ages until t. ``status`` and
``pending_amount`` are snapshots and only decide whether ``payment_date`` is a
real settlement. AP and AR are aggregated apart and never averaged.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import polars as pl

from .contracts import Params

# Schema of the clean invoice table (document_type == "invoice" only).
CLEAN_INVOICE_COLUMNS: dict[str, pl.DataType] = {
    "operation_id": pl.String,
    "company_id": pl.String,
    "group_id": pl.String,
    "counterparty_id": pl.String,
    "side": pl.String,  # AR (amount > 0) | AP (amount < 0)
    "issuance_date": pl.Date,
    "due_date": pl.Date,
    "settled_date": pl.Date,  # payment_date iff status == paid and pending == 0, else null
    "amount_cents": pl.Int64,  # absolute value, invoice currency
    "currency": pl.String,
    "fx_rate": pl.Float64,
    "fx_excluded": pl.Boolean,
    "terms_days": pl.Int64,  # due_date - issuance_date
    "stamped": pl.Boolean,  # ERP-stamped row: due == issuance and settled == due
}

_KEY_COLUMNS: dict[str, pl.DataType] = {
    "entity_kind": pl.String,  # group | company
    "entity_id": pl.String,
    "group_id": pl.String,
    "month": pl.Date,
    "side": pl.String,  # AP | AR
}

# One row per (entity, side, month) with at least one invoice in the window.
DBT_COLUMNS: dict[str, pl.DataType] = {
    **_KEY_COLUMNS,
    "n_all": pl.Int64,  # invoices in the window, stamped and fx-excluded included
    "n": pl.Int64,  # invoices behind the average: not stamped, with an FX rate
    "neff": pl.Float64,  # Kish effective n of the EUR weights; null when n == 0
    "amount": pl.Float64,  # EUR, sum of the weights
    "days_beyond_terms": pl.Float64,  # value-weighted; null when n == 0
    "stamped_share": pl.Float64,  # stamped rows / n_all
    "open_share": pl.Float64,  # weight still open at month end / amount; null when n == 0
}

# Counts behind the average, same rows and keys as ``DBT_COLUMNS``; every
# count is taken over the ``n`` invoices and read at month end.
EVIDENCE_COLUMNS: dict[str, pl.DataType] = {
    **_KEY_COLUMNS,
    "n": pl.Int64,
    "settled_n": pl.Int64,  # settled by month end
    "late_paid_n": pl.Int64,  # settled by month end, after due_date
    "late_paid_amount": pl.Float64,  # EUR
    "open_overdue_n": pl.Int64,  # open at month end and past due
    "open_overdue_amount": pl.Float64,  # EUR
    "zero_terms_n": pl.Int64,  # due == issuance: days beyond terms are days since issuance
    "zero_terms_open_n": pl.Int64,  # ... and open at month end: no real date on the row yet
    "aged_n": pl.Int64,  # not stamped, due in (T - 365 days, T - window_days]
    "aged_open_n": pl.Int64,  # ... and still open at month end
}

# Dataset-level facts per side, read on the cached invoices (no hygiene filter).
SETTLED_LATE_COLUMNS: dict[str, pl.DataType] = {
    "side": pl.String,
    "marked_paid_n": pl.Int64,  # status paid, nothing pending, with a payment date
    "settled_late_n": pl.Int64,  # ... and payment_date > due_date
    "settled_late_amount": pl.Float64,  # EUR; currencies outside the FX table left out
}

_INVOICE = "invoice"
_PAID = "paid"
_CANCELLED = "cancel"
_SORT_KEY = ("entity_kind", "entity_id", "side", "month")
_AS_OF_INPUTS = (
    "company_id", "group_id", "side", "due_date", "settled_date", "amount_cents", "fx_rate",
    "fx_excluded", "terms_days", "stamped",
)
# Settlement check of the evidence: invoices that left the scoring window
# within the last year. When nearly all of them are still open the ERP does
# not record payments, and open invoices say nothing about punctuality.
_AGED_DAYS = 365


def _fx_rates(params: Params) -> pl.DataFrame:
    rates = params.fx.rates
    return pl.DataFrame(
        {"currency": list(rates), "fx_rate": list(rates.values())},
        schema={"currency": pl.String, "fx_rate": pl.Float64},
    )


def clean_invoices(
    invoices: pl.DataFrame, companies: pl.DataFrame, params: Params, as_of: date
) -> pl.DataFrame:
    """Cached invoices -> ``CLEAN_INVOICE_COLUMNS``, sorted by operation_id.

    Keeps ``document_type == "invoice"`` and drops status ``cancel``, zero
    amounts and impossible dates (due or payment before issuance).
    ``settled_date = payment_date`` only when status is ``paid`` and nothing is
    pending; a payment date after ``as_of`` is an expected date and stays null.
    AR is amount > 0, AP amount < 0; ``amount_cents`` is stored as a magnitude.
    ``fx_rate`` follows the invoice currency and ``params.fx.rates``; outside
    the table the rate is null and ``fx_excluded`` true. ``group_id`` comes
    from companies. Counterparty ids are kept as they are (no zero-padding).
    """
    members = companies.select("company_id", "group_id").unique(
        subset="company_id", keep="first", maintain_order=True
    )
    # payment_date of an unpaid row is a placeholder (mostly the due date): never read
    paid_in_full = (pl.col("status") == _PAID) & (pl.col("pending_cents") == 0)
    settled = pl.when(paid_in_full & (pl.col("payment_date") <= as_of)).then(pl.col("payment_date"))
    return (
        invoices.filter(
            (pl.col("document_type") == _INVOICE)
            & pl.col("status").ne_missing(_CANCELLED)
            & (pl.col("amount_cents") != 0)
        )
        .with_columns(settled.alias("settled_date"))
        .filter(
            (pl.col("due_date") >= pl.col("issuance_date"))
            & (pl.col("settled_date").is_null() | (pl.col("settled_date") >= pl.col("issuance_date")))
        )
        .join(members, on="company_id", how="left")
        .join(_fx_rates(params), on="currency", how="left")
        .with_columns(
            pl.when(pl.col("amount_cents") > 0).then(pl.lit("AR")).otherwise(pl.lit("AP")).alias("side"),
            pl.col("amount_cents").abs(),
            pl.col("fx_rate").is_null().alias("fx_excluded"),
            (pl.col("due_date") - pl.col("issuance_date")).dt.total_days().alias("terms_days"),
            (
                (pl.col("due_date") == pl.col("issuance_date"))
                & (pl.col("settled_date") == pl.col("due_date")).fill_null(False)
            ).alias("stamped"),
        )
        .select(pl.col(name).cast(dtype) for name, dtype in CLEAN_INVOICE_COLUMNS.items())
        .sort("operation_id")
    )


def _due_between(
    invoices: pl.DataFrame, months: Sequence[date], first_day: int, last_day: int
) -> pl.DataFrame:
    # one row per (invoice, month) with first_day <= month end - due_date < last_day
    age = (pl.col("month").dt.month_end() - pl.col("due_date")).dt.total_days()
    return (
        # fixed row order: float sums do not depend on the order of the input
        invoices.sort("operation_id")
        .select(_AS_OF_INPUTS)
        .with_columns(
            pl.date_ranges(
                pl.col("due_date").dt.offset_by(f"{first_day}d").dt.truncate("1mo"),
                pl.col("due_date").dt.offset_by(f"{last_day - 1}d").dt.truncate("1mo"),
                interval="1mo",
                closed="both",
            ).alias("month")
        )
        .explode("month", empty_as_null=False)
        .filter(pl.col("month").is_in(sorted(set(months))) & (age >= first_day) & (age < last_day))
    )


def _per_entity(rows: pl.DataFrame, *aggregations: pl.Expr) -> pl.DataFrame:
    # the same aggregation over every company and over every group (members pooled)
    return pl.concat(
        rows.filter(pl.col(entity).is_not_null())
        .group_by(pl.col(entity).alias("entity_id"), "group_id", "side", "month")
        .agg(*aggregations)
        .with_columns(pl.lit(kind).alias("entity_kind"))
        for kind, entity in (("company", "company_id"), ("group", "group_id"))
    )


def _settled_by_month_end() -> pl.Expr:
    month_end = pl.col("month").dt.month_end()
    return pl.col("settled_date").is_not_null() & (pl.col("settled_date") <= month_end)


def _as_of_aggregates(invoices: pl.DataFrame, months: Sequence[date], params: Params) -> pl.DataFrame:
    low, high = params.invoices.clip_days
    month_end = pl.col("month").dt.month_end()
    settled = _settled_by_month_end()
    rows = _due_between(invoices, months, 0, params.invoices.window_days).with_columns(
        (~pl.col("stamped") & ~pl.col("fx_excluded") & pl.col("fx_rate").is_not_null()).alias("scored"),
        settled.alias("settled"),
        (pl.col("amount_cents") / 100 * pl.col("fx_rate")).alias("weight"),
        pl.when(settled)
        .then(pl.col("settled_date") - pl.col("due_date"))
        .otherwise(month_end - pl.col("due_date"))
        .dt.total_days()
        .cast(pl.Float64)
        .clip(low, high)
        .alias("days"),
    )
    scored, weight = pl.col("scored"), pl.col("weight")
    late_paid = pl.col("settled") & (pl.col("settled_date") > pl.col("due_date"))
    open_overdue = ~pl.col("settled") & (pl.col("due_date") < month_end)
    zero_terms = pl.col("terms_days") == 0

    def count(flag: pl.Expr) -> pl.Expr:
        return (scored & flag).sum().cast(pl.Int64)

    def value(flag: pl.Expr) -> pl.Expr:
        return weight.filter(scored & flag).sum()

    def measured(expr: pl.Expr) -> pl.Expr:
        # an average over no invoice is not observable: null, never 0
        return pl.when(pl.col("n") > 0).then(expr)

    return (
        _per_entity(
            rows,
            pl.len().cast(pl.Int64).alias("n_all"),
            scored.sum().cast(pl.Int64).alias("n"),
            pl.col("stamped").sum().alias("stamped_n"),
            weight.filter(scored).sum().alias("amount"),
            (weight * pl.col("days")).filter(scored).sum().alias("weighted_days"),
            (weight * weight).filter(scored).sum().alias("squared_weights"),
            value(~pl.col("settled")).alias("open_amount"),
            count(pl.col("settled")).alias("settled_n"),
            count(late_paid).alias("late_paid_n"),
            value(late_paid).alias("late_paid_amount"),
            count(open_overdue).alias("open_overdue_n"),
            value(open_overdue).alias("open_overdue_amount"),
            count(zero_terms).alias("zero_terms_n"),
            count(zero_terms & ~pl.col("settled")).alias("zero_terms_open_n"),
        )
        .with_columns(
            measured(pl.col("weighted_days") / pl.col("amount")).alias("days_beyond_terms"),
            measured(pl.col("amount") ** 2 / pl.col("squared_weights")).alias("neff"),
            measured(pl.col("open_amount") / pl.col("amount")).alias("open_share"),
            (pl.col("stamped_n") / pl.col("n_all")).alias("stamped_share"),
        )
        .sort(_SORT_KEY)
    )


def days_beyond_terms_as_of(
    invoices: pl.DataFrame, months: Sequence[date], params: Params
) -> pl.DataFrame:
    """As-of aggregates per company-month and group-month, as ``DBT_COLUMNS``.

    ``invoices`` follows ``CLEAN_INVOICE_COLUMNS``; ``months`` are first days of
    complete months. For month t with month end T, per entity and side:
      window: ``due_date`` in (T - ``invoices.window_days``, T];
      stamped rows only count in ``n_all`` and ``stamped_share``;
      fx-excluded rows only count in ``n_all``;
      every other row: ``days = settled_date - due_date`` when
      ``settled_date <= T``, else ``T - due_date`` (open, still ageing), clipped
      to ``invoices.clip_days``; weight ``w = amount_cents / 100 * fx_rate``;
      ``days_beyond_terms = sum(w * days) / sum(w)``; ``neff = sum(w)^2 /
      sum(w^2)``; ``open_share`` = weight with ``settled_date`` null or > T.
    Group rows pool the invoices of every member company (``entity_id =
    group_id``). Nothing dated after T is read, so month t does not change
    when later invoices or payments arrive. Sorted by (entity_kind, entity_id,
    side, month).
    """
    frame = _as_of_aggregates(invoices, months, params)
    return frame.select(pl.col(name).cast(dtype) for name, dtype in DBT_COLUMNS.items())


def window_evidence_as_of(
    invoices: pl.DataFrame, months: Sequence[date], params: Params
) -> pl.DataFrame:
    """Counts behind ``days_beyond_terms_as_of``, as ``EVIDENCE_COLUMNS``.

    Same window, rows, keys and order. Over the ``n`` invoices behind the
    average, read at month end T: ``settled_n`` settled by T, ``late_paid_*``
    settled by T after the due date, ``open_overdue_*`` not settled by T and
    due before T. Amounts are EUR. A payment dated after T is not known yet:
    that invoice is open at T, never late-paid. ``zero_terms_*`` count rows
    with ``due_date == issuance_date``: the ERP holds no payment terms for
    them, so their days run from issuance. ``aged_*`` look at the not stamped
    invoices due in (T - 365 days, T - ``window_days``]: an entity with nearly
    all of them open at T has an ERP that does not record payments.
    """
    older = _due_between(
        invoices.filter(~pl.col("stamped")), months, params.invoices.window_days, _AGED_DAYS
    )
    aged = _per_entity(
        older,
        pl.len().cast(pl.Int64).alias("aged_n"),
        (~_settled_by_month_end()).sum().cast(pl.Int64).alias("aged_open_n"),
    ).drop("group_id")
    frame = (
        _as_of_aggregates(invoices, months, params)
        .join(aged, on=_SORT_KEY, how="left")
        .with_columns(pl.col("aged_n", "aged_open_n").fill_null(0))
        .sort(_SORT_KEY)
    )
    return frame.select(pl.col(name).cast(dtype) for name, dtype in EVIDENCE_COLUMNS.items())


def settled_late_summary(invoices: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Invoices marked paid and settled after the due date, as ``SETTLED_LATE_COLUMNS``.

    ``invoices`` follows ``io.CACHE_SCHEMAS["invoices"]``. A fact about the
    whole extraction (one row per side, AP then AR), for the receipt; no score
    reads it. Expected payment dates are counted as they are written.
    """
    late = pl.col("payment_date") > pl.col("due_date")
    frame = (
        invoices.filter(
            (pl.col("document_type") == _INVOICE)
            & (pl.col("amount_cents") != 0)
            & (pl.col("status") == _PAID)
            & (pl.col("pending_cents") == 0)
            & pl.col("payment_date").is_not_null()
        )
        .join(_fx_rates(params), on="currency", how="left")
        .with_columns(
            pl.when(pl.col("amount_cents") > 0).then(pl.lit("AR")).otherwise(pl.lit("AP")).alias("side"),
            (pl.col("amount_cents").abs() / 100 * pl.col("fx_rate")).alias("amount"),
        )
        .sort("operation_id")
        .group_by("side")
        .agg(
            pl.len().alias("marked_paid_n"),
            late.sum().alias("settled_late_n"),
            pl.col("amount").filter(late).sum().alias("settled_late_amount"),
        )
        .sort("side")
    )
    return frame.select(pl.col(name).cast(dtype) for name, dtype in SETTLED_LATE_COLUMNS.items())


def invoice_states_as_of(invoices: pl.DataFrame, last_month: date) -> pl.DataFrame:
    """Open and overdue invoice stock at every month end, without look-ahead.

    ``invoices`` follows ``CLEAN_INVOICE_COLUMNS``. An invoice is open at the
    end of month m when it was issued by then and ``settled_date`` is null or
    later than that month end; it is overdue when open and past due. Returns
    one row per (company_id, side, currency, month) with ``open_cents``,
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
        .with_columns(pl.col("month").dt.month_end().alias("month_end"))
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
