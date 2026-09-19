#!/usr/bin/env python3
"""Print Phase A evaluation summary from validation.json (sin acrónimos)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from xray_engine.eval_labels import BAND_LABELS, CHECK_LABELS

PASS_LABEL = "superada"
FAIL_LABEL = "fallida"


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return PASS_LABEL if value else FAIL_LABEL
    if isinstance(value, float):
        if 0 <= value <= 1 and abs(value) <= 1:
            return f"{value:.4g}"
        return f"{value:.6g}"
    return str(value)


def _pct(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f} %"


def _check_label(key: str) -> str:
    return CHECK_LABELS.get(key, key.replace("_", " "))


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/validation.json")
    if not path.exists():
        print(f"No existe {path}. Ejecuta: make eval-phase-a", file=sys.stderr)
        return 1
    doc = json.loads(path.read_text(encoding="utf-8"))
    kpis = doc.get("kpis") or {}
    stages = kpis.get("by_stage") or {}
    reconcile = stages.get("reconcile") or {}
    normalize = stages.get("normalize") or {}
    score = stages.get("score") or {}
    window = kpis.get("window") or {}

    gate_keys = {
        "isolation", "truncation", "additivity", "scale", "determinism", "ablation",
        "neutrality", "rank_stability", "netting_placebo", "rolling_origin",
    }
    failed = [
        _check_label(key)
        for key, item in doc.items()
        if isinstance(item, dict) and item.get("pass") is False and key in gate_keys
    ]

    print("=" * 72)
    print("EVALUACIÓN FASE A — conciliación · normalización · scoring")
    print("=" * 72)
    print(f"Motor:              {doc.get('engine_version', '—')}")
    print(f"Huella del dataset: {str(doc.get('dataset_hash', '—'))[:16]}…")
    print(f"Huella parámetros:  {str(doc.get('params_hash', '—'))[:16]}…")
    print(f"Ventana:            {window.get('first_month', '—')} → {window.get('last_month', '—')}")
    print(f"Duración:           {doc.get('runtime_seconds', '—')} s")
    if failed:
        print(f"Pruebas obligatorias: FALLIDAS — {', '.join(failed)}")
    else:
        print("Pruebas obligatorias: todas superadas")
    print()

    print("── 1 · CONCILIACIÓN (¿leemos bien el rastro bancario?) ──")
    print("  Placebo de traspasos internos")
    print("    Qué prueba: los espejos y reversiones reales no son coincidencias de fechas.")
    print(f"    Resultado:  {_fmt(reconcile.get('netting_placebo_pass'))}")
    print("  Feed bancario caído")
    print("    Qué mide:   grupos sin movimientos recientes en el último mes.")
    print(f"    Resultado:  {_pct(reconcile.get('stale_feed_pct'))} de los grupos")
    print()

    print("── 2 · NORMALIZACIÓN (¿el panel respeta el tiempo y la moneda?) ──")
    print("  Sin mirar al futuro")
    print("    Qué prueba: truncar el histórico en un mes pasado no cambia scores anteriores.")
    print(f"    Resultado:  {_fmt(normalize.get('truncation_pass'))}")
    print("  Invarianza de escala")
    print("    Qué prueba: multiplicar todos los importes por 1024 no cambia el score.")
    print(f"    Resultado:  {_fmt(normalize.get('scale_pass'))}")
    print("  Cobertura de la cartera")
    print(f"    Grupos puntuables:     {_pct(normalize.get('coverage_scored_pct'))}")
    print(f"    Con pilar pagos:       {_pct(normalize.get('coverage_payments_pct'))}")
    print(f"    Con pilar cobros:      {_pct(normalize.get('coverage_collections_pct'))}")
    print(f"    Con pilar deuda:       {_pct(normalize.get('coverage_debt_pct'))}")
    print("  Neutralidad")
    print("    Qué prueba: el score no se explica por tamaño, ERP, banco ni mes del año.")
    print(f"    Exceso máximo η²:      {_fmt(normalize.get('neutrality_max_excess'))} (objetivo < 0,06)")
    print()

    print("── 3 · SCORING (¿el número es estable, explicable y honesto?) ──")
    print("  Ensayo aislado de 60 grupos (proxy del test oculto)")
    print("    Qué prueba: puntuar 60 grupos solos da el mismo score que en la cartera completa.")
    print(
        f"    Resultado:  {_fmt(score.get('isolation_pass'))} — "
        f"{score.get('holdout_n_groups', '—')} grupos, diferencia máxima {score.get('holdout_max_abs_diff', '—')}"
    )
    print("  Identidad aditiva")
    print("    Qué prueba: base + contribuciones − penalización − tope = score mostrado.")
    print(f"    Resultado:  {_fmt(score.get('additivity_pass'))}")
    print("  Determinismo")
    print("    Qué prueba: dos ejecuciones y filas barajadas producen el mismo resultado.")
    print(f"    Resultado:  {_fmt(score.get('determinism_pass'))}")
    print("  Estabilidad del orden")
    print("    Qué prueba: pequeños cambios de peso no reordenan la cartera entera.")
    print(f"    Resultado:  {_fmt(score.get('rank_stability_pass'))}")
    print("  Persistencia de nivel (3 meses)")
    print("    Qué mide:   si el score de hoy predice el score dentro de 3 meses.")
    print(f"    Resultado:  correlación {_fmt(score.get('level_autocorr_lag3'))}")
    print("  Persistencia de pendiente (3 meses)")
    print("    Qué mide:   si el cambio mensual del score se repite — suele ser bajo.")
    print(f"    Resultado:  correlación {_fmt(score.get('slope_autocorr_lag3'))}")
    print("  Origen rodante")
    print("    Qué prueba: re-puntuar solo con datos hasta 2025-11, 2026-02 y 2026-05.")
    print(f"    Correlación mínima en el mes del corte: {_fmt(score.get('rolling_min_spearman'))}")
    print("  Inyección de deterioros (monitor)")
    print("    Pico confundido con caída estructural:")
    print(f"      {_pct(score.get('p_structural_given_spike'))} (objetivo ≤ 10 %)")
    print("    Escalón leído como estructural:")
    print(f"      {_pct(score.get('p_structural_given_step'))} (objetivo ≥ 70 %)")
    print("    Rampa lenta leída como estructural:")
    print(f"      {_pct(score.get('p_structural_given_ramp'))} (informativo)")
    print("    Meses hasta detectar un escalón permanente (mediana):")
    print(f"      {_fmt(score.get('injection_median_verdict_delay_step'))} meses (objetivo ≤ 3)")
    print("    Meses hasta detectar una rampa (mediana):")
    print(f"      {_fmt(score.get('injection_median_verdict_delay_ramp'))} meses")
    print("    Alertas de deterioro sin inyección real:")
    print(f"      {_fmt(score.get('false_alarms_per_100_gy'))} por cada 100 grupo-años")
    print("    Acierto del abanico de escenarios a 3 meses:")
    print(f"      {_pct(score.get('outlook_fan_hit_rate'))}")
    print("    Tutorial completo:  make eval-injection  →  docs/engine/INJECTION_STUDY.md")
    print("  Anticipación natural (R9 — cartera real)")
    print("    AUC a 3 / 6 meses:")
    print(f"      {_fmt(score.get('natural_auc_h3'))} / {_fmt(score.get('natural_auc_h6'))}")
    print("    Meses de antelación mediana (señal → onset estructural):")
    print(f"      {_fmt(score.get('natural_median_lead_months'))} meses")
    print("    Calibración escalón AUC-6 (onset conocido):")
    print(f"      {_fmt(score.get('injection_cal_auc_h6_step'))}")
    print("    Informe completo:  make eval-anticipation  →  docs/engine/NATURAL_ANTICIPATION.md")
    print()

    coverage = doc.get("coverage") or {}
    groups = coverage.get("groups") or {}
    bands = groups.get("bands") or {}
    if bands:
        print("── Distribución por banda (último mes, grupos) ──")
        for key in ("critical", "watch", "stable", "solid"):
            if key in bands:
                print(f"  {BAND_LABELS.get(key, key):12} {bands[key]} grupos")
        print()

    rolling = doc.get("rolling_origin") or {}
    cuts = rolling.get("cuts") or {}
    if cuts:
        print("── Detalle origen rodante por mes de corte ──")
        for label, item in cuts.items():
            print(
                f"  Corte {label}: identidad {_fmt(item.get('pass'))}, "
                f"correlación {_fmt(item.get('spearman_at_cut'))}, "
                f"cambio de banda {_pct(item.get('band_change_share'))}"
            )
        print()

    print(f"Artefacto completo: {path}")
    print("Historial de runs:  docs/engine/KPI_HISTORY.md")
    print("Glosario:           docs/engine/EVALUATION.md § Estilo de presentación")
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
