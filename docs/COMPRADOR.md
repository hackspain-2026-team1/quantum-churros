# Comprador identificado — el CFO paga, y por qué le sale a cuenta

Respuesta al requisito *«Comprador identificado»* de la tabla de entrega del brief
(`track.md`). Es la fuente de verdad del posicionamiento comercial; el motor que la
sostiene está documentado en [ENGINE.md](./engine/ENGINE.md).

**Cambio de destinatario.** El guion anterior vendía el módulo a un intermediario
(Embat como licenciatario y canal de colocación). Desde hoy el cliente comprador es el
**cliente final**: el CFO del grupo. Ya no vendemos un módulo para que otro cobre la
colocación; vendemos al director financiero la lectura continua de su propio rastro y la
ejecución de su financiación.

**La respuesta en una frase.** Vendemos al **CFO de grupos empresariales pyme con una o
varias sociedades filiales** un servicio continuo de decisión financiera: leemos su rastro
consolidado día a día, lo convertimos en score, forecast y avisos, señalamos las palancas
con su efecto exacto y, cuando la señal y el momento son financiables, abrimos su ronda de
financiación con proveedores compitiendo — sin que su nombre sea visible hasta que él decide.
El CFO paga la suscripción; el proveedor que gana la operación paga la colocación.

## El comprador

| Atributo | Definición | Evidencia en el dataset |
|----------|-----------|-------------------------|
| Qué organización es | Grupo empresarial pyme: una matriz con una o más sociedades filiales, tesorería centralizada | 250 grupos con 1.286 sociedades; **72% multi-sociedad** (mediana 2, hasta 22) |
| Tamaño | Facturación 2–50 M€ (micro-grande del EU SME); el grueso, pequeño y mediano | Bandas de tamaño del motor: 33 micro / 50 small / 79 medium / 63 large con buffer definido |
| Huella | España como núcleo, con filiales en divisa distinta (GBP, USD, MXN, …) | 89% EUR; 11% multimoneda → cambio de divisa y consolidación son dolor real |
| Digitalización | ERP conectado y banca digital (la lectura del rastro exige conectividad) | 167 de 250 grupos con facturas sincronizadas; el resto son banca pura |
| Quién compra y opera | El CFO / director financiero del grupo compra; la tesorería opera el día a día | Los datos que entrega (banca + ERP) son exactamente los de su mesa de tesorería |

**Por qué este segmento y no otro.** La pyme de una sola sociedad puede ir al banco con su
dossier. El grupo multi-sociedad no: su financiación está **fragmentada por filial** (un
leasing aquí, una línea allá, un confirming en otra entidad), nadie ve el riesgo
consolidado, y cada banco le enseña una foto fija de una sola pieza. Es el único comprador
para el que «leer el rastro consolidado» vale dinero — y coincide con la unidad de scoring
del motor: el grupo, con la sociedad como drill-down.

**Por qué ahora.** El score cambia con el rastro diario; las decisiones de financiación se
toman por trimestres. El CFO que contrata hoy con la foto de diciembre está financiando la
empresa de hace seis meses. Nosotros le entregamos la foto de hoy y la trayectoria, con el
momento de negociar marcado en el calendario.

**Por qué el CFO paga y no espera.** Tres dolores que ya sufre y que el producto elimina:

1. **El dossier.** Antes de cada operación recompone a mano los mismos datos que ya
   conecta: score con receipt, cartera y forecast sustituyen ese trabajo para siempre.
2. **El momento.** Financiar con el score ya caído sale más caro. El forecast marca la
   ventana y el monitor avisa solo; un solo aviso a tiempo paga años de suscripción.
3. **El control.** Hoy envía el mismo dossier a ocho bancos y pierde la palanca de
   negociación. La ronda invierte el flujo: los proveedores compiten sobre un teaser
   seudonimizado y su identidad solo se revela si él preselecciona.

## Lo que compra el CFO: lectura → forecast → palancas → ronda

Cuatro capas, cada una apoyada en una salida concreta del motor. Nada de lo que se enseña
es simulado: cada número sale del bundle (`xray-export-v1`).

### 1. Estudio de salud financiera continuo

Score 0–100 del grupo (y de cada sociedad) con banda, pilares, confianza y explicación
exacta (`base + Σ contribuciones − penalización − cap`). Es su foto viva — y su credencial
ante cualquier banco, con el receipt auditable incluido.

### 2. Forecast y monitor que avisa solo

El motor mide trayectoria pasada-only (`direction`, `nature`, deriva Theil-Sen de 12 meses
en `drift_points`/`drift_months`). El forecast (`forecast-v1`, regresión cuantílica por
horizonte validada con origen móvil) proyecta el score y conserva las previsiones pasadas
para contrastarlas con lo ocurrido. El monitor levanta la mano sin que nadie pregunte y
separa un bache (`bump`) de un deterioro estructural.

- Score actual 55 con deriva −1,2 pts/mes sostenida 7 meses → proyección ≈ 51/47, banda
  *Estable → Vigilancia*: el momento de pedir financiación es **ahora**, no en seis meses.
- La regla honesta: el nivel mide dónde estás; el forecast dice cuánto te queda de ventana
  para negociar en buena posición.

### 3. Cartera financiera ya contratada (input imprescindible)

La lectura empieza por el inventario, no por el catálogo. Del grupo leemos:

- **Productos vivos**: `debt_products` — préstamos, líneas de crédito, confirming,
  leasing, avales, hipotecas, renting, factoring (2.239 productos en el dataset; media de
  9 por grupo, 8 tipos distintos).
- **Importes y saldo**: `granted` y `outstanding` por producto → **headroom** real (línea
  concedida menos dibujada) que el motor ya reconstruye por mes.
