"""Non-compensatory aggregate with an exact additive explanation. Pure.

Branch = pillars whose score is not None; ``w_ef`` = nominal weights
renormalised over the branch; ``B_k`` = ``p.reference.medians``.

  level_weighted   = sum(w_ef * P_k)
  penalty          = min(lam * max(0, tau - min P_k), level_weighted)
  cap_adjustment   = max(0, level_weighted - penalty - ceiling)
  level            = level_weighted - penalty - cap_adjustment
  score            = clip(level, 0, 100)
  base             = sum(w_ef * B_k)                 (one base per branch)
  contributions[k] = w_ef[k] * (P_k - B_k)

so ``score == base + sum(contributions) - penalty - cap_adjustment`` to 1e-9.
The penalty floor keeps ``level >= 0``, hence the clip never binds and the
identity is exact. Confidence is reported next to the score and never changes
it; nothing is smoothed. On the empty branch ``level_weighted = base =
sum(w_k * B_k)`` with the nominal weights and the month is abstained.
Penalty and caps apply only on a live feed. A stale month is scored here with
both off; ``scoring.carry_forward`` then copies the last live explanation.
"""

from __future__ import annotations

from collections.abc import Mapping

from .contracts import (
    ABSTAIN_REASONS,
    BRANCH_NONE,
    CAP_KEYS,
    CAP_TEXTS,
    PILLAR_KEYS,
    PILLAR_LABELS,
    SCORE_FLAGS,
    UNLOCK_HINTS,
    ConfidenceParts,
    DeltaParts,
    Driver,
    PanelRow,
    Params,
    PillarResult,
    ScoreParts,
    band_of,
)
from .pillars import format_es, pillar_note

PENALTY_LABEL = "Penalización por pilar débil"
CAP_LABEL = "Tope"
PENALTY_TEMPLATE = (
    "El pilar más débil ({pillar}, {score} puntos) queda por debajo de {tau}: resta {penalty} puntos."
)


def _available(pillars: Mapping[str, PillarResult]) -> list[str]:
    return [key for key in PILLAR_KEYS if key in pillars and pillars[key].score is not None]


def live_feed(row: PanelRow, p: Params) -> bool:
    """False (stale) when any of these holds, else True:

      ``rows_3m == 0``;
      a group row with ``zero_row_month`` (``group_zero_row_month_is_stale``);
      the baseline is defined and ``rows_3m / (recent_months *
      rows_base_median) < threshold``.
    The baseline is undefined when ``rows_base_median`` is None or not positive
    or ``rows_base_months < min_base_months``: short history reads as live.
    """
    feed = p.live_feed
    if (row.rows_3m or 0) <= 0:
        return False
    if feed.group_zero_row_month_is_stale and row.entity_kind == "group" and row.zero_row_month:
        return False
    base = row.rows_base_median
    if base is None or not base > 0 or (row.rows_base_months or 0) < feed.min_base_months:
        return True
    return row.rows_3m / (feed.recent_months * base) >= feed.threshold


def confidence_parts(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params, feed_live: bool
) -> ConfidenceParts:
    """``history = C.history(months_observed)``;
    ``coverage = C.coverage(sum of nominal weights of available pillars)``;
    ``quality`` = ``quality_dash(dash_share) * quality_fx_excluded(
    fx_excluded_share) * quality_orphan(orphan_product_share) *
    quality_no_cash_anchor(no_cash_anchor_share)`` (a None share counts as
    factor 1), times ``limit_assumed_constant_factor`` when the row carries
    that flag, times ``stale_feed_factor`` when the feed is not live.
    Each part lies in [0, 1].
    """
    tables = p.confidence
    covered = sum(p.weights[key] for key in _available(pillars))
    quality = 1.0
    for table, share in (
        (tables.quality_dash, row.dash_share),
        (tables.quality_fx_excluded, row.fx_excluded_share),
        (tables.quality_orphan, row.orphan_product_share),
        (tables.quality_no_cash_anchor, row.no_cash_anchor_share),
    ):
        if share is not None:
            quality *= table(share)
    if row.limit_assumed_constant:
        quality *= tables.limit_assumed_constant_factor
    if not feed_live:
        quality *= tables.stale_feed_factor
    return ConfidenceParts(
        history=tables.history(row.months_observed or 0),
        coverage=tables.coverage(covered),
        quality=quality,
    )


