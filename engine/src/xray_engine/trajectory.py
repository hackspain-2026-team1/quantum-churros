"""Direction and nature of the score, outside the score arithmetic. Pure, past-only.

The trajectory of month t reads ``history[-1]`` (month t) and earlier items
only, so a verdict never changes when later months arrive. ``history`` holds
the final ``ScoreParts`` of one entity, carried months included; their score is
the last live one, so a stale spell is a flat segment. ``trajectories`` gives
the verdict of every month in one forward pass.

Two horizons make the call. The short one compares month t with month
``t - horizon_months``; the long one (slow-drift detector) fits a Theil-Sen
slope to the live months of the last ``long_horizon`` months that are measured
like month t, so a drift of under a point a month, which never reaches the
short threshold, is still seen. Each horizon needs its own condition to hold
``structural_consecutive_months`` months in a row before the call is
``structural``; until then it is ``shock_pending``. When the two horizons
disagree the recent move makes the call, unconfirmed.
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
    if p.liquidity.segmented and now.size_band != then.size_band:
        # another size band reads another liquidity table
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


def _theil_sen(points: Sequence[tuple[int, float]]) -> float:
    """Median of the pairwise slopes (mean of the two middle ones when even)."""
    slopes = sorted(
        (y1 - y0) / (x1 - x0)
        for index, (x0, y0) in enumerate(points)
        for x1, y1 in points[index + 1:]
    )
    middle = len(slopes) // 2
    return slopes[middle] if len(slopes) % 2 else (slopes[middle - 1] + slopes[middle]) / 2.0


def _drift(
    history: Sequence[ScoreParts], position: int, p: Params
) -> tuple[float, int, ScoreParts] | None:
    """(drift points, months, first month used) of the long window, or None.

    The window holds the live months of ``t - long_horizon + 1 .. t`` measured
    like month t (``_like_for_like`` is None), and stops at the latest month
    flagged ``perimeter_shift``: months before it describe another perimeter.
    With at least ``long_min_months`` of them, ``months`` = calendar months
    from the first one used to t and ``drift = Theil-Sen slope * months``.
    """
    cfg = p.trajectory
    now = history[position]
    oldest = _shift(now.month, 1 - cfg.long_horizon)
    used: list[ScoreParts] = [now]
    for item in reversed(history[:position]):
        if item.month < oldest or "perimeter_shift" in item.flags:
            break
        if item.feed_live and _like_for_like(now, item, p) is None:
            used.append(item)
    if len(used) < cfg.long_min_months:
        return None
    used.reverse()
    points = [(item.month.year * 12 + item.month.month, item.score) for item in used]
    months = points[-1][0] - points[0][0] + 1
    return _theil_sen(points) * months, months, used[0]


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
    shifted = "perimeter_shift" in now.flags
    short = None
    if not shifted and not echo and abs(delta3) >= threshold:
        own = _like_for_like(now, then, p)
        if own is None or (own * delta3 > 0 and abs(own) >= threshold):
            short = "improving" if delta3 > 0 else "deteriorating"
    long = None
    drift = None if shifted else _drift(history, position, p)
    if drift is not None and abs(drift[0]) >= max(cfg.long_threshold, cfg.long_sigma_mult * sigma):
        long = "improving" if drift[0] > 0 else "deteriorating"

    direction, horizon = "stable", None
    conflict = short is not None and long is not None and short != long
    if shifted:
        direction = "perimeter_shift"
    elif conflict:  # the recent move makes the call, unconfirmed while the drift opposes it
        direction, horizon = short, "short"
    elif long is not None and short is None and abs(delta3) >= threshold and (delta3 > 0) != (drift[0] > 0):
        pass  # the score moved the other way beyond the threshold (call vetoed by a guard): no call
    elif long is not None:
        direction, horizon = long, "both" if short == long else "long"
    elif short is not None:
        direction, horizon = short, "short"

    # what moved: against t - horizon, or against the start of the long window
    reference, sign = (drift[2], drift[0]) if horizon == "long" else (then, delta3)
    moved = tuple(
        key
        for key in _available(now)
        if reference.pillar_scores.get(key) is not None
        and abs(now.pillar_scores[key] - reference.pillar_scores[key]) >= cfg.pillar_move_points
        and (now.pillar_scores[key] - reference.pillar_scores[key]) * sign > 0
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
        horizon=horizon,
        drift_points=drift[0] if drift is not None else None,
        drift_months=drift[1] if drift is not None else None,
        drift_call=long,
    )

    if direction in _CALLS:
        run, first = 1, now.month
        for item in range(position - 1, -1, -1):
            if history[item].month != _shift(first, -1) or verdicts[item].direction != direction:
                break
            run, first = run + 1, history[item].month
        # each horizon is confirmed by its own condition, month after month
        held = max(
            _own_run(history, position, verdicts, _short_call, short) if short == direction else 0,
            _own_run(history, position, verdicts, _long_call, long) if long == direction else 0,
        )
        if conflict or held < cfg.structural_consecutive_months:
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
            # a spike is a short-horizon event: a pending drift that fades is not a bump
            if verdicts[item].nature != "shock_pending" or _short_call(verdicts[item]) is None or not spike:
                continue
            undone = (history[item].score - now.score) * (1.0 if spike > 0 else -1.0)
            if undone >= cfg.bump_revert_fraction * abs(spike):
                return Trajectory(**common, nature="bump", shock_month=history[item].month)
    return Trajectory(**common)


def _short_call(verdict: Trajectory) -> str | None:
    return verdict.direction if verdict.horizon in ("short", "both") else None


def _long_call(verdict: Trajectory) -> str | None:
    return verdict.drift_call


def _own_run(history, position, verdicts, call, now_call) -> int:
    """Consecutive calendar months, ending at ``position``, on which one horizon
    made the same call on its own condition."""
    run, month = 1, history[position].month
    for item in range(position - 1, -1, -1):
        if history[item].month != _shift(month, -1) or call(verdicts[item]) != now_call:
            break
        run, month = run + 1, history[item].month
    return run


NOTE_DRIFT_OPPOSES = {
    "improving": "La mejora es reciente: la deriva de los últimos {months} meses todavía apunta a la baja ({points} puntos).",
    "deteriorating": "La caída es reciente: la deriva de los últimos {months} meses todavía apunta al alza ({points} puntos).",
}


def drift_opposes(verdict: Trajectory) -> bool:
    """The long horizon holds its condition against the direction called."""
    return (
        verdict.direction in _CALLS and verdict.drift_call in _CALLS and verdict.drift_call != verdict.direction
    )


def trajectory_note(verdict: Trajectory) -> str | None:
    """Spanish sentence for a verdict whose two horizons disagree, else None."""
    if not verdict.available or not drift_opposes(verdict) or verdict.drift_points is None:
        return None
    points = f"{verdict.drift_points:+.1f}".replace(".", ",")
    return NOTE_DRIFT_OPPOSES[verdict.direction].format(months=verdict.drift_months, points=points)


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
    ``perimeter_shift`` when month t carries the flag ``perimeter_shift``
    (accounts connected in the last three months bring too much of the inflow):
    no improvement or deterioration call on either horizon, nature None.
    Short horizon: improving / deteriorating when ``|delta3| >=
    max(min_delta_points, min_sigma_multiple * sigma)``; never when
    ``compared_to`` is the ``shock_month`` of an earlier ``bump`` verdict (a
    spike that reverted is not a base to compare against, so it leaves no echo
    three months later).
    Like-for-like guard on that call: when the two ends are not measured the
    same way (a pillar is available at one end only; the activity momentum
    came online in between, i.e. ``months_observed`` crossed
    ``activity.min_months_observed``; the flag ``inherited_from_group`` is on
    one end only; ``size_band`` differs, so liquidity reads another table),
    the pillars that are comparable at both ends, with the nominal weights
    renormalised over them, must move in the same direction by at least the
    same threshold; else no call. A pillar that appears, drops out or changes
    its source moves the level, not the health of the entity.
    Long horizon (``_drift``): ``drift_points`` = Theil-Sen slope of the score
    over the live months of the last ``long_horizon`` months measured like
    month t, after the latest ``perimeter_shift`` month, times ``drift_months``
    (calendar months covered); needs ``long_min_months`` such months. It calls
    improving / deteriorating when ``|drift_points| >= max(long_threshold,
    long_sigma_mult * sigma)``. The guard is built in: months measured another
    way never enter the fit.
    ``drift_call`` keeps that call of the long condition on its own.
    ``direction`` is the call of either horizon, else stable; ``horizon`` =
    ``short`` | ``long`` | ``both`` (None without a call). On a conflict (the
    two horizons call opposite signs, e.g. a sharp rebound after a long
    decline) the direction follows the SHORT horizon, ``horizon`` = ``short``,
    and the nature stays ``shock_pending`` while the drift opposes it
    (``trajectory_note`` says so). When the short call was vetoed by a guard
    and the score still moved beyond the threshold against the drift, there is
    no call. ``pillars_moved`` compares with the first month of the long window
    when only the long horizon calls.
    ``persistence_months`` counts the consecutive months, ending at t, with the
    same improving / deteriorating direction (0 otherwise); past verdicts are
    those of the prefixes of ``history``. ``detected_since`` is the first month
    of that run.
    Nature on an improving / deteriorating month: ``structural`` when one of
    the horizons behind the call has held its OWN condition, same sign, for
    ``structural_consecutive_months`` consecutive months (the long horizon is
    confirmed exactly like the short one: a drift that first appears in month t
    is not structural until it is still there at t + 1); ``shock_pending``
    until then and on every conflict month (``shock_pending=True``,
    ``shock_month`` = first month of the run).
    On a stable month: ``bump`` when a month of the last
    ``bump_revert_months`` was a ``shock_pending`` call of the short horizon
    and the score has since undone at least ``bump_revert_fraction`` of the
    ``delta3`` of that month (``shock_month`` = that month); else None.
    """
    if not history:
        return Trajectory(available=False, reason="short_history")
    return trajectories(history, p)[-1]
