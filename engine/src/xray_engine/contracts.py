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
"not observable", never zero. A panel row holds pre-aggregated as-of facts, so
the pure core never reads history arrays. The score is the level itself: no
confidence shrink, no smoothing, no seasonal factors.
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
Direction = Literal["improving", "stable", "deteriorating", "perimeter_shift"]
Trend = Literal["improving", "stable", "deteriorating"]  # v1 readers
Nature = Literal["structural", "shock_pending", "bump"]
Horizon = Literal["short", "long", "both"]
AlertKind = Literal[
    "deterioration_structural",
    "improvement_structural",
    "level_critical",
    "cap_fired",
    "stale_feed",
]
AlertState = Literal["fired", "suppressed", "abstained"]
Band = Literal["critical", "watch", "stable", "solid"]
ConfidenceLabel = Literal["high", "medium", "low"]
FlowClass = Literal[
    "internal", "adjustment", "debt_service", "op_in", "op_out", "financial", "other"
]

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
# ``liquidity`` is the absolute fallback table; the size-band tables live in
# ``LiquidityParams.band_anchors``.
ANCHOR_KEYS: tuple[str, ...] = (
    "liquidity",
    "payments",
    "collections",
    "activity_coverage",
    "activity_momentum",
    "debt_burden",
)
CAP_KEYS: tuple[str, ...] = ("negative_liquidity", "weak_payments")
BRANCH_NONE = "none"

# Bands, ascending; the minimum of each one is frozen in ``Params.bands``.
BAND_KEYS: tuple[str, ...] = ("critical", "watch", "stable", "solid")
BAND_LABELS: dict[str, str] = {
    "critical": "Crítico",
    "watch": "Vigilancia",
    "stable": "Estable",
    "solid": "Sólido",
}
CONFIDENCE_LABEL_KEYS: tuple[str, ...] = ("high", "medium", "low")
CONFIDENCE_LABELS: dict[str, str] = {"high": "Alta", "medium": "Media", "low": "Baja"}
# Size bands, ascending; upper bounds in ``SizeBandParams`` (EU SME thresholds).
SIZE_BANDS: tuple[str, ...] = ("micro", "small", "medium", "large")
SIZE_BAND_LABELS: dict[str, str] = {
    "micro": "Micro (< 2 M€)",
    "small": "Pequeña (2-10 M€)",
    "medium": "Mediana (10-50 M€)",
    "large": "Grande (≥ 50 M€)",
}
# One class per booked transaction (``cleaning.classify_flows``).
FLOW_CLASSES: tuple[str, ...] = (
    "internal",
    "adjustment",
    "debt_service",
    "op_in",
    "op_out",
    "financial",
    "other",
)
# Pillars read from bank rows; without any of them the engine abstains.
BANK_PILLARS: tuple[str, ...] = ("liquidity", "activity")
# First reason that applies.
ABSTAIN_REASONS: tuple[str, ...] = ("stale_feed", "short_history", "no_bank_pillar")
SUPPRESSION_REASONS: tuple[str, ...] = ("perimeter_change", "abstention")
TRAJECTORY_REASONS: tuple[str, ...] = ("short_history", "stale_feed")
# Gate appended by ``scoring`` to every pillar of a carried-forward month.
CARRIED_GATE = "carried_forward"

