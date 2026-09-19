"""Row-level cleaning, in the binding order a -> e.

a. currency via product_id + static FX      (``assign_currency``)
b. mirror netting, all categories           (``net_mirror_pairs``)
c. recovery of the ``-`` category           (``recover_dash``)
d. operating / debt flow flags              (``classify_flows``)
e. invoices as-of                           (``invoices_as_of``)

DataFrame in, DataFrame out. No function reads files or looks at other groups:
every step is a row-wise rule or a join inside one ``group_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl

from .contracts import Params
from .io import Tables, Window

# Columns added to the cached transactions, in order.
CLEAN_TRANSACTION_COLUMNS: dict[str, pl.DataType] = {
    "group_id": pl.String,
    "currency": pl.String,  # from the product; null for an unknown product
    "product_type": pl.String,  # checking, card, lineofcredit, loan, ...
    "product_family": pl.String,  # banking | debt
    "fx_rate": pl.Float64,  # EUR per unit; null when the currency is outside the FX table
    "fx_excluded": pl.Boolean,  # true: counts rows, never value
    "mirror_id": pl.String,  # transaction_id of the negative leg; null when not netted
    "mirror_scope": pl.String,  # intra_company | intra_group | null
    "label": pl.String,  # category, or the recovered label for "-" rows
    "label_rule": pl.String,  # DashRule.id that fired; null otherwise
    "is_op_inflow": pl.Boolean,
    "is_op_outflow": pl.Boolean,
    "is_debt_service": pl.Boolean,
    "is_debt_drawdown": pl.Boolean,
}

# Schema of the as-of invoice table (document_type == "invoice" only).
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
    "stamped": pl.Boolean,  # due == issuance and settled in (null, due)
}

# Union of banking and debt products, one row per product_id.
PRODUCT_COLUMNS: dict[str, pl.DataType] = {
    "product_id": pl.String,
    "company_id": pl.String,
    "group_id": pl.String,
    "product_type": pl.String,
    "product_family": pl.String,
    "bank_name": pl.String,
    "service": pl.String,
    "currency": pl.String,
    "created_at": pl.Date,
    "granted_cents": pl.Int64,  # debt products only
    "outstanding_cents": pl.Int64,  # debt products only
}


@dataclass(frozen=True)
class CleanTables:
    transactions: pl.DataFrame  # CACHE_SCHEMAS["transactions"] + CLEAN_TRANSACTION_COLUMNS
    invoices: pl.DataFrame  # CLEAN_INVOICE_COLUMNS
    products: pl.DataFrame  # PRODUCT_COLUMNS
    balances: pl.DataFrame  # CACHE_SCHEMAS["balances"] + group_id, currency, product_type, fx_rate
    companies: pl.DataFrame
    groups: pl.DataFrame
    debt_schedule_config: pl.DataFrame
    dataset_hash: str
    window: Window


def build_products(tables: Tables) -> pl.DataFrame:
    """Union of banking_products and debt_products as ``PRODUCT_COLUMNS``.

    ``group_id`` comes from companies. Sorted by product_id.
    """
    raise NotImplementedError


def assign_currency(
    transactions: pl.DataFrame, products: pl.DataFrame, params: Params
) -> pl.DataFrame:
    """Step a. Adds group_id, currency, product_type, product_family, fx_rate, fx_excluded.

    Currency is inherited from ``product_id``; ``fx_rate`` comes from
    ``params.fx.rates``. Unknown product or currency outside the table:
    ``fx_rate`` null and ``fx_excluded`` true. ``exchange_rate`` is never used.
    Row count is unchanged.
    """
    raise NotImplementedError


def net_mirror_pairs(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Step b. Adds mirror_id and mirror_scope; runs before any category logic.

    Key (group_id, currency, |amount_cents|, month); legs have opposite sign
    and different product_id. One rank-join pass per ``params.mirror.day_offsets``
    (0, +1, -1, +2, -2 days between the negative and the positive leg): inside
    (key, date, sign) rows are ranked by transaction_id and equal ranks match,
    so pairing is 1:1 and independent of row order. Matched rows leave the pool
    before the next pass. Scope is intra_company when both legs share
    company_id, else intra_group. No amount floor. Row count is unchanged.
    """
    raise NotImplementedError


def recover_dash(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Step c. Adds label and label_rule.

    Only rows with category "-" that are not mirror-netted are tested, against
    ``params.dash_rules`` in order (first match wins): case-insensitive regex on
    the description with newlines as spaces, ``exclude`` vetoes, ``sign`` must
    agree with the amount. Other rows keep ``label = category``.
    """
    raise NotImplementedError


def classify_flows(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Step d. Adds the four flow flags from ``label`` and the sign of the amount.

    Mirror-netted and fx-excluded rows are never flagged. Revolving credit
    lines are operating accounts: their rows are classified like any other.
    ``interest_charge`` is both operating outflow and debt service.
    """
    raise NotImplementedError


def invoices_as_of(
    invoices: pl.DataFrame, companies: pl.DataFrame, params: Params, as_of: date
) -> pl.DataFrame:
    """Step e. Cached invoices -> ``CLEAN_INVOICE_COLUMNS``.

    Keeps ``document_type == "invoice"`` and drops status ``cancel``, zero
    amounts and impossible dates (due or payment before issuance). A payment
    date after ``as_of`` is an expected date: ``settled_date`` stays null.
    ``status`` and ``pending_amount`` are snapshots and are only used to decide
    whether ``payment_date`` is a real settlement.
    """
    raise NotImplementedError


def clean(tables: Tables, params: Params) -> CleanTables:
    """Runs a -> e and returns ``CleanTables``. Deterministic row order (primary keys)."""
    raise NotImplementedError