def confidence_label(value: float, p: Params) -> str:
    """``high`` from ``label_high_min``, ``medium`` from ``label_medium_min``, else ``low``."""
    if value >= p.confidence.label_high_min:
        return "high"
    return "medium" if value >= p.confidence.label_medium_min else "low"


def abstention(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params, feed_live: bool
) -> tuple[str | None, str | None]:
    """(reason, unlock hint); (None, None) when the engine does not abstain.

    First of ``ABSTAIN_REASONS`` that applies: ``stale_feed`` (feed not live),
    ``short_history`` (``months_observed < abstention.min_months_observed``),
    ``no_bank_pillar`` (none of ``abstention.bank_pillars`` is available).
    The hint is ``UNLOCK_HINTS[reason]`` with ``{months}`` filled in. Confidence
    plays no part. The number is always emitted.
    """
    available = _available(pillars)
    applies = {
        "stale_feed": not feed_live,
        "short_history": (row.months_observed or 0) < p.abstention.min_months_observed,
        "no_bank_pillar": not any(key in available for key in p.abstention.bank_pillars),
    }
    for reason in ABSTAIN_REASONS:
        if applies[reason]:
            return reason, UNLOCK_HINTS[reason].format(months=p.abstention.min_months_observed)
    return None, None


def score_flags(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params, feed_live: bool
) -> tuple[str, ...]:
    """Flags of the month, in ``SCORE_FLAGS`` order: ``stale_feed`` (not live),
    ``perimeter_changed``, ``perimeter_shift`` (``new_perimeter_inflow_share_3m
    > trajectory.perimeter_shift_share``), ``short_history`` (``months_observed
    < trajectory.min_scored_months``), ``limit_assumed_constant``,
    ``debt_snapshot`` (``has_debt_products``), ``fx_excluded`` and
    ``orphan_products`` and ``no_cash_anchor`` (share > 0),
    ``no_external_revenue``, ``inherited_from_group`` (liquidity gate)."""

    def above(share: float | None, floor: float = 0.0) -> bool:
        return share is not None and share > floor

    liquidity = pillars.get("liquidity")
    raised = {
        "stale_feed": not feed_live,
        "perimeter_changed": bool(row.perimeter_changed),
        "perimeter_shift": above(row.new_perimeter_inflow_share_3m, p.trajectory.perimeter_shift_share),
        "short_history": (row.months_observed or 0) < p.trajectory.min_scored_months,
        "limit_assumed_constant": bool(row.limit_assumed_constant),
        "debt_snapshot": bool(row.has_debt_products),
        "fx_excluded": above(row.fx_excluded_share),
        "orphan_products": above(row.orphan_product_share),
        "no_cash_anchor": above(row.no_cash_anchor_share),
        "no_external_revenue": bool(row.no_external_revenue),
        "inherited_from_group": liquidity is not None and "inherited_from_group" in liquidity.gates,
    }
    return tuple(flag for flag in SCORE_FLAGS if raised[flag])


