#!/usr/bin/env python3
"""Human-readable natural anticipation report from validation.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _num(value: object, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        text = f"{int(value)}" if value == int(value) else f"{value:.3g}"
    else:
        text = str(value)
    return f"{text} {unit}".strip()


def _horizon_table(by_horizon: dict) -> None:
    print("  h (meses)   AUC      positivos   observaciones")
    print("  " + "-" * 44)
    for key in sorted(by_horizon, key=lambda item: int(item)):
        row = by_horizon[key]
        print(
            f"  {int(key):>9}   {_num(row.get('auc')):>8}   "
            f"{row.get('n_pos', 0):>9}   {row.get('n_obs', 0):>13}"
        )


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/validation.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    block = doc.get("natural_anticipation") or {}
    natural = block.get("natural") or {}
    calibration = block.get("calibration_on_injection") or {}
    audit = block.get("audit_rolling_origin") or {}
    lead = natural.get("lead_time") or {}

    print("=" * 72)
    print("ANTICIPACIÓN NATURAL — informe de evaluación")
    print("=" * 72)
    print(f"Dataset: {doc.get('dataset_hash', '—')[:16]}…")
    print(f"Params:  {doc.get('params_hash', '—')[:16]}…")
    print(f"Motor:   {doc.get('engine_version', '—')}")
    print()
    print(block.get("summary", ""))
    print()

    print("1 · Cartera real (target: deterioro estructural en los próximos h meses)")
    print("-" * 72)
    print("Qué medimos: si la nota de hoy ordena quién empeorará de verdad, y cuántos")
    print("meses antes aparece la señal respecto al onset estructural.")
    print()
    _horizon_table(natural.get("by_horizon") or {})
    print()
    print(f"  Anticipación mediana: {_num(lead.get('median_months'), 'meses')}")
    print(f"  Onsets observados:    {lead.get('n_events', 0)}")
    print(f"  Eventos / 100 gy:     {_num(natural.get('events_per_100_group_years'))}")
    print()

    print("2 · Calibración con inyección (onset conocido — escalón y rampa)")
    print("-" * 72)
    for kind, label in (("step", "Escalón brusco"), ("ramp", "Rampa lenta")):
        item = calibration.get(kind) or {}
        item_lead = item.get("lead_time") or {}
        print(f"  {label}")
        print(f"    AUC a 6 meses: {_num(item.get('auc_h6'))}")
        print(f"    Lead mediano:  {_num(item_lead.get('median_months'), 'meses')}")
    print()

    print("3 · Auditoría origen rodante (misma metodología sin mirar al futuro)")
    print("-" * 72)
    print(f"  AUC completo (h=6): {_num(audit.get('full_auc'))}")
    for cut, row in sorted((audit.get("cuts") or {}).items()):
        ok = row.get("within_tolerance")
        mark = "ok" if ok else ("—" if ok is None else "revisar")
        print(
            f"  Corte {cut}: AUC {_num(row.get('auc'))} · "
            f"Δ {_num(row.get('delta_from_full'))} · {mark}"
        )
    print()
    print("Interpretación: la inyección prueba capacidad del motor; la cartera real")
    print("publica lo observado sin retocar la nota. No hay labels de quiebra.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
