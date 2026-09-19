# Comprador identificado — quién paga y por qué le sale a cuenta

Respuesta al requisito *«Comprador identificado»* de la tabla de entrega del brief
(`track.md`). Es la fuente de verdad del posicionamiento comercial; el motor que la
sostiene está documentado en [ENGINE.md](./engine/ENGINE.md).

**La respuesta en una frase.** Vendemos intermediación de financiación a **grupos
empresariales pyme con una o varias sociedades filiales**: les hacemos un estudio de salud
financiera con score, lo proyectamos a 3 y 6 meses, y con esa lectura — y con lo que ya
tienen contratado — recomendamos (o desaconsejamos) productos financieros concretos.
Cobra la entidad financiera que cierra la operación, no el grupo.

## El comprador

| Atributo | Definición | Evidencia en el dataset |
|----------|-----------|-------------------------|
| Qué organización es | Grupo empresarial pyme: una matriz con una o más sociedades filiales, tesorería centralizada | 250 grupos con 1.286 sociedades; **72% multi-sociedad** (mediana 2, hasta 22) |
| Tamaño | Facturación 2–50 M€ (micro-grande del EU SME); el grueso, pequeño y mediano | Bandas de tamaño del motor: 33 micro / 50 small / 79 medium / 63 large con buffer definido |
| Huella | España como núcleo, con filiales en divisa distinta (GBP, USD, MXN, …) | 89% EUR; 11% multimoneda → cambio de divisa y consolidación son dolor real |
| Digitalización | ERP conectado y banca digital (la lectura del rastro exige conectividad) | 167 de 250 grupos con facturas sincronizadas; el resto son banca pura |
| Quién firma | CFO / director financiero del grupo; la tesorería opera el día a día | Los datos que entrega (banca + ERP) son exactamente los de su mesa de tesorería |

**Por qué este segmento y no otro.** La pyme de una sola sociedad puede ir al banco con su
dossier. El grupo multi-sociedad no: su financiación está **fragmentada por filial** (un
leasing aquí, una línea allá, un confirming en otra entidad), nadie ve el riesgo
consolidado, y cada banco le enseña una foto fija de una sola pieza. Es el único comprador
para el que «leer el rastro consolidado» vale dinero — y coincide con la unidad de scoring
del motor: el grupo, con la sociedad como drill-down.

**Por qué ahora.** El score cambia con el rastro diario; las decisiones de financiación se
toman por trimestres. El grupo que contrata hoy con la foto de diciembre está financiando
la empresa de hace seis meses. Nosotros vendemos la foto de hoy y la trayectoria.

## El producto que se vende: estudio → forecast → recomendación

Tres capas, cada una apoyada en una salida concreta del motor. Nada de lo que se enseña es
simulado: cada número sale del bundle (`xray-export-v1`).

### 1. Estudio de salud financiera

Score 0–100 del grupo (y de cada sociedad) con banda, pilares, confianza y explicación
exacta (`base + Σ contribuciones − penalización − cap`). Es la credencial: sin un número
que se puede auditar no hay intermediación que defender ante un banco.

### 2. Forecast a 3 y 6 meses

El motor mide trayectoria pasada-only (`direction`, `nature`, deriva Theil-Sen de 12 meses
en `drift_points`/`drift_months`). El forecast es el **producto** que extrapola esa
pendiente: proyección del score a 3 y 6 meses con banda proyectada e intervalo derivado de
la volatilidad propia (`sigma_own`).

- Score actual 55 con deriva −1,2 pts/mes sostenida 7 meses → proyección ≈ 51/47, banda
  *Estable → Vigilancia*: el momento de pedir financiación es **ahora**, no en seis meses.
- La regla honesta del pitch: el nivel mide dónde estás; el forecast dice cuánto te queda
  de ventana para negociar en buena posición.

### 3. Cartera financiera ya contratada (input imprescindible)

La recomendación empieza por el inventario, no por el catálogo. Del grupo leemos:

- **Productos vivos**: `debt_products` — préstamos, líneas de crédito, confirming,
  leasing, avales, hipotecas, renting, factoring (2.239 productos en el dataset; media de
  9 por grupo, 8 tipos distintos).
- **Importes y saldo**: `granted` y `outstanding` por producto → **headroom** real (línea
  concedida menos dibujada) que el motor ya reconstruye por mes.
- **Coste y calendario**: `debt_schedule_config` (cuota, frecuencia, tipo de interés,
  próxima fecha) → servicio de deuda y cargas futuras conocidas.

