<script lang="ts">
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import { Search, X } from '@lucide/svelte';

	let query = $state('');

	// Lowercased and without accents, so «moneda», «Moneda» and «móNeda» match alike.
	// Search hits hit the question, the answer and the keyword list, so a reader that
	// says «divisa» still finds the entry that says «moneda» (and vice versa).
	const normalize = (value: string) =>
		value
			.toLowerCase()
			.normalize('NFD')
			.replaceAll(/[\u0300-\u036f]/g, '');
	const matches = $derived.by(() => {
		const needle = normalize(query.trim());
		if (needle === '') return solutions;
		return solutions.filter((s) =>
			normalize(`${s.question} ${s.answer} ${s.keywords.join(' ')}`).includes(needle)
		);
	});

	const matchingTerms = $derived.by(() => {
		const needle = normalize(query.trim());
		if (needle === '') return terms;
		return terms.filter((t) => normalize(`${t.term} ${t.def}`).includes(needle));
	});

	const solutions = [
		{
			id: 'modelo',
			question: '¿Por qué no entrenamos una inteligencia artificial?',
			keywords: [
				'modelo',
				'machine learning',
				'ml',
				'ia',
				'inteligencia artificial',
				'entrenamiento',
				'target',
				'etiqueta',
				'label',
				'prediccion',
				'medir',
				'medicion',
				'no compensatorio'
			],
			answer:
				'Los datos no incluyen el desenlace de ninguna empresa: ni impagos, ni notas de riesgo, ni señales de que vaya bien o mal. Cualquier modelo que entrenáramos aprendería nuestra propia opinión y nos la devolvería con ruido. Por eso X-Ray no predice: mide. Cada empresa y cada mes se evalúan con cinco hechos observables, se convierten en una nota de 0 a 100 con tablas de referencia fijas y se combinan sin que un punto fuerte tape un problema. Ningún dato de las demás empresas influye en la nota de una.'
		},
		{
			id: 'espejos',
			question: '¿Qué hacemos con los movimientos entre cuentas del mismo grupo?',
			keywords: [
				'espejo',
				'mirror',
				'netting',
				'traspaso',
				'duplicado',
				'duplicacion',
				'transferencia',
				'transfer',
				'interno',
				'tesoreria',
				'sweeping',
				'pares',
				'neto',
				'operativo'
			],
			answer:
				'Más de la mitad del dinero que sale son movimientos internos: tesorería que el grupo pasa de una cuenta a otra, no compras ni ventas reales. Detectamos esas parejas (mismo grupo, misma moneda, importe idéntico al céntimo y fechas casi iguales, con hasta 3 días de margen si el hueco cae en fin de semana) y las sacamos de todas las medidas operativas. El emparejamiento es uno a uno, por la fecha más cercana, y no depende del orden de los datos. Si aplicamos el mismo criterio a fechas elegidas al azar, el porcentaje detectado cae del 46,6\u00A0% al 1,9\u00A0%: el criterio responde a un patrón real, no a la casualidad.'
		},
		{
			id: 'guion',
			question: '¿Qué hacemos con los movimientos que llegan sin categoría?',
			keywords: [
				'guion',
				'dash',
				'categoria',
				'clasificacion',
				'signo',
				'reglas',
				'narrativas',
				'retencion',
				'ajuste',
				'descripcion',
				'sin categoria'
			],
			answer:
				'Uno de cada cuatro movimientos llega sin categoría, y no los descartamos: son cuentas operativas. El signo del movimiento acierta la familia del flujo nueve de cada diez veces, y solo lo corrigen unas pocas reglas escritas a mano (los ajustes de libro van a operaciones internas, los pagos a la Seguridad Social o a Hacienda son salidas operativas y las amortizaciones son servicio de deuda). Las retenciones, el 35\u00A0% del valor sin categoría, se marcan como ajustes y quedan fuera de todas las medidas. Ninguna fila se borra: las que no se pueden clasificar se marcan, nunca se ocultan.'
		},
		{
			id: 'facturas',
			question: '¿Qué pasa si una empresa no aporta facturas?',
			keywords: [
				'factura',
				'facturas',
				'puntualidad',
				'dias',
				'atraso',
				'dbt',
				'paydex',
				'proveedores',
				'clientes',
				'erp',
				'sellada',
				'vencimiento',
				'pagos',
				'sin facturas'
			],
			answer:
				'A 78 de los 250 grupos les faltan facturas, y la puntualidad de pago es un dato escaso por naturaleza. No inventamos un valor intermedio: ese pilar se muestra como no disponible, con el motivo a la vista, y la nota se recalcula con lo que sí se puede observar (liquidez, actividad y deuda). La confianza de la nota refleja esa carencia. También excluimos una a una las facturas que el propio programa emite y liquida el mismo día: miden el software, no la conducta de pago.'
		},
		{
			id: 'sweeping',
			question: '¿Por qué la cuenta de una filial aparece vacía?',
			keywords: [
				'sweeping',
				'barrido',
				'saldo cero',
				'saldo',
				'filial',
				'grupo',
				'tesoreria',
				'liquidez heredada'
			],
			answer:
				'Porque la política del grupo decide barrer su caja hacia un centro de tesorería, no porque la empresa esté mal. Detectamos las cuentas a cero que siguen ese patrón y las evaluamos con la liquidez del grupo, con el motivo indicado junto al dato. Así, una caja vacía deja de leerse como señal de estrés.'
		},
		{
			id: 'tamano',
			question: '¿Comparamos a cada empresa con empresas de su tamaño?',
			keywords: [
				'liquidez',
				'tamano',
				'size',
				'tramo',
				'banda de tamano',
				'pyme',
				'sme',
				'micro',
				'grande',
				'mediana',
				'ancla',
				'cuantil',
				'union europea',
				'umbrales'
			],
			answer:
				'Sí. Las empresas grandes manejan poco efectivo y viven de líneas de crédito: es estructura, no angustia. Por eso la liquidez se compara dentro del tramo de facturación, con los umbrales oficiales de la Unión Europea (micro por debajo de 2\u00A0M€, pequeña por debajo de 10\u00A0M€, mediana por debajo de 50\u00A0M€ y grande a partir de 50\u00A0M€), y con puntos de referencia independientes para cada tramo. También existe una tabla única para todos los tamaños, pero queda desactivada por defecto.'
		},
		{
			id: 'unidad',
			question: '¿Puntuamos el grupo entero o cada empresa por separado?',
			keywords: [
				'grupo',
				'empresa',
				'consolidado',
				'perimetro',
				'unidades',
				'drilldown',
				'detalle',
				'media',
				'miembro'
			],
			answer:
				'El grupo. La mayoría de los movimientos internos cruzan empresas del mismo grupo y arrastran los importes grandes: las filiales vacían su caja hacia el centro y la deuda se concentra en un miembro. Una ratio aislada de una empresa mediría esa fontanería interna, no su salud. Por eso primero sumamos los movimientos de todo el grupo y después calculamos las ratios: la nota de un grupo nunca es un promedio de notas. Cada empresa también recibe su nota y aparece como detalle.'
		},
		{
			id: 'moneda',
			question: '¿Cómo convertimos las monedas extranjeras?',
			keywords: [
				'moneda',
				'divisa',
				'convertir',
				'conversion',
				'euro',
				'eur',
				'fx',
				'cambio',
				'tipo de cambio',
				'moneda extranjera'
			],
			answer:
				'Cada cuenta informa en una moneda, y la convertimos a la moneda contable de su empresa con una tabla de tipos de cambio fija. La conversión no siempre es directa: en una parte de los movimientos multimoneda (entre el 4\u00A0% y el 14\u00A0%) el dato llega incoherente, así que lo verificamos antes de usarlo. Los movimientos en monedas no cubiertas cuentan en los recuentos, pero salen de los totales de valor, y su peso se publica.'
		},
		{
			id: 'cohortindependiente',
			question: '¿La nota sería la misma si volviéramos a calcularla?',
			keywords: [
				'independiente',
				'cohorte',
				'cohort',
				'aislamiento',
				'test oculto',
				'congelado',
				'determinismo',
				'reproducible'
			],
			answer:
				'Sí. Todos los pesos, referencias y umbrales se fijan y se congelan antes de puntuar; el cálculo nunca se reajusta con los datos que ve. Lo comprobamos: puntuar un subconjunto de empresas reproduce exactamente las mismas notas que en el cálculo completo, hasta el último decimal. Así se puede puntuar una empresa nueva sin que cambie ninguna nota anterior.'
		},
		{
			id: 'feed',
			question: '¿Qué pasa cuando deja de llegar información de una cuenta?',
			keywords: [
				'feed',
				'rancio',
				'stale',
				'conector',
				'carry',
				'carry forward',
				'carried',
				'sin datos',
				'falta de datos',
				'abstencion'
			],
			answer:
				'Falta de datos no es mal diagnóstico. Cuando desaparecen, por ejemplo, los pagos a la Seguridad Social, el volumen de información se desploma aunque la empresa no haya dejado de pagar. Detectamos estas caídas comparando los últimos meses con la actividad habitual de la propia cuenta. Si la información no es suficiente, mantenemos la explicación del último mes sano, se apagan las alertas por ausencia y el mes se abstiene con su motivo a la vista. El número no se cambia por esto.'
		},
		{
			id: 'no-compensatorio',
			question: '¿Puede un punto fuerte tapar un problema grave?',
			keywords: [
				'pena',
				'penalty',
				'tope',
				'cap',
				'limite',
				'lambda',
				'compensacion',
				'pesos',
				'contribucion',
				'explicacion',
				'base',
				'identidad'
			],
			answer:
				'No. Cuando un pilar baja de 45 puntos, su desfase pesa el doble en la nota final, hasta 22,5 puntos; y hay techos que no se pueden comprar con otros pilares: con caja negativa sostenida, la nota no puede pasar de 40. Además todo queda a la vista: la nota final siempre es la suma de sus partes menos penalizaciones y topes, y puedes comprobarlo con las cifras que acompañan a cada dato.'
		},
		{
			id: 'evaluacion',
			question: '¿Cómo evaluamos el motor?',
			keywords: [
				'evaluacion',
				'evaluar',
				'prueba',
				'pruebas',
				'validacion',
				'benchmark',
				'regresion',
				'fase a',
				'conciliacion',
				'normalizacion',
				'scoring',
				'persistencia',
				'origen rodante',
				'ensayo aislado',
				'placebo',
				'inyeccion',
				'deterioro',
				'fiabilidad'
			],
			answer:
				'Sin impagos ni etiquetas de riesgo no hay porcentaje de acierto: comprobamos que el sistema hace lo que promete en tres etapas — conciliación, normalización y scoring. Cada prueba tiene nombre claro y una frase sobre qué se está probando: placebo de traspasos, sin mirar al futuro, ensayo aislado de 60 grupos, identidad aditiva, persistencia de nivel, origen rodante y deterioros simulados.',
			readMore: '/wiki/como-evaluamos'
		},
		{
			id: 'validacion',
			question: '¿Cómo sabemos que las notas son fiables?',
			keywords: [
				'validacion',
				'validacion sin etiquetas',
				'placebo',
				'additividad',
				'aditividad',
				'invariancia',
				'precision',
				'acuerdo',
				'decisions',
				'fiabilidad'
			],
			answer:
				'Los datos no traen la respuesta correcta, así que no prometemos porcentajes de acierto. La fiabilidad descansa en cómo está construido el sistema: referencias fijas, comprobaciones de que las partes suman el total y pruebas de que el resultado no cambia al reordenar o recortar los datos. Cada decisión y cada valor elegido está documentado, con su evidencia y su análisis de sensibilidad.',
			readMore: '/wiki/como-evaluamos'
		}
	];

	const terms = [
		{
			term: 'Pilar',
			def: 'Cada uno de los cinco hechos que se miden: liquidez (30\u00A0%), pagos (20\u00A0%), cobros (15\u00A0%), actividad (20\u00A0%) y deuda (15\u00A0%).'
		},
		{
			term: 'Puerta',
			def: 'El motivo por el que un dato no está disponible (por ejemplo, sin facturas). Cuando algo no se puede medir, se dice: nunca se inventa un cero ni un valor intermedio.'
		},
		{
			term: 'Días sobre términos (DBT)',
			def: 'El retraso medio de pago a proveedores, ponderado por el importe de cada factura. Se recorta entre 30 días de adelanto y 90 de retraso, y las facturas sin pagar siguen envejeciendo hasta fin de mes.'
		},
		{
			term: 'Días de colchón',
			def: 'Cuántos días de gastos cubre el dinero disponible: la caja más el margen sin usar de las líneas de crédito.'
		},
		{
			term: 'Cobertura operativa',
			def: 'Cuánto entra por la actividad frente a cuánto sale (gastos más devolución de deuda), en los últimos 6 meses.'
		},
		{
			term: 'Bloque espejo',
			def: 'Movimientos internos entre cuentas del mismo grupo (mismo importe, sentido opuesto, fechas casi iguales) que no son compras ni ventas reales: salen de todas las medidas operativas.'
		},
		{
			term: 'Factura sellada',
			def: 'Una factura que el software emite y liquida el mismo día: no dice nada de la conducta de pago y se excluye una a una.'
		},
		{
			term: 'Like-for-like',
			def: 'Toda comparación usa solo las cuentas que informan en los dos periodos, para que un cambio de perímetro no falsee la diferencia.'
		},
		{
			term: 'Feed vivo / rancio',
			def: 'Si los últimos meses traen mucha menos información de lo habitual, el mes se marca sin datos fiables y se mantiene la explicación del último mes sano. Falta de datos no es mal diagnóstico.'
		},
		{
			term: 'Abstención',
			def: 'Con menos de 4 meses de información, un feed sin datos o sin cuentas bancarias, el sistema emite la nota pero sin alertas: no hay base suficiente para alarmarse.'
		},
		{
			term: 'Banda',
			def: 'Las notas se agrupan en zonas: Crítico por debajo de 40, Vigilancia de 40 a 60, Estable de 60 a 80 y Sólido a partir de 80.'
		},
		{
			term: 'Traza',
			def: 'La dirección del cambio (mejora o deterioro), su naturaleza (un bache puntual, un cambio estructural o un movimiento pequeño) y el perímetro afectado.'
		}
	];
