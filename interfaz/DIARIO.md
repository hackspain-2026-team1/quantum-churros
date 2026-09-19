# Diario de Rumbo (antes X Ray)

Registro de lo que se hace en `interfaz/`, en qué orden y por qué. Lo lleva el equipo de interfaz (José Luis). Todo lo que se cuenta aquí se puede comprobar en el código.

---

## 19 de septiembre de 2026, la portada como monitor (propuesta 08)

La portada deja de ser una puerta y pasa a ser el monitor de la cartera. Sigue la propuesta `hackspain/08-propuesta-portada-monitor.md`, con las decisiones tomadas: organizaciones por defecto (con conmutador a empresas), la regla de gravedad propuesta, siete formas y Jev en un Worker propio.

### Lo que se ve, de arriba abajo

- **La rosa de los vientos, primero, grande y centrada.** Sus puntas diagonales son las cuatro zonas del plano; el largo es cuántas hay en cada una, y cada zona es un filtro. La aguja azul apunta hacia donde va la cartera: a la derecha si la media supera el corte de 60, arriba si el ritmo medio sube.
- **El estado del mes**, con cada cifra como filtro: las bandas con quién entra y quién sale de crítico (7 entran y 8 salen en agosto: el total apenas cambia y esconde siete casos nuevos), los cambios de banda, lo que cae tres puntos o más, lo que va hacia crítico y los avisos.
- **«Abrir el plano» y «Abrir el tapiz»**, a pantalla completa, como antes, con los filtros que el mapa también entiende.
- **Dos campos.** «rumbo de ¿qué organización?» busca y abre una organización. Debajo, «o dile qué quieres ver…», con ejemplos que se pueden tocar.
- **Piden atención y avisos del mes**, en dos columnas. El orden de gravedad: entran en crítico, deterioro confirmado, siguen en crítico y bajan, van hacia crítico (horizonte con un 50 % o más), golpe por confirmar. Debajo, las que suben. Los avisos llevan el triaje de siempre, y los que quedan sin revisar suben a una campana en la cabecera.
- **La cartera**: siete formas (ranking, bandas, plano, tapiz, flujo, avisos y horizonte), cada una **en arena o en tabla**, por organizaciones o por empresas, con su orden y sus filtros en la URL. Las vistas se pueden guardar.

### La arena como vista mutable (`src/arena/vistas.ts`)

Cada entidad es dueña de sus granos (120 por organización, 20 por empresa), siempre en el mismo orden. La placa de la vista va la primera de la página, así que al cambiar de forma, de orden o de filtro los granos de cada una viajan de un sitio a otro: el recorrido mide que al pasar de bandas a plano se mueven casi 20.000. `disponer` es pura: calcula dónde va cada entidad (para rótulos, clics y la etiqueta al pasar) y devuelve la función que dibuja.

Tres formas son nuevas:
- **bandas**, cuatro montones con las recién llegadas arriba, en rojo si bajan y en verde si suben;
- **flujo**, de la banda del mes pasado a la de este, con hilos rojos y verdes;
- **horizonte**, de hoy a la mediana a seis meses, con las que van hacia crítico en rojo y rotuladas.

### «Dile qué quieres ver» (`src/datos/interpretar.ts` y `worker/`)

- **Dos capas.** Primero, palabras clave, al instante y sin red. Después, Jev a través del Worker `rumbo-vista` (`https://rumbo-vista.jlsf2005.workers.dev`, cuenta de José Luis). La clave de TypeSafe es un secreto del Worker y las preguntas viven en él, así que el Worker no sirve para otra cosa. Limita a 30 peticiones por minuto y dirección.
- **Qué pregunta.** Trece preguntas en una sola petición: forma, arena o tabla, unidad, orden, banda, movimiento, zona, sector, país, tamaño, producto y si ya lo tienen, y si la frase tiene que ver con la cartera. A TypeSafe solo viaja la frase y el vocabulario (sectores y países presentes); ningún dato financiero.
- **Cómo decide la interfaz.** Los filtros piden más probabilidad que la forma o el orden. Si duda entre dos opciones, pregunta en vez de aplicar. Además quita las piezas redundantes que solo estrechan la vista: una zona que repite la banda, o un «cae» que repite el orden. El «tiene» de las palabras manda sobre el «encaja» de Jev.
- **Cuánto acierta.** `pruebas/jev/evaluar.mjs` escribe 40 frases en la portada y compara la vista que queda con la esperada. Última ejecución: 63 de 63 piezas; 40 de 40 vistas con todas sus piezas y sin filtros de más; 33 de 40 exactas (las otras 7 añaden una forma o un orden razonables, como abrir el flujo para «las que suben de banda»). 1,2 s de media. Resultados en `pruebas/jev/resultados.json`.
- **Coste.** Unos 2.400 tokens de entrada por petición: una diezmilésima de dólar.

