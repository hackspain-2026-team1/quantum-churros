# Track.md → producto y pipeline

Trazabilidad entre [`track.md`](../../track.md), el motor y la demo navegable de Rumbo.

## Requisitos obligatorios

| track.md | Estado | Evidencia |
|----------|--------|-----------|
| Leer el rastro | Cubierto | Conciliación, invoice as-of e ingesta reproducible |
| El score, el eje | Cubierto | Aislamiento, aditividad, determinismo, estabilidad y trayectoria |
| Predicción test oculto | Cubierto como proxy | 60 grupos puntuados solos reproducen la cartera; el test real lo decide el organizador |
| Señal en dos direcciones | Cubierto | Trayectorias y alertas estructurales de mejora y deterioro |
| Trayectoria, no foto | Cubierto | Dirección, naturaleza, horizontes corto/largo y escenarios |
| Explicación | Cubierto | Pilares, delta_parts, cascada y recibo exacto |
| Producto encima del score | Cubierto | Diagnóstico, acciones, escenarios y financiación |
| Comprador identificado | Cubierto | Empresa usuaria de Embat; banco como receptor de cliente pre-calificado |
| Demo navegable | Cubierto | Radar, fichas, diagnóstico, acciones, escenarios, técnico y wiki |

## Bonus

| track.md | Estado | Evidencia |
|----------|--------|-----------|
| Anticipación medida | Implementado; publicación real pendiente | AUC h=3/h=6 y anticipación interna en cartera; calibración pareada y retardos desde onset en inyección |
| Monitor que avisa | Cubierto | Alertas generadas por el motor, inbox y vínculo alerta → causa → acción/financiación |

La AUC natural usa futuros onsets internos, no impagos etiquetados. Solo se publica cuando hay ambas clases y soporte suficiente. La inyección no se presenta como anticipación de un shock exógeno: mide discriminación y retardo desde un onset conocido. Véase [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md).

## Las seis preguntas

| Pregunta | Evidencia |
|----------|-----------|
| Quién está sano | Banda, score y persistencia de nivel |
| Quién mejora | Dirección, alertas de mejora y casos canónicos |
| Quién empieza a torcerse | Dirección, señal previa, alertas y escenario central |
| Bache o caída | Pico frente a escalón/rampa; naturaleza shock_pending frente a structural |
| Por qué cambió | Pilares movidos, delta_parts y acciones enlazadas |
| Cuándo se vio venir | Anticipación interna natural y retardo desde onset inyectado |

## Bloques de evaluación del jurado

| Bloque | Evidencia principal |
|--------|---------------------|
| Si acierta | Aislamiento, origen rodante, nivel frente a pendiente y AUC con soporte |
| Si llega a tiempo | Retardo step/ramp, picos no estructurales, anticipación interna y monitor |
| Si vale algo | Acciones, escenarios, financiación, comprador y demo navegable |
