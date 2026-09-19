# Track.md → pipeline (Fase A)

Trazabilidad entre [`track.md`](../../track.md) y las **tres etapas iniciales** del motor.

## Requisitos obligatorios cubiertos en Fase A

| track.md | Etapa | Evidencia |
|----------|-------|-----------|
| Leer el rastro | Conciliación | R6, invoice as-of, ingest |
| El score, el eje | Scoring | P1, P3, P5, R4, trajectory |
| Explicarse | Scoring | P3 additivity, receipt |
| Predicción test oculto | Scoring | P1 holdout 60 (proxy) |
| Trayectoria, no foto | Scoring | direction, nature, level_vs_slope |
| Señal dos direcciones | Scoring | R8 mejoras (baseline) |

## Pendiente de Fase B

| track.md | Etapa |
|----------|-------|
| Producto encima del score | Acciones + forecast |
| Demo navegable (guion 3 segmentos) | pitcher + roster |
| Bonus monitor (aviso anticipado `trend_shift_pending`) | Alertas (compañero) |

## Bonus cubiertos en MVP anticipación

| track.md | Evidencia |
|----------|-----------|
| **Anticipación medida** | `natural_anticipation`: AUC(h) + lead-time mediano en cartera real; calibración R8; [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md) |
| **Monitor que avisa** (parcial) | Lead-time desde alertas/veredictos en informe; alertas `deterioration_structural` ya disparan en producto |

## Las seis preguntas (Fase A)

| Pregunta | Medición Fase A |
|----------|-----------------|
| Quién está sano | band + score; R7 persistencia nivel |
| Quién mejora / torce | trajectory direction; R8 (inyección) |
| Bache o caída | R8 spike vs step |
| Por qué cambió | P3 delta_parts |
| Cuándo se vio venir | R8 delays + `natural_anticipation` lead-time |

## Bloques de evaluación del jurado

| Bloque | Fase A |
|--------|--------|
| Si acierta | P1, rolling_origin, level_vs_slope |
| Si llega a tiempo | R8 baseline + `natural_anticipation` |
| Si vale algo | receipt + gates; producto en Fase B |