Esto evita el error clásico del marketplace: recomendar una línea a quien ya tiene una sin
dibujar, o un factoring a quien ya cobra al contado.

### 4. Recomendación (o desaconsejo)

| Señal en el rastro | Lectura | Producto | Por qué le sale a cuenta |
|--------------------|---------|----------|--------------------------|
| Liquidity baja y headroom sin dibujar | Tiene la línea y no la usa | Usar / ampliar la línea existente | Más barato que un producto nuevo: la concesión ya está, solo falta activarla |
| Liquidity baja, sin headroom | Sin colchón ni margen | Nueva línea de circulante | Evita la cascada de impagos en cadena |
| Debt burden alto (pilar deuda < 40) con préstamos caros | Apalancamiento estructural | Refinanciación / consolidación | Baja el servicio mensual antes de que el score entre en *Crítico* |
| Payments deteriorándose con pagos a proveedores | Se está pagando tarde | Confirming | Financia a proveedores sin consumir CTA propia, protege la cadena |
| Collections con clientes que pagan tarde | Rotación de cobro lenta | Factoring | Convierte la factura en caja el día 1 |
| Inversión en activos productivos (renting/leasing ya presente) | Renueva flota/equipo | Leasing o renting | Conserva la liquidez; cuota fija preservable |
| Score *Sólido* + forecast estable/mejorando | Ventana de fortaleza | Renegociar tipo o ampliar límite | El banco ve score con receipt; el grupo aprovecha su mejor momento, no su peor |
| **Cualquier grupo con forecast en caída** | Ventana que se cierra | Acelerar la operación ya en curso | El coste de la financiación sube cuando el score baja: es la tesis entera del producto |

La recomendación **también dice «no»**: grupo con score *Crítico*, confianza baja o
abstención (`short_history`, `stale_feed`) no recibe producto — recibe el `unlock_hint` de
qué dato falta para poder asesorarle. Es lo que distingue a un asesor de un lead-broker.

## Quién paga

**Primario: la entidad financiera que cierra la operación.** Paga comisión de
intermediación por financiación colocada (y por la renovación/ampliación que el monitor
detona). Compra lo que no tiene: un lead **cualificado con score auditable, forecast y
cartera declarada** — el dossier que hoy se reconstruye a mano en cada operación. El grupo
no paga por ser recomendado; eso elimina la fricción de entrada y alinea el incentivo: si
la recomendación es mala, la operación no se cierra y no hay comisión.

**Secundario: el propio grupo (o Embat en white-label).** Suscripción al estudio continuo:
score + forecast + alertas + recomendaciones como cuadro de mando del CFO. Es la línea de
ingresos recurrente y la que convierte el marketplace en producto, no en corredor.

**El comprador más obvio es Embat.** Ya entrega los datos (conecta banca y ERP de estos
mismos grupos), ya les vende la plataforma de tesorería, y monetiza la distribución de
financiación. El estudio + forecast + recomendación es un **módulo que Embat incrusta en
su producto actual**: convierte su panel pasivo en un canal de colocación con comisión,
fideliza al CFO (el score le ahorra el dossier ante cada banco) y usa el activo que nadie
más tiene: el rastro diario consolidado del grupo. Nosotros podemos ser el proveedor del
módulo o el intermediario independiente que se apoya en su conectividad — en ambos casos
Embat es el canal, y el jury del reto es a la vez el primer cliente potencial.

## Por qué el jurado puede creérselo

1. **El comprador existe en los datos**: 72% de los grupos son multi-sociedad; su dolor
   (fragmentación de financiación, foto fija) está medido en el dataset, no inventado.
2. **El producto ya funciona end-to-end**: score, explicación, forecast por deriva,
   cartera (`debt_products`/headroom) y recomendaciones con uplift simulado están en la
   demo; el guardrail de abstención es real, no de marketing.
3. **El dinero tiene sentido**: comisión del prestamista por colocación cualificada es el
   modelo estándar del canal pyme (factoring/confirming pagan entre 0,5–2% del volumen);
   con 250 grupos de cartera es un negocio unit-económico creíble.

## Lo que NO es

- **No es un buscador de créditos**: la recomendación parte del rastro observado y de la
  cartera contratada, no de un formulario del usuario.
- **No es un rating de agencia**: el score es una medición transaccional con receipt, no
  una opinión crediticia; se enseña con sus gates y su confianza.
- **No es un lead-broker**: si el sistema se abstiene, se abstiene — y eso se enseña.
