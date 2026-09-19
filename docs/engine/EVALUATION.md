# Cómo probamos el motor (Fase A)

Protocolo de evaluación para las tres primeras etapas: **conciliación → normalización → scoring**. Este documento es la fuente de verdad sobre *cómo* medimos; los números viven en [`MODEL_CARD.md`](MODEL_CARD.md) y la serie temporal en [`KPI_HISTORY.md`](KPI_HISTORY.md).

Relacionado: [`VALIDATION.md`](VALIDATION.md) (checks completos, con códigos internos), [`TRACK_COVERAGE.md`](TRACK_COVERAGE.md) (track.md → pipeline), [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md) (AUC + lead-time).

## Estilo de presentación (sin acrónimos)

En informes para personas (`make eval-report`, [`KPI_HISTORY.md`](KPI_HISTORY.md), [`MODEL_CARD.md`](MODEL_CARD.md)) **no usamos códigos internos** (P1, R6, holdout, gy, ρ). Cada cifra lleva:

1. **Nombre en castellano** — qué aspecto del motor se examina.
2. **Qué se está probando** — una frase en lenguaje llano.
3. **Resultado** — superada / fallida, porcentaje o correlación, con objetivo cuando exista.

Las claves internas del motor (`netting_placebo`, `truncation`, …) viven solo en `validation.json` y en [`VALIDATION.md`](VALIDATION.md). Las etiquetas legibles están centralizadas en [`engine/src/xray_engine/eval_labels.py`](../engine/src/xray_engine/eval_labels.py).

| Código interno (solo docs técnicos) | Cómo lo mostramos al equipo |
|-----------------------------------|-----------------------------|
| `netting_placebo` | Placebo de traspasos internos |
| `truncation` | Sin mirar al futuro |
| `scale` | Invarianza de escala |
| `isolation` | Ensayo aislado de 60 grupos |
| `additivity` | Identidad aditiva |
| `determinism` | Determinismo |
| `rank_stability` | Estabilidad del orden |
| `level_vs_slope` | Persistencia de nivel vs pendiente |
| `rolling_origin` | Origen rodante |
| `injection` | Deterioros inyectados |
| `natural_anticipation` | Anticipación natural (AUC y lead-time) |
| «gy» | grupo-años |
| «ρ» / Spearman | correlación (Spearman) |

## ¿Hace falta un notebook?

**No como harness principal.** El notebook es útil para exploración puntual, no para regresión ni para la demo.

| Enfoque | Cuándo usarlo |
|---------|----------------|
| **`make daily-core`** | Cada cambio de motor/params: reproducible, comparable, una fila en KPI_HISTORY |
| **`make validate`** | Suite completa → `artifacts/validation.json` con `kpis.by_stage` |
| **Tests CI** (`make test-engine`) | Propiedades exactas en dataset sintético |
| **Notebook opcional** | Solo para analizar *a mano* un subconjunto tras inyección (ver abajo) |

Motivo: el jurado y el equipo necesitan **un solo artefacto sellado** (`dataset_hash`, `params_hash`, fecha), no celdas que nadie vuelve a ejecutar.

## Flujo diario (Fase A)

```bash
# Pipeline completo (recomendado)
make eval-phase-a XRAY_DATA=data/raw

# Con PostgreSQL (conciliación + ingesta)
make eval-phase-a-docker XRAY_DATA=data/raw

# Atajos
make daily-core          # = eval-phase-a
make daily-core-docker   # = eval-phase-a-docker

# Solo informe del último run
make eval-report
```

Salida:

- `artifacts/validation.json` — checks + `coverage` + `kpis.by_stage`
- `docs/engine/KPI_HISTORY.md` — fila append por run

## Qué prueba cada etapa

### 1 · Conciliación

| Qué | Cómo lo probamos | Gate |
|-----|------------------|------|
| Ingesta idempotente | `make db-seed-dry-run` → hash; `db-seed` no-op si igual | operacional |
| Lectura CSV (NUL, comillas) | `test_io.py` | CI |
| Espejos y reversiones | Placebo de traspasos internos | **obligatoria** |
| Facturas en su mes | `test_invoices_as_of.py` | CI |
| Feed bancario caído | bloque `coverage` | informativa |

**Regresión:** si falla el placebo de traspasos, no tocar scoring.

### 2 · Normalización

| Qué se prueba | Cómo lo probamos | Gate |
|---------------|------------------|------|
| Sin mirar al futuro | truncación en 3 cortes | **obligatoria** |
| Invarianza de escala | multiplicar importes ×1024 | **obligatoria** |
| Cobertura de pilares | bloque `coverage` | informativa |
| Neutralidad (tamaño, ERP, banco) | exceso η² | obligatoria |

### 3 · Scoring

| Qué se prueba | Cómo lo probamos | Gate |
|---------------|------------------|------|
| Ensayo aislado de 60 grupos | puntuar solos vs cartera completa | **obligatoria** |
| Identidad aditiva | desglose cuadra con el score | **obligatoria** |
| Determinismo | misma entrada, misma salida | **obligatoria** |
| Nivel frente a pendiente | correlación a 3 meses | informativa |
| Origen rodante | cortes 2025-11 / 2026-02 / 2026-05 | informativa |
| Deterioros inyectados | pico, escalón, rampa | informativa (publicar baseline) |
| Anticipación natural | AUC(h) + meses de antelación en cartera real | informativa ([`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md)) |

Comandos:

```bash
make eval-injection      # tutorial R8
make eval-anticipation   # informe AUC + lead-time
```

## Post-inyección de datos

La prueba de deterioros inyectados (`injection`) ya simula pico, escalón y rampa en grupos sanos dentro de `make validate`. Eso **es** la evaluación masiva post-inyección; no hace falta un segundo pipeline.

Si quieres **explorar gráficos** (distribución de delays por banda de tamaño, ventanas concretas):

1. Ejecuta `make validate` con dataset real.
2. Abre `artifacts/validation.json` → claves `injection.by_kind`, `injection.untouched`.
3. Ejecuta `make eval-injection` para el tutorial en terminal con puntos de mejora.
4. Lee [`INJECTION_STUDY.md`](INJECTION_STUDY.md) para el informe completo de R8.
5. Ejecuta `make eval-anticipation` y lee [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md) para AUC(h) y lead-time en cartera real (R9).

Regla: el notebook no sustituye a `validation.json`; como mucho visualiza lo ya sellado.

## Criterio de mejora

Tras cada cambio, comparar la última fila de KPI_HISTORY:

| Qué miramos | Mejor si… |
|-------------|-----------|
| Placebo de traspasos | sigue superada |
| Sin mirar al futuro / invarianza escala | siguen superadas |
| Grupos puntuables (%) | no cae sin motivo |
| Persistencia de nivel (3 meses) | se mantiene alta (~0,7+) |
| Persistencia de pendiente (3 meses) | baja o ≈0 (honesto) |
| Origen rodante (correlación mínima) | 1,0 (identidad al corte) |
| Pico confundido con caída estructural | baja (≤10 %) |
| Retardo mediano en escalón | baja (≤3 meses) |
| AUC anticipación · 3 meses (R9) | documentado; no retocar score para subirlo |
| Lead-time mediano cartera (R9) | publicado en [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md) |

## Segmentos sana / media / mala (Fase B)

La Fase A mide **cartera agregada**. La evaluación por segmento (roster demo) llegará en Fase B con `demo-roster` y desgloses en checks.

Casos canónicos del brief (tests, no métricas de cartera):

- `engine/tests/test_canonical_drift.py` — Northbrook 45→65, Velasco 82→68