### Los horizontes cambian de modelo

A las 18:07 otra sesión regeneró `rumbo/horizons` con `forecast-v1`: regresión cuantílica con calibración conformal, validada en 12 cortes, y guardó la simulación anterior en `horizons-v1-simulacion`. Los escenarios «deriva» y «peor trimestre» ahora solo traen la mediana, sin granos ni probabilidades de banda. Rumbo lee los dos formatos:
- la metodología y la sección técnica explican el modelo que venga;
- los percentiles que faltan salen de los granos o de la mediana;
- los escenarios sin granos se dibujan como su hilo.

### Pruebas

El recorrido pasa a 50 comprobaciones:
- el estado del mes igual al de `portfolio.json`;
- el ranking de gravedad;
- la campana;
- las siete formas en arena y en tabla;
- que los granos viajan al cambiar de forma;
- el cambio a empresas;
- el campo de lenguaje natural a la vista y funcionando (con una respuesta de Jev grabada);
- los botones del plano y del tapiz.

Última ejecución: **50 de 50**.

---

## 19 de septiembre de 2026, la marca, la cabecera, los escenarios y el informe

### La marca (`src/vistas/marca.ts`)

El monograma sale de los bocetos de José Luis y sigue su lectura (la reducción de *El toro* de Picasso). De «rumbo» quedan la r, la u y la m, porque son las letras de la familia del arco. La b y la o se quedan fuera: son formas cerradas.

- **Un solo recorrido.** El hombro de la r se convierte en un arco grande, unas 2,4 veces la altura de los pequeños. Su cima es asimétrica, del lado de la subida.
- **Trazos que hacen dos trabajos.** La bajada del arco es a la vez el primer lado de la u. La subida desde el valle es el segundo lado de la u y la primera asta de la m.
- **Coda.** Los dos arcos de la m son pequeños y van sin espuela.
- **Principio y final.** Arranca con un gancho corto bajo la base, que hace de ancla. Termina con una salida corta hacia la derecha, que marca el avance.
- **Construcción.** Primero el esqueleto, engrosado después con `stroke`. El contraste es cero, los remates redondos y la inclinación de 6°. El grosor ronda 1/14 de la altura, con corrección óptica en pequeño.
- **Tamaños diminutos.** Por debajo de 20 px pierde el segundo arco pequeño: es el favicon.

El logotipo «rumbo» se construye con el mismo módulo de arco. La o es la única forma cerrada; la panza de la b queda abierta.

Dónde vive la marca:
- En la cabecera, el monograma es de arena: un lienzo 2D propio con granos que caen en el orden de la pluma y se apartan al pasar el puntero.
- En la portada, el objeto sigue siendo la rosa de los vientos, hecha de arena. La frase empieza con el logotipo: «rumbo de ¿qué organización?».

### La cabecera

Antes había dos barras, marca y miga, y la portada repetía «Rumbo» tres veces. Ahora hay una sola línea:
- la marca;
- la miga (Grupo › Empresa · mes);
- las acciones de la página (Informe en PDF, Mapa de la cartera);
- Metodología y la ayuda.

Debajo de la cabecera va una raya de granos, el horizonte de arena. En la portada la marca no aparece en la cabecera: allí ya están la rosa y el logotipo en la frase. En el mapa (plano y tapiz) se quedan las lentes y el selector de vista.

### El reloj de arena

Queda en dos líneas: el contorno de un solo trazo y el nivel de la arena. Al reproducir, un grano cae por el cuello y se posa. La primera prueba llevaba un montón curvo con un grano encima y parecía una cara triste, así que se descartó.

### Los escenarios, a la vez

En Scoring se ven los tres futuros juntos, cada uno con su color de arena:
- «todo igual», en gris;
- «deriva», en morado;
- «peor trimestre», en ocre, un tono nuevo de la paleta.

El elegido se ve definido, con sus granos apretados, más opacos y con su mediana. Los otros se ven sueltos y finos, rotulados al final de su mediana.

Cada simulación tiene siempre cuatro granos y el orden no cambia. Por eso, al elegir otro escenario, la arena se reorganiza delante de los ojos: unos granos se aprietan y otros se sueltan. El escenario se elige con la leyenda, con el rótulo o tocando su arena en el gráfico. Con acciones marcadas (sección III) se sigue viendo solo el básico con las acciones.

