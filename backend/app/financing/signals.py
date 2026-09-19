from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

PILLAR_LABELS = {
    "liquidity": "Liquidez",
    "payments": "Pagos",
    "collections": "Cobros",
    "activity": "Actividad",
    "debt": "Deuda",
}


@dataclass(frozen=True)
class FinancingSignal:
    entity_id: str
    company_name: str
    score_snapshot_id: str
    score: float
    previous_score: float
    amount: float
    amount_low: float
    amount_high: float
    source_month: date
    detected_since: date | None
    needed_from: date
    needed_to: date
    confidence: float
    trajectory: str
    trajectory_nature: str | None
    model_version: str
    params_hash: str
    dataset_hash: str
    drivers: dict[str, str]
    profile: dict[str, str]
    product_types: list[str]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _month(value: str | None) -> date | None:
    return date.fromisoformat(f"{value}-01") if value else None


def _add_months(value: date, count: int) -> date:
    index = value.year * 12 + value.month - 1 + count
    return date(index // 12, index % 12 + 1, 1)


def _round_down(value: float, step: float) -> float:
    return math.floor(value / step) * step


def _round_up(value: float, step: float) -> float:
    return math.ceil(value / step) * step


def _evidence_amount(
    bundle_dir: Path, entity_id: str, entry: dict[str, Any], action: dict[str, Any]
) -> float | None:
    evidence_path = bundle_dir / "evidence" / f"{entity_id}.json"
    if not evidence_path.is_file():
        return None
    evidence = _load(evidence_path)
    month = next(
        (
            item
            for item in evidence.get("months", [])
            if item.get("month") == entry.get("month")
        ),
        None,
    )
    if month is None:
        return None
    monthly_outflow = next(
        (
            row.get("value")
            for row in month.get("rows", [])
            if row.get("label") == "Mediana mensual de pagos operativos y deuda"
            and row.get("unit") == "EUR"
        ),
        None,
    )
    if monthly_outflow is None:
        return None
    return (
        max(0.0, float(action["target"]) - float(action["current"]))
        * float(monthly_outflow)
        / 30.0
    )


def _aliases(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    payload = _load(path)
    groups = payload.get("groups", {})
    return groups if isinstance(groups, dict) else {}


def _candidate(
    bundle_dir: Path, path: Path, aliases: dict[str, dict[str, Any]]
) -> tuple[tuple[Any, ...], FinancingSignal] | None:
    payload = _load(path)
    months = payload.get("months") or []
    if len(months) < 2:
        return None
    entry = months[-1]
    verdict = entry.get("verdict") or {}
    confidence = entry.get("conf") or {}
    if (
        entry.get("abstain") is not None
        or not entry.get("feed_live")
        or verdict.get("direction") != "deteriorating"
    ):
        return None
    action = next(
        (
            item
            for item in entry.get("actions", [])
            if item.get("id") == "liquidity-buffer"
        ),
        None,
    )
    if action is None:
        return None
    amount = action.get("amount_eur")
    if amount is None:
        amount = _evidence_amount(bundle_dir, payload["id"], entry, action)
    if amount is None or float(amount) <= 0:
        return None
    amount = float(amount)
    score = float(entry["shown"]) / 10.0
    previous_score = float(months[-2]["shown"]) / 10.0
    source_month = _month(entry["month"])
    if source_month is None:
        return None
    drivers = {
        PILLAR_LABELS.get(item["key"], item["key"].title()): str(item["note"])
        for item in sorted(
            entry.get("pillars", []),
            key=lambda item: abs(float(item.get("contrib") or 0)),
            reverse=True,
        )
        if item.get("note") and float(item.get("contrib") or 0) != 0
    }
    entity_id = str(payload["id"])
    name = str(aliases.get(entity_id, {}).get("name") or entity_id)
    alias = aliases.get(entity_id, {})
    rounded = max(5_000.0, round(amount / 1_000.0) * 1_000.0)
    signal = FinancingSignal(
        entity_id=entity_id,
        company_name=name,
        score_snapshot_id=f"{entity_id}:{entry['month']}:{entry['shown']}",
        score=score,
        previous_score=previous_score,
        amount=rounded,
        amount_low=max(5_000.0, _round_down(rounded * 0.85, 5_000.0)),
        amount_high=_round_up(rounded * 1.15, 5_000.0),
        source_month=source_month,
        detected_since=_month(verdict.get("detected_since")),
        needed_from=_add_months(source_month, 4),
        needed_to=_add_months(source_month, 6),
        confidence=float(confidence.get("value") or 0.0),
        trajectory=str(verdict["direction"]),
        trajectory_nature=verdict.get("nature"),
        model_version="engine-v2",
        params_hash="",
        dataset_hash="",
        drivers=dict(list(drivers.items())[:3]),
        profile={
            "country": str(alias.get("country") or "—"),
            "industry": str(alias.get("industry_label") or "Empresa"),
            "size": str(alias.get("size") or "—"),
        },
        product_types=[
            "linea_credito",
            *(
                ["factoring"]
                if any(
                    item.get("pillar") == "collections"
                    for item in entry.get("actions", [])
                )
                else []
            ),
        ],
    )
    eligible = (
        40 <= score < 80
        and float(confidence.get("value") or 0.0) >= 0.7
        and 50_000 <= rounded <= 750_000
    )
    rank = (
        0 if eligible else 1,
        0 if verdict.get("nature") == "structural" else 1,
        abs(math.log(max(rounded, 1.0) / 100_000.0)),
        entity_id,
    )
    return rank, signal


def load_financing_signal(bundle_dir: Path, aliases_path: Path) -> FinancingSignal:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Engine bundle not found at {bundle_dir}")
    manifest = _load(manifest_path)
    aliases = _aliases(aliases_path)
    candidates = [
        item
        for path in sorted((bundle_dir / "groups").glob("*.json"))
        if (item := _candidate(bundle_dir, path, aliases)) is not None
    ]
    if not candidates:
        raise RuntimeError(
            "The engine bundle contains no explainable financing candidate"
        )
    signal = min(candidates, key=lambda item: item[0])[1]
    return replace(
        signal,
        model_version=str(manifest.get("engine_version") or "engine-v2"),
        params_hash=str(manifest.get("params_hash") or "unknown"),
        dataset_hash=str(manifest.get("dataset_hash") or "unknown"),
    )
