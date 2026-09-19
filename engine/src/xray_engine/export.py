"""Static JSON bundle for the web app (contract ``contracts/xray-export-v1.schema.json``).

Files: ``manifest.json``, ``portfolio.json``, ``groups/<id>.json``,
``companies/<id>.json``, ``evidence/<id>.json``, ``alerts.json``,
``receipt.json``. Every number comes from a ``ScoreResult``; evidence rows are
aggregates, never raw descriptions. Output is byte-identical for identical
inputs: sorted keys, fixed separators, no wall-clock values.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import contracts
from .contracts import (
    BAND_KEYS,
    BAND_LABELS,
    ENGINE_VERSION,
    PILLAR_KEYS,
    PILLAR_LABELS,
    UNLOCK_HINTS,
    EntityMonth,
)
from .pillars import NOTE_TEMPLATES, pillar_note
from .trajectory import trajectory_note

if TYPE_CHECKING:  # the result object is only read through its public fields
    from .scoring import ScoreResult

BUNDLE_SCHEMA = "xray-export-v1"
DEFAULT_VALIDATION_PATH = Path("artifacts/validation.json")
SINGLE_FILES = ("manifest.json", "portfolio.json", "alerts.json", "receipt.json")
ENTITY_FOLDERS = ("groups", "companies", "evidence")
SCORES_FILE = "scores.parquet"
FALLBACK_GATE = "unavailable"
MAX_CHECK_METRICS = 12

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_PERIOD_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}(-[0-9]{2})?(\.\.[0-9]{4}-[0-9]{2}(-[0-9]{2})?)?$")
_SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9_./-]{1,64}$")
_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_STAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})?)?$"
)

# key -> (label, unit, decimals); same keys as ``contracts.SERIES_KEYS``.
SERIES_META: dict[str, tuple[str, str, int]] = {
    "cash_month_end": ("Caja a fin de mes", "EUR", 2),
    "cash_intra_month_min": ("Caja mínima del mes", "EUR", 2),
    "headroom": ("Disponible en líneas de crédito", "EUR", 2),
    "drawn": ("Dispuesto en líneas de crédito", "EUR", 2),
    "op_inflow_1m": ("Cobros operativos del mes", "EUR", 2),
    "op_outflow_1m": ("Pagos operativos del mes", "EUR", 2),
    "debt_service_1m": ("Servicio de la deuda del mes", "EUR", 2),
    "buffer_days": ("Días de colchón a fin de mes", "días", 1),
    "ap_days_beyond_terms": ("Días sobre el vencimiento al pagar", "días", 1),
    "ar_days_beyond_terms": ("Días sobre el vencimiento al cobrar", "días", 1),
    "activity_coverage": ("Cobros sobre pagos y deuda (6 meses)", "ratio", 4),
    "activity_momentum": ("Impulso de cobros en cuentas comparables", "ratio", 4),
    "debt_burden": ("Servicio de la deuda sobre cobros (12 meses)", "ratio", 4),
}
_SERIES_ROW_FIELDS = (
    "cash_month_end", "cash_intra_month_min", "headroom", "drawn",
    "op_inflow_1m", "op_outflow_1m", "debt_service_1m",
)  # fmt: skip
_SERIES_PILLAR_INPUTS = {
    "buffer_days": ("liquidity", "buffer_days_month_end"),
    "ap_days_beyond_terms": ("payments", "days_beyond_terms"),
    "ar_days_beyond_terms": ("collections", "days_beyond_terms"),
    "activity_coverage": ("activity", "coverage"),
    "activity_momentum": ("activity", "momentum"),
    "debt_burden": ("debt", "burden"),
}

SIGNAL_WHY: dict[str, str] = {
    "liquidity": "Días de salidas que cubren la caja y las líneas disponibles, a fin de mes y en el mínimo del mes.",
    "payments": "Días sobre el vencimiento con que se paga a proveedores, vistos con lo que se sabía a cada cierre.",
    "collections": "Días sobre el vencimiento con que pagan los clientes, vistos con lo que se sabía a cada cierre.",
    "activity": "Cobertura de pagos con cobros operativos e impulso de los cobros en cuentas comparables.",
    "debt": "Parte de los cobros de 12 meses que consume el servicio de la deuda.",
}
# Signals kept at weight 0 on purpose: (name, label, why).
ZERO_WEIGHT_SIGNALS: tuple[tuple[str, str, str], ...] = (
    (
        "industry", "Sector inferido",
        "Contexto de la ficha: no entra en el número porque la clasificación no es fiable para la mayoría de empresas.",
    ),
    (
        "customer_concentration", "Concentración de clientes",
        "Se muestra en la ficha: es un rasgo del negocio, no un pilar ni una alerta.",
    ),
    (
        "seasonality", "Estacionalidad",
        "El patrón mensual no se distingue del ruido con dos años de historia, así que no se desestacionaliza.",
    ),
    (
        "exchange_rate", "Tipo de cambio del fichero",
        "La columna no es utilizable: las divisas se convierten con una tabla fija y las que no están en ella "
        "cuentan en filas, no en importes.",
    ),
    (
        "transfer_category", "Categoría «transfer»",
        "No decide qué es un movimiento interno: los traspasos se detectan emparejando las dos patas dentro del grupo.",
    ),
    (
        "confidence", "Confianza",
        "Se muestra junto al score (alta, media o baja) y decide la abstención, pero nunca cambia el número.",
    ),
)  # fmt: skip

TRUTH_TEXTS: dict[str, str] = {
    "swept": "La liquidez de esta filial se evalúa a nivel de grupo: barre su caja a la matriz.",
    "treasury_centre": "Concentra la caja del grupo: recibe los barridos de las filiales.",
    "financing_hub": "Concentra la financiación del grupo y la reparte entre las filiales.",
    "line_funded": "Se financia con líneas de crédito: el disponible en las líneas forma parte de su liquidez.",
    "group_funded": "Se financia con el grupo: sus entradas son traspasos internos, no cobros de terceros.",
    "no_external_revenue": "No tiene cobros de fuera del grupo: la actividad no se puede medir con sus cuentas.",
}

# validation key -> (title, what the check asks)
CHECK_TEXTS: dict[str, tuple[str, str]] = {
    "isolation": ("Aislamiento de cohorte", "Cada grupo puntuado en solitario obtiene el mismo score que dentro de la cartera completa."),
    "truncation": ("Sin mirar al futuro", "Cortar los ficheros en un mes pasado no cambia ningún score anterior al corte."),
    "additivity": ("Identidad aditiva", "Base más contribuciones menos penalización y tope da el score, mes a mes."),
    "scale": ("Invarianza de escala", "Multiplicar todos los importes por una constante no cambia el score."),
    "determinism": ("Determinismo", "Dos ejecuciones, y una con las filas barajadas, dan exactamente el mismo resultado."),
    "ablation": ("Ablación pareada", "Los mismos grupos con y sin pilares de facturas: desplazamiento medio y orden."),
    "branch_parity": ("Paridad entre ramas", "El score no depende de qué pilares están disponibles."),
    "neutrality": ("Neutralidad", "El score no se explica por tamaño, ERP, banco, mes del año ni rama de cobertura."),
    "penalty_by_branch": ("Penalización por rama", "Penalización media según los pilares disponibles."),
    "rank_stability": ("Estabilidad del orden", "El orden de los grupos aguanta cambios de ±10 puntos en los pesos y de la penalización."),
    "history_truncation": ("Historia mínima", "Cuánto cambia el score cuando solo se ven los últimos meses de un grupo."),
    "persistence": ("Persistencia", "La caja negativa de hoy sigue siendo negativa seis meses después."),
    "netting_placebo": ("Placebo de traspasos", "El emparejamiento de traspasos internos casi no encuentra nada con las fechas desplazadas."),
    "injection": ("Deterioros inyectados", "Retraso de detección y falsas alertas al inyectar picos, escalones y rampas."),
}  # fmt: skip
CHECK_MISMATCH = "La validación disponible corresponde a otro dataset o a otros parámetros."
CHECK_NOT_RUN = "Comprobación no ejecutada en esta validación."
CHECK_STATUSES = ("pass", "fail", "info", "not_run")
HORIZON_LABELS = {"short": "corto (3 meses)", "long": "largo (deriva lenta)", "both": "corto y largo"}


# --------------------------------------------------------------------------
# rounding
# --------------------------------------------------------------------------


def round_preserving_sum(
    parts: Sequence[float], total: float, scale: int = 10
) -> list[int]:
    """Largest-remainder rounding of signed ``parts`` to integers of ``1/scale``.

    Returns integers ``r`` with ``sum(r) == round(total * scale)`` and
    ``|r[i] - parts[i] * scale| < 1``: each part is floored, then the missing
    units go to the largest fractional remainders (ties: lowest index).
    Expects ``sum(parts) == total`` up to float noise. With parts ``[base,
    *contributions, -penalty, -cap_adjustment]`` and ``total = score`` the
    on-screen sum is exact in integer tenths.
    """
    target = round(total * scale)
    if not parts:
        return []
    scaled = []
    for value in parts:
        exact = value * scale
        nearest = round(exact)
        # float noise around an integer must not cost a whole unit
        scaled.append(float(nearest) if abs(exact - nearest) < 1e-7 else exact)
    floors = [math.floor(value) for value in scaled]
    missing = target - sum(floors)
    order = sorted(range(len(parts)), key=lambda index: (-(scaled[index] - floors[index]), index))
    # 0 <= missing <= len(parts) whenever the parts add up to the total
    every, first = divmod(missing, len(parts))
    rounded = [value + every for value in floors]
    for index in order[:first]:
        rounded[index] += 1
    return rounded


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _month(value: date) -> str:
    return f"{value:%Y-%m}"


def _month_axis(first: date, last: date) -> list[str]:
    start, end = first.year * 12 + first.month - 1, last.year * 12 + last.month - 1
    return [f"{index // 12:04d}-{index % 12 + 1:02d}" for index in range(start, end + 1)]


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _number(value: Any, decimals: int) -> float | int | None:
    number = _finite(value)
    if number is None:
        return None
    rounded = round(number, decimals)
    return 0.0 if rounded == 0 else rounded  # no "-0.0"


def _share(value: Any) -> float:
    number = _finite(value)
    return 0.0 if number is None else round(min(1.0, max(0.0, number)), 4)


def _tenths(value: Any) -> int | None:
    number = _finite(value)
    return None if number is None else round(number * 10)


def _score_tenths(value: Any) -> int | None:
    tenths = _tenths(value)
    return None if tenths is None else min(1000, max(0, tenths))


def _text(value: Any, limit: int = 400, fallback: str = "-") -> str:
    text = " ".join(str(value).split()) if value is not None else ""
    if not text:
        return fallback
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _nullable_text(value: Any, limit: int) -> str | None:
    return None if value is None or not str(value).strip() else _text(value, limit)


def _codes(values: Iterable[Any]) -> list[str]:
    return [str(value) for value in values if _CODE_PATTERN.match(str(value))]


def _dump(data: Any) -> bytes:
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (text + "\n").encode("utf-8")


def bundle_digest(bundle_dir: Path) -> str:
    """sha256 over every file but the manifest: path bytes then file bytes, sorted by path."""
    digest = hashlib.sha256()
    files = {
        path.relative_to(bundle_dir).as_posix(): path
        for path in Path(bundle_dir).rglob("*")
        if path.is_file()
    }
    for relative in sorted(files):
        if relative != "manifest.json":
            digest.update(relative.encode())
            digest.update(files[relative].read_bytes())
    return digest.hexdigest()


# --------------------------------------------------------------------------
# entity-months
# --------------------------------------------------------------------------


def _bands(params: Any) -> list[dict[str, Any]]:
    return [
        {"key": key, "label": BAND_LABELS[key], "min": round(params.bands[key] * 10)}
        for key in BAND_KEYS
    ]


def _band(shown: int, bands: Sequence[Mapping[str, Any]]) -> str:
    return [band["key"] for band in bands if shown >= band["min"]][-1]


def _waterfall(parts: Any) -> tuple[int, int, dict[str, int], int, int]:
    """(shown, base, contributions, penalty, cap) in integer tenths, identity exact."""
    available = [key for key in PILLAR_KEYS if parts.pillar_scores.get(key) is not None]
    contributions = [float(parts.contributions.get(key, 0.0)) for key in available]
    score = min(100.0, max(0.0, float(parts.score)))
    penalty, cap = max(0.0, float(parts.penalty)), max(0.0, float(parts.cap_adjustment))
    # whatever the engine identity leaves unexplained (float noise) stays in the base
    base = score - sum(contributions) + penalty + cap
    rounded = round_preserving_sum([base, *contributions, -penalty, -cap], score)
    shown, penalty_tenths, cap_tenths = round(score * 10), -rounded[-2], -rounded[-1]
    if cap_tenths > 0 and not parts.caps_fired:  # a cap amount needs a rule on screen
        rounded[0] -= cap_tenths
        cap_tenths = 0
    by_key = dict(zip(available, rounded[1:-2]))
    return shown, rounded[0], by_key, penalty_tenths, cap_tenths


def _verdict(month: EntityMonth) -> dict[str, Any]:
    verdict, parts = month.trajectory, month.parts
    available, reason = bool(verdict.available), verdict.reason
    if available and parts.abstained:  # an abstained month gives no verdict on screen
        available, reason = False, parts.abstain_reason or "short_history"
    if not available:
        return {
            "available": False, "reason": reason or "short_history", "direction": "stable",
            "nature": None, "shock_pending": False, "shock_month": None, "delta3": None,
            "sigma": None, "delta3_sigma": None, "compared_to": None, "pillars_moved": [],
            "persistence_months": 0, "detected_since": None,
        }  # fmt: skip
    sigma = _tenths(verdict.sigma)
    return {
        "available": True,
        "reason": None,
        "direction": verdict.direction,
        "nature": verdict.nature,
        "shock_pending": verdict.nature == "shock_pending",
        "shock_month": _month(verdict.shock_month) if verdict.shock_month else None,
        "delta3": _tenths(verdict.delta3),
        "sigma": None if sigma is None else max(0, sigma),
        "delta3_sigma": _number(verdict.delta3_sigma, 2),
        "compared_to": _month(verdict.compared_to) if verdict.compared_to else None,
        "pillars_moved": [key for key in PILLAR_KEYS if key in verdict.pillars_moved],
        "persistence_months": max(0, int(verdict.persistence_months or 0)),
        "detected_since": _month(verdict.detected_since) if verdict.detected_since else None,
    }


def _unlock(parts: Any, params: Any) -> str:
    if parts.unlock_hint:
        return _text(parts.unlock_hint)
    template = UNLOCK_HINTS.get(parts.abstain_reason or "", "Hacen falta más datos bancarios.")
    minimum = getattr(getattr(params, "abstention", None), "min_months_observed", 4)
    return _text(template.format(months=minimum))


def _entity_month(month: EntityMonth, params: Any, bands: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    row, parts = month.row, month.parts
    shown, base, contributions, penalty, cap = _waterfall(parts)
    pillars = []
    for key in PILLAR_KEYS:
        result = month.pillars.get(key)
        score = _score_tenths(parts.pillar_scores.get(key))
        gates = _codes(result.gates) if result is not None else []
        if score is None and not gates:
            gates = [FALLBACK_GATE]
        note = pillar_note(result, params) if result is not None else NOTE_TEMPLATES["unavailable"]
        pillars.append(
            {
                "key": key,
                "score": score,
                "w_eff": _share(parts.weights_effective.get(key, 0.0)) if score is not None else 0,
                "contrib": contributions.get(key, 0),
                "gates": gates,
                "note": _nullable_text(note, 400),
            }
        )
    confidence = parts.confidence_parts
    fired = _codes(parts.caps_fired)
    return {
        "month": _month(row.month),
        "shown": shown,
        "band": _band(shown, bands),
        "level": _score_tenths(parts.level),
        "base": base,
        "pillars": pillars,
        "penalty": penalty,
        "cap": {"amount": cap, "rule": fired[0] if cap > 0 and fired else None, "fired": fired},
        "conf": {
            "value": _share(parts.confidence),
            "label": parts.confidence_label,
            "history": _share(confidence.history),
            "coverage": _share(confidence.coverage),
            "quality": _share(confidence.quality),
        },
        "branch": parts.branch,
        "flags": _codes(parts.flags),
        "feed_live": bool(parts.feed_live),
        "months_observed": max(0, int(parts.months_observed or 0)),
        "perimeter_changed": bool(row.perimeter_changed),
        "verdict": _verdict(month),
        "abstain": (
            {"reason": parts.abstain_reason or "short_history", "unlock": _unlock(parts, params)}
            if parts.abstained
            else None
        ),
    }


def _series(months: Sequence[EntityMonth]) -> list[dict[str, Any]]:
    series = []
    for key in getattr(contracts, "SERIES_KEYS", tuple(SERIES_META)):
        if key not in SERIES_META:
            continue
        label, unit, decimals = SERIES_META[key]
        values = []
        for month in months:
            if key in _SERIES_ROW_FIELDS:
                raw = getattr(month.row, key, None)
            else:
                pillar, name = _SERIES_PILLAR_INPUTS[key]
                result = month.pillars.get(pillar)
                raw = result.inputs.get(name) if result is not None else None
            values.append(_number(raw, decimals))
        if any(value is not None for value in values):
            series.append({"key": key, "label": label, "unit": unit, "values": values})
    return series


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------


def _evidence_row(pillar: str | None, item: Any, month: str) -> dict[str, Any] | None:
    label = _text(getattr(item, "label", None), 120, "")
    if not label:
        return None
    value = getattr(item, "value", None)
    if isinstance(value, bool) or value is None:
        value = None if value is None else ("sí" if value else "no")
    elif isinstance(value, (int, float)):
        value = _number(value, 4)
    else:
        value = _text(value, 80)
    period = str(getattr(item, "period", "") or "")
    source = str(getattr(item, "source_file", "") or "")
    rows = getattr(item, "n_rows", None)
    return {
        "pillar": pillar,
        "label": label,
        "value": value,
        "unit": _text(getattr(item, "unit", ""), 24, ""),
        "period": period if _PERIOD_PATTERN.match(period) else month,
        "source_file": source if _SOURCE_PATTERN.match(source) else SCORES_FILE,
        "n_rows": max(0, int(rows)) if _finite(rows) is not None else None,
    }


def _fact(label: str, value: Any, unit: str, period: str, n_rows: int | None = None) -> dict[str, Any]:
    return {
        "pillar": None, "label": label, "value": value, "unit": unit,
        "period": period, "source_file": SCORES_FILE, "n_rows": n_rows,
    }  # fmt: skip


def _entity_facts(month: EntityMonth) -> list[dict[str, Any]]:
    """Facts about the whole entity-month: the trajectory extras the verdict
    block of the frozen contract has no field for, and the carried month."""
    verdict, parts, label = month.trajectory, month.parts, _month(month.row.month)
    facts = []
    if parts.carried_from is not None:
        facts.append(_fact("Score mantenido desde el último mes con feed vivo", _month(parts.carried_from), "", label))
    if not verdict.available or parts.abstained:
        return facts
    horizon = getattr(verdict, "horizon", None)
    if horizon in HORIZON_LABELS:
        facts.append(_fact("Horizonte que decide la trayectoria", HORIZON_LABELS[horizon], "", label))
    drift, span = _finite(getattr(verdict, "drift_points", None)), getattr(verdict, "drift_months", None)
    if drift is not None and span:
        start = month.row.month.year * 12 + month.row.month.month - int(span)
        period = f"{start // 12:04d}-{start % 12 + 1:02d}..{label}"
        facts.append(_fact("Deriva acumulada del score (pendiente robusta)", _number(drift, 1), "puntos", period, int(span)))
    note = trajectory_note(verdict)
    if note:  # the two horizons disagree: the recent move makes the call, unconfirmed
        facts.append(_fact(_text(note, 120), "pendiente de confirmar", "", label))
    return facts


def _evidence(
    kind: str, entity_id: str, group_id: str, months: Sequence[EntityMonth], evidence_months: int
) -> dict[str, Any]:
    chosen = list(months)[-evidence_months:] if evidence_months > 0 else []
    out = []
    for month in chosen:
        label = _month(month.row.month)
        rows = []
        for key in PILLAR_KEYS:
            result = month.pillars.get(key)
            for item in getattr(result, "evidence", ()) or ():
                row = _evidence_row(key, item, label)
                if row is not None:
                    rows.append(row)
        rows.extend(_entity_facts(month))
        out.append({"month": label, "rows": rows})
    return {
        "schema": BUNDLE_SCHEMA, "kind": "evidence", "entity_kind": kind,
        "entity_id": entity_id, "group_id": group_id, "months": out,
    }  # fmt: skip


# --------------------------------------------------------------------------
# profile, context and the treasury reading of a company
# --------------------------------------------------------------------------


def _profile(card: Any) -> list[dict[str, Any]]:
    attributes = []
    for item in getattr(card, "attributes", ()) or ():
        if not _CODE_PATTERN.match(str(item.key)):
            continue
        value = item.value
        if isinstance(value, float):
            value = _number(value, 4)
        elif isinstance(value, str):
            value = _text(value, 160)
        elif not isinstance(value, (bool, int)) and value is not None:
            value = _text(value, 160)
        attributes.append(
            {
                "key": item.key,
                "label": _text(item.label or item.key),
                "value": value,
                "evidence": _text(item.evidence, 400, ""),
                "coverage": _share(item.coverage),
            }
        )
    return attributes


def _context(card: Any) -> dict[str, Any]:
    raw = (getattr(card, "context", None) or {}).get("industry")
    industry = None
    if isinstance(raw, Mapping) and raw.get("slug") and raw.get("label"):
        industry = {
            "slug": _text(raw["slug"], 80),
            "label": _text(raw["label"]),
            "confidence": _share(raw.get("confidence")),
            "reason": _text(raw.get("reason"), 400, ""),
        }
    # a sector benchmark (invoice to cash days) is context and is never compared
    # with days beyond terms; none is shipped without a sourced sentence
    return {"industry": industry, "benchmark": None}


def _attribute(card: Any, key: str) -> Any:
    for item in getattr(card, "attributes", ()) or ():
        if item.key == key:
            return item.value
    return None


def _label_codes() -> dict[str, dict[str, str]]:
    """Spanish value label -> engine code, for the attributes the truth reads."""
    try:
        from . import profile
    except Exception:  # noqa: BLE001 - the card is optional context
        return {"role": {}, "treasury": {}, "financing": {}}
    return {
        "role": {label: code for code, label in profile.GROUP_ROLE_LABELS.items()},
        "treasury": {label: code for code, label in profile.TREASURY_LABELS.items()},
        "financing": {label: code for code, label in profile.FINANCING_LABELS.items()},
    }


def _truth(card: Any, last: EntityMonth, codes: Mapping[str, Mapping[str, str]]) -> str | None:
    """Treasury reading of a company inside its group, from panel and card facts."""
    row, parts = last.row, last.parts
    liquidity = last.pillars.get("liquidity")
    role = codes["role"].get(str(_attribute(card, "group_role")))
    treasury = codes["treasury"].get(str(_attribute(card, "treasury_structure")))
    financing = codes["financing"].get(str(_attribute(card, "financing_profile")).split(" · ")[0])
    inherited = liquidity is not None and "inherited_from_group" in liquidity.gates
    keys = []
    if inherited or getattr(row, "swept_subsidiary", False) or role == "swept_subsidiary":
        keys.append("swept")
    if role in ("treasury_centre", "financing_hub"):
        keys.append(role)
    if treasury == "line_funded":
        keys.append("line_funded")
    if role == "captive" or financing == "intercompany":
        keys.append("group_funded")
    if getattr(row, "no_external_revenue", False) or "no_external_revenue" in parts.flags:
        keys.append("no_external_revenue")
    return _nullable_text(" ".join(TRUTH_TEXTS[key] for key in keys), 400)


# --------------------------------------------------------------------------
# alerts, glossary, receipt
# --------------------------------------------------------------------------


def _alert(alert: Any, shown: int) -> dict[str, Any]:
    muted = alert.suppressed_by
    return {
        "id": alert.id,
        "entity_kind": alert.entity_kind,
        "entity_id": alert.entity_id,
        "group_id": alert.group_id,
        "month": _month(alert.month),
        "kind": alert.kind,
        "state": alert.state,
        "title": _text(alert.title),
        "detail": _text(alert.detail),
        "shown": shown,
        "suppressed_by": (
            None
            if muted is None or alert.state == "fired"
            else {
                "reason": muted.reason,
                "since": _month(muted.since),
                "until": _month(muted.until) if muted.until else None,
            }
        ),
    }


def _engine_texts(name: str) -> dict[str, str]:
    """``<name>`` tables of every pure module that declares one (contracts first)."""
    found: dict[str, str] = {}
    modules: list[Any] = [contracts]
    for module_name in ("pillars", "aggregate", "alerts", "trajectory"):
        try:
            modules.append(importlib.import_module(f"{__package__}.{module_name}"))
        except Exception:  # noqa: BLE001 - a missing module only loses its own texts
            continue
    for module in modules:
        table = getattr(module, name, None)
        if isinstance(table, Mapping):
            for code, text in table.items():
                if _CODE_PATTERN.match(str(code)) and str(text).strip():
                    found.setdefault(str(code), _text(text))
    return found


def _glossary(entities: Iterable[Mapping[str, Any]], alerts: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    """Every code the engine can emit, plus any code the bundle uses."""
    glossary = {
        "gates": {**_engine_texts("GATE_TEXTS"), FALLBACK_GATE: NOTE_TEMPLATES["unavailable"]},
        "flags": _engine_texts("FLAG_TEXTS"),
        "caps": _engine_texts("CAP_TEXTS"),
        "reasons": _engine_texts("REASON_TEXTS"),
    }
    used: dict[str, set[str]] = defaultdict(set)
    for entity in entities:
        for entry in entity["months"]:
            for pillar in entry["pillars"]:
                used["gates"].update(pillar["gates"])
            used["flags"].update(entry["flags"])
            used["caps"].update(entry["cap"]["fired"])
            if entry["abstain"] is not None:
                used["reasons"].add(entry["abstain"]["reason"])
            if entry["verdict"]["reason"] is not None:
                used["reasons"].add(entry["verdict"]["reason"])
    for alert in alerts:
        if alert["suppressed_by"] is not None:
            used["reasons"].add(alert["suppressed_by"]["reason"])
    for section, codes in used.items():
        for code in sorted(codes):
            # a code without a text table entry still reads as Spanish on screen
            glossary[section].setdefault(code, f"Código del motor: {code.replace('_', ' ')}.")
    return glossary


def _metric_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        number = _finite(value)
        return None if number is None else (int(number) if isinstance(value, int) else float(f"{number:.6g}"))
    if isinstance(value, (list, tuple)) and all(not isinstance(item, (Mapping, list, tuple)) for item in value):
        return _text(", ".join(str(item) for item in value), 80, "")
    return _text(value, 80, "") if isinstance(value, str) else None


def _check(key: str, raw: Any, mismatch: bool) -> dict[str, Any]:
    title, question = CHECK_TEXTS.get(key, (key.replace("_", " ").capitalize(), "Comprobación sin etiquetas."))
    if not isinstance(raw, Mapping):
        return {"key": key, "title": title, "status": "not_run", "summary": CHECK_NOT_RUN, "metrics": []}
    passed = raw.get("pass")
    status = "not_run" if mismatch else "pass" if passed is True else "fail" if passed is False else "info"
    metrics: list[dict[str, Any]] = []
    bars: list[dict[str, Any]] = []
    for name, value in raw.items():
        if name in ("pass", "summary", "title"):
            continue
        label = _text(str(name).replace("_", " ").capitalize(), 400)
        if isinstance(value, Mapping):
            numeric = {str(k): _finite(v) for k, v in value.items()}
            if not bars and numeric and all(item is not None for item in numeric.values()) and any(
                word in str(name) for word in ("distribution", "bars", "histogram", "delay")
            ):
                bars = [{"label": _text(k, 40), "value": v} for k, v in numeric.items()]
                continue
            for inner, item in value.items():
                if not isinstance(item, (Mapping, list, tuple)):
                    metrics.append({"label": _text(f"{label} · {inner}"), "value": _metric_value(item), "unit": ""})
            continue
        if isinstance(value, (list, tuple)) and any(isinstance(item, (Mapping, list, tuple)) for item in value):
            continue
        metrics.append({"label": label, "value": _metric_value(value), "unit": ""})
    check = {
        "key": key,
        "title": _text(raw.get("title") or title),
        "status": status,
        "summary": _text(CHECK_MISMATCH if mismatch else raw.get("summary") or question),
        "metrics": [] if mismatch else metrics[:MAX_CHECK_METRICS],
    }
    if bars and not mismatch:
        check["bars"] = bars
    return check


def _ready_check(item: Mapping[str, Any], mismatch: bool) -> dict[str, Any] | None:
    """A check the validation already wrote in bundle shape, within the contract limits."""
    key = str(item.get("key") or "")
    if not _CODE_PATTERN.match(key):
        return None
    title, question = CHECK_TEXTS.get(key, (key.replace("_", " ").capitalize(), "Comprobación sin etiquetas."))
    status = item.get("status")
    check: dict[str, Any] = {
        "key": key,
        "title": _text(item.get("title") or title),
        "status": "not_run" if mismatch or status not in CHECK_STATUSES else status,
        "summary": _text(CHECK_MISMATCH if mismatch else item.get("summary") or question),
        # figures measured on another dataset or other params are never shown
        "metrics": [
            {
                "label": _text(metric.get("label")),
                "value": _metric_value(metric.get("value")),
                "unit": _text(metric.get("unit"), 24, ""),
            }
            for metric in (() if mismatch else item.get("metrics") or ())
            if isinstance(metric, Mapping)
        ],
    }
    bars = [
        {"label": _text(bar.get("label"), 40), "value": _finite(bar.get("value"))}
        for bar in item.get("bars") or ()
        if isinstance(bar, Mapping) and _finite(bar.get("value")) is not None
    ]
    if bars and not mismatch:
        check["bars"] = bars
    return check


def _checks(receipt: Mapping[str, Any] | None, params_hash: str, dataset_hash: str) -> list[dict[str, Any]]:
    if not receipt:
        return []
    mismatch = any(
        receipt.get(name) not in (None, expected)
        for name, expected in (("params_hash", params_hash), ("dataset_hash", dataset_hash))
    )
    ready = receipt.get("checks")
    if isinstance(ready, list):  # already in bundle shape: only trimmed to the contract limits
        checks, seen = [], set()
        for item in ready:
            if not isinstance(item, Mapping) or item.get("key") in seen:
                continue
            check = _ready_check(item, mismatch)
            if check is not None:
                seen.add(check["key"])
                checks.append(check)
        return checks
    try:
        from .validation import CHECK_KEYS as known
    except Exception:  # noqa: BLE001
        known = tuple(CHECK_TEXTS)
    skipped = ("dataset_hash", "params_hash", "engine_version", "generated_at", "quick")
    keys = [key for key in known if key in receipt or key in CHECK_TEXTS]
    keys += [key for key in receipt if key not in keys and key not in skipped and isinstance(receipt[key], Mapping)]
    seen: set[str] = set()
    checks = []
    for key in keys:
        if key in seen or not _CODE_PATTERN.match(key) or (key not in receipt and key not in known):
            continue
        seen.add(key)
        checks.append(_check(key, receipt.get(key), mismatch))
    return checks


# --------------------------------------------------------------------------
# bundle
# --------------------------------------------------------------------------


def _clean_target(out_dir: Path) -> None:
    """Removes the bundle files of a previous export (and nothing else)."""
    for name in SINGLE_FILES:
        (out_dir / name).unlink(missing_ok=True)
    for folder in ENTITY_FOLDERS:
        for path in (out_dir / folder).glob("*.json"):
            path.unlink()


def export_bundle(
    result: ScoreResult,
    out_dir: Path,
    *,
    evidence_months: int = 24,
    receipt: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Writes the bundle under ``out_dir`` and returns the manifest.

    ``manifest``: schema, bundle_id (sha256 of the other files, sorted by
    path), engine_version, params_hash, dataset_hash, generated_at, months,
    counts, pillars (label, nominal weight, B_k), bands (``Params.bands`` with
    ``BAND_LABELS``) and the glossary (``GATE_TEXTS``, ``FLAG_TEXTS``,
    ``CAP_TEXTS``, ``REASON_TEXTS``). ``generated_at`` defaults to
    ``result.window.as_of`` so that two runs give the same bytes.
    Entity-months: ``shown`` = ``parts.score``, ``level`` = ``parts.level``
    (they differ only on carried months), ``band`` decided on the rounded
    tenths of ``shown``, ``conf`` = value, label and the three parts,
    ``abstain`` = {reason, unlock} or null. Pillar scores, ``w_eff`` and
    contributions come from ``parts`` (a carried month shows the explanation it
    copied), gates and notes from ``month.pillars``. Contributions are emitted
    in integer tenths through ``round_preserving_sum`` over ``[base,
    *contributions, -penalty, -cap_adjustment]``. An abstained month never
    carries a verdict. The trajectory extras the frozen verdict block has no
    field for (horizon, drift points) are evidence rows of the entity-month
    (``pillar`` null); the alert detail already names the drift.
    ``evidence_months`` limits ``evidence/<id>.json`` to the last months.
    ``context.industry`` comes from the profile card; ``context.benchmark`` is
    null unless a sourced sentence is supplied: a sector benchmark of invoice
    to cash days is context and is never compared with days beyond terms.
    ``receipt`` is the output of ``validation.run_validation``; without it
    ``receipt.json`` holds only the sections derivable from ``result`` (signals
    and weights, abstentions).
    """
    out_dir = Path(out_dir)
    params = result.params
    stamp = str(generated_at) if generated_at else result.window.as_of.isoformat()
    if not _STAMP_PATTERN.match(stamp):
        raise ValueError(f"generated_at {stamp!r} is not an ISO date or date-time")
    profiles = getattr(result, "profiles", None) or {}
    bands = _bands(params)

    by_entity: dict[tuple[str, str], list[EntityMonth]] = defaultdict(list)
    for month in result.months:
        by_entity[(month.row.entity_kind, month.row.entity_id)].append(month)
    for key, months in by_entity.items():
        if not _ID_PATTERN.match(key[1]):
            raise ValueError(f"entity id {key[1]!r} is not safe as a file name")
        months.sort(key=lambda item: item.row.month)

    entries: dict[tuple[str, str], list[dict[str, Any]]] = {
        key: [_entity_month(month, params, bands) for month in months] for key, months in by_entity.items()
    }
    shown_at = {
        (kind, entity_id, entry["month"]): entry["shown"]
        for (kind, entity_id), months in entries.items()
        for entry in months
    }
    alerts = sorted(
        (
            _alert(alert, shown_at[(alert.entity_kind, alert.entity_id, _month(alert.month))])
            for alert in getattr(result, "alerts", ()) or ()
            if (alert.entity_kind, alert.entity_id, _month(alert.month)) in shown_at
        ),
        key=lambda item: (item["month"], item["id"]),
    )
    alerts_of: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for alert in alerts:
        alerts_of[alert["entity_id"]].append(alert)

    group_ids = sorted(entity_id for kind, entity_id in by_entity if kind == "group")
    members: dict[str, list[str]] = defaultdict(list)
    for kind, entity_id in sorted(by_entity):
        owner = by_entity[(kind, entity_id)][-1].row.group_id
        if kind == "company" and ("group", owner) in by_entity:
            members[owner].append(entity_id)

    all_months = [month.row.month for months in by_entity.values() for month in months]
    window = result.window
    axis = _month_axis(min([window.first_month, *all_months]), max([window.last_month, *all_months]))

    codes = _label_codes()
    files: dict[str, dict[str, Any]] = {}
    company_heads: dict[str, dict[str, Any]] = {}
    for group_id in group_ids:
        for company_id in members[group_id]:
            months, card = by_entity[("company", company_id)], profiles.get(company_id)
            months_out = entries[("company", company_id)]
            head = {
                "role": _nullable_text(_attribute(card, "group_role"), 80),
                "treasury_class": _nullable_text(_attribute(card, "treasury_structure"), 80),
                "truth": _truth(card, months[-1], codes),
                "inherits_liquidity": "inherited_from_group" in months_out[-1]["pillars"][0]["gates"],
                "first_month": months_out[0]["month"],
            }
            company_heads[company_id] = head
            files[f"companies/{company_id}.json"] = {
                "schema": BUNDLE_SCHEMA, "kind": "company", "id": company_id, "group_id": group_id,
                **head, "profile": _profile(card), "context": _context(card), "months": months_out,
                "series": _series(months), "alerts": alerts_of.get(company_id, []),
            }  # fmt: skip
            files[f"evidence/{company_id}.json"] = _evidence("company", company_id, group_id, months, evidence_months)

    portfolio_rows = []
    for group_id in group_ids:
        months, card = by_entity[("group", group_id)], profiles.get(group_id)
        months_out = entries[("group", group_id)]
        own_axis = [entry["month"] for entry in months_out]
        companies = []
        for company_id in members[group_id]:
            by_month = {entry["month"]: entry for entry in entries[("company", company_id)]}
            companies.append(
                {
                    "id": company_id,
                    **company_heads[company_id],
                    "shown": [by_month[m]["shown"] if m in by_month else None for m in own_axis],
                    "band": [by_month[m]["band"] if m in by_month else None for m in own_axis],
                }
            )
        context = _context(card)
        files[f"groups/{group_id}.json"] = {
            "schema": BUNDLE_SCHEMA, "kind": "group", "id": group_id, "first_month": own_axis[0],
            "profile": _profile(card), "context": context, "months": months_out, "companies": companies,
            "series": _series(months), "alerts": alerts_of.get(group_id, []),
        }  # fmt: skip
        files[f"evidence/{group_id}.json"] = _evidence("group", group_id, group_id, months, evidence_months)

        by_month = {entry["month"]: entry for entry in months_out}
        own_alerts = [alert for alert in alerts if alert["group_id"] == group_id]

        def column(getter: Any, by_month: Mapping[str, Any] = by_month) -> list[Any]:
            return [getter(by_month[m]) if m in by_month else None for m in axis]

        portfolio_rows.append(
            {
                "id": group_id,
                "n_companies": len(companies),
                "first_month": own_axis[0],
                "country": _nullable_text(_attribute(card, "country"), 80),
                "size_band": _nullable_text(_attribute(card, "size_band"), 80),
                "industry": _nullable_text((context["industry"] or {}).get("label"), 120),
                "shown": column(lambda entry: entry["shown"]),
                "band": column(lambda entry: entry["band"]),
                "direction": column(lambda entry: entry["verdict"]["direction"]),
                "nature": column(lambda entry: entry["verdict"]["nature"]),
                "conf": column(lambda entry: entry["conf"]["label"]),
                "abstained": column(lambda entry: entry["abstain"] is not None),
                "perimeter_changed": column(lambda entry: entry["perimeter_changed"]),
                "alerts_fired": [
                    sum(1 for a in own_alerts if a["month"] == m and a["state"] == "fired") for m in axis
                ],
                "alerts_muted": [
                    sum(1 for a in own_alerts if a["month"] == m and a["state"] != "fired") for m in axis
                ],
            }
        )

    # alerts of entities the bundle does not describe cannot be shown
    written = {name.split("/")[1][:-5] for name in files if not name.startswith("evidence/")}
    alerts = [alert for alert in alerts if alert["entity_id"] in written]
    files["portfolio.json"] = {"schema": BUNDLE_SCHEMA, "kind": "portfolio", "months": axis, "groups": portfolio_rows}
    files["alerts.json"] = {"schema": BUNDLE_SCHEMA, "kind": "alerts", "alerts": alerts}

    params_hash = str(getattr(params, "sha256", "") or "unhashed")
    dataset_hash = str(getattr(result, "dataset_hash", "") or "unknown")
    weights = {key: float(params.weights[key]) for key in PILLAR_KEYS}
    signals = [
        {"name": key, "label": PILLAR_LABELS[key], "weight": weights[key], "why": SIGNAL_WHY[key]}
        for key in PILLAR_KEYS
    ]
    signals += [{"name": name, "label": label, "weight": 0.0, "why": why} for name, label, why in ZERO_WEIGHT_SIGNALS]
    abstentions = []
    for name in sorted(files):
        folder, _, _ = name.partition("/")
        if folder not in ("groups", "companies"):
            continue
        entity, last = files[name], files[name]["months"][-1]
        if last["month"] == axis[-1] and last["abstain"] is not None:
            abstentions.append(
                {
                    "entity_kind": entity["kind"],
                    "entity_id": entity["id"],
                    "group_id": entity.get("group_id", entity["id"]),
                    "month": last["month"],
                    "reason": last["abstain"]["reason"],
                    "unlock": last["abstain"]["unlock"],
                }
            )
    abstentions.sort(key=lambda item: (item["entity_kind"] != "group", item["entity_id"]))
    files["receipt.json"] = {
        "schema": BUNDLE_SCHEMA, "kind": "receipt", "engine_version": ENGINE_VERSION,
        "params_hash": params_hash, "dataset_hash": dataset_hash, "signals": signals,
        "abstentions": abstentions, "checks": _checks(receipt, params_hash, dataset_hash),
    }  # fmt: skip

    _clean_target(out_dir)
    for name in sorted(files):
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_dump(files[name]))

    entities = [data for name, data in files.items() if name.startswith(("groups/", "companies/"))]
    manifest = {
        "schema": BUNDLE_SCHEMA,
        "kind": "manifest",
        "bundle_id": bundle_digest(out_dir),
        "engine_version": ENGINE_VERSION,
        "params_hash": params_hash,
        "dataset_hash": dataset_hash,
        "generated_at": stamp,
        "months": axis,
        "counts": {
            "groups": len(group_ids),
            "companies": sum(len(members[group_id]) for group_id in group_ids),
            "alerts": len(alerts),
        },
        "pillars": [
            {
                "key": key,
                "label": PILLAR_LABELS[key],
                "weight": weights[key],
                "baseline": _score_tenths(params.reference.medians[key]),
            }
            for key in PILLAR_KEYS
        ],
        "bands": bands,
        "glossary": _glossary(entities, alerts),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_bytes(_dump(manifest))
    return manifest


def export_from_result(
    result: ScoreResult,
    export_dir: Path,
    *,
    validation_path: Path | None = DEFAULT_VALIDATION_PATH,
    evidence_months: int = 24,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """CLI entry: ``export_bundle`` with the validation report when the file
    exists (``xray-score validate`` writes it), else the minimal receipt."""
    receipt = None
    if validation_path is not None and Path(validation_path).is_file():
        try:
            loaded = json.loads(Path(validation_path).read_text(encoding="utf-8"))
            receipt = loaded if isinstance(loaded, Mapping) else None
        except (OSError, ValueError):
            receipt = None
    return export_bundle(
        result, export_dir, evidence_months=evidence_months, receipt=receipt, generated_at=generated_at
    )


__all__ = [
    "BUNDLE_SCHEMA",
    "bundle_digest",
    "export_bundle",
    "export_from_result",
    "round_preserving_sum",
]