</script>

<svelte:head>
	<title>Wiki · Rumbo</title>
	<meta
		name="description"
		content="Cómo funciona X-Ray: cada problema de datos, la decisión que tomamos y por qué, explicado de forma sencilla."
	/>
</svelte:head>

<main class="mx-auto max-w-3xl px-6 py-10 text-left">
	<p class="text-sm text-muted-foreground">Wiki</p>
	<h1 class="mt-1 text-3xl font-bold tracking-tight">Cómo lo hemos resuelto</h1>
	<p class="mt-2 text-muted-foreground">
		Cada problema que encontramos en los datos, la decisión que tomamos y por qué, explicado de
		forma sencilla. Las cifras son las medidas reales sobre los datos analizados. Para el método
		completo, <a class="underline" href="/wiki/como-puntuamos">aprende cómo puntuamos</a> o
		<a class="underline" href="/wiki/como-evaluamos">cómo evaluamos el motor</a>.
	</p>

	<div class="relative mt-8">
		<Search class="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
		<Input
			class="rounded-full py-2 pr-9 pl-9 shadow-none ring-0 focus-visible:ring-0"
			placeholder="Buscar: monedas, facturas, movimientos internos…"
			aria-label="Buscar en el wiki"
			bind:value={query}
		/>
		{#if query !== ''}
			<button
				type="button"
				class="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-accent"
				aria-label="Limpiar búsqueda"
				onclick={() => (query = '')}
			>
				<X class="size-4" />
			</button>
		{/if}
	</div>
	<p class="mt-2 text-xs text-muted-foreground">
		{#if query.trim() === ''}
			{solutions.length} preguntas · {terms.length} términos
		{:else if matches.length === 0 && matchingTerms.length === 0}
			Sin resultados para "{query}". Prueba con otra palabra.
		{:else}
			{matches.length + matchingTerms.length} resultado
			{matches.length + matchingTerms.length === 1 ? '' : 's'} para "{query}"
		{/if}
	</p>

	<nav class="mt-4">
		<div class="flex flex-wrap gap-2">
			{#each matches as s (s.id)}
				<a href="#{s.id}" class="rounded-md border px-2.5 py-1 text-xs hover:bg-accent"
					>{s.question}</a
				>
			{/each}
		</div>
	</nav>

	<section class="mt-10 space-y-4">
		{#each matches as s (s.id)}
			<Card.Root id={s.id} class="scroll-mt-6">
				<Card.Header>
					<Card.Title class="text-lg">{s.question}</Card.Title>
				</Card.Header>
				<Card.Content>
					<p class="text-sm leading-relaxed text-muted-foreground">{s.answer}</p>
					{#if 'readMore' in s && s.readMore}
						<p class="mt-3 text-sm">
							<a class="underline text-muted-foreground" href={s.readMore}>Leer el protocolo completo</a>
						</p>
					{/if}
				</Card.Content>
			</Card.Root>
		{:else}
			<p class="text-muted-foreground text-sm">Ninguna pregunta coincide con "{query}".</p>
		{/each}
	</section>

	<hr class="my-12" />

	<section>
		<h2 class="text-2xl font-bold tracking-tight">Los términos que verás en pantalla</h2>
		<p class="mt-1 text-sm text-muted-foreground">
			Si en pantalla aparece un término técnico, siempre va acompañado de su explicación en español,
			junto al dato al que se refiere.
		</p>
		<div class="mt-6 grid gap-4 sm:grid-cols-2">
			{#each matchingTerms as t (t.term)}
				<div class="rounded-lg border p-4">
					<Badge variant="outline">{t.term}</Badge>
					<p class="mt-2 text-sm leading-relaxed text-muted-foreground">{t.def}</p>
				</div>
			{:else}
				{#if query.trim() !== ''}
					<p class="text-muted-foreground text-sm">Ningún término coincide con "{query}".</p>
				{/if}
			{/each}
		</div>
	</section>

	<footer class="mt-12 text-sm text-muted-foreground">
		Fuente: la documentación interna del motor, con cada decisión de diseño, sus evidencias y sus
		límites conocidos.
	</footer>
</main>
