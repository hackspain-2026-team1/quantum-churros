# Guion de demo — 3 minutos

Demo navegable de **Rumbo** sobre el bundle exportado. Mes fijado: **agosto de 2026** (`m=2026-08`).

Regenerar datos antes de grabar:

```bash
make db-sync   # o make export si solo necesitas el bundle
make validate  # congela hashes para el recibo
```

Verificar identificadores en el bundle actual (ver [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) §Q-16).

---

## Pestañas preparadas (abrir antes de empezar)

1. `/?tab=radar&m=2026-08`
2. `/group/GROUP_0153?m=2026-08`
3. `/?tab=diagnostico&focus=COMP_0180&m=2026-08`
4. `/?tab=diagnostico&focus=COMP_1015&m=2026-08`
5. `/?tab=escenarios&focus=GROUP_0153&m=2026-08`
6. `/?tab=tecnico&focus=GROUP_0153&m=2026-08`

Opcional: `/?tab=diagnostico&focus=GROUP_0083&m=2026-08` (abstención).

---

## 0:00–0:25 · Leo la cartera

**Pantalla:** Radar

**Decir:** «250 grupos, 24 meses de rastro bancario y facturas. No es una foto: cuántos empeoran, cuántos mejoran, cuántos aún no podemos puntuar.»

**Hacer:** señalar contadores → buscar GROUP_0153 → entrar en la ficha.

**Cubre:** cartera, quién está mal, mención de abstención.

---

## 0:25–1:05 · Esta empresa ya torció

**Pantalla:** `/group/GROUP_0153?m=2026-08`

**Decir:** «Score en banda crítica — pero importa la dirección: el pilar de pagos se movió hace meses.»

**Hacer:**
- Cabecera: score, banda, dirección, naturaleza.
- Selector de mes → **septiembre de 2025** («aquí aún no era crítico»).
- Abanico de escenarios (optimista / central / pesimista).
- Desglose de pilares → pagos.
- Entrar en **COMP_0089** (filial con deterioro de pagos).

**Cubre:** trayectoria, por qué cambió, cuándo se vio venir, grupo → empresa.

---

## 1:05–1:35 · Bache ≠ caída

**Pantalla:** Diagnóstico COMP_0180 → COMP_1015

**Decir:** «Un mes malo revierte; una erosión de colchón no. El monitor no alerta igual.»

**Hacer:**
- COMP_0180: naturaleza bache.
- COMP_1015: deterioro estructural.
- 5 s en Técnico → alerta suprimida por cambio de perímetro (COMP_0265 si aparece).

**Cubre:** bache vs caída, monitor, falsas alarmas filtradas.

---

## 1:35–2:25 · Qué hago el lunes

**Pantalla:** Escenarios GROUP_0153

**Decir:** «Embat vende el plan, no el número. Activo palancas — el score proyectado sube sin tocar la historia.»

**Hacer:** activar 2–3 acciones → ver mejora en gráfico → pestaña Acciones.

**Cubre:** producto encima del score, valor para la empresa.

---

## 2:25–3:00 · Por qué confiar

**Pantalla:** Técnico GROUP_0153

**Decir:** «La suma cuadra al décimo. Sesenta grupos fuera del ajuste, mismo resultado. Cinco pilares medibles — esto se lo enseñas al banco.»

**Hacer:**
- Recibo: prueba de holdout, suma exacta, placebo de neteo.
- Cascada del score.
- 10 s GROUP_0083: abstención con indicación de desbloqueo.
- Cierre: comprador = Embat (empresa) + banco (cliente pre-calificado).

**Cubre:** explicabilidad, artesanía, comprador identificado.

---

## Frases de reserva

| Si preguntan… | Respuesta |
|---------------|-----------|
| ¿Es inteligencia artificial? | «No entrenamos un modelo: medimos cinco pilares con reglas congeladas. Wiki → Cómo puntuamos.» |
| ¿Predicís el futuro? | «Mostramos escenarios descriptivos. R8 mide capacidad con inyección; R9 publica AUC y meses de antelación en cartera real — ver wiki Cómo evaluamos.» |
| ¿Y Velasco 82→68? | «Erosión lenta documentada en tests; el umbral de deriva larga es conservador a propósito.» |

---

## Evidencia numérica para el pitch (última validación)

Ejecutar `make eval-injection` y citar (capacidad del motor):

- Pico confundido con caída estructural: **7,7 %** (objetivo ≤ 10 %)
- Escalón detectado en mediana: **1 mes**
- Rampa sin detectar en 9 meses: **22,4 %** (punto de mejora honesto)
- Falsas alarmas en cartera: **24,4 / 100 grupo-años**

Ejecutar `make eval-anticipation` y citar (bonus anticipación medida — cartera real):

- AUC a 3 meses: **0,48** (66 eventos estructurales)
- AUC a 6 meses: **0,44**
- Anticipación mediana (señal → onset): **1 mes** (68 onsets)
- Calibración escalón AUC-6: **0,51** (onset conocido, coherente con R8)

Detalle: [`INJECTION_STUDY.md`](INJECTION_STUDY.md) · [`NATURAL_ANTICIPATION.md`](NATURAL_ANTICIPATION.md)