# Gates a pillar may report (PillarResult.gates). A gate explains why a score
# is missing or how it was obtained; it never changes the arithmetic by itself.
PILLAR_GATES: tuple[str, ...] = (
    "inherited_from_group",
    "no_cash_anchor",
    "buffer_undefined",
    "absolute_anchors",
    "no_invoices",
    "stamped_regime",
    "few_invoices",
    "low_effective_n",
    "erp_never_settles",
    "no_external_revenue",
    "short_history",
    "no_base",
    "coverage_undefined",
    "coverage_only",
    "momentum_only",
    "no_debt",
    "burden_undefined",
    CARRIED_GATE,
)
# Flags an entity-month may carry (ScoreParts.flags), in this order.
SCORE_FLAGS: tuple[str, ...] = (
    "stale_feed",
    "perimeter_changed",
    "perimeter_shift",
    "short_history",
    "limit_assumed_constant",
    "debt_snapshot",
    "fx_excluded",
    "orphan_products",
    "no_cash_anchor",
    "no_external_revenue",
    "inherited_from_group",
)
# Keys of PillarResult.inputs, per pillar. Missing values are None.
PILLAR_INPUT_KEYS: dict[str, tuple[str, ...]] = {
    "liquidity": (
        "buffer_days_month_end",
        "buffer_days_intra_min",
        "score_month_end",
        "score_intra_min",
        "cash_month_end",
        "cash_intra_month_min",
        "headroom",
        "headroom_at_min",
        "monthly_outflow",
    ),
    "payments": (
        "days_beyond_terms",
        "n",
        "neff",
        "amount",
        "stamped_share",
        "open_share",
    ),
    "collections": (
        "days_beyond_terms",
        "n",
        "neff",
        "amount",
        "stamped_share",
        "open_share",
    ),
    "activity": (
        "coverage",
        "momentum",
        "score_coverage",
        "score_momentum",
        "op_in_6m",
        "outflow_6m",
        "lfl_recent_mean",
        "lfl_prior_mean",
    ),
    "debt": ("burden", "debt_service_12m", "op_in_12m", "months"),
}
# Monthly facts kept next to each snapshot for charts (EntitySnapshot.series).
SERIES_KEYS: tuple[str, ...] = (
    "cash_month_end",
    "cash_intra_month_min",
    "headroom",
    "drawn",
    "op_inflow_1m",
    "op_outflow_1m",
    "debt_service_1m",
    "buffer_days",
    "ap_days_beyond_terms",
    "ar_days_beyond_terms",
    "activity_coverage",
    "activity_momentum",
    "debt_burden",
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
# Category-like labels a narrative rule may give to a ``-`` row (evidence only).
DASH_LABELS: tuple[str, ...] = (
    "transfer",
    "collection",
    "fee",
    "utility",
    "tax",
    "social_security",
    "debt_repayment",
    "balance_adjustment",
)

# Spanish text of every code that reaches the screen (bundle glossary).
GATE_TEXTS: dict[str, str] = {
    "inherited_from_group": "Liquidez heredada del grupo: la caja de esta filial se barre a la matriz.",
    "no_cash_anchor": "Ninguna cuenta de caja tiene un saldo de referencia para reconstruir la caja.",
    "buffer_undefined": "Sin salidas en los últimos 3 ni 12 meses: el colchón no está definido.",
    "absolute_anchors": "Liquidez medida con la escala absoluta, sin segmentar por tamaño.",
    "no_invoices": "No vence ninguna factura en los últimos 90 días.",
    "stamped_regime": "Las fechas de las facturas las estampa el ERP: no miden puntualidad.",
    "few_invoices": "Menos de 10 facturas con fechas reales en la ventana.",
    "low_effective_n": "El importe se concentra en muy pocas facturas: la media ponderada no es fiable.",
    "erp_never_settles": "El ERP no registra los pagos: casi todas las facturas vencidas hace 3 a 12 meses siguen abiertas.",
    "no_external_revenue": "Todos los cobros son movimientos internos del grupo.",
    "short_history": "Historia insuficiente para calcular este pilar.",
    "no_base": "No hay meses de comparación con las mismas cuentas.",
    "coverage_undefined": "Sin salidas operativas en la ventana: la cobertura no está definida.",
    "coverage_only": "Actividad medida solo con la cobertura operativa.",
    "momentum_only": "Actividad medida solo con el impulso de cobros.",
    "no_debt": "Sin productos de deuda ni servicio de deuda en los últimos 12 meses.",
    "burden_undefined": "Sin cobros operativos en la ventana: la carga de deuda no está definida.",
    CARRIED_GATE: "Valor del último mes con el feed bancario vivo.",
}
FLAG_TEXTS: dict[str, str] = {
    "stale_feed": "El feed bancario ha dejado de llegar: se mantiene el último score con datos vivos.",
    "perimeter_changed": "Este mes se conectó una empresa o una cuenta nueva.",
    "perimeter_shift": "Las cuentas conectadas en los últimos 3 meses aportan más del 20 % de los cobros.",
    "short_history": "Menos de 6 meses observados: sin trayectoria.",
    "limit_assumed_constant": "El límite de las líneas de crédito se asume constante en el tiempo.",
    "debt_snapshot": "Los productos de deuda son una foto de la fecha de extracción.",
    "fx_excluded": "Hay movimientos en divisas fuera de la tabla de cambio: cuentan en filas, no en importes.",
    "orphan_products": "Hay movimientos de cuentas que no figuran en el maestro de productos.",
    "no_cash_anchor": "Hay cuentas de caja con movimientos pero sin saldo de referencia.",
    "no_external_revenue": "Sin cobros de fuera del grupo en los últimos 12 meses.",
    "inherited_from_group": "La liquidez mostrada es la del grupo.",
}
CAP_TEXTS: dict[str, str] = {
    "negative_liquidity": "Caja más líneas disponibles en negativo 3 de los últimos 6 meses: score máximo 40.",
    "weak_payments": "Pagos a proveedores por debajo de 40 (más de 60 días sobre el vencimiento): score máximo 50.",
}
REASON_TEXTS: dict[str, str] = {
    "stale_feed": "Feed bancario sin datos recientes.",
    "short_history": "Historia insuficiente.",
    "no_bank_pillar": "Sin pilares basados en banco.",
    "perimeter_change": "Cambio de perímetro este mes.",
    "abstention": "El motor se abstiene en este mes.",
}
# What would lift the abstention, by reason; ``{months}`` = minimum history.
UNLOCK_HINTS: dict[str, str] = {
    "stale_feed": "Reconectar el feed bancario: no llegan movimientos recientes.",
    "short_history": "Hacen falta al menos {months} meses de movimientos bancarios.",
    "no_bank_pillar": "Conectar cuentas con saldo y movimientos operativos.",
}


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
class SizeBandParams:
    upper_bounds_eur: tuple[float, ...]  # annualised op inflow; one bound per band but the last
    window_months: int  # trailing months that are annualised
    hold_months: int  # a new band is adopted once it has held this many months in a row


@dataclass(frozen=True)
class LiquidityParams:
    month_end_weight: float  # weight of A(buffer at month end)
    intra_min_weight: float  # weight of A(buffer at intra-month minimum)
    outflow_window_months: int  # trailing months of the median monthly outflow
    outflow_fallback_months: int  # used when the short median is 0
    days_per_month: float
    segmented: bool  # False: every band reads anchors["liquidity"]
    band_quantiles: tuple[float, ...]  # reference quantiles of buffer days ...
    band_scores: tuple[float, ...]  # ... and the score each one maps to
    band_anchors: Mapping[str, Anchors]  # SIZE_BANDS; (0, 0) + quantile points
    band_anchors_fitted: bool
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
    window_days: int  # invoices with due_date in (t - window_days, t]
    clip_days: tuple[float, float]  # per-invoice days beyond terms
    min_invoices: int  # non-stamped invoices in the window
    min_effective_n: float  # Kish n of the value weights
    stamped_share_max: float  # at or above it the date regime is not scorable
    # share of the zero-terms invoices settled by month end that are stamped; at or
    # above it every zero-terms invoice of the entity-side counts as stamped that month
    zero_terms_stamped_share: float
    never_settles_min_aged: int  # aged invoices needed to tell whether the ERP records payments
    never_settles_open_share: float  # aged invoices still open at or above it: not scorable


@dataclass(frozen=True)
class ActivityParams:
    coverage_window_months: int
    coverage_min_months: int
    recent_months: int  # momentum numerator
    prior_months: int  # momentum denominator, right before the recent months
    min_prior_months: int
    min_months_observed: int  # momentum only


@dataclass(frozen=True)
class DebtParams:
    window_months: int
    min_months: int


@dataclass(frozen=True)
class RobustParams:
    monthly_winsor_multiple: float  # cap of a month = multiple * median positive month


@dataclass(frozen=True)
class PenaltyParams:
    lam: float  # lambda
    tau: float  # points


@dataclass(frozen=True)
class CapsParams:
    negative_liquidity_ceiling: float
    negative_liquidity_min_months: int
    negative_liquidity_window_months: int
    negative_liquidity_max_no_anchor_share: float  # above it cash is under-stated: no cap
    weak_payments_ceiling: float
    weak_payments_threshold: float


@dataclass(frozen=True)
class LiveFeedParams:
    threshold: float  # rows_3m / (recent_months * rows_base_median)
    recent_months: int
    base_from_months: int  # base window starts at t - base_from_months
    base_to_months: int  # and ends at t - base_to_months
    min_base_months: int  # fewer observed base months: baseline undefined
    group_zero_row_month_is_stale: bool


@dataclass(frozen=True)
class ConfidenceParams:
    history: Anchors  # months_observed -> c_history
    coverage: Anchors  # sum of nominal weights of available pillars -> c_coverage
    quality_dash: Anchors  # dash_share -> factor
    quality_fx_excluded: Anchors  # fx_excluded_share -> factor
    quality_orphan: Anchors  # orphan_product_share -> factor
    quality_no_cash_anchor: Anchors  # no_cash_anchor_share -> factor
    limit_assumed_constant_factor: float
    stale_feed_factor: float
    label_high_min: float
    label_medium_min: float


@dataclass(frozen=True)
class AbstentionParams:
    min_months_observed: int
    bank_pillars: tuple[str, ...]  # at least one must be available


@dataclass(frozen=True)
class TrajectoryParams:
    horizon_months: int  # delta3 = score(t) - score(t - horizon)
    min_delta_points: float
    min_sigma_multiple: float
    sigma_floor: float
    structural_consecutive_months: int
    pillar_move_points: float  # |delta P_k| over the horizon to count as moved
    bump_revert_months: int
    bump_revert_fraction: float  # share of the spike that must be undone
    min_scored_months: int
    perimeter_shift_share: float  # new_perimeter_inflow_share_3m above it
    perimeter_shift_window_months: int
    # slow-drift detector: Theil-Sen slope of the monthly score over the last
    # h = min(long_horizon, comparable live months) months, times h
    long_horizon: int
    long_min_months: int
    long_threshold: float  # points
    long_sigma_mult: float  # times the own sigma


@dataclass(frozen=True)
class AlertParams:
    critical_score: float


@dataclass(frozen=True)
class ProfileParams:
    concentration_top1_share: float  # top counterparty / total monthly collections
    concentration_min_months: int
    concentration_window_months: int


@dataclass(frozen=True)
class FxParams:
    base: str
    rates: Mapping[str, float]  # currency -> EUR per unit; others are excluded


@dataclass(frozen=True)
class ReferenceParams:
    medians: Mapping[str, float]  # B_k per pillar
    fitted: bool


@dataclass(frozen=True)
class FlowParams:
    op_inflow_categories: tuple[str, ...]  # amount > 0 -> op_in
    op_outflow_categories: tuple[str, ...]  # amount < 0 -> op_out
    debt_service_categories: tuple[str, ...]  # amount < 0 -> debt_service
    internal_categories: tuple[str, ...]  # any sign -> internal
    financial_categories: tuple[str, ...]  # any sign -> financial
    dash_category: str  # defaulted by sign unless a narrative rule fires
    cash_product_types: tuple[str, ...]
    revolving_product_types: tuple[str, ...]
    excluded_debt_types: tuple[str, ...]  # contingent, outside has_debt_products
    sentinel_abs_balance: float  # |balance| >= sentinel is dropped
    pending_status: str


@dataclass(frozen=True)
class MirrorParams:
    min_amount_eur: float  # |amount| at the static FX rate
    max_day_gap: int
    weekend_bridge_day_gap: int  # allowed when the earlier leg falls on bridge_weekdays
    weekend_bridge_weekdays: tuple[int, ...]  # date.weekday(): 4 Friday, 5 Saturday
    reversal_max_day_gap: int  # same product, opposite sign, equal cents


@dataclass(frozen=True)
class DashRule:
    """High-precision narrative rule that overrides the sign default of a ``-`` row."""

    id: str
    flow_class: str  # one of FLOW_CLASSES
    label: str  # one of DASH_LABELS
    pattern: str  # case-insensitive regex on the description (newlines as spaces)
    exclude: str | None  # regex that vetoes the match
    sign: Literal["negative", "positive", "any"]
    precision: float | None  # share of categorised matches that agree; fit-reference refreshes it
    support: int | None  # categorised rows matched when measuring


@dataclass(frozen=True)
class Params:
    version: str
    sha256: str  # over the canonical dump without this field
    fitted: bool
    fitted_on: str | None  # dataset hash used by fit-reference
    weights: Mapping[str, float]  # PILLAR_KEYS, sum 1
    anchors: Mapping[str, Anchors]  # ANCHOR_KEYS
    size_bands: SizeBandParams
    liquidity: LiquidityParams
    invoices: InvoiceParams
    activity: ActivityParams
    debt: DebtParams
    robust: RobustParams
    penalty: PenaltyParams
    caps: CapsParams
    bands: Mapping[str, float]  # BAND_KEYS -> inclusive minimum score
    live_feed: LiveFeedParams
    confidence: ConfidenceParams
    abstention: AbstentionParams
    trajectory: TrajectoryParams
    alerts: AlertParams
    profile: ProfileParams
    fx: FxParams
    reference: ReferenceParams
    flows: FlowParams
    mirror: MirrorParams
    dash_rules: tuple[DashRule, ...]


def band_of(score: float, bands: Mapping[str, float]) -> str:
    """Band of a score, decided on integer tenths so screen and engine agree."""
    tenths = round(score * 10)
    return [key for key in BAND_KEYS if tenths >= round(bands[key] * 10)][-1]


def size_band_of(annual_inflow: float, upper_bounds: tuple[float, ...]) -> str:
    """Size band of an annualised operating inflow in EUR."""
    for key, bound in zip(SIZE_BANDS, upper_bounds):
        if annual_inflow < bound:
            return key
    return SIZE_BANDS[-1]


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
    sources are limited to the balance anchor, ``granted`` limits and the list
    of debt products. Flows are booked, netted of mirrors and reversals,
    classified by ``flow_class`` and converted with the static FX table; rows
    in unknown currencies or of unknown products count as rows, never as value.
    ``*_w`` sums add monthly totals capped at ``monthly_winsor_multiple`` times
    the median positive month of the same window. Windows only hold observed
    months (from the first booked row of the entity). Defaults exist for
    synthetic rows only; ``panel.py`` fills every column.
    """

    entity_kind: str = _col(pl.String, "-", "group | company")
    entity_id: str = _col(pl.String, "-", "group_id or company_id")
    group_id: str = _col(pl.String, "-", "owning group (equals entity_id for groups)")
    month: date = _col(pl.Date, "date", "first day of the scored complete month")

    # history and perimeter
    months_observed: int = _col(
        pl.Int64, "months", "months from the first observed booked row to month, inclusive", 0
    )
    n_members: int = _col(
        pl.Int64, "count", "companies whose first booked month is <= month (1 for a company)", 1
    )
    n_products: int = _col(
        pl.Int64, "count", "accounts whose first booked month is <= month, of members in perimeter", 0
    )
    perimeter_changed: bool = _col(
        pl.Boolean, "flag", "a member or an account started reporting this month, after the first month of the entity", False
    )
    members_joined: int = _col(pl.Int64, "count", "members that started reporting this month", 0)
    products_connected: int = _col(
        pl.Int64, "count", "members with an account first seen this month (events deduped to company-month)", 0
    )
    months_since_perimeter_change: int | None = _col(
        pl.Int64, "months", "0 on the change month; None when the perimeter never changed", None
    )
    new_perimeter_inflow_share_3m: float | None = _col(
        pl.Float64, "share", "operating inflow of t-2..t booked on accounts first seen in t-2..t after the "
        "first month of the entity / operating inflow of t-2..t; None without inflow", None
    )
    size_band: str | None = _col(
        pl.String, "-", "micro | small | medium | large from op_in_sum_12m_w * 12 / months_in_12m_window; "
        "sticky: a new band is adopted after size_bands.hold_months months in a row", None
    )

    # live-feed gate
    rows_month: int = _col(pl.Int64, "rows", "booked rows in month", 0)
    rows_3m: int = _col(pl.Int64, "rows", "booked rows in t-2..t", 0)
    rows_base_median: float | None = _col(
        pl.Float64, "rows", "median monthly booked rows over observed months of t-12..t-4; None below min_base_months", None
    )
    rows_base_months: int = _col(
        pl.Int64, "months", "observed months inside t-12..t-4", 0
    )
    zero_row_month: bool = _col(pl.Boolean, "flag", "no booked row in month", False)

    # cash and revolving lines, back-rolled per product and per month
    cash_month_end: float | None = _col(
        pl.Float64, "EUR", "back-rolled balance at month end of the cash accounts in perimeter (first booked "
        "row <= month; an account without booked rows is never read); None without any anchor", None
    )
    cash_intra_month_min: float | None = _col(
        pl.Float64, "EUR", "minimum over the days of month of the summed daily cash", None
    )
    headroom: float = _col(
        pl.Float64, "EUR", "sum over anchored lines of max(0, |granted| - drawn) at month end; a line is a "
        "facility of its company and counts from the first booked month of that company, whatever its own rows", 0.0
    )
    headroom_at_min: float = _col(
        pl.Float64, "EUR", "same sum on the first day that reaches cash_intra_month_min", 0.0
    )
    granted: float = _col(
        pl.Float64, "EUR", "sum of |granted| over revolving lines of the members in perimeter (snapshot, assumed constant)", 0.0
    )
    drawn: float = _col(
        pl.Float64, "EUR", "sum of drawn balances (>= 0) of anchored revolving lines at month end", 0.0
    )
    n_cash_products: int = _col(
        pl.Int64, "count", "cash products in perimeter with a usable balance anchor", 0
    )
    n_credit_lines: int = _col(pl.Int64, "count", "revolving lines of the members in perimeter", 0)
    neg_liquidity_months_6m: int = _col(
        pl.Int64, "months", "months of t-5..t with cash_month_end + headroom < 0", 0
    )
    no_cash_anchor_share: float | None = _col(
        pl.Float64, "share", "cash products with booked rows and no usable anchor / cash products with booked rows", None
    )
    limit_assumed_constant: bool = _col(
        pl.Boolean, "flag", "headroom uses a snapshot limit (granted > 0)", False
    )
    swept_subsidiary: bool = _col(
        pl.Boolean, "flag", "company whose cash is swept to the group (LiquidityParams rule); False for groups", False
    )
    cash_share_of_group: float | None = _col(
        pl.Float64, "share", "company cash_month_end / group cash_month_end, clipped to [0, 1]; None for groups and without positive group cash", None
    )
    zero_balance_account_share: float | None = _col(
        pl.Float64, "share", "cash accounts classified zero-balance over t-11..t / cash accounts", None
    )
    sweep_pairs_12m: int = _col(
        pl.Int64, "count", "intra-group mirror pairs touching the entity in t-11..t", 0
    )
    sentinel_balances_dropped: int = _col(
        pl.Int64, "count", "balance anchors dropped as sentinels", 0
    )

    # flows
    op_inflow_1m: float = _col(pl.Float64, "EUR", "op_in in month", 0.0)
    op_outflow_1m: float = _col(pl.Float64, "EUR", "op_out in month (positive)", 0.0)
    debt_service_1m: float = _col(pl.Float64, "EUR", "debt_service in month (positive)", 0.0)
    outflow_median_3m: float | None = _col(
        pl.Float64, "EUR", "median monthly op_out + debt_service over t-2..t", None
    )
    outflow_median_12m: float | None = _col(
        pl.Float64, "EUR", "median monthly op_out + debt_service over t-11..t", None
    )
    op_in_sum_6m_w: float = _col(pl.Float64, "EUR", "op_in over t-5..t, winsorised months", 0.0)
    outflow_sum_6m_w: float = _col(
        pl.Float64, "EUR", "op_out + debt_service over t-5..t, winsorised months", 0.0
    )
    months_in_6m_window: int = _col(pl.Int64, "months", "observed months inside t-5..t", 0)
    op_in_sum_12m_w: float = _col(pl.Float64, "EUR", "op_in over t-11..t, winsorised months", 0.0)
    debt_service_sum_12m_w: float = _col(
        pl.Float64, "EUR", "debt_service over t-11..t, winsorised months", 0.0
    )
    months_in_12m_window: int = _col(pl.Int64, "months", "observed months inside t-11..t", 0)
    op_in_lfl_recent_mean: float | None = _col(
        pl.Float64, "EUR", "mean monthly op_in over t-2..t on accounts with booked rows in both t-2..t and "
        "t-8..t-3 that were already reporting on the first observed month of t-8..t-3; months winsorised "
        "over t-8..t; None without such accounts", None
    )
    op_in_lfl_prior_mean: float | None = _col(
        pl.Float64, "EUR", "same accounts and cap, mean over the observed months of t-8..t-3", None
    )
    lfl_prior_months: int = _col(pl.Int64, "months", "observed months inside t-8..t-3", 0)
    no_external_revenue: bool = _col(
        pl.Boolean, "flag", "inflow exists in t-11..t and op_in over t-11..t is exactly 0", False
    )
    intragroup_in: float = _col(
        pl.Float64, "EUR", "positive legs of intra-group mirror pairs in month (context, never scored)", 0.0
    )
    intragroup_out: float = _col(
        pl.Float64, "EUR", "negative legs of intra-group mirror pairs in month (positive)", 0.0
    )
    mirror_netted_1m: float = _col(
        pl.Float64, "EUR", "value of one leg of every mirror pair and reversal netted in month", 0.0
    )

    # debt
    has_debt_products: bool = _col(
        pl.Boolean, "flag", "a debt product of a member in perimeter, contingent types excluded (snapshot)", False
    )

    # invoices as of month end: invoices with due_date in (t - window_days, t]
    has_invoices: bool = _col(pl.Boolean, "flag", "at least one invoice issued <= month end", False)
    ap_n: int = _col(pl.Int64, "invoices", "AP invoices in the window, stamped rows excluded", 0)
    ap_neff: float | None = _col(
        pl.Float64, "invoices", "Kish effective n of the AP value weights: (sum w)^2 / sum w^2", None
    )
    ap_amount: float = _col(pl.Float64, "EUR", "AP value behind ap_days_beyond_terms", 0.0)
    ap_days_beyond_terms: float | None = _col(
        pl.Float64, "days", "value-weighted AP days beyond terms: settled by t -> settle - due, open -> "
        "t - due, each invoice clipped to clip_days", None
    )
    ap_stamped_share: float | None = _col(
        pl.Float64, "share", "AP invoices in the window with due == issue and settle == due (every zero-terms "
        "invoice under the zero-terms regime of the month) / AP invoices in the window", None
    )
    ap_open_share: float | None = _col(
        pl.Float64, "share", "AP window value still open at month end / ap_amount", None
    )
    ap_open: float = _col(pl.Float64, "EUR", "AP open at month end", 0.0)
    ap_overdue: float = _col(pl.Float64, "EUR", "AP open and past due at month end", 0.0)
    ap_aged_n: int = _col(
        pl.Int64, "invoices", "AP invoices due 90-365 days before month end, stamped rows excluded "
        "(input of the erp_never_settles gate)", 0
    )
    ap_aged_open_n: int = _col(pl.Int64, "invoices", "... of which still open at month end", 0)
    ar_n: int = _col(pl.Int64, "invoices", "AR invoices in the window, stamped rows excluded", 0)
    ar_neff: float | None = _col(
        pl.Float64, "invoices", "Kish effective n of the AR value weights", None
    )
    ar_amount: float = _col(pl.Float64, "EUR", "AR value behind ar_days_beyond_terms", 0.0)
    ar_days_beyond_terms: float | None = _col(
        pl.Float64, "days", "value-weighted AR days beyond terms, same recipe as AP", None
    )
    ar_stamped_share: float | None = _col(
        pl.Float64, "share", "AR invoices in the window with due == issue and settle == due (every zero-terms "
        "invoice under the zero-terms regime of the month) / AR invoices in the window", None
    )
    ar_open_share: float | None = _col(
        pl.Float64, "share", "AR window value still open at month end / ar_amount", None
    )
    ar_open: float = _col(pl.Float64, "EUR", "AR open at month end", 0.0)
    ar_overdue: float = _col(pl.Float64, "EUR", "AR open and past due at month end", 0.0)
    ar_aged_n: int = _col(pl.Int64, "invoices", "AR invoices due 90-365 days before month end, stamped rows excluded", 0)
    ar_aged_open_n: int = _col(pl.Int64, "invoices", "... of which still open at month end", 0)

    # data quality, booked rows of t-11..t
    dash_share: float | None = _col(
        pl.Float64, "share", "rows with category '-' / rows", None
    )
    fx_excluded_share: float | None = _col(
        pl.Float64, "share", "rows in currencies outside the FX table / rows", None
    )
    orphan_product_share: float | None = _col(
        pl.Float64, "share", "rows of products absent from both product files / rows", None
    )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> PanelRow:
        """Strict constructor for panel rows: every PANEL_COLUMNS key is required."""
        missing = [name for name in PANEL_COLUMNS if name not in values]
        if missing:
            raise KeyError(f"Panel row is missing columns: {missing}")
        return cls(**{name: values[name] for name in PANEL_COLUMNS})

    def to_mapping(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in PANEL_COLUMNS}


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
    score: float | None  # 0..100; None = not observable, with at least one gate
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

    Explanation block: ``branch`` .. ``band``. Exact identities (1e-9):
      score = level_weighted - penalty - cap_adjustment
      score = base + sum(contributions) - penalty - cap_adjustment
    with base = sum(w_ef * B_k) (one base per coverage branch) and
    contributions[k] = w_ef[k] * (P_k - B_k). Confidence never enters.
    On a live month the block is computed from the pillars of the month and
    ``level == score``. On a stale month that follows a live one the block is
    the one of that live month, verbatim (``carried_from``), while ``level``
    keeps the arithmetic of the month itself with penalty and caps off.
    """

    month: date
    months_observed: int
    months_since_perimeter_change: int | None
    branch: str  # available pillar keys joined by "+", PILLAR_KEYS order; BRANCH_NONE when empty
    pillar_scores: Mapping[str, float | None]  # all PILLAR_KEYS
    weights_effective: Mapping[str, float]  # available pillars only, sum 1
    level_weighted: float  # sum(w_ef * P_k); the nominal-weight reference on the empty branch
    penalty: float  # points, >= 0
    cap_adjustment: float  # points removed by the binding cap, >= 0
    caps_fired: tuple[str, ...]  # CAP_KEYS that hold, strictest first
    base: float
    contributions: Mapping[str, float]  # available pillars only
    score: float  # 0..100, the number on screen
    band: str  # band_of(score)
    level: float  # own level of the month; differs from score only when carried
    feed_live: bool
    carried_from: date | None  # live month the explanation block was copied from
    confidence: float
    confidence_parts: ConfidenceParts
    confidence_label: str  # one of CONFIDENCE_LABEL_KEYS
    flags: tuple[str, ...]  # subset of SCORE_FLAGS, in that order
    abstained: bool  # the number is still emitted; alerts are not fired
    abstain_reason: str | None  # one of ABSTAIN_REASONS
    unlock_hint: str | None  # Spanish; what would lift the abstention
    # size band behind the liquidity table (the one of the group when the
    # liquidity is inherited); part of the explanation block, copied when carried
    size_band: str | None = None


@dataclass(frozen=True)
class DeltaParts:
    """score(t) - score(t-1) = base + sum(contributions) - penalty - cap_adjustment.

    ``base`` is the delta_base term: it moves when the coverage branch changes.
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
    reason: str | None  # one of TRAJECTORY_REASONS when not available
    direction: Direction = "stable"
    nature: Nature | None = None
    shock_pending: bool = False
    shock_month: date | None = None  # month of the spike a shock_pending / bump refers to
    delta3: float | None = None  # score(t) - score(t - horizon)
    sigma: float | None = None  # own sigma of monthly score changes, floored
    delta3_sigma: float | None = None
    compared_to: date | None = None  # month t - horizon
    pillars_moved: tuple[str, ...] = ()
    persistence_months: int = 0  # consecutive months with the current improving / deteriorating direction
    detected_since: date | None = None  # first month of that run
    horizon: Horizon | None = None  # which horizon makes the call; None without a call
    drift_points: float | None = None  # Theil-Sen slope x drift_months; None when not measurable
    drift_months: int | None = None  # months behind drift_points (long_min_months..long_horizon)


@dataclass(frozen=True)
class EntityMonth:
    """Everything computed for one entity-month, before serialisation."""

    row: PanelRow
    pillars: Mapping[str, PillarResult]  # all PILLAR_KEYS
    parts: ScoreParts
    trajectory: Trajectory


@dataclass(frozen=True)
class SuppressedBy:
    reason: str  # one of SUPPRESSION_REASONS
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
    trend: Trend  # v1 view of trajectory.direction; perimeter_shift reads as stable
    persistence_months: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    drivers: list[Driver]
    detected_since: date | None
    feature_version: str = FEATURE_VERSION
    dataset_hash: str

    # v2
    entity_kind: EntityKind = "company"
    group_id: str | None = None
    band: str | None = None
    size_band: str | None = None
    level: float | None = None
    base: float | None = None
    pillars: dict[str, float | None] = Field(default_factory=dict)
    weights_effective: dict[str, float | None] = Field(default_factory=dict)
    contributions: dict[str, float | None] = Field(default_factory=dict)
    penalty: float = 0.0
    cap_adjustment: float = 0.0
    caps_fired: list[str] = Field(default_factory=list)
    branch: str = BRANCH_NONE
    feed_live: bool = True
    carried_from: date | None = None
    confidence_label: str | None = None
    confidence_parts: ConfidenceParts | None = None
    delta_parts: DeltaParts | None = None
    trajectory: Trajectory | None = None
    gates: dict[str, list[str]] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    abstained: bool = False
    abstain_reason: str | None = None
    unlock_hint: str | None = None
    months_observed: int = 0
    perimeter_changed: bool = False
    series: dict[str, float | None] = Field(default_factory=dict)
    engine_version: str = ENGINE_VERSION
    params_hash: str = ""

    # deprecated v1 fields, kept so existing readers do not break
    observed_score: float = Field(ge=0, le=100)  # = level
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
    "band": pl.String,
    "size_band": pl.String,
    "level": pl.Float64,
    "base": pl.Float64,
    "pillars": _PILLAR_STRUCT,
    "weights_effective": _PILLAR_STRUCT,
    "contributions": _PILLAR_STRUCT,
    "penalty": pl.Float64,
    "cap_adjustment": pl.Float64,
    "caps_fired": pl.List(pl.String),
    "branch": pl.String,
    "feed_live": pl.Boolean,
    "carried_from": pl.Date,
    "confidence": pl.Float64,
    "confidence_label": pl.String,
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
            "horizon": pl.String,
            "drift_points": pl.Float64,
            "drift_months": pl.Int64,
        }
    ),
    "gates": pl.Struct({key: pl.List(pl.String) for key in PILLAR_KEYS}),
    "flags": pl.List(pl.String),
    "abstained": pl.Boolean,
    "abstain_reason": pl.String,
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
