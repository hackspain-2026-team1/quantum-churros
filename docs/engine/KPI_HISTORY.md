# Historial de evaluación — Fase A

Una fila por `make eval-phase-a`. No editar a mano las filas generadas.

## Qué mide cada columna

| Columna | Qué se está probando |
| --- | --- |
| traspasos_ok | Traspasos internos: los espejos reales superan al placebo de fechas |
| sin_futuro_ok | Sin mirar al futuro: cortar datos en un mes pasado no altera ese mes |
| escala_ok | Invarianza de escala: ×1024 en importes no mueve el score |
| pct_puntuables | Grupos puntuables en el último mes (%) |
| grupos_ensayo | Grupos en el ensayo aislado (proxy del test oculto) |
| persistencia_nivel | Persistencia de nivel: correlación del score a 3 meses de distancia |
| persistencia_pendiente | Persistencia de pendiente: correlación del cambio mensual a 3 meses |
| origen_rodante | Origen rodante: correlación mínima al re-puntuar en cortes 2025-11, 2026-02, 2026-05 |
| pico_vs_caida | Probabilidad de llamar «caída estructural» a un pico de un mes |

| fecha | dataset | params | motor | traspasos_ok | sin_futuro_ok | escala_ok | pct_puntuables | grupos_ensayo | persistencia_nivel | persistencia_pendiente | origen_rodante | pico_vs_caida | runtime |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-19 14:11 UTC | `195ae6298c77117b49974a7a8c0d0bf362edbd68396c83cca44b00ff8f149412` | `b8d32c501400f6d218473e2334d2a74bc6dc6d4f5f16801cd3ab439c0bf676e3` | engine-v2 | sí | sí | sí | 0.88 | 60 | 0.0001889 | -0.1118 | 1 | 0.07692 | 149.2s |
| 2026-09-19 14:22 UTC | `195ae6298c77117b49974a7a8c0d0bf362edbd68396c83cca44b00ff8f149412` | `b8d32c501400f6d218473e2334d2a74bc6dc6d4f5f16801cd3ab439c0bf676e3` | engine-v2 | sí | sí | sí | 0.88 | 60 | 0.618 | -0.1364 | 1 | 0.07692 | 130.9s |
