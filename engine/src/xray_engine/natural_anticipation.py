"""Natural anticipation: AUC(h) and lead-time on portfolio and injection calibration.

Reads the published score only — no retuning. Target ``engine_outcome``: structural
deterioration (verdict or alert) that was not already present at month *t*.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from statistics import median
from typing import Any

import numpy as np

from .alerts import build_alerts
from .contracts import Alert, EntityMonth, Params
from .scoring import score_entity

DEFAULT_HORIZONS: tuple[int, ...] = (1, 3, 6, 9, 12)
CALIBRATION_KINDS: tuple[str, ...] = ("step", "ramp")
SIGNAL_ALERT_KINDS: frozenset[str] = frozenset({"deterioration_structural", "level_critical"})
AUDIT_HORIZON = 6
AUDIT_EPSILON = 0.01
LOOKBACK_MONTHS = 6


def _metric(label: str, value: Any, unit: str = "") -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f} %"


def _num(value: float | None, unit: str = "") -> str:
    if value is None:
        return "—"
    text = f"{int(value)}" if float(value) == int(value) else f"{value:.2g}"
    return f"{text} {unit}".strip()


def _deteriorating(item: EntityMonth, *, structural: bool = False) -> bool:
    verdict = item.trajectory
    if getattr(verdict, "direction", None) != "deteriorating":
        return False
    return not structural or getattr(verdict, "nature", None) == "structural"


def _eligible(item: EntityMonth) -> bool:
    parts = item.parts
    return bool(parts.feed_live and not parts.abstained and not parts.carried_from)


def _structural_alert_index(alerts: Sequence[Alert]) -> set[tuple[str, str, date]]:
    return {
        (alert.entity_kind, alert.entity_id, alert.month)
        for alert in alerts
        if alert.state == "fired" and alert.kind == "deterioration_structural"
    }


def _structural_at(
    item: EntityMonth,
    alert_index: set[tuple[str, str, date]],
) -> bool:
    if _deteriorating(item, structural=True):
        return True
    row = item.row
    return (row.entity_kind, row.entity_id, row.month) in alert_index


def _months_between(first: date, second: date) -> int:
    return (second.year - first.year) * 12 + second.month - first.month


def _auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    if len(scores) != len(labels) or len(scores) < 2:
        return None
    pos = int(sum(labels))
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return None
    ordered = sorted(zip(scores, labels, strict=True), key=lambda item: item[0])
    positive_rank_sum = 0.0
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][0] == ordered[start][0]:
            end += 1
        average_rank = (start + 1 + end) / 2
        positive_rank_sum += average_rank * sum(label for _, label in ordered[start:end])
        start = end
    return (positive_rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def _summarize_lead(delays: Sequence[int]) -> dict[str, Any]:
    if not delays:
        return {
            "median_months": None,
            "p25_months": None,
            "p75_months": None,
            "distribution": {},
            "n_events": 0,
        }
    ordered = sorted(delays)
    mid = len(ordered) // 2
    med = float(ordered[mid]) if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    p25 = float(ordered[max(0, len(ordered) // 4 - 1)])
    p75 = float(ordered[min(len(ordered) - 1, (3 * len(ordered)) // 4)])
    return {
        "median_months": med,
        "p25_months": p25,
        "p75_months": p75,
        "distribution": dict(Counter(str(delay) for delay in delays)),
        "n_events": len(delays),
    }


def _event_within_horizon(
    items: Sequence[EntityMonth],
    t_idx: int,
    horizon: int,
    alert_index: set[tuple[str, str, date]],
) -> bool | None:
    """True if structural onset in (t, t+h]; None if window breaks eligibility."""
    if _structural_at(items[t_idx], alert_index):
        return False
    end = min(t_idx + horizon, len(items) - 1)
    for at in range(t_idx + 1, end + 1):
        if not _eligible(items[at]):
            return None
        if _structural_at(items[at], alert_index):
            return True
    return False


def _risk_score(item: EntityMonth) -> float:
    return -float(item.parts.score)


def _build_horizon_metrics(
    observations: Sequence[Mapping[str, Any]],
    horizons: Sequence[int],
) -> dict[str, Any]:
    by_horizon: dict[str, Any] = {}
    for horizon in horizons:
        rows = [row for row in observations if row["horizon"] == horizon]
        labels = [int(row["label"]) for row in rows]
        scores = [float(row["risk_score"]) for row in rows]
        by_horizon[str(horizon)] = {
            "auc": _auc(scores, labels),
            "n_obs": len(rows),
            "n_pos": sum(labels),
            "n_neg": len(labels) - sum(labels),
        }
    return by_horizon


def _portfolio_observations(
    groups: Mapping[str, Sequence[EntityMonth]],
    alert_index: set[tuple[str, str, date]],
    *,
    horizons: Sequence[int],
    min_delta: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observations: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for group_id, items in groups.items():
        if len(items) < min(horizons) + 2:
            continue
        for horizon in horizons:
            for t_idx in range(len(items) - horizon):
                if not _eligible(items[t_idx]):
                    continue
                label = _event_within_horizon(items, t_idx, horizon, alert_index)
                if label is None:
                    continue
                observations.append({
                    "group_id": group_id,
                    "month": items[t_idx].row.month,
                    "horizon": horizon,
                    "label": int(label),
                    "risk_score": _risk_score(items[t_idx]),
                    "size_band": str(items[t_idx].parts.size_band),
                })
        had = False
        for idx, item in enumerate(items):
            if not _structural_at(item, alert_index):
                had = False
                continue
            if had:
                continue
            had = True
            signal_idx, signal_kind = _signal_before(items, idx, alert_index, min_delta=min_delta)
            if signal_idx is None:
                continue
            events.append({
                "group_id": group_id,
                "onset_month": item.row.month,
                "signal_month": items[signal_idx].row.month,
                "lead_months": idx - signal_idx,
                "signal_kind": signal_kind,
                "size_band": str(item.parts.size_band),
            })
    return observations, events


def _signal_before(
    items: Sequence[EntityMonth],
    onset_idx: int,
    alert_index: set[tuple[str, str, date]],
    *,
    min_delta: float,
) -> tuple[int | None, str | None]:
    for idx in range(onset_idx - 1, max(-1, onset_idx - LOOKBACK_MONTHS - 1), -1):
        item = items[idx]
        if not _eligible(item):
            continue
        if _deteriorating(item):
            return idx, "verdict"
        row = item.row
        if (row.entity_kind, row.entity_id, row.month) in alert_index:
            return idx, "alert"
        if idx > 0:
            drop = items[idx].parts.score - items[idx - 1].parts.score
            if drop <= -min_delta:
                return idx, "score_drop"
    return None, None


def natural_portfolio_study(
    scored: Any,
    *,
    horizons: Sequence[int] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    from .validation import _groups

    alert_index = _structural_alert_index(scored.alerts)
    groups = _groups(scored)
    observations, events = _portfolio_observations(
        groups,
        alert_index,
        horizons=horizons,
        min_delta=scored.params.trajectory.min_delta_points / 2,
    )
    by_horizon = _build_horizon_metrics(observations, horizons)
    delays = [event["lead_months"] for event in events]
    lead = _summarize_lead(delays)
    live_months = sum(
        _eligible(item) for items in groups.values() for item in items
    )
    events_per_100_gy = (
        100 * len(events) / (live_months / 12) if live_months else None
    )
    bands: dict[str, list[int]] = defaultdict(list)
    for event in events:
        bands[event["size_band"]].append(event["lead_months"])
    return {
        "by_horizon": by_horizon,
        "lead_time": lead,
        "events_per_100_group_years": events_per_100_gy,
        "by_size_band": {
            band: _summarize_lead(delays) for band, delays in sorted(bands.items())
        },
        "n_observations": len(observations),
        "n_events": len(events),
    }


def injection_calibration_study(
    scored: Any,
    *,
    horizons: Sequence[int] = (3, 6),
) -> dict[str, Any]:
    from .validation import _deteriorating as inj_deteriorating, _groups, inject

    params = scored.params
    window = scored.tables.window
    observations: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CALIBRATION_KINDS}
    detection_rows: dict[str, list[int]] = {kind: [] for kind in CALIBRATION_KINDS}
    structural_rows: dict[str, list[int]] = {kind: [] for kind in CALIBRATION_KINDS}
    windows: Counter[str] = Counter()

    for base in _groups(scored).values():
        if base[0].row.month != window.first_month or base[-1].row.month != window.last_month:
            continue
        rows = [item.row for item in base]
        for back in (11, 10, 9, 8):
            first = len(base) - 1 - back
            last = first + 9 - 1
            if first < 8 or last >= len(base):
                continue
            before = base[first - 1].parts
            if before.score < 60.0 or before.abstained or not all(
                item.parts.feed_live for item in base[first - 1: last + 1]
            ):
                continue
            for kind in CALIBRATION_KINDS:
                injected = score_entity(inject(rows, kind, base[first].row.month, params), params)
                windows[kind] += 1
                detected = next(
                    (
                        at for at in range(first, last + 1)
                        if inj_deteriorating(injected[at]) and not inj_deteriorating(base[at])
                    ),
                    None,
                )
                structural = next(
                    (
                        at for at in range(first, last + 1)
                        if inj_deteriorating(injected[at], True)
                        and not inj_deteriorating(base[at], True)
                    ),
                    None,
                )
                if detected is not None:
                    detection_rows[kind].append(detected - first)
                if structural is not None:
                    structural_rows[kind].append(structural - first)
                for horizon in horizons:
                    for at in range(first, min(first + horizon, last + 1)):
                        if not _eligible(base[at]) or not _eligible(injected[at]):
                            continue
                        uplift = float(base[at].parts.score - injected[at].parts.score)
                        observations[kind].extend((
                            {"horizon": horizon, "label": 1, "risk_score": uplift},
                            {"horizon": horizon, "label": 0, "risk_score": 0.0},
                        ))

    by_kind: dict[str, Any] = {}
    for kind in CALIBRATION_KINDS:
        rows = observations[kind]
        by_horizon = _build_horizon_metrics(rows, horizons)
        detected = len(detection_rows[kind])
        structural = len(structural_rows[kind])
        by_kind[kind] = {
            "by_horizon": by_horizon,
            "detection_delay": _summarize_lead(detection_rows[kind]),
            "structural_delay": _summarize_lead(structural_rows[kind]),
            "n_windows": windows[kind],
            "detection_rate": detected / windows[kind] if windows[kind] else None,
            "structural_rate": structural / windows[kind] if windows[kind] else None,
            "n_observations": len(rows),
        }
        for horizon in horizons:
            by_kind[kind][f"auc_h{horizon}"] = by_horizon.get(str(horizon), {}).get("auc")
    return by_kind


def audit_rolling_origin(
    scored: Any,
    natural: Mapping[str, Any],
    *,
    horizon: int = AUDIT_HORIZON,
    epsilon: float = AUDIT_EPSILON,
) -> dict[str, Any]:
    from .validation import ROLLING_ORIGIN_CUTS, score_core, truncate_tables

    full_auc = (natural.get("by_horizon") or {}).get(str(horizon), {}).get("auc")
    by_cut: dict[str, Any] = {}
    for month in ROLLING_ORIGIN_CUTS:
        if month <= scored.tables.window.first_month or month >= scored.tables.window.last_month:
            continue
        truncated = score_core(truncate_tables(scored.tables, month, scored.params), scored.params)
        partial = natural_portfolio_study(truncated, horizons=(horizon,))
        partial_auc = (partial.get("by_horizon") or {}).get(str(horizon), {}).get("auc")
        delta = (
            abs(float(full_auc) - float(partial_auc))
            if full_auc is not None and partial_auc is not None
            else None
        )
        by_cut[f"{month:%Y-%m}"] = {
            "auc": partial_auc,
            "delta_from_full": delta,
            "within_tolerance": None if delta is None else delta <= epsilon,
        }
    deltas = [item["delta_from_full"] for item in by_cut.values() if item["delta_from_full"] is not None]
    ok = bool(deltas) and all(delta <= epsilon for delta in deltas)
    return {
        "horizon_months": horizon,
        "full_auc": full_auc,
        "epsilon": epsilon,
        "pass": ok if deltas else None,
        "cuts": by_cut,
    }


def anticipation_study(scored: Any) -> dict[str, Any]:
    """Full anticipation report: natural portfolio, injection calibration, audit."""
    natural = natural_portfolio_study(scored)
    calibration = injection_calibration_study(scored)
    audit = audit_rolling_origin(scored, natural)
    h3 = (natural.get("by_horizon") or {}).get("3", {})
    h6 = (natural.get("by_horizon") or {}).get("6", {})
    step_cal = calibration.get("step") or {}
    lead = natural.get("lead_time") or {}
    summary = (
        f"Cartera real: AUC a 3 meses {_num(h3.get('auc'))} "
        f"({h3.get('n_pos', 0)} eventos / {h3.get('n_obs', 0)} observaciones); "
        f"AUC a 6 meses {_num(h6.get('auc'))}. "
        f"Anticipación mediana {_num(lead.get('median_months'), 'meses')} "
        f"({lead.get('n_events', 0)} onsets). "
        f"Calibración escalón AUC-6 {_num(step_cal.get('auc_h6'))}, "
        f"lead mediano {_num((step_cal.get('lead_time') or {}).get('median_months'), 'meses')}."
    )
    metrics = [
        _metric("AUC cartera · 3 meses", h3.get("auc")),
        _metric("AUC cartera · 6 meses", h6.get("auc")),
        _metric("Anticipación mediana · cartera", lead.get("median_months"), "meses"),
        _metric("Eventos por 100 grupo-años", natural.get("events_per_100_group_years")),
        _metric("AUC calibración · escalón · 6 meses", step_cal.get("auc_h6")),
        _metric(
            "Lead mediano · calibración · escalón",
            (step_cal.get("lead_time") or {}).get("median_months"),
            "meses",
        ),
        _metric("Auditoría origen rodante", audit.get("pass")),
    ]
    return {
        "pass": None,
        "natural": natural,
        "calibration_on_injection": calibration,
        "audit_rolling_origin": audit,
        "summary": summary,
        "metrics": metrics,
    }
