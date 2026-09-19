"""Row-level cleaning, in the binding order a -> d.

a. currency via product_id + static FX      (``assign_currency``)
b. mirror netting, then reversals           (``net_mirror_pairs``, ``net_reversals``)
c. one flow class per row                   (``classify_flows``)
d. invoices                                 (``invoices.clean_invoices``)

DataFrame in, DataFrame out. No function reads files or looks at other groups:
every step is a row-wise rule or a join inside one ``group_id``. No step drops
a row: rows that may not feed value aggregates are flagged, so row counts stay
whole. Every pairing rule only joins rows of the same calendar month, so month
t never changes when later rows arrive.

Mirrors go first: an equal opposite row on another account of the group
explains a movement better than one on the same account (a funded payment is
a transfer in plus a real payment out, not a booking and its undo). Both
orders net almost the same rows; this one keeps sweeps labelled as sweeps.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from .contracts import Params
from .invoices import CLEAN_INVOICE_COLUMNS, clean_invoices
from .io import Tables, Window

_ROW = "_row"  # position in the input frame: results are attached by it, never by a wide join
_ORDER = "_order"  # position of a pool row in transaction_id order
_PAIR_COLUMNS = ("transaction_id", "product_id", "company_id", "date", "month", "amount_cents")

# Columns added to the cached transactions, in order.
CLEAN_TRANSACTION_COLUMNS: dict[str, pl.DataType] = {
    "group_id": pl.String,
    "currency": pl.String,  # from the product; null for an orphan product
    "product_type": pl.String,  # checking, card, lineofcredit, loan, ...
    "product_family": pl.String,  # banking | debt
    "fx_rate": pl.Float64,  # EUR per unit; null when the currency is outside the FX table
    "fx_excluded": pl.Boolean,  # true: counts rows, never value
    "orphan_product": pl.Boolean,  # product_id absent from both product files
    "reversal_id": pl.String,  # transaction_id of the negative leg; null when not a reversal
    "mirror_id": pl.String,  # transaction_id of the negative leg; null when not netted
    "mirror_scope": pl.String,  # intra_company | intra_group | null
    "flow_class": pl.String,  # one of contracts.FLOW_CLASSES
    "label": pl.String,  # category, or the label of the narrative rule that fired
    "label_rule": pl.String,  # DashRule.id that fired; null otherwise
    "counterparty_key": pl.String,  # counterparty_id, else the single COUNTERPARTY_n token of the description
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


def _company_groups(companies: pl.DataFrame) -> pl.DataFrame:
    return companies.select("company_id", "group_id").unique("company_id", keep="first", maintain_order=True)


def _fx_rates(params: Params) -> pl.DataFrame:
    rates = params.fx.rates
    return pl.DataFrame(
        {"currency": list(rates), "fx_rate": [float(rate) for rate in rates.values()]},
        schema={"currency": pl.String, "fx_rate": pl.Float64},
    )


def _greedy_other_product(left: pl.DataFrame, right: pl.DataFrame, bucket: list[str]) -> pl.DataFrame:
    """Buckets holding a product on both sides: each negative, in transaction_id
    order, takes the first free positive of another product. One negative per
    bucket and round, so the result equals the row-by-row greedy."""
    edges = (
        left.join(right, on=bucket, suffix="_pos")
        .filter(pl.col("product_id") != pl.col("product_id_pos"))
        .select(pl.col(_ORDER).min().over(bucket).alias("bucket"), _ORDER, f"{_ORDER}_pos")
    )
    found = []
    while not edges.is_empty():
        first = edges.filter(pl.col(_ORDER) == pl.col(_ORDER).min().over("bucket"))
        taken = first.group_by(_ORDER).agg(pl.col(f"{_ORDER}_pos").min())
        found.append(taken)
        edges = edges.filter(
            ~pl.col(_ORDER).is_in(taken[_ORDER].implode())
            & ~pl.col(f"{_ORDER}_pos").is_in(taken[f"{_ORDER}_pos"].implode())
        )
    return pl.concat(found) if found else edges.select(_ORDER, f"{_ORDER}_pos")


def _pair_rows(
    pool: pl.DataFrame, keys: list[str], max_gap: int, *, free_gap: int,
    bridge_weekdays: tuple[int, ...], other_product: bool,
) -> pl.DataFrame:
    """1:1 pairs of opposite rows with equal ``|amount_cents|`` inside one month.

    ``pool``: _row, transaction_id, product_id, company_id, date, month,
    amount_cents and ``keys``. One pass per gap (date of the positive leg minus
    date of the negative leg) in the order 0, +1, -1, +2, -2, ...; matched rows
    leave the pool. Inside a pass each negative, in transaction_id order, takes
    the first free positive of its (keys, amount, month) on the target date:
    equal ranks match, and with ``other_product`` a row skips its own product.
    Beyond ``free_gap`` the earlier leg must fall on one of ``bridge_weekdays``.
    Independent of row order. Returns _row, _row_pos, pair_id, scope.
    """
    keys = list(dict.fromkeys([*keys, "abs_cents", "month"]))
    bucket = [*keys, "target"]
    pool = pool.with_columns(
        pl.col("amount_cents").abs().alias("abs_cents"), (pl.col("amount_cents") < 0).alias("negative")
    )
    both_signs = pool.group_by(keys).agg(pl.col("negative").n_unique().alias("signs")).filter(pl.col("signs") == 2)
    pool = pool.join(both_signs.select(keys), on=keys, how="semi")
    pool = pool.sort("transaction_id", _ROW).with_row_index(_ORDER)
    columns = list(dict.fromkeys([_ORDER, "product_id", "date", *keys]))
    negatives = pool.filter(pl.col("negative")).select(columns)
    positives = pool.filter(~pl.col("negative")).select(columns)
    rank = pl.int_range(pl.len()).over(bucket).alias("rank")
    on_bridge_day = (pl.col("date").dt.weekday() - 1).is_in(list(bridge_weekdays))  # date.weekday()
    found = []
    for gap in [0, *(sign * days for days in range(1, max_gap + 1) for sign in (1, -1))]:
        left, right = negatives, positives
        if abs(gap) > free_gap:  # the earlier leg decides
            left, right = (left.filter(on_bridge_day), right) if gap > 0 else (left, right.filter(on_bridge_day))
        left = left.with_columns((pl.col("date") + pl.duration(days=gap)).alias("target")).drop("date")
        right = right.rename({"date": "target"})
        contested = []
        if other_product:
            shared = left.join(right, on=[*bucket, "product_id"], how="semi").select(bucket).unique()
            contested.append(_greedy_other_product(
                left.join(shared, on=bucket, how="semi"), right.join(shared, on=bucket, how="semi"), bucket
            ))
            left = left.join(shared, on=bucket, how="anti")
        ranked = left.with_columns(rank).join(right.with_columns(rank), on=[*bucket, "rank"], suffix="_pos")
        pairs = pl.concat([ranked.select(_ORDER, f"{_ORDER}_pos"), *contested])
        if pairs.is_empty():
            continue
        found.append(pairs)
        negatives = negatives.filter(~pl.col(_ORDER).is_in(pairs[_ORDER].implode()))
        positives = positives.filter(~pl.col(_ORDER).is_in(pairs[f"{_ORDER}_pos"].implode()))
    if not found:
        index = pl.get_index_type()
        return pl.DataFrame(schema={_ROW: index, f"{_ROW}_pos": index, "pair_id": pl.String, "scope": pl.String})
    legs = pool.select(_ORDER, _ROW, "transaction_id", "company_id")
    return (
        pl.concat(found)
        .join(legs, on=_ORDER)
        .join(legs.select(pl.all().name.suffix("_pos")), on=f"{_ORDER}_pos")
        .select(
            _ROW, f"{_ROW}_pos", pl.col("transaction_id").alias("pair_id"),
            pl.when(pl.col("company_id") == pl.col("company_id_pos")).then(pl.lit("intra_company"))
            .otherwise(pl.lit("intra_group")).alias("scope"),
        )
    )


def _attach(transactions: pl.DataFrame, pairs: pl.DataFrame, names: dict[str, str]) -> pl.DataFrame:
    """Both legs of every pair get the pair columns, renamed by ``names``; other rows get nulls."""
    legs = pl.concat([pairs.select(_ROW, *names), pairs.select(pl.col(f"{_ROW}_pos").alias(_ROW), *names)])
    rows = pl.select(pl.int_range(transactions.height, dtype=pl.get_index_type()).alias(_ROW))
    added = rows.join(legs, on=_ROW, how="left", maintain_order="left").select(
        pl.col(source).alias(target) for source, target in names.items()
    )
    return transactions.hstack(added)


def _free(transactions: pl.DataFrame, taken_by: str) -> pl.Expr:
    """Rows that are not a leg of the other pairing rule (when it already ran)."""
    return pl.col(taken_by).is_null() if taken_by in transactions.columns else pl.lit(True)


def build_products(tables: Tables) -> pl.DataFrame:
    """Union of banking_products and debt_products as ``PRODUCT_COLUMNS``.

    ``group_id`` comes from companies. Sorted by product_id.
    """
    empty = pl.lit(None, dtype=pl.Int64)
    banking = tables.banking_products.select(
        "product_id", "company_id", pl.col("type").alias("product_type"),
        pl.lit("banking").alias("product_family"), "bank_name", "service", "currency", "created_at",
        empty.alias("granted_cents"), empty.alias("outstanding_cents"),
    )
    debt = tables.debt_products.select(
        "product_id", "company_id", pl.col("type").alias("product_type"),
        pl.lit("debt").alias("product_family"), "bank_name", "service", "currency", "created_at",
        "granted_cents", "outstanding_cents",
    )
    # a product listed twice keeps its debt row: it is the one holding the limit
    products = pl.concat([debt, banking]).unique("product_id", keep="first", maintain_order=True)
    products = products.with_columns(pl.col("currency").str.strip_chars().str.to_uppercase())
    products = products.join(_company_groups(tables.companies), on="company_id", how="left")
    return products.select(list(PRODUCT_COLUMNS)).sort("product_id")


def assign_currency(
    transactions: pl.DataFrame, products: pl.DataFrame, companies: pl.DataFrame, params: Params
) -> pl.DataFrame:
    """Step a. Adds group_id, currency, product_type, product_family, fx_rate,
    fx_excluded, orphan_product.

    ``group_id`` comes from ``company_id``. Currency is inherited from
    ``product_id``; ``fx_rate`` comes from ``params.fx.rates``. A product absent
    from both product files is an orphan: currency null. Orphan rows and rows
    in a currency outside the table get ``fx_rate`` null and ``fx_excluded``
    true: they count as rows and never as value. ``exchange_rate`` is never
    used. Row count is unchanged.
    """
    lookup = products.select(
        "product_id", "currency", "product_type", "product_family",
        pl.col("group_id").alias("product_group_id"),
    ).unique("product_id", keep="first", maintain_order=True)
    added = (
        transactions.select("company_id", "product_id")
        .join(_company_groups(companies), on="company_id", how="left", maintain_order="left")
        .join(lookup, on="product_id", how="left", maintain_order="left")
        .join(_fx_rates(params), on="currency", how="left", maintain_order="left")
        .select(
            pl.coalesce("group_id", "product_group_id").alias("group_id"),
            "currency", "product_type", "product_family", "fx_rate",
            pl.col("fx_rate").is_null().alias("fx_excluded"),
            pl.col("product_family").is_null().alias("orphan_product"),
        )
    )
    return transactions.hstack(added)


def net_reversals(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Step b2. Adds reversal_id: a booking and its undo on the same account.

    Candidates: rows outside mirror pairs (``clean`` nets the mirrors first).
    Pair: same product_id, opposite sign, equal ``|amount_cents|`` (not zero),
    same calendar month, date gap <= ``params.mirror.reversal_max_day_gap``. No
    amount floor and no FX rate needed. Same pass recipe as ``net_mirror_pairs``
    with the gaps 0, +1, -1, ...; pairing is 1:1. Row count is unchanged.
    """
    gap = params.mirror.reversal_max_day_gap
    pool = (
        transactions.select(*_PAIR_COLUMNS, _free(transactions, "mirror_id").alias("free"))
        .with_row_index(_ROW)
        .filter(pl.col("free") & (pl.col("amount_cents") != 0))
    )
    pairs = _pair_rows(pool, ["product_id"], gap, free_gap=gap, bridge_weekdays=(), other_product=False)
    return _attach(transactions, pairs, {"pair_id": "reversal_id"})