def _caps_holding(
    pillars: Mapping[str, PillarResult], row: PanelRow, p: Params
) -> list[tuple[float, str]]:
    """(ceiling, rule) of every cap rule that holds, strictest first."""
    caps = p.caps
    holding: list[tuple[float, str]] = []
    blind_share = row.no_cash_anchor_share or 0.0
    liquidity = pillars.get("liquidity")
    # a swept subsidiary shows the cash of the group: its own balance is no signal
    own_cash = liquidity is None or "inherited_from_group" not in liquidity.gates
    if (
        own_cash
        and (row.neg_liquidity_months_6m or 0) >= caps.negative_liquidity_min_months
        and blind_share <= caps.negative_liquidity_max_no_anchor_share
    ):
        holding.append((caps.negative_liquidity_ceiling, "negative_liquidity"))
    payments = pillars["payments"].score if "payments" in pillars else None
    if payments is not None and payments < caps.weak_payments_threshold:
        holding.append((caps.weak_payments_ceiling, "weak_payments"))
    return sorted(holding, key=lambda item: (item[0], CAP_KEYS.index(item[1])))


def aggregate(
    pillars: Mapping[str, PillarResult],
    row: PanelRow,
    p: Params,
    group_row: PanelRow | None = None,
) -> ScoreParts:
    """One entity-month -> ``ScoreParts`` (see the module identities).

    ``group_row`` is the row ``compute_pillars`` received; it only names the
    ``size_band`` behind an inherited liquidity.

    Caps (live feed only; the lowest ceiling binds, ``caps_fired`` lists every
    rule that holds, strictest first):
      negative_liquidity: ``neg_liquidity_months_6m >= min_months`` and
        ``no_cash_anchor_share`` (None reads as 0) ``<= max_no_anchor_share``;
        never when the liquidity pillar is ``inherited_from_group`` (the own
        balance of a swept subsidiary is no signal; the group row carries it);
      weak_payments: payments available and ``< weak_payments_threshold``.
    Caps do not need a pillar: they also hold on the empty branch.
    ``level = score``, ``carried_from = None``, ``band = band_of(score,
    p.bands)``. ``abstained``, ``abstain_reason`` and ``unlock_hint`` come from
    ``abstention``; ``flags`` from ``score_flags``. ``weights_effective`` and
    ``contributions`` list the available pillars in ``PILLAR_KEYS`` order.
    ``size_band`` is the band whose liquidity table was read: the one of
    ``group_row`` when the liquidity is ``inherited_from_group``, else the one
    of ``row``.
    """
    available = _available(pillars)
    medians = p.reference.medians
    if available:
        total = sum(p.weights[key] for key in available)
        weights = {key: p.weights[key] / total for key in available}
        level_weighted = sum(weights[key] * pillars[key].score for key in available)
        base = sum(weights[key] * medians[key] for key in available)
    else:  # nothing observable: the reference level with the nominal weights
        weights = {}
        level_weighted = base = sum(p.weights[key] * medians[key] for key in PILLAR_KEYS)
    contributions = {key: weights[key] * (pillars[key].score - medians[key]) for key in available}

    feed_live = live_feed(row, p)
    penalty = cap_adjustment = 0.0
    holding: list[tuple[float, str]] = []
    if feed_live:
        if available:
            weakest = min(pillars[key].score for key in available)
            penalty = min(p.penalty.lam * max(0.0, p.penalty.tau - weakest), level_weighted)
        holding = _caps_holding(pillars, row, p)
        if holding:
            cap_adjustment = max(0.0, level_weighted - penalty - holding[0][0])
    score = min(100.0, max(0.0, level_weighted - penalty - cap_adjustment))

    confidence = confidence_parts(pillars, row, p, feed_live)
    reason, hint = abstention(pillars, row, p, feed_live)
    liquidity = pillars.get("liquidity")
    inherited = liquidity is not None and "inherited_from_group" in liquidity.gates
    banded = group_row if inherited and group_row is not None else row
    return ScoreParts(
        month=row.month,
        months_observed=row.months_observed or 0,
        months_since_perimeter_change=row.months_since_perimeter_change,
        branch="+".join(available) if available else BRANCH_NONE,
        pillar_scores={key: pillars[key].score if key in pillars else None for key in PILLAR_KEYS},
        weights_effective=weights,
        level_weighted=level_weighted,
        penalty=penalty,
        cap_adjustment=cap_adjustment,
        caps_fired=tuple(rule for _, rule in holding),
        base=base,
        contributions=contributions,
        score=score,
        band=band_of(score, p.bands),
        level=score,
        feed_live=feed_live,
        carried_from=None,
        confidence=confidence.value,
        confidence_parts=confidence,
        confidence_label=confidence_label(confidence.value, p),
        flags=score_flags(pillars, row, p, feed_live),
        abstained=reason is not None,
        abstain_reason=reason,
        unlock_hint=hint,
        size_band=banded.size_band,
    )


