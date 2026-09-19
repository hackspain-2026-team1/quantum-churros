"""Direction and nature of the level, outside the score arithmetic. Pure, past-only.

The trajectory of month t reads ``history[-1]`` (month t) and earlier items
only, so a verdict never changes when later months arrive.
"""

from __future__ import annotations

from collections.abc import Sequence

from .contracts import Params, ScoreParts, Trajectory


def own_sigma(history: Sequence[ScoreParts], p: Params) -> float:
    """Standard deviation of the monthly changes of ``level_raw`` over the
    consecutive months of ``history``, floored at ``sigma_floor``; the floor
    alone with fewer than three changes."""
    raise NotImplementedError


def trajectory(history: Sequence[ScoreParts], p: Params) -> Trajectory:
    """Verdict for the last month of ``history`` (ascending, one entity).

    Not available (``available=False``, direction stable):
      ``short_history``    when ``months_observed < min_months_observed`` or
                           month ``t - horizon_months`` is not in history;
      ``perimeter_change`` when ``months_since_perimeter_change`` is not None
                           and ``<= perimeter_quiet_months``.
    Else ``delta3 = level_raw(t) - level_raw(t - horizon)``, ``sigma =
    own_sigma``, ``delta3_sigma = delta3 / sigma``. Direction is improving or
    deteriorating when ``|delta3| >= min_delta_points`` and ``|delta3_sigma| >=
    min_sigma_multiple``, else stable.
    ``pillars_moved``: pillars available at both ends whose score moved at
    least ``pillar_move_points`` in the direction of ``delta3``.
    Nature: ``structural`` when the same non-stable direction held on the
    previous ``structural_consecutive_months - 1`` months too, at least
    ``structural_min_pillars`` pillars moved and ``structural_required_pillar``
    is one of them. A non-stable month that is not structural is
    ``shock_pending`` (``shock_pending=True``, ``shock_month = t``). On a
    stable month, ``bump`` when a shock_pending month within the last
    ``bump_revert_months`` has been undone by at least ``bump_revert_fraction``
    (``shock_month`` = that month); else None.
    ``persistence_months`` counts the consecutive months, ending at t, with the
    current non-stable direction (0 when stable); ``detected_since`` is the
    first month of that run.
    """
    raise NotImplementedError
