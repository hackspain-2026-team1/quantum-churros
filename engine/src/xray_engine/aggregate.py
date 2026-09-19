"""Non-compensatory aggregate with an exact additive explanation. Pure.

Branch = pillars whose score is not None; ``w_ef`` = nominal weights
renormalised over the branch; ``B_k`` = ``p.reference.medians``.

  level_weighted       = sum(w_ef * P_k)                     (50 on the empty branch)
  penalty_level        = min(lam * max(0, tau - min P_k), level_weighted)
  cap_adjustment_level = max(0, level_weighted - penalty_level - ceiling)
  level_raw            = level_weighted - penalty_level - cap_adjustment_level
  confidence           = c_history * c_coverage * c_quality
  score                = 50 + confidence * (level_raw - 50)
  base                 = 50 + confidence * (sum(w_ef * B_k) - 50)
  contributions[k]     = confidence * w_ef[k] * (P_k - B_k)
  penalty, cap_adjustment = confidence * (their level counterparts)

so ``score == base + sum(contributions) - penalty - cap_adjustment`` to 1e-9.
Penalty and caps apply only on a live feed. The penalty floor keeps
``level_raw >= 0``, hence the score inside [0, 100].
"""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import (
    ConfidenceParts,
    DeltaParts,
    Driver,
    PanelRow,
    Params,
    PillarResult,
    ScoreParts,
)


def live_feed(row: PanelRow, p: Params) -> bool:
    """``rows_3m / (recent_months * rows_base_median) >= threshold``.

    True when the base is unknown (``rows_base_median`` None or not positive,
    or ``rows_base_months < min_base_months``): no evidence of a dead feed.
    """
    raise NotImplementedError


def confidence_parts(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params, feed_live: bool
) -> ConfidenceParts:
    """``history = C.history(months_observed)``;
    ``coverage = C.coverage(sum of nominal weights of available pillars)``;
    ``quality`` = product of the three quality tables (a None input counts as
    factor 1, except ``cash_anchor_coverage`` None which reads as 0) times
    ``stale_feed_factor`` when the feed is not live. Each part lies in [0, 1].
    """
    raise NotImplementedError


def aggregate(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params
) -> ScoreParts:
    """One entity-month -> ``ScoreParts`` (see the module identities).

    Caps (live feed only; the lowest ceiling binds, ``caps_fired`` lists every
    rule that holds, strictest first):
      negative_liquidity: ``neg_liquidity_months_6m >= min_months``
      lines_fully_drawn:  ``granted > 0`` and ``drawn / granted >= threshold``
      weak_pillar:        any of ``weak_pillars`` available and below threshold
    Flags: ``stale_feed``, ``perimeter_changed``, ``perimeter_quiet`` (within
    ``trajectory.perimeter_quiet_months`` of a change), ``short_history``,
    ``granted_assumed_constant`` (granted > 0), ``debt_snapshot``
    (n_debt_products > 0), ``fx_excluded`` (share > 0), ``inherited_from_group``.
    ``abstained = confidence < abstain_below``; only then ``unlock_hint`` is
    set and says, in Spanish, what data would lift it (None otherwise). The
    number is always emitted. ``weights_effective`` and ``contributions`` list
    the available pillars in ``PILLAR_KEYS`` order.
    """
    raise NotImplementedError


def delta_parts(current: ScoreParts, previous: ScoreParts) -> DeltaParts:
    """Exact month-on-month decomposition, including the ``base`` term.

    ``contributions`` has every pillar present on either side; a missing side
    counts as 0. ``score == base + sum(contributions) - penalty -
    cap_adjustment`` to 1e-9.
    """
    raise NotImplementedError


def explain(
    parts: ScoreParts, pillars: Mapping[str, PillarResult], p: Params
) -> list[Driver]:
    """Drivers in ``PILLAR_KEYS`` order for available pillars, then ``penalty``
    and ``cap`` when non-zero (negative contributions).

    ``contribution`` = score points; ``observed`` = P_k; ``baseline`` = B_k;
    ``label`` and ``evidence`` in Spanish, built from ``PillarResult.inputs``;
    ``source = "observable"``.
    """
    raise NotImplementedError
