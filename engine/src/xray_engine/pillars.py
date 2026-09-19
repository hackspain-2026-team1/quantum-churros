"""Five pillars, 0-100, from fixed domain anchors. Pure: no I/O, no frames.

Every function reads one ``PanelRow`` and ``Params`` and returns a
``PillarResult`` whose ``inputs`` carry exactly ``PILLAR_INPUT_KEYS[key]``.
``score`` is None when the pillar is not observable; the reason goes to
``gates``. Missing data lowers confidence in the aggregate, never the score.
Money only enters through ratios, so scores are invariant to the money scale.
At this stage ``score == raw_score``; ``smooth_pillars`` applies the EWMA.
"""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import PanelRow, Params, PillarResult


def pillar_liquidity(
    row: PanelRow, p: Params, group_row: PanelRow | None = None
) -> PillarResult:
    """Liquidity (anchors ``liquidity``).

    ``daily_outflow = op_outflow_median_3m / days_per_month``;
    ``buffer_days = (cash + headroom) / daily_outflow`` at month end and at the
    intra-month minimum, winsorised with ``winsor["buffer_days"]``;
    ``score = month_end_weight * A(end) + intra_min_weight * A(min)``.
    When ``row.swept_subsidiary`` and ``group_row`` is given, everything is
    computed from ``group_row`` and the gate ``inherited_from_group`` is added.
    None with gate ``no_cash_anchor`` (cash is None) or ``no_outflow``
    (median outflow missing or not positive).
    """
    raise NotImplementedError


def pillar_payments(row: PanelRow, p: Params) -> PillarResult:
    """Payments to suppliers, AP due-cohorts (anchors ``payments``).

    ``days = (n * ap_days_beyond_terms + k * prior) / (n + k)`` with
    ``n = ap_cohort_n``, ``k = shrinkage_pseudo_count`` and
    ``prior = prior_days["payments"]``; winsorised with
    ``winsor["days_beyond_terms"]``; ``score = A(days)``.
    None, first gate that applies: ``no_invoices``, ``invoice_burn_in``
    (``invoice_months_observed < burn_in_months``), ``stamped_regime``
    (``ap_stamped_share > stamped_share_max``), ``few_settlements``
    (``ap_settlements_6m < min_settlements``), ``empty_cohort``.
    """
    raise NotImplementedError


def pillar_collections(row: PanelRow, p: Params) -> PillarResult:
    """Collections from customers: same as payments on the ``ar_*`` columns."""
    raise NotImplementedError


def pillar_activity(row: PanelRow, p: Params) -> PillarResult:
    """Activity (anchors ``activity``).

    Each value of ``lfl_op_inflow_12m`` is divided by the month-of-year factor
    of its calendar month. ``ratio = sum(last recent_months) / (recent_months *
    median(non-null values of the base_months before))``, winsorised with
    ``winsor["activity_ratio"]``. None with gate ``short_history``
    (``months_observed < min_months_observed``) or ``no_base`` (fewer than
    ``min_base_months`` base values, or a base median that is not positive).
    """
    raise NotImplementedError


def pillar_debt(row: PanelRow, p: Params) -> PillarResult:
    """Debt (anchors ``debt_dscr`` and ``debt_utilisation``).

    No debt products, no debt service and no revolving limit: ``neutral_score``
    with gate ``no_debt``. Else blend of
    ``dscr = (op_inflow_12m - (op_outflow_12m - interest_12m)) / debt_service_12m``
    (when debt service > 0) and ``utilisation = drawn / granted`` (when
    granted > 0), both winsorised, weighted by ``dscr_weight`` and
    ``utilisation_weight``; a single available side takes the full weight
    (gates ``dscr_only`` / ``utilisation_only``). Debt products without any
    observable side: ``neutral_score`` with gate ``no_debt``.
    """
    raise NotImplementedError


def compute_pillars(
    row: PanelRow, p: Params, group_row: PanelRow | None = None
) -> dict[str, PillarResult]:
    """All five pillars, keyed and ordered by ``PILLAR_KEYS``. ``group_row`` is
    the group row of the same month, used only by the liquidity inheritance."""
    raise NotImplementedError


def smooth_pillars(
    current: Mapping[str, PillarResult],
    previous: Mapping[str, float | None] | None,
    p: Params,
) -> dict[str, PillarResult]:
    """EWMA on P_k, never on the score.

    ``score = alpha * raw_score + (1 - alpha) * previous[k]`` when both exist,
    else ``raw_score``. ``previous`` holds the smoothed scores of month t-1
    (None on the first month). A pillar that is None stays None.
    """
    raise NotImplementedError
