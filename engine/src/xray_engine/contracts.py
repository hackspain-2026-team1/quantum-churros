"""X-Ray engine v2 contracts.

Single source of truth for every structure shared between modules:

- ``Params`` (frozen reference parameters, loaded by ``params.py``)
- ``PanelRow`` / ``PANEL_COLUMNS`` (one entity-month, produced by ``panel.py``)
- ``PillarResult`` / ``ScoreParts`` / ``DeltaParts`` / ``Trajectory`` (pure core)
- ``Alert``, ``ProfileAttribute`` / ``ProfileCard``
- ``EntitySnapshot`` / ``SNAPSHOT_SCHEMA`` (one row of ``scores.parquet``)

Conventions: money is EUR ``float`` derived from Int64 cents; outflows, debt
service, drawn balances and limits are positive magnitudes; ``month`` is the
first day of a complete calendar month; shares are in [0, 1]; ``None`` means
"not observable", never zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields
from datetime import date
from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, Field

ENGINE_VERSION = "engine-v2"
FEATURE_VERSION = "panel-v2"

EntityKind = Literal["group", "company"]
Direction = Literal["improving", "stable", "deteriorating"]
Nature = Literal["structural", "shock_pending", "bump"]
AlertKind = Literal[
    "deterioration_structural",
    "improvement_structural",
    "level_critical",
    "cap_fired",
    "stale_feed",
]
AlertState = Literal["fired", "suppressed", "abstained"]

# Order is part of the contract: branches, structs and drivers follow it.
PILLAR_KEYS: tuple[str, ...] = (
    "liquidity",
    "payments",
    "collections",
    "activity",
    "debt",
)
PILLAR_LABELS: dict[str, str] = {
    "liquidity": "Liquidez",
    "payments": "Pagos a proveedores",
    "collections": "Cobros de clientes",
    "activity": "Actividad",
    "debt": "Deuda",
}
ANCHOR_KEYS: tuple[str, ...] = (
    "liquidity",
    "payments",
    "collections",
    "activity",
    "debt_dscr",
    "debt_utilisation",
)
CAP_KEYS: tuple[str, ...] = ("negative_liquidity", "lines_fully_drawn", "weak_pillar")
BRANCH_NONE = "none"

# Gates a pillar may report (PillarResult.gates). A gate explains why a score
# is missing or how it was obtained; it never changes the arithmetic by itself.
PILLAR_GATES: tuple[str, ...] = (
    "inherited_from_group",
    "no_cash_anchor",
    "no_outflow",
    "no_invoices",
    "invoice_burn_in",
    "stamped_regime",
    "few_settlements",
    "empty_cohort",
    "short_history",
    "no_base",
    "no_debt",
    "dscr_only",
    "utilisation_only",
)
# Flags an entity-month may carry (ScoreParts.flags).
SCORE_FLAGS: tuple[str, ...] = (
    "stale_feed",
    "perimeter_changed",
    "perimeter_quiet",
    "short_history",
    "granted_assumed_constant",
    "debt_snapshot",
    "fx_excluded",
    "inherited_from_group",
)
# Keys of PillarResult.inputs, per pillar. Missing values are None.
PILLAR_INPUT_KEYS: dict[str, tuple[str, ...]] = {
    "liquidity": (
        "buffer_days_month_end",
        "buffer_days_intra_min",
        "cash_month_end",
        "cash_intra_month_min",
        "headroom",
        "daily_outflow",
    ),
    "payments": (
        "days_beyond_terms",
        "days_beyond_terms_raw",
        "cohort_amount",
        "cohort_n",
        "settlements_6m",
        "unpaid30_share",
    ),
    "collections": (
        "days_beyond_terms",
        "days_beyond_terms_raw",
        "cohort_amount",
        "cohort_n",
        "settlements_6m",
        "unpaid30_share",
    ),
    "activity": ("ratio", "recent_3m", "base_monthly_median", "base_months"),
    "debt": (
        "dscr",
        "utilisation",
        "operating_cash_flow_12m",
        "debt_service_12m",
        "score_dscr",
        "score_utilisation",
    ),
}
# Monthly facts kept next to each snapshot for charts (EntitySnapshot.series).
SERIES_KEYS: tuple[str, ...] = (
    "cash_month_end",
    "cash_intra_month_min",
    "headroom",
    "drawn",
    "op_inflow_1m",
    "op_outflow_1m",
    "buffer_days",
    "ap_days_beyond_terms",
    "ar_days_beyond_terms",
    "activity_ratio",
    "dscr",
    "lines_utilisation",
)
PROFILE_KEYS: tuple[str, ...] = (
    "country",
    "size_band",
    "erp_tier",
    "group_role",
    "treasury_structure",
    "financing_profile",
    "history_depth",
    "seasonality",
    "customer_concentration",
    "payment_policy",
    "revenue_model",
    "data_quality",
)
DASH_LABELS: tuple[str, ...] = (
    "debt_installment",
    "debt_drawdown",
    "internal_transfer",
    "tax",
    "social_security",
    "salary",
    "fee",
    "balance_adjustment",
)


# --------------------------------------------------------------------------
# Params
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Anchors:
    """Piecewise-linear table ``x -> y``; clamped to the end values outside."""

    points: tuple[tuple[float, float], ...]

    def __call__(self, x: float) -> float:
        points = self.points
        if x <= points[0][0]:
            return points[0][1]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x <= x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        return points[-1][1]


@dataclass(frozen=True)
class LiquidityParams:
    month_end_weight: float  # weight of A(buffer at month end)
    intra_min_weight: float  # weight of A(buffer at intra-month minimum)
    outflow_window_months: int  # trailing months for the median monthly outflow
    days_per_month: float
    # swept-subsidiary rule (company rows, groups with more than one member)
    swept_zero_balance_share_min: float
    swept_group_cash_share_max: float
    swept_pairs_min: int
    swept_pairs_cash_share_max: float
    tiny_cash_share_max: float
    # an account is zero-balance when |balance| <= relative * own p95 on at
    # least days_share of the days (relative only: keeps scale invariance)
    zero_balance_relative: float
    zero_balance_days_share: float


@dataclass(frozen=True)
class InvoiceParams:
    observation_lag_days: int  # a due-cohort is read at due + lag
    pooled_cohorts: int  # trailing due-months pooled
    settled_clip_days: tuple[float, float]
    unsettled_base_days: float
    unsettled_cap_days: float
    min_settlements: int
    settlements_window_months: int
    shrinkage_pseudo_count: float  # count-based, so it is scale invariant
    prior_days: Mapping[str, float]  # keys: payments, collections
    stamped_share_max: float  # above it the date regime is not scorable
    stamped_window_months: int
    burn_in_months: int


@dataclass(frozen=True)
class ActivityParams:
    recent_months: int
    base_months: int
    min_base_months: int
    min_months_observed: int


@dataclass(frozen=True)
class DebtParams:
    neutral_score: float  # no debt products and no debt service
    dscr_weight: float
    utilisation_weight: float
    window_months: int


@dataclass(frozen=True)
class PenaltyParams:
    lam: float  # lambda
    tau: float  # points


@dataclass(frozen=True)
class CapsParams:
    negative_liquidity_ceiling: float
    negative_liquidity_min_months: int
    negative_liquidity_window_months: int
    lines_drawn_ceiling: float
    lines_drawn_threshold: float  # drawn / granted
    weak_pillar_ceiling: float
    weak_pillar_threshold: float
    weak_pillars: tuple[str, ...]


@dataclass(frozen=True)
class LiveFeedParams:
    threshold: float  # rows_3m / (recent_months * rows_base_median)
    recent_months: int
    base_from_months: int  # base window starts at t - base_from_months
    base_to_months: int  # and ends at t - base_to_months
    min_base_months: int  # fewer observed base months: feed is assumed live


@dataclass(frozen=True)
class ConfidenceParams:
    history: Anchors  # months_observed -> c_history
    coverage: Anchors  # sum of nominal weights of available pillars -> c_coverage
    quality_uncategorised: Anchors  # uncategorised_share -> factor
    quality_fx_excluded: Anchors  # fx_excluded_share -> factor
    quality_cash_anchor: Anchors  # cash_anchor_coverage -> factor
    stale_feed_factor: float  # multiplies c_quality when the feed is stale
    abstain_below: float


@dataclass(frozen=True)
class TrajectoryParams:
    horizon_months: int  # delta3 = level(t) - level(t - horizon)
    min_delta_points: float
    min_sigma_multiple: float
    sigma_floor: float
    structural_consecutive_months: int
    structural_min_pillars: int
    structural_required_pillar: str
    pillar_move_points: float  # |delta P_k| over the horizon to count as moved
    bump_revert_months: int
    bump_revert_fraction: float  # share of the spike that must be undone
    min_months_observed: int
    perimeter_quiet_months: int


@dataclass(frozen=True)
class AlertParams:
    critical_score: float
    perimeter_quiet_months: int


@dataclass(frozen=True)
class FxParams:
    base: str
    rates: Mapping[str, float]  # currency -> EUR per unit; others are excluded


@dataclass(frozen=True)
class SeasonalityParams:
    month_factors: tuple[float, ...]  # January..December, mean 1
    fitted: bool


@dataclass(frozen=True)
class ReferenceParams:
    medians: Mapping[str, float]  # B_k per pillar
    fitted: bool


@dataclass(frozen=True)
class PsiParams:
    edges: tuple[float, ...]  # score bin edges
    reference: Mapping[str, tuple[float, ...]]  # branch -> bin shares
    fitted: bool


@dataclass(frozen=True)
class FlowParams:
    op_inflow_categories: tuple[str, ...]  # amount > 0
    op_outflow_categories: tuple[str, ...]  # amount < 0
    debt_service_categories: tuple[str, ...]  # amount < 0, labels after recovery
    drawdown_labels: tuple[str, ...]  # amount > 0
    cash_product_types: tuple[str, ...]
    revolving_product_types: tuple[str, ...]
    excluded_debt_types: tuple[str, ...]  # contingent, outside debt stock
    sentinel_abs_balance: float  # |balance| >= sentinel is dropped
    pending_status: str


@dataclass(frozen=True)
class MirrorParams:
    day_offsets: tuple[int, ...]  # rank-join passes, in order


@dataclass(frozen=True)
class DashRule:
    """High-precision narrative rule that relabels a ``-`` transaction."""

    id: str
    label: str  # one of DASH_LABELS
    pattern: str  # case-insensitive regex on the description (newlines as spaces)
    exclude: str | None  # regex that vetoes the match
    sign: Literal["negative", "positive", "any"]
    precision: float | None  # measured by fit-reference on categorised rows
    support: int | None  # categorised rows matched when measuring


@dataclass(frozen=True)
class Params:
    version: str
    sha256: str  # over the canonical dump without this field
    fitted: bool
    fitted_on: str | None  # dataset hash used by fit-reference
    weights: Mapping[str, float]  # PILLAR_KEYS, sum 1
    anchors: Mapping[str, Anchors]  # ANCHOR_KEYS
    liquidity: LiquidityParams
    invoices: InvoiceParams
    activity: ActivityParams
    debt: DebtParams
    ewma_alpha: float  # 1.0 disables smoothing
    penalty: PenaltyParams
    caps: CapsParams
    live_feed: LiveFeedParams
    confidence: ConfidenceParams
    trajectory: TrajectoryParams
    alerts: AlertParams
    fx: FxParams
    seasonality: SeasonalityParams
    reference: ReferenceParams
    psi: PsiParams
    flows: FlowParams
    mirror: MirrorParams
    dash_rules: tuple[DashRule, ...]
    winsor: Mapping[str, tuple[float, float]]


# --------------------------------------------------------------------------
# Panel
# --------------------------------------------------------------------------


def _col(dtype: Any, unit: str, doc: str, default: Any = MISSING) -> Any:
    metadata = {"dtype": dtype, "unit": unit, "doc": doc}
    if default is MISSING:
        return field(metadata=metadata)
    return field(default=default, metadata=metadata)


@dataclass(frozen=True)
class PanelRow:
    """One entity-month. Company and group rows share every column.

    Group rows sum member flows in cents first and take ratios afterwards.
    Every value uses only facts knowable at the end of ``month``; snapshot
    sources are limited to the balance anchor and ``granted`` limits.
    Defaults exist for synthetic rows only; ``panel.py`` fills every column.
    """

    entity_kind: str = _col(pl.String, "-", "group | company")
    entity_id: str = _col(pl.String, "-", "group_id or company_id")
    group_id: str = _col(pl.String, "-", "owning group (equals entity_id for groups)")
    month: date = _col(pl.Date, "date", "first day of the scored complete month")

    # history and perimeter
    months_observed: int = _col(
        pl.Int64, "months", "months from the first observed booked row to month, inclusive", 0
    )
    months_active_12m: int = _col(
        pl.Int64, "months", "months with at least one booked row in t-11..t", 0
    )
    n_members: int = _col(
        pl.Int64, "count", "companies whose first observed row is <= month (1 for a company)", 1
    )
    n_products: int = _col(
        pl.Int64, "count", "products whose first observed row is <= month", 0
    )
    perimeter_changed: bool = _col(
        pl.Boolean, "flag", "a member or an account started reporting this month, after the first month", False
    )
    members_joined: int = _col(pl.Int64, "count", "members that started reporting this month", 0)
    products_connected: int = _col(
        pl.Int64, "count", "accounts that started reporting this month", 0
    )
    months_since_perimeter_change: int | None = _col(
        pl.Int64, "months", "0 on the change month; None when the perimeter never changed", None
    )

    # live-feed gate
    rows_month: int = _col(pl.Int64, "rows", "booked rows in month", 0)
    rows_3m: int = _col(pl.Int64, "rows", "booked rows in t-2..t", 0)
    rows_base_median: float | None = _col(
        pl.Float64, "rows", "median monthly booked rows over observed months of t-12..t-4", None
    )
    rows_base_months: int = _col(
        pl.Int64, "months", "observed months inside t-12..t-4", 0
    )

    # cash and revolving lines
    cash_month_end: float | None = _col(
        pl.Float64, "EUR", "back-rolled balance of cash products at month end; None without anchor", None
    )
    cash_intra_month_min: float | None = _col(
        pl.Float64, "EUR", "minimum over the days of month of the summed daily cash", None
    )
    n_cash_products: int = _col(
        pl.Int64, "count", "cash products in perimeter with a usable balance anchor", 0
    )
    cash_anchor_coverage: float | None = _col(
        pl.Float64, "share", "cash products with rows that have a usable anchor / cash products with rows", None
    )
    granted: float = _col(
        pl.Float64, "EUR", "sum of |granted| over revolving lines in perimeter (snapshot, assumed constant)", 0.0
    )
    drawn: float = _col(
        pl.Float64, "EUR", "sum of drawn balances (>= 0) of revolving lines at month end, back-rolled", 0.0
    )
    headroom: float = _col(
        pl.Float64, "EUR", "sum over lines of max(0, |granted| - drawn)", 0.0
    )
    n_credit_lines: int = _col(pl.Int64, "count", "revolving lines in perimeter", 0)
    neg_liquidity_months_6m: int = _col(
        pl.Int64, "months", "months of t-5..t with cash_month_end + headroom < 0", 0
    )
    swept_subsidiary: bool = _col(
        pl.Boolean, "flag", "company whose cash is swept to the group (LiquidityParams rule); False for groups", False
    )
    cash_share_of_group: float | None = _col(
        pl.Float64, "share", "company cash_month_end / group cash_month_end; None for groups", None
    )
    zero_balance_account_share: float | None = _col(
        pl.Float64, "share", "cash accounts classified zero-balance over t-11..t / cash accounts", None
    )
    sweep_pairs_12m: int = _col(
        pl.Int64, "count", "intra-group mirror pairs touching the entity in t-11..t", 0
    )

    # operating flows: booked, mirror-netted, '-' recovered, FX to EUR
    op_inflow_1m: float = _col(pl.Float64, "EUR", "operating inflow in month", 0.0)
    op_outflow_1m: float = _col(pl.Float64, "EUR", "operating outflow in month (positive)", 0.0)
    op_inflow_3m: float = _col(pl.Float64, "EUR", "operating inflow over t-2..t", 0.0)
    op_outflow_3m: float = _col(pl.Float64, "EUR", "operating outflow over t-2..t (positive)", 0.0)
    op_outflow_median_3m: float | None = _col(
        pl.Float64, "EUR", "median monthly operating outflow over observed months of t-2..t", None
    )
    op_inflow_12m: float = _col(pl.Float64, "EUR", "operating inflow over t-11..t", 0.0)
    op_outflow_12m: float = _col(
        pl.Float64, "EUR", "operating outflow over t-11..t (positive, includes interest)", 0.0
    )
    lfl_op_inflow_12m: tuple[float | None, ...] = _col(
        pl.List(pl.Float64),
        "EUR",
        "monthly operating inflow t-11..t (oldest first, 12 values) restricted to products with "
        "booked rows in both t-2..t and t-11..t-3; None before the first observed month",
        (),
    )
    intragroup_in: float = _col(
        pl.Float64, "EUR", "intra-group mirror inflow in month (groups: sum of members)", 0.0
    )
    intragroup_out: float = _col(
        pl.Float64, "EUR", "intra-group mirror outflow in month (positive)", 0.0
    )
    mirror_netted_1m: float = _col(
        pl.Float64, "EUR", "value of one leg of every pair netted in month, both scopes", 0.0
    )

    # debt
    n_debt_products: int = _col(
        pl.Int64, "count", "debt products of the entity, contingent types excluded (snapshot)", 0
    )
    debt_outstanding: float = _col(
        pl.Float64, "EUR", "sum of |outstanding| owed, contingent types excluded (snapshot)", 0.0
    )
    debt_service_12m: float = _col(
        pl.Float64, "EUR", "debt service over t-11..t, net of same-month revolving rollovers", 0.0
    )
    interest_12m: float = _col(
        pl.Float64, "EUR", "interest_charge over t-11..t (part of op_outflow_12m and debt_service_12m)", 0.0
    )
    debt_rollover_netted_12m: float = _col(
        pl.Float64, "EUR", "repayments excluded as rollovers over t-11..t", 0.0
    )
    debt_drawdowns_12m: float = _col(
        pl.Float64, "EUR", "recovered debt drawdowns over t-11..t", 0.0
    )

    # invoices, as-of month end; cohorts = invoices due in t-1..t-3, pooled
    has_invoices: bool = _col(pl.Boolean, "flag", "at least one invoice issued <= month end", False)
    invoice_months_observed: int = _col(
        pl.Int64, "months", "months from the first issuance month to month, inclusive; 0 without invoices", 0
    )
    ap_cohort_n: int = _col(pl.Int64, "invoices", "AP invoices in the pooled cohorts", 0)
    ap_cohort_amount: float = _col(pl.Float64, "EUR", "AP value in the pooled cohorts", 0.0)
    ap_days_beyond_terms: float | None = _col(
        pl.Float64, "days", "value-weighted AP days beyond terms, before shrinkage", None
    )
    ap_unpaid30_share: float | None = _col(
        pl.Float64, "share", "AP cohort value not settled at min(due + lag, month end)", None
    )
    ap_settlements_6m: int = _col(
        pl.Int64, "invoices", "AP invoices settled inside t-5..t", 0
    )
    ap_stamped_share: float | None = _col(
        pl.Float64, "share", "AP invoices issued in t-11..t with due == issue and settle in (null, due)", None
    )
    ap_open: float = _col(pl.Float64, "EUR", "AP open at month end", 0.0)
    ap_overdue: float = _col(pl.Float64, "EUR", "AP open and past due at month end", 0.0)
    ar_cohort_n: int = _col(pl.Int64, "invoices", "AR invoices in the pooled cohorts", 0)
    ar_cohort_amount: float = _col(pl.Float64, "EUR", "AR value in the pooled cohorts", 0.0)
    ar_days_beyond_terms: float | None = _col(
        pl.Float64, "days", "value-weighted AR days beyond terms, before shrinkage", None
    )
    ar_unpaid30_share: float | None = _col(
        pl.Float64, "share", "AR cohort value not settled at min(due + lag, month end)", None
    )
    ar_settlements_6m: int = _col(
        pl.Int64, "invoices", "AR invoices settled inside t-5..t", 0
    )
    ar_stamped_share: float | None = _col(
        pl.Float64, "share", "AR invoices issued in t-11..t with due == issue and settle in (null, due)", None
    )
    ar_open: float = _col(pl.Float64, "EUR", "AR open at month end", 0.0)
    ar_overdue: float = _col(pl.Float64, "EUR", "AR open and past due at month end", 0.0)

    # data quality
    uncategorised_share: float | None = _col(
        pl.Float64, "share", "booked rows still '-' after recovery / booked rows, t-11..t", None
    )
    fx_excluded_share: float | None = _col(
        pl.Float64, "share", "booked rows in currencies outside the FX table / booked rows, t-11..t", None
    )
    sentinel_balances_dropped: int = _col(
        pl.Int64, "count", "balance anchors dropped as sentinels", 0
    )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> PanelRow:
        """Strict constructor for panel rows: every PANEL_COLUMNS key is required."""
        missing = [name for name in PANEL_COLUMNS if name not in values]
        if missing:
            raise KeyError(f"Panel row is missing columns: {missing}")
        data = {name: values[name] for name in PANEL_COLUMNS}
        series = data["lfl_op_inflow_12m"]
        data["lfl_op_inflow_12m"] = tuple(series) if series is not None else ()
        return cls(**data)

    def to_mapping(self) -> dict[str, Any]:
        data = {name: getattr(self, name) for name in PANEL_COLUMNS}
        data["lfl_op_inflow_12m"] = list(self.lfl_op_inflow_12m)
        return data


# Ordered column -> polars dtype. The only panel schema: panel.py writes it,
# the pure core reads it through PanelRow.
PANEL_COLUMNS: dict[str, Any] = {
    item.name: item.metadata["dtype"] for item in fields(PanelRow)
}
PANEL_UNITS: dict[str, str] = {
    item.name: item.metadata["unit"] for item in fields(PanelRow)
}
PANEL_MONEY_COLUMNS: tuple[str, ...] = tuple(
    name for name, unit in PANEL_UNITS.items() if unit == "EUR"
)
PANEL_KEY: tuple[str, ...] = ("entity_kind", "entity_id", "month")


# --------------------------------------------------------------------------
# Pure core results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Evidence:
    """Aggregate fact behind a number. Never a raw description or a row."""

    label: str  # Spanish
    value: float | str | None
    unit: str
    period: str  # e.g. "2026-06..2026-08"
    source_file: str  # e.g. "transactions.csv"
    n_rows: int | None = None


@dataclass(frozen=True)
class PillarResult:
    key: str  # one of PILLAR_KEYS
    score: float | None  # 0..100 as it enters the aggregate (after EWMA); None = unavailable
    raw_score: float | None  # before EWMA
    inputs: Mapping[str, float | None] = field(default_factory=dict)  # PILLAR_INPUT_KEYS[key]
    gates: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class ConfidenceParts:
    history: float
    coverage: float
    quality: float

    @property
    def value(self) -> float:
        return self.history * self.coverage * self.quality


@dataclass(frozen=True)
class ScoreParts:
    """Aggregate of one entity-month.

    Exact identities (tolerance 1e-9):
      level_raw = level_weighted - penalty_level - cap_adjustment_level
      score     = 50 + confidence * (level_raw - 50)
      score     = base + sum(contributions) - penalty - cap_adjustment
    with base = 50 + confidence * (sum(w_ef * B_k) - 50),
    contributions[k] = confidence * w_ef[k] * (P_k - B_k),
    penalty = confidence * penalty_level and
    cap_adjustment = confidence * cap_adjustment_level.
    """

    month: date
    months_observed: int
    months_since_perimeter_change: int | None
    branch: str  # available pillar keys joined by "+", PILLAR_KEYS order; BRANCH_NONE when empty
    pillar_scores: Mapping[str, float | None]  # all PILLAR_KEYS
    weights_effective: Mapping[str, float]  # available pillars only, sum 1
    level_weighted: float  # sum(w_ef * P_k); 50 on the empty branch
    penalty_level: float  # level points
    cap_adjustment_level: float  # level points removed by the binding cap
    caps_fired: tuple[str, ...]  # CAP_KEYS that bind, strictest first
    level_raw: float
    confidence: float
    confidence_parts: ConfidenceParts
    base: float
    contributions: Mapping[str, float]  # available pillars only
    penalty: float  # score points
    cap_adjustment: float  # score points
    score: float
    feed_live: bool
    flags: tuple[str, ...]  # subset of SCORE_FLAGS
    abstained: bool  # confidence < abstain_below; the number is still emitted
    unlock_hint: str | None  # Spanish; what would lift the abstention


@dataclass(frozen=True)
class DeltaParts:
    """score(t) - score(t-1) = base + sum(contributions) - penalty - cap_adjustment.

    ``base`` is the delta_base term: it moves when branch or confidence change.
    A pillar missing on one side contributes with 0 on that side.
    """

    score: float
    base: float
    contributions: Mapping[str, float]
    penalty: float
    cap_adjustment: float


@dataclass(frozen=True)
class Trajectory:
    available: bool
    reason: str | None  # "short_history" | "perimeter_change" when not available
    direction: Direction = "stable"
    nature: Nature | None = None
    shock_pending: bool = False
    shock_month: date | None = None  # month of the spike a shock_pending / bump refers to
    delta3: float | None = None  # level_raw(t) - level_raw(t - horizon)
    sigma: float | None = None  # own sigma of monthly level changes, floored
    delta3_sigma: float | None = None
    compared_to: date | None = None  # month t - horizon
    pillars_moved: tuple[str, ...] = ()
    persistence_months: int = 0  # consecutive months with the current non-stable direction
    detected_since: date | None = None  # first month of that run


@dataclass(frozen=True)
class EntityMonth:
    """Everything computed for one entity-month, before serialisation."""

    row: PanelRow
    pillars: Mapping[str, PillarResult]  # all PILLAR_KEYS
    parts: ScoreParts
    trajectory: Trajectory


@dataclass(frozen=True)
class SuppressedBy:
    reason: str  # "perimeter_change" | "abstention"
    since: date
    until: date | None


@dataclass(frozen=True)
class Alert:
    id: str  # f"{entity_id}:{month:%Y-%m}:{kind}"
    entity_kind: str
    entity_id: str
    group_id: str
    month: date
    kind: AlertKind
    state: AlertState
    title: str  # Spanish
    detail: str  # Spanish
    suppressed_by: SuppressedBy | None = None


@dataclass(frozen=True)
class ProfileAttribute:
    key: str  # one of PROFILE_KEYS
    label: str  # Spanish
    value: str | float | int | bool | None
    evidence: str  # Spanish sentence built from aggregates
    coverage: float  # 0..1; 0 when the attribute cannot be inferred


@dataclass(frozen=True)
class ProfileCard:
    entity_kind: str
    entity_id: str
    group_id: str
    as_of_month: date
    attributes: tuple[ProfileAttribute, ...]  # PROFILE_KEYS order
    context: Mapping[str, Any] = field(default_factory=dict)  # context["industry"]; never a score input


# --------------------------------------------------------------------------
# Serialised snapshot (scores.parquet, API)
# --------------------------------------------------------------------------


class Driver(BaseModel):
    feature: str  # pillar key, "penalty" or "cap"
    label: str
    direction: Literal["positive", "negative", "neutral"]
    contribution: float
    observed: float
    baseline: float
    evidence: str
    source: Literal["observable", "predictive"] = "observable"


class IndustryClassification(BaseModel):
    entity_id: str
    industry_slug: str
    industry_label: str
    confidence: float = Field(ge=0, le=1)
    source: Literal["signal", "override", "insufficient_data"]
    reason: str
    classifier_version: str
    dataset_hash: str
    signals: dict[str, float] = Field(default_factory=dict)


class EntitySnapshot(BaseModel):
    """One row of scores.parquet. Superset of the v1 snapshot."""

    entity_id: str
    month: date
    score: float = Field(ge=0, le=100)
    delta: float  # score(t) - score(t-1); 0 on the first month
    trend: Direction
    persistence_months: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    drivers: list[Driver]
    detected_since: date | None
    feature_version: str = FEATURE_VERSION
    dataset_hash: str

    # v2
    entity_kind: EntityKind = "company"
    group_id: str | None = None
    level_raw: float | None = None
    base: float | None = None
    pillars: dict[str, float | None] = Field(default_factory=dict)
    pillars_raw: dict[str, float | None] = Field(default_factory=dict)
    weights_effective: dict[str, float | None] = Field(default_factory=dict)
    contributions: dict[str, float | None] = Field(default_factory=dict)
    penalty: float = 0.0
    cap_adjustment: float = 0.0
    caps_fired: list[str] = Field(default_factory=list)
    branch: str = BRANCH_NONE
    confidence_parts: ConfidenceParts | None = None
    delta_parts: DeltaParts | None = None
    trajectory: Trajectory | None = None
    gates: dict[str, list[str]] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    abstained: bool = False
    unlock_hint: str | None = None
    months_observed: int = 0
    perimeter_changed: bool = False
    series: dict[str, float | None] = Field(default_factory=dict)
    engine_version: str = ENGINE_VERSION
    params_hash: str = ""

    # deprecated v1 fields, kept so existing readers do not break
    observed_score: float = Field(ge=0, le=100)  # = level_raw
    predicted_future_score: float = Field(ge=0, le=100)  # = score (no forecast exists)
    forecast_delta: float = 0.0  # always 0
    shap_base_value: float  # = base
    explanation_residual: float = 0.0  # always 0: the decomposition is exact
    model_version: str = ENGINE_VERSION


# Deprecated name of EntitySnapshot.
ScoreSnapshot = EntitySnapshot

_PILLAR_STRUCT = pl.Struct({key: pl.Float64 for key in PILLAR_KEYS})

SNAPSHOT_SCHEMA: dict[str, Any] = {
    "entity_kind": pl.String,
    "entity_id": pl.String,
    "group_id": pl.String,
    "month": pl.Date,
    "score": pl.Float64,
    "level_raw": pl.Float64,
    "base": pl.Float64,
    "pillars": _PILLAR_STRUCT,
    "pillars_raw": _PILLAR_STRUCT,
    "weights_effective": _PILLAR_STRUCT,
    "contributions": _PILLAR_STRUCT,
    "penalty": pl.Float64,
    "cap_adjustment": pl.Float64,
    "caps_fired": pl.List(pl.String),
    "branch": pl.String,
    "confidence": pl.Float64,
    "confidence_parts": pl.Struct(
        {"history": pl.Float64, "coverage": pl.Float64, "quality": pl.Float64}
    ),
    "delta": pl.Float64,
    "delta_parts": pl.Struct(
        {
            "score": pl.Float64,
            "base": pl.Float64,
            "contributions": _PILLAR_STRUCT,
            "penalty": pl.Float64,
            "cap_adjustment": pl.Float64,
        }
    ),
    "trend": pl.String,
    "persistence_months": pl.Int64,
    "detected_since": pl.Date,
    "trajectory": pl.Struct(
        {
            "available": pl.Boolean,
            "reason": pl.String,
            "direction": pl.String,
            "nature": pl.String,
            "shock_pending": pl.Boolean,
            "shock_month": pl.Date,
            "delta3": pl.Float64,
            "sigma": pl.Float64,
            "delta3_sigma": pl.Float64,
            "compared_to": pl.Date,
            "pillars_moved": pl.List(pl.String),
            "persistence_months": pl.Int64,
            "detected_since": pl.Date,
        }
    ),
    "gates": pl.Struct({key: pl.List(pl.String) for key in PILLAR_KEYS}),
    "flags": pl.List(pl.String),
    "abstained": pl.Boolean,
    "unlock_hint": pl.String,
    "months_observed": pl.Int64,
    "perimeter_changed": pl.Boolean,
    "drivers": pl.List(
        pl.Struct(
            {
                "feature": pl.String,
                "label": pl.String,
                "direction": pl.String,
                "contribution": pl.Float64,
                "observed": pl.Float64,
                "baseline": pl.Float64,
                "evidence": pl.String,
                "source": pl.String,
            }
        )
    ),
    "series": pl.Struct({key: pl.Float64 for key in SERIES_KEYS}),
    "observed_score": pl.Float64,
    "predicted_future_score": pl.Float64,
    "forecast_delta": pl.Float64,
    "shap_base_value": pl.Float64,
    "explanation_residual": pl.Float64,
    "feature_version": pl.String,
    "model_version": pl.String,
    "engine_version": pl.String,
    "params_hash": pl.String,
    "dataset_hash": pl.String,
}