- **Coste y calendario**: `debt_schedule_config` (cuota, frecuencia, tipo de interés,
  próxima fecha) → servicio de deuda y cargas futuras conocidas.

Esto evita el error clásico del marketplace: recomendar una línea a quien ya tiene una sin
dibujar, o un factoring a quien ya cobra al contado.

### 4. Palancas con efecto exacto y ronda de financiación

| Señal en el rastro | Lectura | Palanca / producto | Por qué le sale a cuenta al CFO |
|--------------------|---------|--------------------|---------------------------------|
| Liquidity baja y headroom sin dibujar | Tiene la línea y no la usa | Usar / ampliar la línea existente | Más barato que un producto nuevo: la concesión ya está, solo falta activarla |
| Liquidity baja, sin headroom | Sin colchón ni margen | Nueva línea de circulante | Evita la cascada de impagos en cadena |
| Debt burden alto (pilar deuda < 40) con préstamos caros | Apalancamiento estructural | Refinanciación / consolidación | Baja el servicio mensual antes de que el score entre en *Crítico* |
| Payments deteriorándose con pagos a proveedores | Se está pagando tarde | Confirming | Financia a proveedores sin consumir CTA propia, protege la cadena |
| Collections con clientes que pagan tarde | Rotación de cobro lenta | Factoring | Convierte la factura en caja el día 1 |
| Inversión en activos productivos (renting/leasing ya presente) | Renueva flota/equipo | Leasing o renting | Conserva la liquidez; cuota fija preservable |
| Score *Sólido* + forecast estable/mejorando | Ventana de fortaleza | Renegociar tipo o ampliar límite | El banco ve score con receipt; el CFO negocia desde su mejor momento, no desde el peor |
| **Cualquier grupo con forecast en caída** | Ventana que se cierra | Acelerar la operación ya en curso | El coste de la financiación sube cuando el score baja: es la tesis entera del producto |

Las palancas no son consejos genéricos: el motor **recomputa el score** con la palanca
aplicada y el forecast prevé desde ahí — el CFO ve el efecto exacto en el horizonte, no una
estimación. Y cuando la palanca es dinero, la señal abre el **expediente de financiación**:
necesidad prevista y explicable (importe y ventana salen del bundle), autorización expresa
del alcance, teaser seudonimizado para proveedores, ofertas comparables, preselección,
aceptación, revocación y auditoría de cada transición. El CFO decide qué comparte, cuándo
revela su identidad y a quién acepta; puede retirar el permiso en cualquier momento.

El servicio **también dice «no»**: grupo con score *Crítico*, confianza baja o abstención
(`short_history`, `stale_feed`) no recibe palanca ni ronda — recibe el `unlock_hint` de qué
dato falta para poder asesorarle. Es lo que distingue a un asesor de un lead-broker.

## Quién paga

**Primario: el CFO, por la suscripción del grupo.** Cuota mensual por grupo conectado
(banca + ERP). Compra tres cosas que hoy paga caras por otros caminos: no rehacer el
dossier ante cada banco, saber el momento de negociar y tener una ronda donde los
proveedores compiten. El ancla no es el precio del software sino el coste de una sola
decisión tomada con la foto equivocada: financiar con el score ya caído encarece el tipo
de toda la operación.

**Secundario: el proveedor financiero que gana la operación.** Paga la colocación sobre la
ronda cualificada (0,5–2% del volumen en confirming/factoring pyme, estándar de canal).
Es lo que mantiene la ronda **gratis para el CFO** y alinea el incentivo: si las ofertas
son malas, no se cierra operación y no hay comisión; el proveedor gana compitiendo, no
comprando el contacto.

**Embat deja de ser el comprador y pasa a ser el canal.** Ya conecta la banca y el ERP de
estos mismos grupos y ya vende la plataforma de tesorería; Rumbo encaja como módulo
white-label o como servicio directo apoyado en su conectividad. La relación comercial con
Embat sigue abierta, pero el comprador que firma es el director financiero — y ese cambio
simplifica la historia: un solo cliente, un solo dolor, una sola decisión de compra.

## Por qué el jurado puede creérselo

1. **El comprador existe en los datos**: 72% de los grupos son multi-sociedad; su dolor
   (fragmentación de financiación, foto fija) está medido en el dataset, no inventado.
2. **El producto ya funciona end-to-end**: score, explicación, forecast por deriva,
   cartera (`debt_products`/headroom), palancas con uplift recomputado y una ronda de
   financiación real (`FIN-024`) con autorización, ofertas y revocación están en la demo;
   el guardrail de abstención es real, no de marketing.
3. **El dinero tiene sentido**: suscripción por grupo (SaaS de decisión financiera) más
   colocación del proveedor ganador es el modelo estándar del canal pyme; con 250 grupos
   de cartera es un negocio unit-económico creíble sin depender de la comisión sola.
4. **El control vence la objeción**: autorización explícita, identidad oculta hasta
   preselección, alcance revocable y auditoría de cada transición — lo que hoy frena al
   CFO de compartir su rastro queda resuelto por diseño.

## Lo que NO es

- **No es un buscador de créditos**: la lectura parte del rastro observado y de la cartera
  contratada, no de un formulario del usuario.
- **No es un rating de agencia**: el score es una medición transaccional con receipt, no
  una opinión crediticia; se enseña con sus gates y su confianza.
- **No es un lead-broker**: si el sistema se abstiene, se abstiene — y eso se enseña.
- **No es una tienda con una sola vitrina**: la ronda siempre abre con varios proveedores
  compitiendo; el CFO compara importe, tipo, plazo, comisión y garantías antes de decidir.
