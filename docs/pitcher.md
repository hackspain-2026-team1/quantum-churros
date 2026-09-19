# Pitch — comprador perfecto (demo 5 minutos)

Guion oral para la demo de HackSpain 2026. El posicionamiento comercial está en
[COMPRADOR.md](./COMPRADOR.md); la verdad técnica del motor, en
[ENGINE.md](./engine/ENGINE.md).

**Una frase.** Embat compra un módulo de decisión financiera que incrusta en su tesorería;
el CFO recibe alertas e informes; un intermediario (equipo interno o partner certificado)
coloca productos financieros sobre el mismo score auditable; la entidad que cierra la
operación paga la comisión.

## Tres roles

| Rol | Quién | Qué obtiene | Qué paga |
|-----|-------|-------------|----------|
| **Comprador** | Embat | Motor embebido (score, forecast, monitor, receipt) | Licencia SaaS por cartera conectada |
| **Operador** | Intermediario interno o partner sobre Embat | Cola priorizada de grupos + dossier auditable para el banco | Take-rate por operación cerrada |
| **Usuario final** | CFO / tesorero del grupo pyme | Alertas, informe mensual, score explicado, palancas operativas | Incluido en la suscripción Embat (sin fricción de marketplace) |

El beneficiario del valor es el **grupo multi-sociedad** (72% del dataset tiene más de una
filial; mediana 2 sociedades, hasta 22). El que **firma el cheque del módulo** es Embat: ya
entrega el rastro (banca + ERP), ya vende tesorería y ya monetiza la distribución de
financiación.

## Modelo de canal

```
Embat (licencia) → intermediario (colocación) → CFO (alertas e informes)
                              ↓
                    entidad financiera (take-rate)
```

- **Capa CFO:** alertas proactivas, score con explicación exacta, acciones con uplift
  recomputado (no estimado). Sin empuje directo de catálogo de crédito.