### El informe en PDF (`src/vistas/imprimir.ts`)

El informe es el mismo HTML de las cuatro secciones, seguido y sin controles, y respeta el escenario elegido y las acciones marcadas. Se monta en una capa aparte con el ancho útil de un A4 (182 mm) y se imprime con el diálogo del navegador («Guardar como PDF»). Se abre con el botón «Informe en PDF» o con ⌘P.

- **La arena.** Es WebGL, así que no se imprime. Cada placa se vuelve a componer con su escena y se pinta grano a grano en una imagen a 3×: el papel lleva la misma arena, quieta.
- **Paginación.** Cada sección empieza en una hoja y no se parten ni filas ni gráficos.
- **Anchos.** Las reglas de ancho del CSS son solo de pantalla (`screen and`), para que el papel no tome el diseño del móvil.
- **Animaciones.** Dentro del informe están apagadas: si no, los bloques se quedan en su primer fotograma, invisibles.

### Un fallo de tipografía

El cuerpo llevaba `font-variant-numeric: tabular-nums`, y en Schibsted Grotesk «tnum» también ensancha la coma, el punto y el punto y coma. Por eso en la prosa parecía haber un espacio delante («motor ; donde», «+0 , 3»). Ahora las cifras tabulares van solo donde se alinean en columna.

### Pruebas

El recorrido pasa a 41 comprobaciones. Las nuevas son cinco:
- la portada con la rosa y sin la marca repetida;
- una sola cabecera;
- los escenarios alternativos a la vez;
- elegir uno mueve la arena (más de 30.000 granos);
- el informe con sus cuatro secciones y la arena cocida.

`pruebas/informe.mjs <url> <pdf>` genera el PDF de una ficha como lo haría el navegador. `pruebas/foto.mjs` hace capturas sueltas para diseñar piezas.

Última ejecución: **41 de 41**.

---

## 19 de septiembre de 2026, Rumbo

Implementa las propuestas `hackspain/06-propuesta-rumbo.md` y `07-propuesta-rumbo-pr1.md`. La aplicación se llama **Rumbo**. Sigue sin Svelte ni shadcn por decisión de José Luis (el `AGENTS.md` del repositorio los pide para `frontend/`; esta carpeta es aparte).

### Los datos: todo sale de ficheros, nada del código

