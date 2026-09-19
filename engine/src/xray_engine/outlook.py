"""Scenarios best / common / worst of the score, three months ahead. Pure, past-only.

The outlook of month t reads ``history[: t]`` (month t and earlier items only),
so a scenario never changes when later months arrive; ``outlooks`` gives the
outlook of every month in one forward pass. Nothing here feeds the score: the
outlook is a reading of the trend, written to the bundle next to each month.

``common`` projects the score of the month with the drift of the long horizon
(same Theil-Sen machinery as the trajectory: ``_drift``): when the fit measures
a slope, the projection adds ``slope x horizon_months``; otherwise it holds the
score (``basis = "flat"``) and a gate says why — the fit needs
``long_min_months`` comparable live months, or the month itself carries the
flag ``perimeter_shift`` and describes another perimeter. ``best`` and
``worst`` fan out from ``common`` by ``max(min_delta_points, long_sigma_mult *
own sigma)`` points, clamped to 0 and 100: an abanico of the own volatility of
the business, not a forecast, so the three points travel with a gate whenever
the projection is flat.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .contracts import Params, ScoreParts
from .trajectory import _drift, own_sigma

GATE_TEXTS: dict[str, str] = {
    "no_drift": "La deriva del score no se puede medir con la historia comparable disponible: el escenario común mantiene el score actual.",
    "perimeter_shift": "El perímetro cambió este mes: la deriva de los últimos meses no describe el negocio actual.",
}


@dataclass(frozen=True)
class Outlook:
    """Scenario fan of one month. Not available (all points None) with a reason:
    ``short_history`` without history, ``stale_feed`` on a carried month and
    ``abstention`` on an abstained one. ``basis`` is ``drift`` when the common
    scenario projects the measured slope, ``flat`` when it holds the score;
    ``gates`` explains every flat projection. ``drift_points`` / ``drift_months``
    keep the fit behind a ``drift`` basis (descriptive)."""

    available: bool
    reason: str | None
    basis: str  # drift | flat
    horizon_months: int
    common: float | None  # 0..100
    best: float | None
    worst: float | None
    drift_points: float | None
    drift_months: int | None
    gates: tuple[str, ...] = ()


def _unavailable(reason: str, horizon: int) -> Outlook:
    return Outlook(
        available=False, reason=reason, basis="flat", horizon_months=horizon,
        common=None, best=None, worst=None, drift_points=None, drift_months=None,
    )  # fmt: skip


def outlook(history: Sequence[ScoreParts], p: Params) -> Outlook:
    """Scenario fan for the last month of ``history`` (ascending, one entity)."""
    horizon = p.trajectory.horizon_months
    if not history:
        return _unavailable("short_history", horizon)
    now = history[-1]
    if not now.feed_live:
        return _unavailable("stale_feed", horizon)
    if now.abstained:
        return _unavailable("abstention", horizon)
    shifted = "perimeter_shift" in now.flags
    drift = None if shifted else _drift(history, len(history) - 1, p)
    gates: list[str] = []
    if drift is None:
        common = min(100.0, max(0.0, now.score))
        basis = "flat"
        gates.append("perimeter_shift" if shifted else "no_drift")
    else:
        slope = drift[0] / drift[1]
        common = min(100.0, max(0.0, now.score + slope * horizon))
        basis = "drift"
    sigma = own_sigma(history, p)
    fan = max(p.trajectory.min_delta_points, p.trajectory.long_sigma_mult * sigma)
    return Outlook(
        available=True,
        reason=None,
        basis=basis,
        horizon_months=horizon,
        common=common,
        best=min(100.0, common + fan),
        worst=max(0.0, common - fan),
        drift_points=drift[0] if drift is not None else None,
        drift_months=drift[1] if drift is not None else None,
        gates=tuple(gates),
    )


def outlooks(history: Sequence[ScoreParts], p: Params) -> list[Outlook]:
    """Outlook of every prefix of ``history`` in one forward pass:
    ``outlooks(h, p)[i] == outlook(h[: i + 1], p)``."""
    return [outlook(history[: index + 1], p) for index in range(len(history))]
