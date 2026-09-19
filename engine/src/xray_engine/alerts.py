"""Alert inbox: what fires, what is suppressed and why. Pure.

Kinds: ``deterioration_structural``, ``improvement_structural``,
``level_critical``, ``cap_fired``, ``stale_feed``.
States: ``fired``; ``suppressed`` (the month of a perimeter change, and only
that month); ``abstained`` (the engine abstains on that month).
A non-fired alert always carries ``suppressed_by {reason, since, until}``.
Customer concentration is a profile attribute, never an alert.
"""

from __future__ import annotations

from collections.abc import Sequence

from .contracts import (
    CAP_KEYS,
    CAP_TEXTS,
    PILLAR_LABELS,
    Alert,
    EntityMonth,
    Params,
    SuppressedBy,
)
from .pillars import format_es

TITLES: dict[str, str] = {
    "deterioration_structural": "Deterioro estructural",
    "improvement_structural": "Mejora estructural",
    "level_critical": "Nivel crítico",
    "cap_fired": "Tope aplicado",
    "stale_feed": "Feed bancario sin datos",
}
DETAIL_TEMPLATES: dict[str, str] = {
    "deterioration_structural": (
        "El score cae {points} puntos frente a {compared} y la caída se mantiene {run} meses seguidos{moved}."
    ),
    "improvement_structural": (
        "El score sube {points} puntos frente a {compared} y la mejora se mantiene {run} meses seguidos{moved}."
    ),
    # slow drift: the long horizon makes the call
    "deterioration_structural_long": (
        "El score acumula una caída de {points} puntos en {months} meses: una deriva lenta y sostenida{moved}."
    ),
    "improvement_structural_long": (
        "El score acumula una subida de {points} puntos en {months} meses: una mejora lenta y sostenida{moved}."
    ),
    "level_critical": "El score ({score}) baja de {critical} puntos con el feed bancario activo.",
    "cap_fired": "{rule} Resta {points} puntos.",
    "stale_feed": "No llegan movimientos bancarios recientes: se mantiene el score de {carried}.",
    "stale_feed_uncarried": (
        "No llegan movimientos bancarios recientes y no hay un mes anterior con datos vivos que mantener."
    ),
}


def _conditions(item: EntityMonth, p: Params) -> dict[str, tuple[str, bool, str]]:
    """spell key -> (kind, condition holds, detail) on a live month."""
    parts, verdict = item.parts, item.trajectory
    found: dict[str, tuple[str, bool, str]] = {}
    for kind, direction in (
        ("deterioration_structural", "deteriorating"),
        ("improvement_structural", "improving"),
    ):
        holds = verdict.nature == "structural" and verdict.direction == direction
        detail = ""
        if holds:
            labels = ", ".join(PILLAR_LABELS[key].lower() for key in verdict.pillars_moved)
            moved = f"; se mueven: {labels}" if labels else ""
            if verdict.horizon in ("long", "both") and verdict.drift_points is not None:
                detail = DETAIL_TEMPLATES[f"{kind}_long"].format(
                    points=format_es(abs(verdict.drift_points), 1),
                    months=verdict.drift_months,
                    moved=moved,
                )
            else:
                detail = DETAIL_TEMPLATES[kind].format(
                    points=format_es(abs(verdict.delta3 or 0.0), 1),
                    compared=f"{verdict.compared_to:%Y-%m}" if verdict.compared_to else "tres meses antes",
                    run=verdict.persistence_months,
                    moved=moved,
                )
        found[kind] = (kind, holds, detail)
    critical = parts.score < p.alerts.critical_score
    found["level_critical"] = (
        "level_critical",
        critical,
        DETAIL_TEMPLATES["level_critical"].format(
            score=format_es(parts.score, 1), critical=format_es(p.alerts.critical_score)
        ),
    )
    binding = parts.caps_fired[0] if parts.cap_adjustment > 0 and parts.caps_fired else None
    for rule in CAP_KEYS:  # one spell per binding rule
        detail = DETAIL_TEMPLATES["cap_fired"].format(
            rule=CAP_TEXTS[rule], points=format_es(parts.cap_adjustment, 1)
        )
        found[f"cap_fired/{rule}"] = ("cap_fired", binding == rule, detail)
    return found


def _alert(
    item: EntityMonth, kind: str, state: str, detail: str, muted: SuppressedBy | None
) -> Alert:
    row = item.row
    return Alert(
        id=f"{row.entity_id}:{row.month:%Y-%m}:{kind}",
        entity_kind=row.entity_kind,
        entity_id=row.entity_id,
        group_id=row.group_id,
        month=row.month,
        kind=kind,
        state=state,
        title=TITLES[kind],
        detail=detail,
        suppressed_by=muted,
    )


def build_alerts(months: Sequence[EntityMonth], p: Params) -> list[Alert]:
    """Alerts of one entity; ``months`` ascending. Output sorted by (month, kind).

    Conditions, evaluated per month:
      deterioration_structural / improvement_structural: trajectory direction
        deteriorating / improving with ``nature == "structural"``; emitted on
        the first structural month of the run (the detail names the drift
        when the long horizon makes the call). ``perimeter_shift`` never alerts;
      level_critical: ``score < critical_score`` on a live feed; first month of
        each spell below the threshold;
      cap_fired: ``cap_adjustment > 0`` on a live feed; first month of each
        spell of the binding rule (``caps_fired[0]``);
      stale_feed: first month of each spell with the ``stale_feed`` flag. It is
        the only kind a stale month can emit: spells of the other kinds are
        neither opened nor closed by carried months.
    State: ``stale_feed`` alerts are always ``fired``. Else ``abstained`` when
    ``parts.abstained`` (reason ``abstention``, since = month, until = None);
    else ``suppressed`` when ``row.perimeter_changed`` (reason
    ``perimeter_change``, since = until = month); else ``fired``.
    A spell whose first alert did not fire emits once more, as ``fired``, on
    its first later month that is neither abstained nor suppressed.
    ``id = f"{entity_id}:{month:%Y-%m}:{kind}"``; ``title``/``detail`` in Spanish.
    """
    alerts: list[Alert] = []
    open_spells: dict[str, bool] = {}  # spell key -> an alert of the spell already fired
    stale_spell = False
    for item in sorted(months, key=lambda entry: entry.row.month):
        row, parts = item.row, item.parts
        if not parts.feed_live:
            if not stale_spell:
                carried = parts.carried_from
                detail = (
                    DETAIL_TEMPLATES["stale_feed"].format(carried=f"{carried:%Y-%m}")
                    if carried is not None
                    else DETAIL_TEMPLATES["stale_feed_uncarried"]
                )
                alerts.append(_alert(item, "stale_feed", "fired", detail, None))
            stale_spell = True
            continue
        stale_spell = False

        if parts.abstained:
            state, muted = "abstained", SuppressedBy("abstention", row.month, None)
        elif row.perimeter_changed:
            state, muted = "suppressed", SuppressedBy("perimeter_change", row.month, row.month)
        else:
            state, muted = "fired", None
        for key, (kind, holds, detail) in _conditions(item, p).items():
            if not holds:
                open_spells.pop(key, None)
                continue
            first = key not in open_spells
            if first or (state == "fired" and not open_spells[key]):
                alerts.append(_alert(item, kind, state, detail, muted))
                open_spells[key] = state == "fired"
    return sorted(alerts, key=lambda alert: (alert.month, alert.kind))
