#!/usr/bin/env python3
"""Tutorial legible del estudio de inyección desde validation.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

KIND_LABELS = {
    "spike": "Pico puntual de caja",
    "step": "Escalón brusco de cobros",
    "ramp": "Rampa lenta de cobros",
}

KIND_TUTORIAL = {
    "spike": """
Qué simula
  Un mes con un pago adelantado: las salidas de ese mes crecen como si hubiera un
  desembolso extra grande (el tamaño es la mediana de salidas de los seis meses
  anteriores). Los meses siguientes recuperan ese importe pagando menos, de modo
  que la caja cae un mes y vuelve.

Qué debería hacer el motor
  Etiquetar el episodio como bache (naturaleza «bump»), no como caída estructural.
  El objetivo publicado es que, como mucho, el 10 % de los picos se clasifiquen
  como estructurales.

Qué medimos
  • Probabilidad de caída estructural tras un pico
  • Retraso hasta veredicto de deterioro y hasta alerta
  • Caída media del score a 3 meses y al final del horizonte (debería ser pequeña)
  • Desglose en ventanas «tranquilas» (sin deterioro previo en la carrera real)
""",
    "step": """
Qué simula
  A partir de un mes, los cobros operativos caen un 30 % de golpe y se quedan
  ahí. La caja pierde el déficit acumulado mes a mes. Es el caso «algo ha roto
  en el negocio».

Qué debería hacer el motor
  Detectar deterioro estructural con poca demora. Objetivo: al menos el 70 % de
  los escalones y mediana de detección ≤ 3 meses.

Qué medimos
  • Probabilidad de caída estructural
  • Distribución de retrasos (mes +0, +1, +2… y «sin detectar»)
  • Caída media del score (debería ser grande, ~30–40 puntos al final)
  • Desglose por tamaño de empresa (micro / pequeña / mediana / grande)
""",
    "ramp": """
Qué simula
  Los cobros operativos caen un 30 % de forma gradual durante seis meses. Es el
  caso Northbrook del brief (45→65 al revés: erosión lenta). Comprueba la deriva
  de largo plazo, no el shock de un mes.

Qué debería hacer el motor
  Llegar tarde pero con veredicto estructural de horizonte largo. No hay gate
  duro en la validación actual, pero es la métrica clave del bonus «anticipación
  medida» en mejoras lentas.

Qué medimos
  • Probabilidad de caída estructural (actualmente ~67 %)
  • Retraso mediano (~3 meses en la cartera actual)
  • Cuántos casos no se detectan en el horizonte de 9 meses (~22 %)
