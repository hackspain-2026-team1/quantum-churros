# Handoff — estado del proyecto y siguientes pasos (19-sep-2026, tarde)

Documento para quien retome el trabajo (otro agente o persona). Cubre qué es el
proyecto, cómo se ejecuta, qué está hecho, el diseño de lo que está en curso y
los pasos que faltan, con rutas exactas. Todo lo afirmado acá está medido sobre
el dataset real; si un número no está, no te lo inventes: medilo.

## 1. Qué es esto

HackSpain 2026, reto "X Ray" (Embat). Dataset sintético: 1.286 empresas en 250
grupos, 24 meses (2024-09 a 2026-08), 8 CSV. Consigna: score mensual 0-100 de
salud financiera + un producto vendible encima. El motor es **determinista**,
sin entrenamiento (el dataset no tiene etiquetas): es un sistema de medición
con anclas de dominio congeladas, no un modelo.

- Repo: `hackspain-2026-team1/quantum-churros` (PÚBLICO — es parte de la entrega).
- Dataset: `/Users/bruno/Downloads/output/*.csv` (FUERA del repo; hay copia en
  `data/raw/`, git-ignored). **Nunca commitear el dataset.**
- Rama de trabajo actual: `feat/credible-actions` (PR #1 ya mergeado a `main`).
- Último commit de la rama: `1b4db5b`.

## 2. Cómo ejecutar todo

```bash
export PATH="$HOME/Library/Python/3.12/bin:$PATH"   # uv
cd /Users/bruno/Documents/quantum-churros

# Tests del motor (rápidos, sin dataset)
uv run --package xray-engine pytest engine/tests -q          # 390 passed, 23 skipped

# Tests del backend
uv run --package quantum-churros-api pytest backend/tests -q # 46 passed

# Frontend (bun está instalado global vía npm)
cd frontend && bun install --frozen-lockfile && bun run check && bun run test

# Corrida real completa (~30 s): scores + panel + bundle estático del front
uv run --package xray-engine xray-score predict data/raw \
  --out artifacts/full --export-dir frontend/static/data/v1 --evidence-months 6

# Validación completa (sin etiquetas): aislamiento, truncado, aditividad,
# determinismo, inyección, anticipación natural (R9), persistencia de veredictos
uv run --package xray-engine xray-score validate data/raw --out artifacts/validation.json
make eval-anticipation   # informe AUC(h) + lead-time → docs/engine/NATURAL_ANTICIPATION.md

# App (docker): web en localhost:3000, api en :8000, postgres en :5433
make up        # o: docker compose -f compose.yaml -f compose.dev.yaml up --build -d

# Base de datos: el motor también lee de Postgres (mismas salidas que el CSV)
make db-seed          # ingesta idempotente a source.*
make db-publish       # carga artifacts/full en xray.entity_month_panel/_score/alert
```

El bundle real vive en `frontend/static/data/v1/` (git-ignored, 103 MB). El
frontend NO tiene datos hardcodeados: solo muestra lo que el bundle trae. La
fixture de tests está en `frontend/e2e/fixtures/bundle/v1/`.

## 3. Arquitectura del motor

Paquete `engine/src/xray_engine/` (Python puro, polars; 46 columnas en
`scores.parquet`, 77 en `panel.parquet`):

```
io.py        → lectura de los 8 CSV (o de source.* por URL de Postgres), caché parquet
cleaning.py  → neteo de espejos intra-grupo (46,7 % del valor de salidas),
               reversiones mismo-producto, clasificación de categoría "-"
invoices.py  → días más allá del vencimiento as-of, cohortes de 90 días
panel.py     → 77 columnas punto-en-el-tiempo por empresa-mes y grupo-mes
pillars.py   → los 5 pilares 0-100 (funciones puras sobre PanelRow)
aggregate.py → score = base + Σ contribuciones − penalización − tope (identidad exacta)
trajectory.py→ dirección/naturaleza del movimiento (regla nueva, ver §6)
actions.py   → acciones sugeridas (rediseñado, ver §5)
profile.py   → ficha de empresa (contexto, no es eje del score)
reference.py → params/reference_v1.json (anclas congeladas) + sha256
scoring.py   → orquestación: score_dataset / score_tables
export.py    → bundle JSON estático para el front
validation.py→ suite sin etiquetas (+ natural_anticipation R9)
natural_anticipation.py → AUC(h) y lead-time en cartera real
```

**Score:** 5 pilares con pesos Liquidez 30 / Pagos 20 / Cobros 15 / Actividad 20
/ Deuda 15. Cada pilar sale de una tabla de anclas fija (tipo Paydex para
pagos/cobros; anclas de liquidez segmentadas por banda de tamaño de empresa).
Pilar no observable ⇒ no cuenta (no se inventa). Penalización 0,5·max(0, 40 −
mín P); topes duros: caja+disponible negativa ≥3 de 6 meses ⇒ ≤40, pagos <40 ⇒
≤50. La suma es exacta (cada punto se explica). Abstención explícita en 12 % de
grupos; feed muerto ⇒ arrastra el último score (stale, 12 %). Industria de Juan
y benchmarks Tesorio = contexto en la ficha, nunca eje de scoring.

**Trayectoria (regla nueva, commits `447565c`-`426c414`):** un movimiento de
≥6 puntos sobre 3 meses es estructural si (a) se sostiene 2 meses, (b) no está
ya rebotando y (c) se espera que aguante según el nivel propio (mediana de 12
meses, retención 0,5) o no depende de un solo mes. Inyección: P(estructural |
pico de 1 mes) = 7,7 % (meta ≤10 %); escalones inyectados se detectan 81 % con
2 meses de demora. La persistencia medida quedó en 63 % (estructural) vs 63,5 %
(pendiente) a nivel pooled — la separación real está en el horizonte corto
(87,5 % grupos / 76,4 % empresas). Ver `verdict_persistence` en validation.

## 4. Base de datos

- `source.*`: copia 1:1 de los CSV keyeada por `dataset_hash` (sha256 de
  archivos). La ingesta filtra bytes NUL (Postgres no los acepta; antes `make
  db-seed` fallaba siempre).
- `xray.entity_month_panel` (77 columnas), `xray.entity_month_score` (score,
  banda, pilares aplanados como columnas; drivers/trayectoria en JSONB),
  `xray.alert`. Layout generado en `backend/app/engine_tables.py`; el
  publicador (`backend/app/publish.py`) rechaza esquemas desviados.
- `xray-score predict postgresql://xray:xray-local@localhost:5433/xray` da
  salidas idénticas al CSV (verificado tabla a tabla).
- Migración `20260918_02` está vaciada (antes traía scores viejos hardcodeados);
  `20260919_07` borra esas filas.

## 5. El trabajo en curso: acciones (lo más reciente)

**Diseño nuevo (commit `1b4db5b`, `engine/src/xray_engine/actions.py`):** cada
acción es un **delta sobre los insumos medidos** del mes; el uplift es el score
que el motor da a ese mes modificado, recalculando los 5 pilares + agregación
(penalización y topes incluidos). Nada se estima a mano.

Las 5 palancas y su efecto real (recalculado):

| Pilar | Palanca (acotada) | Efecto en caja | Efecto colateral real |
|---|---|---|---|
| Liquidez | +≤30 días de colchón (capital / financiación a largo plazo; una póliza NO sirve: su disponible ya está contado) | +€ | — |
| Pagos | −≤30 días de atraso a proveedores | −€ (monto cohorte × días/90) | Liquidez baja |
| Cobros | −≤30 días de atraso de clientes | +€ | Liquidez sube |
| Actividad | +15 % de entradas operativas (escala op_in 6m/12m y recent mean) | +€ (un mes de la entrada extra) | Deuda alivia (misma cuota/más ingresos) |
| Deuda | −30 % de servicio de deuda (refinanciación) | +€ (el alivio mensual) | Liquidez sube |

El tope de caja negativa reacciona solo: `neg_liquidity_months_6m` se ajusta si
la acción voltea el signo del cierre del mes.

**Escalera (`ActionPlan.stages`):** etapa 1 sobre el mes actual; cada etapa
siguiente actúa sobre el mes que produjo la anterior, hasta `MAX_STAGES=3`.
`max_score`/`max_uplift` = mejor alcanzable con palancas acotadas. Un caso con
deuda al 906 % de los cobros termina en ~300 %: ahí la escalera muestra
honestamente "no se arregla solo con gestión" → engancha con financiación (§7
paso 4).

**Hecho:** `actions.py` reescrito + tests (`engine/tests/test_actions.py`, 10
tests incl. ladder, caja honesta, determinismo). Suite completa en verde.
También hechos los pasos 2-4:

- **Paso 2 (hecho):** la escalera se exporta en `actions_plan` (stages + max) y
  se muestra en la página de entidad.
- **Paso 3 (hecho):** `invoices.py:open_overdue_ar` + `invoices_due.json` en el
  bundle (top 20 facturas abiertas vencidas por empresa y grupo) + recordatorios
  con botón de envío en la página de entidad.
- **Paso 4 (hecho):** `financing.py` con 5 instrumentos (factoring, confirming,
  póliza nueva, reestructuración, barrido intragrupo), exportado en el campo
  `financing` y mostrado en la página de entidad. Medido en real: 66/250 grupos
  y 211/1.286 empresas reciben al menos una recomendación en 2026-08.

**Pendiente de este trabajo (no empezado):**

- (nada del bloque de acciones; ver pasos 5-7 abajo)
- **Antiguo paso 2 — exportar la escalera al bundle (hecho).** `export.py:_actions` (línea ~343)
  todavía solo emite `actions` (etapa 1) y `actions_combined`. Agregar campo
  opcional `actions_plan` con `stages[{number, score_tenths, uplift_tenths,
  actions[]}]`, `max_score_tenths`, `max_uplift_tenths`. Contratos a tocar:
  `frontend/src/lib/xray/contract.ts` (campos opcionales nuevos, mismo patrón
  que `actions`/`actions_combined`), y los tests de contrato:
  `engine/tests/test_export_contract.py`, `frontend/src/lib/xray/contract.spec.ts`,
  `frontend/src/lib/xray/bundle.spec.ts`. UI: mostrar la escalera en la pantalla
  Escenarios (`scenario-view.svelte` usa `entryActions`/`projectedTenths` de
  `actions.ts`).

- **Paso 3 — recordatorios de cobro con facturas.** El motor ya calcula
  `ar_days_beyond_terms` y `ar_amount` por entidad-mes (cohorte de facturas
  vencidas en 90 días, `invoices.py`), pero el detalle por factura no llega al
  bundle. Hay que exportar, para cada acción de cobros (o cada entidad con
  clientes vencidos), la lista de facturas abiertas vencidas: cliente
  (counterparty_id), importe, días vencida, ordenada por monto. Implica
  conservar en `scoring.py`/`export.py` una vista de facturas abiertas as-of
  por empresa (los datos están en `clean.invoices`; hoy solo se agregan). Cuidar
  el tamaño del bundle (103 MB; la lista solo para el último mes mostrado).

- **Paso 4 — financiación ("no se arregla con gestión").** Reglas deterministas
  en un módulo puro nuevo (`engine/src/xray_engine/financing.py`), sobre la
  ficha y el panel del último mes: clientes pagan tarde + caja corta ⇒ factoring
  (monto = facturas AR abiertas); pagás tarde + caja corta ⇒ confirming;
  colchón corto + negocio sano (sin póliza saturada) ⇒ póliza nueva (monto =
  lo que falta para N días de colchón); servicio de deuda > umbral ⇒
  refinanciación; filial barrida/en rojo con caja ociosa en el grupo ⇒ barrido
  interno. Cada recomendación con score recalculado (mismo mecanismo de deltas
  que actions.py). Exportar al bundle como campo opcional y mostrar en la
  pantalla de empresa.

- **Paso 5 — calendario de salidas próximas.** Impuestos (día 20), SS, nóminas
  y cuotas que vienen: proyectar el mes siguiente desde el historial por
  categoría de cada entidad y mostrar el colchón del peor día. Datos ya
  medidos en `panel.py` (`op_outflow_1m`, medias por categoría). UI: entidad.

- **Paso 6 — accionable 555.** Contar movimientos sin conciliar por entidad
  (el motor ya mide `dash_share`, telemetría de conciliación) y ofrecer
  "conciliá estos N movimientos" como acción de CONFIANZA (no toca el score:
  el índice 555 es calidad de dato, correlación con estrés −0,19; si entrara
  al score mediría el software contable, no la empresa). Mostrar en la pestaña
  Técnico / Recibo.

- **Paso 7 — página compartible para el banco.** Radiografía con fecha,
  versión y consentimiento explícito ("compartir con financiador"). Solo UI
  sobre el bundle. Es el cierre del pitch "quién paga": suscripción del cliente
  + comisión del financiador por un cliente ya calificado.

## 6. Números medidos que NO hay que volver a medir

- Predecir el score extrapolando tendencia es LO PEOR (error medio 19,3 pts a
  3 meses vs 11,7 de "sigue igual" y 10,9 de reversión al nivel propio, en
  grupos). La predicción honesta son dos escenarios (sin cambios / con plan).
- Crítico sigue crítico: 69 % a 3 meses, 65 % a 6 (base 23 %).
- El score es ruidoso: |Δ mensual| mediana 5,0, p90 20,1 (grupos); el ruido
  viene de liquidez, actividad y penalización. Mediana de 3 meses como nivel
  baja el ruido a 1,9 pero casi no mejora la estabilidad de banda (56 %→60 %):
  NO vale el costo de revalidar todo.
- Acciones (antes del rediseño): 204/250 grupos con acciones, uplift mediano
  +8 combinado. Después del rediseño re-medir sobre el bundle real.
- Bandas de grupos a 2026-08: 26,0 % crítico / 28,8 % atención / 33,2 %
  estable / 12,0 % sólido (más 12 % abstención, 12 % stale).
- Puntualidad puntuable: 120/250 grupos en pagos, 96/250 en cobros (sin
  facturas no hay pilar — es argumento de venta para conectar ERP).
- Neteo de espejos: 46,7 % del valor de salidas (placebo 1 %). Spearman
  score-tamaño: −0,012.

## 7. Restricciones (importantes)

1. **Repo público.** Es la entrega. No escribir nada estratégico; los docs
   describen solo qué hace el motor y su evidencia. No tocar `README.md` sin
   que Bruno lo pida.
2. **Nunca commitear** el dataset, `artifacts/` ni `frontend/static/data/`.
3. **No mergear a `main`** ni hacer deploy público (`vercel login` + deploy son
   pasos humanos) sin Bruno.
4. Motor: determinista, sin ML entrenado, sin dependencias nuevas. Tests antes
   de cada commit; commits chicos con mensajes en inglés terminando en
   `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
5. Los textos de acciones/títulos son en español, imperativos, ≤400 chars el
   detalle (tests lo verifican).
6. Todo número afirmado en UI o docs: medido sobre el dataset real. Si no, no
   se afirma.

## 8. Preguntas abiertas para Bruno/Embat

- ¿El test oculto puntúa grupo o empresa? (emitimos ambos CSVs)
- ¿Unidad/métrica del leaderboard? (preguntar a Embat en el aula)
- Deploy en Vercel: pendiente de `vercel login` humano.
- Casos para el vídeo: deterioro COMP_0089/GROUP_0153, mejora COMP_0765,
  bache COMP_0180, cambio de perímetro COMP_0265, filial barrida, financiación
  rotativa COMP_0087.
- Videos/guion: cierre con carpeta fría de 60 grupos → un comando → scores,
  y el "si seguís estas acciones pasás de A a B" como valor principal.

## 9. División de trabajo sugerida si hay otro agente en paralelo

- **Este repo (continuación mía):** pasos 2 → 3 → 4 (§5), motor + bundle, cada
  uno con tests y corrida real.
- **Otro agente (puede arrancar ya sin pisarnos):** paso 7 (página para el
  banco, solo front sobre el bundle), o paso 5 (calendario, motor puro nuevo)
  si toca en un worktree/rama aparte. Coordinar por rama para no chocar en
  `export.py` y `contract.ts` (los pasos 2-4 los toco yo).
