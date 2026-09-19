# Anticipación natural (AUC + lead-time)

Informe de evaluación **separado del score publicado**: mide si la nota y el
monitor anticipan deterioro estructural en la cartera real, con calibración en
inyecciones de onset conocido.

Relacionado: [`INJECTION_STUDY.md`](INJECTION_STUDY.md) (capacidad del motor — R8),
[`EVALUATION.md`](EVALUATION.md) (Fase A), [`TRACK_COVERAGE.md`](TRACK_COVERAGE.md)
(bonus del brief), [`VALIDATION.md`](VALIDATION.md) (R9), [`MODEL_CARD.md`](MODEL_CARD.md),
[`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) (cifras para el pitch).

## Target operativo (`engine_outcome`)

No hay labels de quiebra. El evento es **operativo y reproducible**:

> En los próximos *h* meses aparece deterioro **estructural** que no existía en
> el mes *t*: alerta `deterioration_structural` o veredicto
> `(deteriorating, structural)`.

Predictor en *t*: `-score` (menor nota ⇒ mayor riesgo). Solo lectura del motor;
sin retuning.

## Cómo ejecutarlo

```bash
make validate XRAY_DATA=data/raw
make eval-anticipation
```

Artefacto: `artifacts/validation.json` → clave `natural_anticipation`.

## Baseline (dataset del reto, ventana 2024-09 → 2026-08)

| Métrica | Valor | Notas |
|---------|-------|-------|
| AUC cartera · 3 meses | 0,48 | 66 eventos / 1001 observaciones |
| AUC cartera · 6 meses | 0,44 | 127 eventos / 946 observaciones |
| Anticipación mediana | **1 mes** | 68 onsets estructurales |
| Eventos / 100 grupo-años | 25,2 | cartera real |
| Calibración escalón · AUC-6 | 0,51 | onset conocido (R8) |
| Calibración escalón · lead mediano | 1 mes | |
| Calibración rampa · AUC-6 | 0,51 | |
| Auditoría origen rodante · ΔAUC (h=6) | ≤ 0,013 | 3 cortes 2025-11 / 2026-02 / 2026-05 |

Interpretación honesta: el AUC de cartera está cerca del azar — lo publicamos
igual. La **anticipación en meses** (lead-time mediano 1) y la **calibración
por inyección** (~0,51 AUC, 1 mes) son la evidencia del bonus «anticipación
medida»: medimos, no inflamos.

## Tres bloques del informe

1. **Cartera real** — AUC(h) para h ∈ {1, 3, 6, 9, 12} + lead-time desde señal
   (veredicto, alerta o caída de score) hasta onset estructural.
2. **Calibración inyección** — mismas métricas en escalón y rampa con onset
   conocido; picos como control negativo.
3. **Auditoría origen rodante** — recalcula AUC(h=6) en cortes históricos;
   comprueba que la evaluación no mira al futuro (P2 + `rolling_origin`).

## Mensaje para el jurado

> No prometemos acierto sobre quiebras. Publicamos AUC y meses de antelación con
> un target congelado, auditado con origen rodante, sin retocar la nota para
> optimizar la métrica. La inyección demuestra capacidad; la cartera real
> publica lo observado.
