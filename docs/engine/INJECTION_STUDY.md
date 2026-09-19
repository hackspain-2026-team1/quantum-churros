# Estudio de inyección — tutorial y resultados

Este documento explica **qué es el estudio de inyección**, **cómo interpretar cada tipo de deterioro artificial** y **qué resultados obtuvo la última validación** sobre el dataset local. Para regenerar los números:

```bash
make validate
make eval-injection
```

La salida legible está en la terminal; el artefacto completo vive en `artifacts/validation.json` → clave `injection`.

Relacionado: [`EVALUATION.md`](EVALUATION.md) · [`VALIDATION.md`](VALIDATION.md) · [`MODEL_CARD.md`](MODEL_CARD.md) · [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md) (AUC + lead-time en cartera real)

---

## Para qué sirve

El organizador pregunta tres cosas que un score estático no demuestra:

1. **¿Llega a tiempo?** — Cuántos meses antes se ve un cambio real.
2. **¿Distingue un bache de una caída?** — Un mes malo de caja no es lo mismo que un deterioro estructural.
3. **¿Avisa sin que preguntes?** — Cuántas alertas aparecen en grupos sanos (falsas alarmas).

El estudio de inyección responde insertando deterioros **controlados** en grupos que, sin tocar, estaban sanos (score ≥ 60, feed activo, ventana completa de 24 meses). Solo se re-puntúa la entidad inyectada; el resto de la cartera no cambia.

**Complemento:** [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md) publica AUC(h) y meses de antelación sobre la **cartera real** (mismo target operativo de deterioro estructural, sin retocar el score). R8 = capacidad; R9 = lo observado.

```bash
make eval-anticipation   # informe AUC + lead-time (cartera + calibración)
```

---

## Protocolo (paso a paso)

| Paso | Qué ocurre |
|------|------------|
| 1 | Se recorre cada grupo con los 24 meses observados. |
| 2 | Se prueban cuatro fechas de inicio: 11, 10, 9 y 8 meses antes del último mes. |
| 3 | En cada fecha, el grupo debe tener score ≥ 60, al menos 8 meses de historia previa, feed activo durante 9 meses de observación. |
| 4 | Se aplica una de tres formas de deterioro (pico, escalón, rampa). |
| 5 | Se re-calcula score, trayectoria y alertas solo para ese grupo. |
| 6 | Se mide si aparece veredicto de deterioro, alerta o naturaleza estructural **que no existía** en la carrera real. |

Con 156 ventanas válidas por tipo, el estudio ejecuta **156 × 3 = 468** escenarios de estrés por validación completa.

---

## Los tres casos de estudio

### 1 · Pico puntual de caja (`spike`)

**Historia que simula:** un mes con un pago adicional grande (salidas × mediana de los seis meses previos). Los meses siguientes «devuelven» ese importe reduciendo salidas, así la caja cae un mes y recupera.

**Analogía de negocio:** adelanto de nómina, pago trimestral de impuestos, compra puntual de stock.

**Qué debe hacer el motor:** leer **bache**, no caída estructural.

| Métrica | Objetivo | Resultado actual |
|---------|----------|------------------|
| Probabilidad de caída estructural tras pico | ≤ 10 % | **7,7 %** ✓ |
| Probabilidad de veredicto de deterioro | baja (ideal) | 48,7 % |
| Probabilidad de alerta | baja | 30,8 % |
| Caída media del score al final del horizonte | ~0 puntos | **+0,01** (casi nula) |
| Retraso mediano hasta veredicto | — | 0 meses |

**Lectura:** el gate principal se cumple. Casi la mitad de los picos aún provocan un veredicto de deterioro a corto plazo, pero solo el 7,7 % se etiqueta como **estructural**. En las 54 ventanas sin deterioro previo en la carrera real, la probabilidad baja al **3,7 %** — la lectura más honesta de estabilidad.

**Por tamaño:**

