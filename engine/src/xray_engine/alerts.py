"""Alert inbox: what fires, what is suppressed and why. Pure.

Kinds: ``deterioration_structural``, ``improvement_structural``,
``level_critical``, ``cap_fired``, ``stale_feed``.
States: ``fired``; ``suppressed`` (inside the quiet window that follows a
perimeter change); ``abstained`` (confidence below the abstention threshold).
A non-fired alert always carries ``suppressed_by {reason, since, until}``.
"""

from __future__ import annotations

from collections.abc import Sequence

from .contracts import Alert, EntityMonth, Params


def build_alerts(months: Sequence[EntityMonth], p: Params) -> list[Alert]:
    """Alerts of one entity; ``months`` ascending. Output sorted by (month, kind).

    Conditions, evaluated per month:
      deterioration_structural / improvement_structural: trajectory direction
        with ``nature == "structural"``; emitted on the first month of the run;
      level_critical: ``score < critical_score`` on a live feed; first month of
        each spell below the threshold;
      cap_fired: ``cap_adjustment > 0``; first month of each spell of the
        binding rule;
      stale_feed: first month of each spell with the ``stale_feed`` flag.
    State: ``abstained`` when ``parts.abstained`` (reason ``abstention``, since
    = month, until = None); else ``suppressed`` when
    ``months_since_perimeter_change <= perimeter_quiet_months`` (reason
    ``perimeter_change``, since = change month, until = change month +
    quiet months); else ``fired``. ``stale_feed`` alerts are never suppressed.
    ``id = f"{entity_id}:{month:%Y-%m}:{kind}"``; ``title``/``detail`` in Spanish.
    """
    raise NotImplementedError