def net_mirror_pairs(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Step b1. Adds mirror_id and mirror_scope; runs before any category logic.

    Candidates: rows outside reversal pairs (none yet when called from
    ``clean``), not ``fx_excluded``, with
    ``|amount_cents| / 100 * fx_rate >= params.mirror.min_amount_eur``.
    Pair: same group_id, same account currency, equal ``|amount_cents|``,
    opposite sign, different product_id, same calendar month, and a date gap
    <= ``max_day_gap``, or <= ``weekend_bridge_day_gap`` when the earlier leg
    falls on one of ``weekend_bridge_weekdays``. ``category`` is never a
    criterion.
    Nearest date first, 1:1, independent of row order: one pass per gap between
    the negative and the positive leg in the order 0, +1, -1, +2, -2, +3, -3
    (up to the bridge gap); inside a pass rows still in the pool are ranked by
    transaction_id within (group_id, currency, |amount_cents|, date, sign) and
    equal ranks match; a row never matches its own product: where an account
    sits on both sides, each negative takes the first free positive of another
    account; matched rows leave the pool. Scope is intra_company when both
    legs share company_id, else intra_group. Row count is unchanged.
    """
    mirror = params.mirror
    euros = pl.col("amount_cents").abs() / 100 * pl.col("fx_rate")
    pool = (
        transactions.select(
            *_PAIR_COLUMNS, "group_id", "currency", "fx_rate", "fx_excluded",
            _free(transactions, "reversal_id").alias("free"),
        )
        .with_row_index(_ROW)
        .filter(
            pl.col("free") & ~pl.col("fx_excluded") & (pl.col("amount_cents") != 0)
            & (euros >= mirror.min_amount_eur)
        )
    )
    pairs = _pair_rows(
        pool, ["group_id", "currency"], max(mirror.max_day_gap, mirror.weekend_bridge_day_gap),
        free_gap=mirror.max_day_gap, bridge_weekdays=mirror.weekend_bridge_weekdays, other_product=True,
    )
    return _attach(transactions, pairs, {"pair_id": "mirror_id", "scope": "mirror_scope"})


def classify_flows(transactions: pl.DataFrame, params: Params) -> pl.DataFrame:
    """Step c. Adds flow_class, label, label_rule and counterparty_key.

    First rule that applies:
      1. leg of a reversal or of a mirror pair                  -> internal
      2. category in ``flows.internal_categories``              -> internal
      3. category == ``flows.dash_category``: the first of ``params.dash_rules``
         that matches (case-insensitive regex search on the description with
         newlines as spaces; ``exclude`` vetoes; ``sign`` must agree with the
         amount) gives its ``flow_class``, ``label`` and ``label_rule``;
         without a match the sign decides: amount > 0 -> op_in, < 0 -> op_out
      4. amount < 0 and category in ``debt_service_categories`` -> debt_service
      5. amount > 0 and category in ``op_inflow_categories``    -> op_in
      6. amount < 0 and category in ``op_outflow_categories``   -> op_out
      7. category in ``financial_categories``                   -> financial
      8. anything else (refunds, withdrawals, zero amounts)     -> other
    ``interest_charge`` is debt service only. Revolving credit lines are
    operating accounts: their rows are classified like any other. Rows with
    ``fx_excluded`` get a class too; value aggregates skip them downstream.
    ``counterparty_key`` is ``counterparty_id`` when present, else the
    ``COUNTERPARTY_n`` token of the description when it names exactly one
    (several names are a remittance); ids are never zero-padded. ``label`` is
    the category except for rule matches.
    """
    flows = params.flows
    rows = transactions.select(
        "amount_cents", "description", "counterparty_id",
        pl.when(pl.col("category").str.len_bytes() > 0).then(pl.col("category"))
        .otherwise(pl.lit(flows.dash_category)).alias("category"),
        (pl.col("reversal_id").is_not_null() | pl.col("mirror_id").is_not_null()).alias("netted"),
    ).with_row_index(_ROW)
    cents, category = pl.col("amount_cents"), pl.col("category")
    dash = category == flows.dash_category

    # narrative rules only read the "-" rows that reach them
    flat = pl.col("description").fill_null("").str.replace_all(r"\s+", " ").str.strip_chars()
    candidates = rows.filter(dash & ~pl.col("netted") & (cents != 0)).select(_ROW, "amount_cents", flat)
    hits = []
    for rule in params.dash_rules:
        hit = pl.col("description").str.contains(f"(?i:{rule.pattern})")
        if rule.exclude:
            hit = hit & ~pl.col("description").str.contains(f"(?i:{rule.exclude})")
        if rule.sign != "any":
            hit = hit & ((cents < 0) if rule.sign == "negative" else (cents > 0))
        hits.append(pl.when(hit).then(pl.lit(rule.id)))
    fired = candidates.select(_ROW, pl.coalesce(hits or [pl.lit(None, dtype=pl.String)]).alias("label_rule"))
    rule_ids = [rule.id for rule in params.dash_rules]
    rule_of = pl.col("label_rule")
    rows = rows.join(fired.drop_nulls("label_rule"), on=_ROW, how="left", maintain_order="left").with_columns(
        rule_of.replace_strict(rule_ids, [rule.flow_class for rule in params.dash_rules],
                               default=None, return_dtype=pl.String).alias("rule_class"),
        rule_of.replace_strict(rule_ids, [rule.label for rule in params.dash_rules],
                               default=None, return_dtype=pl.String).alias("rule_label"),
    )

    flow_class = (
        pl.when(pl.col("netted") | category.is_in(flows.internal_categories)).then(pl.lit("internal"))
        .when(dash & pl.col("rule_class").is_not_null()).then(pl.col("rule_class"))
        .when(dash & (cents > 0)).then(pl.lit("op_in"))
        .when(dash & (cents < 0)).then(pl.lit("op_out"))
        .when(dash).then(pl.lit("other"))
        .when((cents < 0) & category.is_in(flows.debt_service_categories)).then(pl.lit("debt_service"))
        .when((cents > 0) & category.is_in(flows.op_inflow_categories)).then(pl.lit("op_in"))
        .when((cents < 0) & category.is_in(flows.op_outflow_categories)).then(pl.lit("op_out"))
        .when(category.is_in(flows.financial_categories)).then(pl.lit("financial"))
        .otherwise(pl.lit("other"))
    )
    tokens = pl.col("description").str.extract_all(r"COUNTERPARTY_\d+")
    single_token = pl.when(tokens.list.n_unique() == 1).then(tokens.list.first())  # repeats are one name
    added = rows.select(
        flow_class.alias("flow_class"),
        pl.coalesce("rule_label", "category").alias("label"),
        "label_rule",
        pl.coalesce("counterparty_id", single_token).alias("counterparty_key"),
    )
    return transactions.hstack(added)


def clean(tables: Tables, params: Params) -> CleanTables:
    """Runs a -> d and returns ``CleanTables``. Deterministic row order (primary keys).

    Invoices go through ``invoices.clean_invoices`` with ``as_of =
    tables.window.as_of``. Balances gain group_id, currency, product_type and
    fx_rate from the product.
    """
    products = build_products(tables)
    transactions = assign_currency(tables.transactions, products, tables.companies, params)
    transactions = net_mirror_pairs(transactions, params)
    transactions = net_reversals(transactions, params)
    transactions = classify_flows(transactions, params)
    transactions = transactions.select([*tables.transactions.columns, *CLEAN_TRANSACTION_COLUMNS])
    if not transactions["transaction_id"].is_sorted():
        transactions = transactions.sort("transaction_id")
    lookup = products.select(
        "product_id", "currency", "product_type", pl.col("group_id").alias("product_group_id")
    )
    balances = (
        tables.balances.join(lookup, on="product_id", how="left", maintain_order="left")
        .join(_company_groups(tables.companies), on="company_id", how="left", maintain_order="left")
        .join(_fx_rates(params), on="currency", how="left", maintain_order="left")
        .select(
            *tables.balances.columns, pl.coalesce("product_group_id", "group_id").alias("group_id"),
            "currency", "product_type", "fx_rate",
        )
    )
    return CleanTables(
        transactions=transactions,
        invoices=clean_invoices(tables.invoices, tables.companies, params, tables.window.as_of),
        products=products,
        balances=balances,
        companies=tables.companies,
        groups=tables.groups,
        debt_schedule_config=tables.debt_schedule_config,
        dataset_hash=tables.dataset_hash,
        window=tables.window,
    )


__all__ = [
    "CLEAN_INVOICE_COLUMNS",
    "CLEAN_TRANSACTION_COLUMNS",
    "PRODUCT_COLUMNS",
    "CleanTables",
    "assign_currency",
    "build_products",
    "classify_flows",
    "clean",
    "net_mirror_pairs",
    "net_reversals",
]