""",
}


def _pct(value: object) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f} %"


def _num(value: object, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value == int(value):
        text = str(int(value))
    elif isinstance(value, float):
        text = f"{value:.2g}"
    else:
        text = str(value)
    return f"{text} {unit}".strip()


def _bar(label: str, count: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return f"  {label:12} —"
    filled = int(round(width * count / total))
    return f"  {label:12} {'█' * filled}{'·' * (width - filled)} {count:3} ({count / total * 100:4.1f} %)"


def _gate(kind: str, item: dict, targets: dict) -> str:
    if kind == "spike":
        limit = targets.get("p_structural_spike_max", 0.10)
        value = item.get("p_structural")
        if value is None:
            return "sin datos"
        return "CUMPLE" if value <= limit else f"REVISAR (>{_pct(limit)})"
    if kind == "step":
        limit = targets.get("p_structural_step_min", 0.70)
        value = item.get("p_structural")
        if value is None:
            return "sin datos"
        return "CUMPLE" if value >= limit else f"REVISAR (<{_pct(limit)})"
    return "informativo (sin gate duro)"


def _improvements(kind: str, item: dict, untouched: dict) -> list[str]:
    tips: list[str] = []
    n = item.get("n") or 0
    if not n:
        return ["Sin inyecciones aplicables en esta corrida."]

    undetected = (item.get("verdict_delay_distribution") or {}).get("none", 0)
    if undetected:
        tips.append(
            f"{undetected} de {n} ventanas ({undetected / n * 100:.1f} %) no recibieron "
            "veredicto de deterioro dentro del horizonte: revisar umbral "
            "`min_delta_points` o sensibilidad del horizonte corto."
        )

    if kind == "spike":
        p_struct = item.get("p_structural")
        p_verdict = item.get("p_verdict")
        quiet = item.get("quiet_base") or {}
        if p_verdict is not None and p_verdict > 0.35:
            tips.append(
                f"El { _pct(p_verdict) } de los picos dispara veredicto de deterioro aunque solo "
                f"{_pct(p_struct)} es estructural: el horizonte corto reacciona al shock; "
                "confirmar que la naturaleza «bache» domina en la interfaz."
            )
        if quiet.get("n") and quiet.get("p_structural") is not None:
            tips.append(
                f"En ventanas sin deterioro previo ({quiet['n']} casos), P(estructural|pico) = "
                f"{_pct(quiet['p_structural'])} — mejor lectura de la estabilidad real."
            )
        by_band = item.get("by_size_band") or {}
        for band, row in by_band.items():
            if row.get("p_structural") is not None and row["p_structural"] >= 0.10:
                tips.append(
                    f"Banda {band}: P(estructural|pico) = {_pct(row['p_structural'])} "
                    "(en el límite del 10 %): vigilar empresas grandes/pequeñas con poco colchón."
                )

    if kind == "step":
        delay = item.get("median_verdict_delay")
        if delay is not None and delay > 2:
            tips.append(
                f"Retraso mediano de {_num(delay, 'meses')}: por encima del objetivo cómodo "
                "(≤ 3 meses). Priorizar detección temprana en el escalón."
            )
        by_band = item.get("by_size_band") or {}
        for band, row in by_band.items():
            band_delay = row.get("median_verdict_delay")
            if band_delay is not None and band_delay >= 2:
                tips.append(
                    f"Banda {band}: retraso mediano {_num(band_delay, 'meses')} — "
                    "puede deberse a ventanas winsorizadas que amortiguan el golpe en empresas grandes."
                )

    if kind == "ramp":
        p_struct = item.get("p_structural")
        if p_struct is not None and p_struct < 0.75:
            tips.append(
                f"Solo {_pct(p_struct)} de las rampas se leen como estructurales: es el principal "
                "punto de mejora para el caso Northbrook (mejora lenta). Valorar umbral "
                "`long_threshold` o meses mínimos de deriva."
            )
        delay = item.get("median_verdict_delay")
        if delay is not None and delay >= 3:
            tips.append(
                f"Retraso mediano de {_num(delay, 'meses')}: aceptable para erosión lenta, "
                "pero 22 %+ sin detectar sugiere ampliar horizonte largo o reducir `long_threshold`."
            )
        horizons = item.get("structural_by_horizon") or {}
        long_calls = sum(horizons.get(key, 0) for key in ("long", "both"))
        total_struct = sum(horizons.values())
        if total_struct and long_calls / total_struct < 0.5:
            tips.append(
                "Menos de la mitad de las detecciones estructurales vienen del horizonte largo: "
                "la rampa podría estar captándose como shock corto antes de consolidarse."
            )

    healthy_rate = untouched.get("healthy_rate_per_100_group_years")
    base_rate = untouched.get("rate_per_100_group_years")
    if healthy_rate is not None and base_rate is not None and healthy_rate > base_rate * 1.5:
        tips.append(
            f"Falsas alarmas en grupos sanos del estudio ({_num(healthy_rate)} / 100 grupo-años) "
            f"superan la cartera ({_num(base_rate)}): muchos grupos «sanos» ya rozaban el umbral "
            "antes de inyectar; filtrar por ventanas tranquilas al interpretar."
        )

    if not tips:
        tips.append("Métricas dentro de objetivo en esta corrida; seguir monitorizando en KPI_HISTORY.")
    return tips


def _print_kind(kind: str, item: dict, targets: dict, untouched: dict) -> None:
    print("=" * 72)
    print(KIND_LABELS[kind].upper())
    print("=" * 72)
    print(KIND_TUTORIAL[kind].strip())
    print()
    print(f"Resultado global · gate: {_gate(kind, item, targets)}")
    print(f"  Ventanas analizadas     {_num(item.get('n'))}")
    print(f"  P(estructural)          {_pct(item.get('p_structural'))}")
    print(f"  P(veredicto deterioro)  {_pct(item.get('p_verdict'))}")
    print(f"  P(alerta disparada)     {_pct(item.get('p_alert'))}")
    print(f"  Retraso mediano veredicto {_num(item.get('median_verdict_delay'), 'meses')}")
    print(f"  Retraso mediano alerta    {_num(item.get('median_alert_delay'), 'meses')}")
    print(f"  Caída media score (+3m)   {_num(item.get('mean_drop_3m'), 'puntos')}")
    print(f"  Caída media score (final) {_num(item.get('mean_drop_end'), 'puntos')}")
    print()

    horizons = item.get("structural_by_horizon") or {}
    if horizons:
        print("Horizonte del veredicto estructural (cuando aplica):")
        for key, count in sorted(horizons.items()):
            label = {"short": "corto (3 meses)", "long": "largo (deriva)", "both": "ambos"}.get(key, key)
            print(f"  {label:22} {count}")
        print()

    distribution = item.get("verdict_delay_distribution") or {}
    if distribution:
        total = item.get("n") or 0
        print("Distribución de retraso hasta veredicto:")
        for delay in range(9):
            count = distribution.get(str(delay), 0)
            if count:
                print(_bar(f"mes +{delay}", count, total))
        none_count = distribution.get("none", 0)
        if none_count:
            print(_bar("sin detectar", none_count, total))
        print()

    by_band = item.get("by_size_band") or {}
    if by_band:
        print("Por tamaño de empresa:")
        print(f"  {'banda':8} {'n':>4} {'P(est)':>8} {'P(ver)':>8} {'retraso':>8}")
        for band, row in sorted(by_band.items()):
            print(
                f"  {band:8} {row.get('n', 0):4} "
                f"{_pct(row.get('p_structural')):>8} "
                f"{_pct(row.get('p_verdict')):>8} "
                f"{_num(row.get('median_verdict_delay'), 'm'):>8}"
            )
        print()

    print("Puntos de mejora:")
    for tip in _improvements(kind, item, untouched):
        print(f"  • {tip}")
    print()


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/validation.json")
    if not path.exists():
        print(f"No existe {path}. Ejecuta: make validate", file=sys.stderr)
        return 1

    doc = json.loads(path.read_text(encoding="utf-8"))
    injection = doc.get("injection") or {}
    by_kind = injection.get("by_kind") or {}
    targets = injection.get("targets") or {}
    untouched = injection.get("untouched") or {}
    outlook = doc.get("outlook_fan") or {}

    print("=" * 72)
    print("ESTUDIO DE INYECCIÓN — tutorial y resultados")
    print("=" * 72)
    print(f"Dataset:  {str(doc.get('dataset_hash', '—'))[:16]}…")
    print(f"Params:   {str(doc.get('params_hash', '—'))[:16]}…")
    print(f"Motor:    {doc.get('engine_version', '—')}")
    print()
    print("Cómo se construye el estudio")
    print("  1. Se eligen grupos sanos (score ≥ 60, feed activo, historia completa).")
    print("  2. Se inyecta un deterioro artificial en cuatro fechas distintas")
    print("     (11, 10, 9 y 8 meses antes del final).")
    print("  3. Solo se re-puntúa la entidad inyectada; la cartera real no cambia.")
    print("  4. Se observa durante 9 meses si aparece veredicto, alerta o caída estructural")
    print("     que no estaba en la carrera sin inyectar.")
    print()
    print(f"Resumen automático: {injection.get('summary', '—')}")
    print()
    print("Grupos sanos sin inyección (referencia de falsas alarmas):")
    print(f"  Alertas deterioro / 100 grupo-años (cartera)   {_num(untouched.get('rate_per_100_group_years'))}")
    print(f"  Ídem en ventanas sanas del estudio               {_num(untouched.get('healthy_rate_per_100_group_years'))}")
    print(f"  Ventanas tranquilas (sin deterioro previo)       {_num(untouched.get('quiet_windows'))}")
    print()

    if outlook:
        print("─ Abanico de escenarios (comprobación aparte) ─")
        print(f"  {outlook.get('summary', '—')}")
        print()

    for kind in ("spike", "step", "ramp"):
        _print_kind(kind, by_kind.get(kind) or {}, targets, untouched)

    print("=" * 72)
    print("Documentación ampliada: docs/engine/INJECTION_STUDY.md")
    print("Regenerar: make validate && make eval-injection")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