| Raíz servida | Qué es | Quién lo genera |
|---|---|---|
| `public/datos` → `~/Developer/hackspain-data/bundle-main` | Bundle del motor de `main` (PR #1 fusionado): 250 grupos, 1.286 empresas, acciones del motor y recibo con 13 comprobaciones | `xray-score validate` y `predict` en el worktree del motor |
| `public/rumbo/params.json` | Copia de `params/reference_v1.json`, solo si su huella coincide con la del bundle | `scripts/datos/parametros.py` |
| `public/rumbo/products/` | Qué tiene contratado cada empresa y cada grupo, con su procedencia | `scripts/datos/productos.py` |
| `public/rumbo/horizons/` | El futuro de cada entidad, simulado y puntuado con el motor | `scripts/datos/horizontes.py` |
| `public/rumbo/indice-empresas.json` | Tamaño, grupo y score de cada empresa en el corte, para compararla con las de su tamaño | `scripts/datos/indice.py` |

`bun run datos` (o `scripts/datos/preparar.sh`) lo prepara todo y crea los enlaces. Si el servidor estaba arrancado, hay que reiniciarlo: Vite no ve los enlaces nuevos.

**Productos contratados** (`productos.py`, corte de agosto de 2026). Lo declarado sale de `debt_products` (líneas, factoring, confirming y demás deudas), `debt_schedule_config` (tipos y cuotas) y `banking_products` (ahorro e inversión). Lo deducido sale de los movimientos de los 12 meses anteriores, con reglas medidas sobre el dataset:
- **factoring**, solo señales explícitas: financiación, operaciones, intereses y comisiones. Los abonos de «Santander Factoring y Confirming» no cuentan, porque esa entidad también paga confirming de clientes; quedan como señal informativa;
- **confirming**, solo las comisiones que paga la propia empresa. Los anticipos que cobra son el confirming de sus clientes;
- **seguro de crédito**, solo los recibos pagados a aseguradoras;
- **cuenta remunerada**, intereses acreedores en al menos dos meses. Los intereses de descubierto no cuentan;
- **depósitos**, imposiciones a plazo y letras;
- **plan de pensiones**, no aparece en los datos.

Resultado: línea 203 empresas, factoring 39 (19 declaradas y 20 deducidas), confirming 72, seguro de crédito 13, cuenta remunerada 25, depósitos 107, pensiones 0. Diecinueve líneas con un dispuesto de más de vez y media el límite se marcan como incoherentes en el origen, sin porcentaje de uso.

**Horizontes** (`horizontes.py`, escrito por un agente con esta especificación y revisado). Se simulan 12 meses, 400 veces, de las métricas de entrada de los pilares, en bloques de 3 meses de la propia historia y con una vuelta suave a su nivel. Cada mes simulado se puntúa con `compute_pillars` y `aggregate` del motor. Hay tres escenarios (si todo sigue igual, si sigue la deriva y si se repite su peor trimestre), las acciones del motor como rampas (liquidez 1 mes, pagos y cobros 3, actividad 6 y deuda 12, sacados de las ventanas de los parámetros) y el score de cada combinación de acciones.

Comprobaciones:
- el corte se reproduce en 1.349 de 1.349 entidades;
- cada acción llega a la cifra del motor en 2.464 de 2.464;
- cada combinación, en 845 de 845.

Prueba hacia atrás desde febrero de 2026:
- la franja del 80 % acierta el 78 % a tres meses y el 82 % a seis, tras ensancharla un 10 %;
- la mediana se equivoca 15,2 puntos frente a 16,1 de «no cambia nada»;
- el escenario de deriva predice peor, y la interfaz lo presenta como «qué pasaría si».

### El recorrido

**Entrada** («Rumbo de ¿qué organización?»):
- una rosa de los vientos de arena;
- un buscador (número, sector o país);
- «las que piden atención hoy», a partir de los cambios de banda, los deterioros confirmados del mes y los horizontes que cruzan a una banda peor con probabilidad de 0,5 o más;
- el mapa de la cartera.

**Organización y empresa**:
- **Cabecera y navegación.** Número en arena, línea de estado (sin píldoras) y cuatro marcas: **I Scoring**, **II Productos**, **III Acciones** y **IV Técnico**. Las teclas 1 a 4 cambian de sección y Esc sube un nivel. La miga de pan (Rumbo › Grupo › Empresa) sustituye a la frase.
- **I · Scoring.**
  - Una sola gráfica que cruza el presente: lo observado es arena asentada y lo previsto, arena suelta, donde cada grano es una simulación.
  - Tiene boyas a 3, 6 y 12 meses, tres escenarios y un selector de métrica con las series del motor.
  - Debajo, cinco cifras: score, confianza desglosada, persistencia, deriva de 12 meses del motor y previsto a seis meses.
  - Después, la partitura de pilares con la nota del motor y las compuertas como llamadas al margen, y el hilo de «de dónde sale».
- **II · Productos.**
  - El inventario de los siete grabados en sus cuatro estados.
  - Lo que tiene, con el sello de contratado o deducido, sus contratos y las otras deudas.
  - Lo que le encajaría, ordenado por el efecto del motor.
- **III · Acciones.**
  - Los avisos del motor, más el previsto por los horizontes, con grano hueco.
  - Las acciones del motor redactadas en tercera persona desde sus campos, con los productos que las resuelven o la palanca propia.
  - Una fila de «no hacer nada».
  - El horizonte en grande con las acciones que se marquen y la cifra del motor de cada combinación.
  - Estado propuesta, en curso o hecha, guardado por entidad, mes y acción.
- **IV · Técnico.**
  - La cascada que cuadra al décimo.
  - Las curvas reales de `params.json` con la entidad encima.
  - El veredicto por dentro (Δ3, σ y el umbral de los parámetros), la confianza y la abstención.
  - El hilo entero, la evidencia filtrable por mes, pilar, fichero y texto, y todos los avisos, incluidos los silenciados.
  - Las acciones con el texto original del motor y el importe leído de él, marcado así.
  - Los supuestos y la calibración de los horizontes, y la huella de cada fichero.

**Comparación con las de su tamaño**: la empresa (desde el índice de empresas) y la organización (desde `portfolio.json`) se sitúan frente a la mediana de las de su tramo de tamaño.

**De cualquier número a su evidencia**: cada nudo del hilo y cada pilar de la partitura abren la sección técnica con la evidencia ya filtrada en ese dato (pilar, fichero o medida).

**Clasificación de avisos**, traída de la bandeja de Bruno: cada aviso se marca como visto, se descarta o se restaura. Hay bandejas de todos, sin revisar, vistos y descartados. Se guarda en el navegador y se comparte entre pestañas.

**La organización, además**:
- la flota (sus empresas en arena, por score y cambio en tres meses), con la tabla de empresas;
- las estelas finas de sus empresas en la gráfica;
- la matriz de empresas por productos;
- lo que proponen sus empresas;
- la comparación con las organizaciones de su tamaño;
- el aviso de que su score no es la media de sus empresas.

**La cartera** (plano y tapiz) se queda como mapa, con dos lentes:
- **horizonte**: cada organización donde estará en seis meses si nada cambia, con la estela desde hoy;
- **productos**: en azul, a las que les encaja alguno.

**Metodología**: la huella, las 13 comprobaciones del recibo (una no superada, la de inyección, y se enseña), las señales, dónde se abstiene, la calibración de los horizontes y las reglas de productos.

### Iconos, dibujados a mano

`src/vistas/iconos.ts` contiene siete grabados:
- contorno de plumilla, con trazo fino y el mismo trazo más grueso y desplazado hacia la sombra;
- sombra en punteado de arena;
- sin baldosa, y la familia en un filete debajo;
- tamaños ópticos (26 px o menos pierde trama y detalle);
- cuatro estados: tiene, encaja (los granos llegan), bloqueado y no consta.

`bun scripts/exportar-iconos.ts` deja los SVG y la hoja de prueba en `public/productos/`.

### Guardias

- **Datos sintéticos.** Solo existen con `?datos=sinteticos` en desarrollo. El generador ni siquiera entra en el paquete de producción, y un manifiesto sintético no arranca en producción. Si no hay bundle, la aplicación lo dice y no enseña nada.
- **Sin umbrales en la interfaz.** Bandas, nombres de pilares y bandas, glosario y curvas salen del manifiesto y de los parámetros. El encaje de productos usa las acciones del motor, lo contratado y el umbral de banda sólida del manifiesto; se retiraron los umbrales provisionales anteriores.
- **Sin peticiones a terceros.**

### Pruebas

`bun run prueba` hace 36 comprobaciones sobre los datos reales:
- ningún identificador escrito en el código;
- la entrada, y el número del grupo y de la empresa, iguales a los de sus ficheros;
- la flota y la matriz con todas las empresas;
- el inventario igual a `products/`;
- las recomendaciones iguales a las acciones del motor, y marcar una la lleva al horizonte;
- la cascada cuadra;
- las curvas, el previsto a seis meses, la metodología con todas las comprobaciones del recibo, el mapa, el tamiz y ⌘Z, las dos lentes;
- la comparación con las de su tamaño, el paso de un pilar a su evidencia filtrada y el descarte de un aviso;
- que no haya errores ni peticiones a terceros, y el móvil.

Última ejecución: **36 de 36**.

### Lo que le falta al motor (para hablar con Bruno)

- el importe de cada acción como campo;
- las combinaciones y los meses que tarda cada acción en notarse (hoy los calcula `horizontes.py` con el motor);
- las curvas y reglas de las acciones en los parámetros;
- que la acción de cobertura tenga en cuenta a las filiales que financia el grupo;
- volver a exportar cuando entre `feat/credible-actions`.

---

## 19 de septiembre de 2026, datos reales y productos (QUA-7)

Rama `jlsf2005/qua-7-crear-un-logoicono-para-cada-uno-de-los-7-productos`.

### El motor ya exporta

La rama `feat/engine-v2-run` de Bruno (d030d7a) completa lo que en la PR #1 faltaba: panel mensual, referencia ajustada y exportación. Se ha ejecutado en `~/Developer/hackspain-motor` sobre el dataset del reto y ha dejado el bundle en `~/Developer/hackspain-data/bundle`: 250 grupos, 24 meses (de septiembre de 2024 a agosto de 2026), 4.623 avisos, unos 3.000 ficheros. Bundle `88ef6f57…`, motor `engine-v2`. El contrato `xray-export-v1` no cambia.

`interfaz/public/datos` es un enlace simbólico a ese bundle (está en `.gitignore`: los datos no se suben). Para reproducirlo en otra máquina basta exportar con el motor y enlazar la carpeta.

### El adaptador (`src/datos/motor.ts`)

- Al arrancar se pregunta si hay bundle (`manifest.json` con `schema: xray-export-v1`). Si lo hay, se leen `portfolio.json`, `alerts.json` y los 250 `groups/<id>.json` con 12 peticiones a la vez; mientras tanto se ve un reloj de arena con la barra de progreso. Si no lo hay, o si la URL lleva `?datos=sinteticos`, se usa la cartera sintética de siempre.
- La barra dice de dónde salen los datos: «datos reales · motor engine-v2» (con el bundle, la versión y la fecha en el título) o «datos sintéticos».
- Los meses de cada grupo se alinean con la ventana de 24; las empresas, también. Del motor se aprovechan la **nota de cada pilar** (explica el número con palabras: «Colchón de 16 días de salidas…»), las compuertas, el veredicto y el **perfil** del grupo (tesorería, financiación, concentración de clientes, etc.).
- País y tamaño llegan como etiquetas («España (ES) · multinacional», «Mediana (10-50 M€)») y se reducen al código y a la palabra que usan los filtros. Se han añadido los países que faltaban y el tamaño «micro».
- **De dónde sale** cada pilar ya no es sintético: al abrir un expediente se pide `evidence/<id>.json` y se enseñan, para el mes de corte, los ficheros de origen, las filas y las primeras medidas con su valor.
- Se reconocen los avisos de **deriva lenta** (`deterioration_drift`, `improvement_drift`) de la rama `feat/slow-drift-detection` de Rubén, aunque el bundle actual todavía no los trae.

### Ajustes que han pedido los datos reales

- El ritmo real se mueve mucho más que el sintético (el 10 % de los grupos, a más de 2,8 puntos al mes). Los ejes del plano se ajustan a la cartera al cargarla: el suelo del score, al percentil 2; el ritmo, al percentil 95. Las marcas del eje salen del dominio.
- Muchos grupos empiezan tarde (el 42, en enero de 2026) y tienen pilares sin dato: la partitura dice «sin dato» y ya no se monta, y si falta alto la trayectoria cede espacio a los pilares.

### Productos (Linear QUA-7)

La base de datos todavía no tiene productos. La interfaz los trae ya para diseñar y probar el front; cuando el backend los sirva, se cambia una función (`encajes`) y nada más.

- **Catálogo** (`src/datos/productos.ts`): los 7 productos en tres familias. Protección (azules): línea de crédito, factoring y confirming. Cobertura (violeta): seguro de crédito. Inversión (verdes y dorados, niveles 1 a 3): cuenta remunerada, depósitos y letras, plan de pensiones.
- **Iconos** (`src/vistas/iconos.ts`): dibujados a mano en SVG sobre una retícula de 24. Escudo con €, factura que se convierte en moneda, engranaje con calendario, paraguas sobre una cartera de facturas, gotas sobre el saldo, cápsula sellada con reloj y árbol de copas apiladas. La familia se lee en la ficha: cuadrada en protección e inversión, **redonda** en cobertura, y en inversión tres puntos de nivel debajo. `bun scripts/exportar-iconos.ts` los exporta a `public/productos/` (con ficha y solo trazo) junto con una hoja de muestras, `productos/muestras.html`.
- **Cuándo encaja cada uno**: reglas provisionales sobre lo que da el motor, sin inventar importes. Línea de crédito si la tesorería es justa o ajustada; factoring si cobra tarde (Cobros por debajo de 55); confirming si paga tarde; seguro de crédito si depende de un cliente; cuenta remunerada, depósitos y plan de pensiones según la holgura de caja, la banda y la confianza. Cada encaje lleva su motivo (la nota del pilar o la evidencia del perfil) y, si hoy no se debe ofrecer, el porqué (por ejemplo, score en banda crítica).
- **En la frase**: el panel «Quién» tiene la sección «Por producto que les encaja» con los siete iconos y cuántos grupos quedarían. También se escribe: «factoring», «seguro», «pensiones»… La frase queda «Los 10 grupos a los que les encaja el factoring». Va en la URL (`pr=`).
- **En el expediente**: el lateral «Qué se le puede ofrecer» enseña una tarjeta por producto (icono, familia, fuerza del encaje, motivo, bloqueo) y un enlace «A quién más le encaja» que vuelve a la cartera con ese filtro. En el móvil el botón del lateral se llama «Avisos y productos».

### Pruebas

`bun run prueba` pasa ahora sobre los datos reales y suma cinco comprobaciones: que se cargan los datos que tocan, los siete productos del panel, las tarjetas del expediente, la evidencia de los cinco pilares y «a quién más le encaja»; en el móvil, el buscador prueba ahora el filtro de producto. Última ejecución: **24 de 24**. `bun run build` también pasa.

---

## 19 de septiembre de 2026, segunda versión

Implementa la propuesta `hackspain/05-propuesta-completa.md`. Sustituye entera a la primera versión: se conservan el motor de arena, las formas y el generador sintético; se reescriben el estado, las escenas y toda la capa de interfaz.

### Punto de partida

- El motor v2 de Bruno (`feat/engine-v2`) tiene congelado el contrato `contracts/xray-export-v1.schema.json`, pero **todavía no exporta** (`build_panel`, `export_bundle` y `round_preserving_sum` lanzan `NotImplementedError`; comprobado con `make export` sobre el dataset real en `~/Developer/hackspain-motor`).
- Decisión de José Luis: interfaz desde cero, **sin Svelte ni shadcn**, en TypeScript sin framework con Vite. Esta carpeta no toca `frontend/`, ni el motor, ni el backend.

### La idea

Una pregunta escrita, un dato hecho de arena y un tiempo que se toca. **La frase, la arena y la regla son la misma consulta dicha de tres maneras**: la frase la dice con palabras, la arena la enseña y la regla la sitúa en el tiempo. Cambias una y las otras dos te siguen.

### La frase (`src/vistas/frase.ts`)

Gramática fija de cuatro huecos, que se lee en voz alta: **quién**, **cuándo**, **a qué escala** (con «al cierre» o «de media») y **frente a qué**. En el tapiz se añade un quinto: el orden.

- Cada hueco es una **ficha** con una forma que dice qué es: un montoncito de granos que crece con el número de grupos, corchetes cuyo ancho es la duración, muescas de regla (12, 4, 3, 2 o 1), dos puntos unidos.
- **Previsualizar antes de decidir**: pasar el ratón (o las flechas) por una opción la aplica en vivo a la arena y a la regla; salir la deshace.
- Cada opción enseña su consecuencia (el número de grupos que quedarían, si el periodo está en curso, etc.).
- **Escribir en cualquier parte** entra en la frase con un intérprete de vocabulario cerrado (`interpretar` en `src/datos/consulta.ts`): números de grupo, meses, trimestres («T2», «segundo trimestre»), años, escalas, «media» o «cierre», «año pasado», zonas, movimientos, sectores, países y tamaños. Nunca da error: dice que no reconoce y sugiere. Un número de grupo abre directamente su expediente.
- En el panel «Quién» hay además un **buscador** con el mismo intérprete, que es como se escribe en pantallas táctiles.
- En el expediente, la frase dice «El Grupo 42» y su ficha lleva a otros grupos o de vuelta a la cartera.
- **Deshacer**: cada cambio confirmado es una entrada del historial. ⌘Z, el botón «deshacer» (visible cinco segundos) y el «atrás» del navegador hacen lo mismo, y ⌘Z nunca sale de la aplicación.

### El tamiz

Tres formas de quedarse con unos grupos: **clic en una zona** del plano (se dibuja su contorno y una pista dice cuántos son), **lazo** arrastrando sobre el plano, o **clic en un montón de avisos** de la regla (arriba, mejoras; abajo, deterioros). Lo que no pasa cae al **sedimento**, que se nombra («185 fuera del tamiz · devolverlos»). La ficha de «Quién» enseña el filtro con un aspa para quitar el último; Esc hace lo mismo.

### La regla del tiempo (`src/vistas/regla.ts` y la arena)

- **Calendario, monitor y mando a la vez**. Los movimientos confirmados se posan como montones de arena en su periodo: mejoras encima (verde), deterioros debajo (rojo). Al pasar por un periodo aparecen sus avisos en frases cortas.
- **Intervalo** con dos asas, «desde» y «hasta», que se arrastran; la ventana entera también se arrastra. Mayúsculas y clic extiende el intervalo.
- **Escalas**: mes, trimestre, cuatrimestre, semestre y año, de calendario (`src/datos/periodos.ts`). Se cambian en la frase, con `[` y `]`, o con la rueda o el pellizco sobre la regla. El primer periodo puede ser «parcial» y el último, «en curso».
- **Qué es un periodo**: por defecto, el score **al cierre** (el del último mes); como alternativa, **de media**. En el expediente, el grosor de la trayectoria es la agitación dentro de cada periodo.
- **Reproducir** es un reloj de arena que se vacía mientras suena, con dos modos: la ventana avanza, o acumula.
- **Sin futuro**: a la derecha de «hasta» no hay arena.
- **Tu última visita** queda marcada (se guarda al salir) y un clic fija el intervalo desde ella hasta hoy.

### Las vistas

| Vista | Qué enseña |
|---|---|
| **Plano** | Cada grupo en horizontal según su score del periodo y en vertical según su ritmo (pendiente de 12 meses, escala raíz). Cada grupo es una **flecha de arena** desde su posición en «desde» (o en el periodo de comparación) hasta «hasta». Las cuatro zonas llevan su nombre escrito en arena. Al pasar por un grupo, su cometa entero se enciende y una línea dice nombre, score y ritmo. |
| **Tapiz** | Grupos × periodos. La densidad de la tinta es el score; el intervalo se marca y lo de fuera se atenúa. Reordenable (score, ritmo, primer aviso, tamaño). |
| **Expediente** | El número acuñado en arena, una frase en tercera persona que lo explica, sellos (banda con su escala de 0 a 100, movimiento con la misma forma que el cometa, confianza en tres granos), cuatro cifras con contexto, la trayectoria por periodos, la partitura de pilares y las empresas. Un cursor de periodo recorre todas las franjas. En el lateral (o en una hoja en pantallas estrechas): qué ha cambiado pilar a pilar, los avisos, de dónde sale cada pilar y el hueco del producto. |

El selector de vista son dos **miniaturas vivas** dibujadas con los datos del momento.

### Aspecto

- Colores de Embat en claro; rojo y verde solo en la arena, azul solo para lo seleccionado.
- **Newsreader** (serif de prensa con tamaños ópticos) para la frase, los números y los títulos; **Schibsted Grotesk** para el resto. Ninguna monoespaciada.
- Fichas y sellos de papel, radios suaves, sombras teñidas de azul marino.
- Voz del sistema en tercera persona y frases cortas (`src/vistas/voz.ts`); cada cifra sale de un campo del modelo.

### Responsive

Tres tamaños (`src/geometria.ts`): escritorio (1100 px o más, con lateral en el expediente), estrecho (de 700 a 1099 px) y móvil (menos de 700 px). En el móvil los paneles son hojas que suben desde abajo, el lateral del expediente se abre con un botón, el primer toque sobre un grupo lo señala y el segundo lo abre. El marco se recalcula con la altura real de la frase; en el expediente, la cabecera HTML se mide antes de colocar la arena debajo.

### Datos: sintéticos, con la forma del contrato

`src/datos/sintetico.ts` sigue las reglas de `docs/engine/ENGINE.md`: 250 grupos, 1.286 empresas, de septiembre de 2024 a agosto de 2026 (24 meses), cinco pilares con sus pesos, `shown = base + Σcontrib − penalty − cap` en décimas, dirección con Δ3 frente a max(6, 1,5σ), naturaleza, abstención, alertas y una **huella** sintética por pilar (fichero y filas, con la forma de `evidence/<id>.json`). Casos plantados: **GROUP_0042** (deriva lenta a la baja, como Velasco) y **GROUP_0113** (deriva lenta al alza, como Northbrook); el Δ3 del motor los ve «estables» y la tendencia larga los separa.

El modelo (`src/datos/modelo.ts`) usa los nombres de campo del contrato: cuando el motor exporte, basta un adaptador `portfolio.json` + `groups/<id>.json` → `Cartera`.

### Rendimiento

- Simulación de 64.000 granos: 1,6 ms por fotograma en el peor caso (medido con Bun).
- Construcción de escenas: plano y tapiz por debajo de un fotograma; expediente, unos 25 ms.
- `?captura` en la URL coloca los granos sin animar (para Chrome headless, que en macOS no genera fotogramas). Con `prefers-reduced-motion` la arena va directa a su sitio y se repinta al cambiar de tamaño.

### Pruebas

`bun run prueba` (con el servidor arrancado) recorre la interfaz con Chrome y hace 19 comprobaciones: las cinco tareas de la propuesta (se tuercen por trimestres, abrir el Grupo 42 escribiendo, frente al año pasado, por años, deshacer hasta el principio), la vista previa, el tamiz por zona, el lazo, el arrastre de las asas, el tapiz, la hoja y el buscador en el móvil, y que no haya errores de consola. Última ejecución: **todo correcto**.

### Cómo se arranca

```bash
cd interfaz
bun install
bun run dev          # http://127.0.0.1:5317
bun run build        # tipos + paquete de producción en dist/
bun run prueba       # recorrido automático
```

### Pendiente

- Productos servidos por el backend (hoy, reglas provisionales en la interfaz).
- Volver a exportar el bundle cuando la deriva lenta de Rubén entre en el motor.
- Expediente de empresa (hoy, las empresas se ven dentro de su grupo).
- Vista «Metodología» a partir de `receipt.json`.