- **Capa intermediario:** misma señal + cartera contratada (`debt_products`, headroom,
  calendario) → producto financiero concreto (confirming, factoring, línea, refinanciación…).
  Ver tabla en [COMPRADOR.md §4](./COMPRADOR.md#4-recomendación-o-desaconsejo).

## Valor con números nuestros

Solo cifras del motor o de la validación; nada simulado en pantalla.

| Afirmación | Número | Fuente |
|------------|--------|--------|
| Unidad de scoring | Grupo consolidado; sociedad como drill-down | 250 grupos, 1.286 sociedades |
| Multi-sociedad | 72% de grupos con más de una filial | COMPRADOR / dataset |
| Cartera financiera declarada | 2.239 productos de deuda; ~9 por grupo | `debt_products` |
| Explicación auditable | `score = base + Σ contribuciones − penalización − cap` | `aggregate.py`, receipt en demo |
| Misma nota sola o entre 250 | Aislamiento de cohorte (tol 1e-9) | `test_isolation.py`, ENGINE.md |
| Uplift de acciones | Recomputación de `aggregate()`, no estimación | `actions.py`, `test_actions.py` |
| Anticipación (caso mejora 45→65) | Alerta `improvement_structural` ≥ **6 meses** antes del mes 24 | `test_canonical_drift.py` |
| Límite honesto (caso erosión 82→68) | Bajo el umbral congelado `long_threshold = 8`; no prometemos anticipación universal | Q-05, ENGINE.md |
| Abstención | Grupos críticos con confianza baja o feed caído no reciben producto | `alerts.py`, bandeja de alertas |

## Monetización

1. **Licencia a Embat** — acceso al motor + bundle exportado + integración en su producto
   de tesorería. Tramos por número de grupos activos (50 / 250 / enterprise).

2. **Take-rate por producto colocado** — paga la entidad financiera que cierra la
   operación: 0,5–2% del volumen en confirming/factoring pyme (estándar de canal).

3. **Ticket de ejemplo (guion, no proyección contable):**
   - Confirming de 200.000 € al 1% → 2.000 € de comisión por operación.
   - Con 250 grupos en cartera y señales priorizadas por el radar, diez colocaciones
     cualificadas al año hacen creíble el negocio del intermediario sin vender crédito
     directo a la pyme.

El CFO no paga por ser recomendado; eso elimina fricción y alinea incentivos: mala
recomendación → no se cierra → no hay comisión.

## Guion demo (5 minutos)

Grupo de referencia: **GROUP_0153** (crítico, con acciones y cartera visible). Mes:
**2026-08** (último cierre del bundle). Ruta base: `/` → pestañas del dashboard.

| Min | Qué decir | Dónde clicar |
|-----|-----------|--------------|
| **0:00–0:45** | «Dos grupos sacan 45 y 48 en la foto de hoy; uno se hunde y otro mejora. Sin rastro diario no se distingue. El 72% de esta cartera es multi-sociedad: la financiación está fragmentada por filial.» | **Radar** — ordenar por score ascendente; señalar GROUP_0153 |
| **0:45–1:30** | «El score no es opinión: es medición con receipt. Cada punto se descompone y se audita.» | Abrir **GROUP_0153** → pestaña **Diagnóstico** → desglose de pilares |
| **1:30–2:15** | «El monitor no espera a que preguntes. Esta alerta llegó meses antes de que el deterioro fuera obvio — en el caso canónico de mejora del brief, ≥6 meses.» | **Técnico** → sección **Alertas**, o bandeja global `/` con filtro del grupo |
| **2:15–3:00** | «Las acciones no son consejos genéricos: el uplift es la nota recomputada con la palanca aplicada. +X puntos significa exactamente eso en la fórmula.» | Pestaña **Escenarios** o **Acciones** del grupo; marcar una acción y mostrar delta |
| **3:00–3:45** | «Antes de recomendar producto, leemos lo que ya tiene contratado: líneas, headroom, cuotas. No vendemos una línea a quien ya la tiene sin dibujar.» | Ficha del grupo → panel de financiación / perfil de deuda |
| **3:45–4:30** | «El CFO ve alertas e informes. El intermediario, encima del mismo score, coloca confirming o factoring cuando la señal y la cartera cuadran — con el receipt para el banco.» | Volver al mapa señal→producto (ver abajo); no hace falta pantalla nueva |
| **4:30–5:00** | «Embat compra el módulo porque ya tiene los datos y el canal. Nosotros somos el motor; ellos retienen al CFO y monetizan la colocación.» | **Técnico** → **Recibo** (params hash, determinismo) |

### Señal → producto (capa intermediario)

Usar en el minuto 3:45 verbalmente, sin cambiar de pantalla si hace falta:

| Lo que enseña la demo | Producto que coloca el intermediario |
|-----------------------|--------------------------------------|
| «Cobra X días antes» (pilar cobros) | Factoring / anticipo de facturas |
| Retraso con proveedores | Confirming |
| Headroom sin dibujar en línea existente | Activar o ampliar la línea |
| Liquidez baja sin headroom | Nueva línea de circulante |
| Carga de deuda alta | Refinanciación / consolidación |
| Forecast en caída | Acelerar la operación ya en curso |

## Objeciones y respuesta

### «¿Por qué no un modelo entrenado?»

El dataset no trae etiqueta de outcome — no hay default, rating ni flag de «sana». Un ML
entrenado aquí aprendería una fórmula que nosotros mismos escribimos y nos la devolvería
con ruido. El motor **mide** cinco hechos observables por mes, los combina con tablas
congeladas y publica el receipt. Misma carpeta sola o entre 250 grupos → misma nota
(`test_isolation.py`). Preferimos un número que se audita a uno que no se explica.

### «¿No sois un buscador de créditos?»

No. Partimos del rastro y de la cartera ya contratada, no de un formulario. Si falta señal
o confianza, nos abstenemos y decimos qué dato falta (`unlock_hint`). Eso se enseña en la
bandeja de alertas.

### «¿Por qué no vendéis directo a la empresa?»

La pyme compra visibilidad (alertas, informe, score). La colocación de confirming o
factoring la hace un operador con relación bancaria — Embat ya está en esa posición como
canal. Vendemos el motor a Embat; ellos distribuyen a CFO e intermediario.

### «¿El score predice quiebras?»

No. Mide comportamiento financiero observable (liquidez, pagos, cobros, actividad, deuda).
No es rating de agencia; es medición transaccional con gates y confianza.

### «¿Anticipáis siempre el cambio?»

Lo medimos, no lo prometemos. El caso de mejora 45→65 del brief dispara alerta ≥6 meses
antes del mes 24. El caso de erosión 82→68 queda bajo el umbral congelado del horizonte
largo — lo documentamos en ENGINE.md (Q-05) en lugar de venderlo.

### «¿Por qué Embat y no otro?»

Porque genera los datos del reto, ya conecta banca y ERP de estos grupos, y el brief lo
dice: «la empresa que os entrega los datos es el comprador más obvio». El jury es a la vez
el primer cliente potencial.

## Lo que NO decir

- «Marketplace de crédito para pymes» — suena a lead-broker; nosotros nos abstenemos.
- «Predicción de quiebra» — no hay etiqueta; no lo afirmamos.
- «Anticipamos todo» — citar el caso 45→65 y el límite del 82→68.
- «El CFO compra el producto financiero en la app» — compra tesorería; el intermediario coloca.

## Ensayo

- Cronometrar 5 minutos con GROUP_0153 cargado en local (`make up` o bundle estático).
- Tener abierta la bandeja de alertas en otra pestaña por si el jurado pregunta por el monitor.
- Cerrar siempre con: **quién paga** (Embat + banco) y **por qué les sale a cuenta** (dossier
  auditable + colocación cualificada + retención del CFO).