| Banda | Ventanas | P(estructural) | P(veredicto) |
|-------|----------|----------------|--------------|
| micro | 23 | 0,0 % | 21,7 % |
| pequeña | 40 | 10,0 % | 55,0 % |
| mediana | 56 | 8,9 % | 57,1 % |
| grande | 37 | 8,1 % | 45,9 % |

---

### 2 · Escalón brusco de cobros (`step`)

**Historia que simula:** a partir de un mes, los cobros operativos caen **un 30 % de golpe** y permanecen ahí. La caja pierde el déficit acumulado.

**Analogía de negocio:** pérdida de un cliente grande, caída de demanda que no se recupera, recorte de tarifas.

**Qué debe hacer el motor:** detectar **deterioro estructural** pronto.

| Métrica | Objetivo | Resultado actual |
|---------|----------|------------------|
| Probabilidad de caída estructural | ≥ 70 % | **81,4 %** ✓ |
| Retraso mediano hasta veredicto | ≤ 3 meses | **1,0 mes** ✓ |
| Retraso mediano hasta alerta | — | 2,0 meses |
| Caída media del score a 3 meses | grande | **30,7 puntos** |
| Caída media al final (9 meses) | grande | **38,7 puntos** |
| Sin detectar en el horizonte | bajo | **18 ventanas (11,5 %)** |

**Distribución de retraso (veredicto):**

```
mes +0  ████████████████████████████  40 (25,6 %)
mes +1  ██████████████████████        31 (19,9 %)
mes +2  ███████████████████████████   38 (24,4 %)
mes +3  ████████                      12 ( 7,7 %)
mes +4  ██████                         9 ( 5,8 %)
sin det ██████████                    18 (11,5 %)
```

**Lectura:** el caso «algo ha roto» funciona bien. El 88,5 % recibe veredicto dentro de 9 meses; la mediana es de **un mes**. Los 18 no detectados son el principal residuo — revisar grupos con pilares incompletos o colchón winsorizado muy alto.

---

### 3 · Rampa lenta de cobros (`ramp`)

**Historia que simula:** los cobros caen un 30 % **de forma gradual en seis meses**. Es el espejo del caso Northbrook del brief (45→65 en 24 meses).

**Analogía de negocio:** erosión lenta de márgenes, pérdida gradual de clientes, subida progresiva de costes.

**Qué debe hacer el motor:** usar la **deriva de largo plazo** (Theil-Sen), no el shock de tres meses.

| Métrica | Objetivo (informal) | Resultado actual |
|---------|---------------------|------------------|
| Probabilidad de caída estructural | alta | **66,7 %** |
| Retraso mediano hasta veredicto | 3–6 meses aceptable | **3,0 meses** |
| Sin detectar en el horizonte | bajo | **35 ventanas (22,4 %)** |
| Caída media al final | grande | **37,0 puntos** |

**Horizonte del veredicto estructural:**

| Tipo de horizonte | Casos |
|-------------------|-------|
| Corto (3 meses) | 52 |
| Largo (deriva) | 13 |
| Ambos | 39 |

**Lectura:** es el **principal punto de mejora**. Una de cada tres rampas no se detecta en 9 meses. Además, muchas detecciones vienen del horizonte corto antes de consolidarse como deriva larga — coherente con el test canónico Velasco (82→68), donde la erosión lenta no siempre alcanza el umbral `long_threshold = 8` puntos en ventana de 12 meses.

---

## Falsas alarmas (grupos sin inyección)

| Métrica | Valor |
|---------|-------|
| Alertas de deterioro / 100 grupo-años (toda la cartera) | 24,4 |
| Ídem en las ventanas «sanas» del estudio | 50,4 |
| Ventanas tranquilas (sin deterioro previo antes de inyectar) | 54 |

**Lectura:** la tasa en ventanas sanas del estudio es el doble que en cartera porque muchos grupos con score ≥ 60 **ya rozaban el umbral** antes de inyectar. Al interpretar picos, usar el subconjunto «tranquilo» (54 ventanas).

---

## Abanico de escenarios (comprobación nueva)

Además del estudio de inyección, la validación incluye `outlook_fan`: para cada mes con abanico optimista/central/pesimista, comprueba si el score real tres meses después cae dentro del rango.

