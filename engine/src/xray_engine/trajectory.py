"""Direction and nature of the score, outside the score arithmetic. Pure, past-only.

The trajectory of month t reads ``history[-1]`` (month t) and earlier items
only, so a verdict never changes when later months arrive. ``history`` holds
the final ``ScoreParts`` of one entity, carried months included; their score is
the last live one, so a stale spell is a flat segment. ``trajectories`` gives
the verdict of every month in one forward pass.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

from .contracts import PILLAR_KEYS, Params, ScoreParts, Trajectory

_CALLS = ("improving", "deteriorating")
_INHERITED = "inherited_from_group"


def _shift(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _available(parts: ScoreParts) -> list[str]:
    return [key for key in PILLAR_KEYS if parts.pillar_scores.get(key) is not None]


def _like_for_like(now: ScoreParts, then: ScoreParts, p: Params) -> float | None:
    """Move of the pillars measured the same way at both ends, with the nominal
    weights renormalised over them. None when the whole coverage branch is
    comparable: the score delta is already like for like."""
    keys = [key for key in _available(now) if then.pillar_scores.get(key) is not None]
    onset = p.activity.min_months_observed
    if (now.months_observed >= onset) != (then.months_observed >= onset):
        # momentum came online in between: activity is not the same measure
        keys = [key for key in keys if key != "activity"]
    if (_INHERITED in now.flags) != (_INHERITED in then.flags):
        # own cash at one end, the cash of the group at the other
        keys = [key for key in keys if key != "liquidity"]
    if keys == _available(now) == _available(then):
        return None
    total = sum(p.weights[key] for key in keys)
    if not keys or total <= 0:
        return 0.0
    return sum(
        p.weights[key] / total * (now.pillar_scores[key] - then.pillar_scores[key]) for key in keys
    )


def own_sigma(history: Sequence[ScoreParts], p: Params) -> float:
    """Sample standard deviation of the month-on-month score changes, floored
    at ``sigma_floor``.

    Only changes between consecutive calendar months that are both live and
    not later than ``t - horizon_months`` count: the window under test does not
    inflate its own noise. A change between two months that are not measured
    the same way (see the like-for-like guard of ``trajectory``) is a change of
    composition, not noise, and is left out. The floor alone with fewer than
    three changes.
    """
    cfg = p.trajectory
    if not history:
        return cfg.sigma_floor
    limit = _shift(history[-1].month, -cfg.horizon_months)
    changes = [
        after.score - before.score
        for before, after in zip(history, history[1:])
        if after.month <= limit
        and before.feed_live
        and after.feed_live
        and _shift(before.month, 1) == after.month
        and _like_for_like(after, before, p) is None
    ]
    if len(changes) < 3:
        return cfg.sigma_floor
    mean = math.fsum(changes) / len(changes)
    variance = math.fsum((change - mean) ** 2 for change in changes) / (len(changes) - 1)
    return max(cfg.sigma_floor, math.sqrt(variance))


def _verdict(
    history: Sequence[ScoreParts],
    position: int,
    verdicts: Sequence[Trajectory],
    index: dict[date, int],
    p: Params,
) -> Trajectory:
    """Verdict of ``history[position]`` from earlier items and their verdicts."""
    cfg = p.trajectory
    now = history[position]
    if not now.feed_live:
        return Trajectory(available=False, reason="stale_feed")
    compared = _shift(now.month, -cfg.horizon_months)
    base = index.get(compared)
    if position + 1 < cfg.min_scored_months or base is None or base >= position:
        return Trajectory(available=False, reason="short_history")
    then = history[base]
    delta3 = now.score - then.score
    sigma = own_sigma(history[: position + 1], p)
    threshold = max(cfg.min_delta_points, cfg.min_sigma_multiple * sigma)

    echo = any(
        verdicts[item].nature == "bump" and verdicts[item].shock_month == compared
        for item in range(base + 1, position)
    )
    direction = "stable"
    if "perimeter_shift" in now.flags:
        direction = "perimeter_shift"
    elif not echo and abs(delta3) >= threshold:
        own = _like_for_like(now, then, p)
        if own is None or (own * delta3 > 0 and abs(own) >= threshold):
            direction = "improving" if delta3 > 0 else "deteriorating"

    moved = tuple(
        key
        for key in _available(now)
        if then.pillar_scores.get(key) is not None
        and abs(now.pillar_scores[key] - then.pillar_scores[key]) >= cfg.pillar_move_points
        and (now.pillar_scores[key] - then.pillar_scores[key]) * delta3 > 0
    )
    common = dict(
        available=True,
        reason=None,
        direction=direction,
        delta3=delta3,
        sigma=sigma,
        delta3_sigma=delta3 / sigma,
        compared_to=compared,
        pillars_moved=moved,
    )

    if direction in _CALLS:
        run, first = 1, now.month
        for item in range(position - 1, -1, -1):
            if history[item].month != _shift(first, -1) or verdicts[item].direction != direction:
                break
            run, first = run + 1, history[item].month
        if run < cfg.structural_consecutive_months:
            return Trajectory(
                **common, nature="shock_pending", shock_pending=True, shock_month=first,
                persistence_months=run, detected_since=first,
            )
        return Trajectory(
            **common, nature="structural", persistence_months=run, detected_since=first
        )

    if direction == "stable":
        for back in range(1, cfg.bump_revert_months + 1):
            item = position - back
            if item < 0 or history[item].month != _shift(now.month, -back):
                break
            spike = verdicts[item].delta3
            if verdicts[item].nature != "shock_pending" or not spike:
                continue
            undone = (history[item].score - now.score) * (1.0 if spike > 0 else -1.0)
            if undone >= cfg.bump_revert_fraction * abs(spike):
                return Trajectory(**common, nature="bump", shock_month=history[item].month)
    return Trajectory(**common)


def trajectories(history: Sequence[ScoreParts], p: Params) -> list[Trajectory]:
    """Verdict of every prefix of ``history`` in one forward pass:
    ``trajectories(h, p)[i] == trajectory(h[: i + 1], p)``."""
    index = {item.month: position for position, item in enumerate(history)}
    verdicts: list[Trajectory] = []
    for position in range(len(history)):
        verdicts.append(_verdict(history, position, verdicts, index, p))
    return verdicts


def trajectory(history: Sequence[ScoreParts], p: Params) -> Trajectory:
    """Verdict for the last month of ``history`` (ascending, one entity).

    Not available (``available=False``, direction stable, nature None), first
    reason that applies:
      ``stale_feed``    month t is not live;
      ``short_history`` fewer than ``min_scored_months`` items, or month
                        ``t - horizon_months`` is not in history.
    Else ``delta3 = score(t) - score(t - horizon)``, ``sigma = own_sigma``,
    ``delta3_sigma = delta3 / sigma``, ``compared_to = t - horizon`` and
    ``pillars_moved`` = pillars available at both ends whose score moved at
    least ``pillar_move_points`` in the direction of ``delta3`` (descriptive).
    Direction, first rule that applies:
      ``perimeter_shift`` when month t carries the flag ``perimeter_shift``
        (accounts connected in the last three months bring too much of the
        inflow): no improvement or deterioration call, nature None;
      stable when ``compared_to`` is the ``shock_month`` of an earlier ``bump``
        verdict: a spike that reverted is not a base to compare against, so it
        leaves no echo three months later;
      improving / deteriorating when ``|delta3| >= max(min_delta_points,
        min_sigma_multiple * sigma)``; else stable.
    Like-for-like guard on that call: when the two ends are not measured the
    same way (a pillar is available at one end only; the activity momentum
    came online in between, i.e. ``months_observed`` crossed
    ``activity.min_months_observed``; the flag ``inherited_from_group`` is on
    one end only), the pillars that are comparable at both ends, with the
    nominal weights renormalised over them, must move in the same direction by
    at least the same threshold; else stable. A pillar that appears, drops out
    or changes its source moves the level, not the health of the entity.
    ``persistence_months`` counts the consecutive months, ending at t, with the
    same improving / deteriorating direction (0 otherwise); past verdicts are
    those of the prefixes of ``history``. ``detected_since`` is the first month
    of that run.
    Nature on an improving / deteriorating month: ``shock_pending`` while the
    run is shorter than ``structural_consecutive_months`` (``shock_pending=
    True``, ``shock_month`` = first month of the run), ``structural`` from
    there on. On a stable month: ``bump`` when a month of the last
    ``bump_revert_months`` was ``shock_pending`` and the score has since undone
    at least ``bump_revert_fraction`` of the ``delta3`` of that month
    (``shock_month`` = that month); else None.
    """
    if not history:
        return Trajectory(available=False, reason="short_history")
    return trajectories(history, p)[-1]
