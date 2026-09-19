# Model card — Fase A (conciliación · normalización · scoring)

Resumen ejecutivo del motor **sin etiquetas**. Baseline del dataset del reto (ventana 2024-09 → 2026-08).

Convención: cada fila indica **qué se prueba**, el **resultado** y el **objetivo**. Sin códigos internos (P1, R6, holdout, …). Glosario: [`EVALUATION.md`](EVALUATION.md) § Estilo de presentación.

| Campo | Valor |
|-------|-------|
| Motor | engine-v2 |
| Huella de parámetros | `b8d32c501400f6d2…` |
| Huella del dataset | `195ae6298c77117b…` |
| Ventana | 2024-09 → 2026-08 |
| Última validación | ver [`KPI_HISTORY.md`](KPI_HISTORY.md) |

## Etapa 1 · Conciliación

| Qué se prueba | Resultado | Objetivo |
|---------------|-----------|----------|
| Placebo de traspasos internos — los espejos reales no son coincidencias de fechas | superada | superada |
| Feed bancario caído — grupos sin movimientos recientes | 12 % de los grupos | documentar |

## Etapa 2 · Normalización

| Qué se prueba | Resultado | Objetivo |
|---------------|-----------|----------|
| Sin mirar al futuro — truncar el histórico no altera meses pasados | superada | superada |
| Invarianza de escala — ×1024 en importes no mueve el score | superada | superada |
| Grupos puntuables en el último mes | 88 % | — |
| Cartera con pilar pagos | 42 % | — |
| Cartera con pilar cobros | 34 % | — |
| Cartera con pilar deuda | 78 % | — |
| Neutralidad — el score no se explica por tamaño, ERP o banco (exceso η² máximo) | 0,039 | < 0,06 |

## Etapa 3 · Scoring

| Qué se prueba | Resultado | Objetivo |
|---------------|-----------|----------|
| Ensayo aislado de 60 grupos — puntuar solos da el mismo score que en cartera | superada (60 grupos, Δ máx. 0) | superada |
| Identidad aditiva — el desglose cuadra con el score | superada | superada |
| Determinismo — misma entrada, misma salida | superada | superada |
| Persistencia de nivel — correlación del score a 3 meses | 0,62 | alta |
| Persistencia de pendiente — correlación del cambio mensual a 3 meses | −0,14 | baja |
| Origen rodante — re-puntuar en cortes históricos (correlación mínima) | 1,0 | 1,0 |
| Pico confundido con caída estructural | 7,7 % | ≤ 10 % |
| Meses hasta detectar un escalón permanente (mediana) | 1,0 | ≤ 3 |
| Alertas de deterioro sin inyección real | 24,4 por cada 100 grupo-años | documentar |

## Qué no prometemos

- No hay modelo entrenado con etiquetas: el score es un nivel auditable, no un clasificador ajustado a defaults históricos.
- La **pendiente** no persiste (correlación ≈ −0,14); la persistencia es de **nivel** (correlación ≈ 0,62).
- El test oculto del organizador se aproxima con el **ensayo aislado de 60 grupos** y parámetros congelados.

## Cómo regenerar

```bash
make eval-phase-a XRAY_DATA=data/raw
make eval-report
```

Detalle: [`EVALUATION.md`](EVALUATION.md) · [`VALIDATION.md`](VALIDATION.md) (códigos internos)