Regenera con `make validate` y consulta `validation.json` → `outlook_fan`.

| Métrica | Valor actual | Lectura |
|---------|--------------|---------|
| Acierto global del abanico | 57,7 % | Por debajo del 70 % aspiracional |
| Con deriva medida (`drift`) | 72,8 % | El abanico funciona cuando hay tendencia |
| Con escenario plano (`flat`) | 53,1 % | El rango de ±6 puntos es estrecho para el ruido real |
| Por debajo del pesimista | 18,0 % | Caídas más bruscas de lo previsto |
| Por encima del optimista | 24,2 % | Recuperaciones no captadas |

**Punto de mejora:** ampliar el abanico cuando `basis = flat` (volatilidad propia insuficiente) o documentar en producto que el escenario plano es conservador en el centro pero estrecho en los extremos.

---

## Puntos de mejora priorizados

### Prioridad alta — rampa lenta (caso Northbrook / Velasco)

1. **22,4 % de rampas no detectadas** en 9 meses → valorar bajar `long_threshold` o ampliar `long_horizon`.
2. Solo **13 de 104** detecciones estructurales vienen solo del horizonte largo → la deriva lenta compite con el veredicto corto.
3. El test `test_canonical_drift.py` documenta el límite Velasco (xfail): 14 puntos en 23 meses no alcanzan 8 en ventana móvil de 12.

### Prioridad media — escalón

1. **18 ventanas (11,5 %)** sin veredicto → auditar si el winsorizado de cobros amortigua el golpe en empresas grandes (retraso mediano 2 meses en banda grande vs 1 en mediana).
2. En ventanas con deterioro previo, P(estructural|escalón) = 75,9 % — mezcla señal base + inyección.

### Prioridad baja — pico (ya cumple gate)

1. Mantener P(estructural|pico) ≤ 10 % — actualmente 7,7 %.
2. Vigilar banda **pequeña** (10,0 % en el límite).
3. El 48,7 % con veredicto de deterioro es esperable si el horizonte corto reacciona; confirmar que la UI muestra naturaleza **bache**.

### Prioridad operativa — monitor

1. **24,4 alertas / 100 grupo-años** en cartera real — documentar y contrastar con alertas suprimidas por cambio de perímetro (casos demo COMP_0265).
2. Filtrar métricas de pico por ventanas tranquilas al presentar al jurado.

---

## Cómo enseñarlo en demo o informe

| Afirmación en voz alta | Evidencia |
|------------------------|-----------|
| «Un mes malo no es una quiebra» | P(estructural\|pico) = 7,7 % |
| «Un escalón se ve en un mes» | Retraso mediano escalón = 1 mes |
| «La erosión lenta tarda más» | Retraso mediano rampa = 3 meses |
| «Medimos anticipación, no magia» | R8: retrasos en `injection` · R9: AUC(h) + lead-time en `natural_anticipation` |
| «No inflamos falsas alarmas en calma» | P(estructural\|pico) en ventanas tranquilas = 3,7 % |
| «Publicamos números en cartera real» | Regenerar AUC-3/AUC-6 con predictor de trayectoria y citar siempre soporte · ver `make eval-anticipation` |

---

## Referencia de código

| Pieza | Archivo |
|-------|---------|
| Receta de inyección | [`engine/src/xray_engine/validation.py`](../engine/src/xray_engine/validation.py) → `inject()` |
| Estudio masivo | misma → `injection_study()` |
| Anticipación natural (R9) | [`engine/src/xray_engine/natural_anticipation.py`](../engine/src/xray_engine/natural_anticipation.py) → `anticipation_study()` |
| Casos canónicos del brief | [`engine/tests/test_canonical_drift.py`](../engine/tests/test_canonical_drift.py) |
| Informe inyección | [`scripts/print_injection_report.py`](../scripts/print_injection_report.py) |
| Informe anticipación | [`scripts/print_anticipation_report.py`](../scripts/print_anticipation_report.py) |