def delta_parts(current: ScoreParts, previous: ScoreParts) -> DeltaParts:
    """Exact month-on-month decomposition, including the ``base`` term.

    ``contributions`` has every pillar present on either side; a missing side
    counts as 0. ``score == base + sum(contributions) - penalty -
    cap_adjustment`` to 1e-9. Works on carried months too: their explanation
    block is a verbatim copy, so every term of the delta is 0.
    """
    keys = [
        key for key in PILLAR_KEYS if key in current.contributions or key in previous.contributions
    ]
    return DeltaParts(
        score=current.score - previous.score,
        base=current.base - previous.base,
        contributions={
            key: current.contributions.get(key, 0.0) - previous.contributions.get(key, 0.0)
            for key in keys
        },
        penalty=current.penalty - previous.penalty,
        cap_adjustment=current.cap_adjustment - previous.cap_adjustment,
    )


def explain(
    parts: ScoreParts, pillars: Mapping[str, PillarResult], p: Params
) -> list[Driver]:
    """Drivers in ``PILLAR_KEYS`` order for available pillars, then ``penalty``
    and ``cap`` when non-zero (negative contributions).

    ``contribution`` = score points; ``observed`` = P_k; ``baseline`` = B_k;
    ``label`` and ``evidence`` in Spanish, built from ``PillarResult.inputs``;
    ``source = "observable"``. Penalty: ``observed`` = weakest pillar,
    ``baseline`` = tau. Cap: ``observed`` = level before the cap, ``baseline``
    = binding ceiling.
    """
    drivers: list[Driver] = []
    scored = [key for key in PILLAR_KEYS if key in parts.contributions]
    for key in scored:
        value = parts.contributions[key]
        direction = "positive" if value > 0 else "negative" if value < 0 else "neutral"
        note = pillar_note(pillars[key], p) if key in pillars else PILLAR_LABELS[key]
        drivers.append(
            Driver(
                feature=key,
                label=PILLAR_LABELS[key],
                direction=direction,
                contribution=value,
                observed=parts.pillar_scores[key],
                baseline=p.reference.medians[key],
                evidence=note,
            )
        )
    if parts.penalty > 0 and scored:
        weakest = min(scored, key=lambda key: parts.pillar_scores[key])
        text = PENALTY_TEMPLATE.format(
            pillar=PILLAR_LABELS[weakest].lower(),
            score=format_es(parts.pillar_scores[weakest], 1),
            tau=format_es(p.penalty.tau),
            penalty=format_es(parts.penalty, 1),
        )
        drivers.append(
            Driver(
                feature="penalty",
                label=PENALTY_LABEL,
                direction="negative",
                contribution=-parts.penalty,
                observed=parts.pillar_scores[weakest],
                baseline=p.penalty.tau,
                evidence=text,
            )
        )
    if parts.cap_adjustment > 0 and parts.caps_fired:
        rule = parts.caps_fired[0]
        ceilings = {
            "negative_liquidity": p.caps.negative_liquidity_ceiling,
            "weak_payments": p.caps.weak_payments_ceiling,
        }
        drivers.append(
            Driver(
                feature="cap",
                label=CAP_LABEL,
                direction="negative",
                contribution=-parts.cap_adjustment,
                observed=parts.level_weighted - parts.penalty,
                baseline=ceilings[rule],
                evidence=CAP_TEXTS[rule],
            )
        )
    return drivers
