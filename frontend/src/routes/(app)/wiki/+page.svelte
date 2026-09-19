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
			question: '¿Por qué no entrenamos un modelo con los datos?',
			keywords: ['modelo', 'machine learning', 'ml', 'entrenamiento', 'target', 'etiqueta', 'label', 'medir', 'medicion', 'no compensatorio'],
			answer:
				'El dataset no trae ni una etiqueta de resultado: ni impagos, ni ratings, ni señales de «empresa sana». Todo lo que entrenáramos aprendería el objetivo que nosotros mismos hubiéramos escrito, y nos devolvería nuestra propia fórmula con ruido. Por eso X-Ray mide: cinco hechos observables por entidad y mes, mapeados a 0–100 con tablas de ancla congeladas y combinados con una regla no compensatoria. Ninguna estadística de la cohorte puntuada entra en el cálculo.'
		},
		{
			id: 'espejos',
			question: '¿Cómo gestionamos la duplicación de traspasos internos?',
			keywords: ['espejo', 'mirror', 'netting', 'traspaso', 'duplicado', 'duplicacion', 'transferencia', 'transfer', 'interno', 'tesoreria', 'sweeping', 'pares', 'neto', 'operativo'],
			answer:
				'Más de la mitad del valor de salida son movimientos entre cuentas del mismo grupo: tesorería que se barre a un centro, no compras ni ventas. Emparejamos pares espejo — mismo grupo, producto distinto, signo opuesto, moneda igual y céntimos idénticos en ±1 día (hasta 3 si el hueco cae en fin de semana) — y los excluimos de todas las medidas operativas. El emparejamiento es 1:1, por fecha más cercana e independiente del orden de las filas. Con placebos de fecha (9–11 días) el porcentaje cae del 46,6 % al 1,9 %: el criterio es real, no un artefacto.'
		},
		{
			id: 'guion',
			question: '¿Qué hacemos con la categoría «-», una de cada cuatro filas?',
			keywords: ['guion', 'dash', 'categoria', 'flow_class', 'clasificacion', 'signo', 'reglas', 'narrativas', 'retencion', 'ajuste', 'descripcion'],
			answer:
				'No la tiramos: son cuentas operativas. El signo predice la familia del flujo con precisión 0,89/0,93, así que por defecto clasificamos por signo y solo lo interrumpen 11 reglas narrativas con precisión medida ≥ 0,83 (ajustes de libro → interno, Seguridad Social o Hacienda → salida operativa, amortizaciones → servicio de deuda…). Las retenciones (RETENCION, AP.RET.DST: un 35 % de todo el valor de «-») quedan como clase «ajuste» y salen de todo. Cada fila recibe un flow_class; nunca se borra una, solo se marca.'
		},
		{
			id: 'facturas',
			question: '¿Cómo puntúamos la puntualidad cuando faltan facturas?',
			keywords: ['factura', 'facturas', 'puntualidad', 'dias', 'atraso', 'dbt', 'paydex', 'proveedores', 'clientes', 'erp', 'sellada', 'vencimiento', 'pagos'],
			answer:
				'78 de los 250 grupos no tienen facturas y la puntualidad es escasa por naturaleza. No inventamos un 50: el pilar queda a None con una puerta nombrada (sin facturas, pocas facturas, régimen ERP, n efectivo bajo) y los pesos se renormalizan sobre lo observable. Una entidad sin facturas se juzga con liquidez, actividad y deuda; la confianza lo comunica. También excluimos por fila las facturas selladas por el ERP (vencimiento = emisión y liquidación = vencimiento): esas fechas miden el software, no el comportamiento.'
		},
		{
			id: 'sweeping',
			question: '¿Qué pasa con las filiales barridas al centro de tesorería?',
			keywords: ['sweeping', 'barrido', 'saldo cero', 'saldo', 'filial', 'grupo', 'tesoreria', 'inherited_from_group', 'liquidez heredada'],
			answer:
				'Su cuenta está a cero porque la política del grupo lo decide, no porque la empresa esté mal. Detectamos cuentas de saldo cero con cuota marginal de la caja del grupo o pares de barrido repetidos, y les damos el pilar de liquidez del grupo con la puerta inherited_from_group y su bandera. La caja vacía deja de leerse como estrés.'
		},
		{
			id: 'tamano',
			question: '¿Cómo evitamos que la liquidez sea una proxy del tamaño?',
			keywords: ['liquidez', 'tamano', 'size', 'tramo', 'banda de tamano', 'pyme', 'sme', 'micro', 'grande', 'mediana', 'jpmorgan', 'ancla', 'cuantil'],
			answer:
				'Con anclas absolutas, la mediana de liquidez cae de ~85 en microgrupos a ~18 en grandes: los grandes corren poco efectivo y viven de líneas, que es estructura, no angustia. Congelamos una tabla por tramo de facturación con los umbrales de pyme de la UE (micro < 2 M€, pequeña < 10 M€, mediana < 50 M€, grande ≥ 50 M€) y cuantiles de referencia por tramo. La tabla absoluta (cuartiles del JPMorgan Chase Institute) queda a un interruptor: params.liquidity.segmented = false.'
		},
		{
			id: 'unidad',
			question: '¿Por qué puntuamos el grupo y no solo la empresa?',
			keywords: ['grupo', 'empresa', 'consolidado', 'perimetro', 'unidades', 'drilldown', 'detalle', 'media', 'miembro'],
			answer:
				'El 60 % de los pares espejo cruza empresas del mismo grupo y arrastra los importes grandes; las filiales se barren a tesorería y la deuda se concentra en un miembro. Una ratio a nivel de empresa mide fontanería de tesorería, no salud. Sumamos los flujos de los miembros en céntimos primero y tomamos ratios después: la puntuación de un grupo nunca es una media de puntuaciones. Cada empresa se puntúa igual y aparece como detalle, y se escribe siempre en los dos CSV porque la unidad del test oculto no está confirmada.'
		},
		{
			id: 'moneda',
			question: '¿Cómo hacemos la conversión de divisa?',
			keywords: ['moneda', 'divisa', 'exchange_rate', 'convertir', 'conversion', 'euro', 'eur', 'fx', 'cambio', 'tipo de cambio', 'moneda extranjera', 'product_id'],
			answer:
				'Esa columna relaciona la moneda de la cuenta con la moneda contable de la empresa, no con el euro, en dirección inversa a la lectura ingenua, y en un 4–14 % de filas multimoneda es incoherente. Cada fila hereda la moneda de su producto (banking_products / debt_products) y convertimos con una tabla estática congelada en params.fx. Filas en otra moneda quedan en recuentos y salen de los agregados de valor, con su cuota publicada.'
		},
		{
			id: 'cohortindependiente',
			question: '¿Cómo garantizamos que puntuar 60 grupos a solas dé el mismo número?',
			keywords: ['independiente', 'cohorte', 'cohort', 'params', 'fit-reference', 'predict', 'sha256', 'aislamiento', 'test oculto', 'congelado', 'determinismo'],
			answer:
				'Todos los parámetros viven en params/reference_v1.json con su sha256: pesos, anclas, tramos, λ/τ, bandas y medianas de referencia. fit-reference es el único paso que mira a la cohorte (una vez); predict nunca reajusta. La prueba de aislamiento verifica que puntuar un subconjunto reproduce las filas completas con tolerancia 1e-9: lo que necesita un test oculto de entidades no vistas.'
		},
		{
			id: 'feed',
			question: '¿Cómo tratamos los meses en que el conector deja de traer datos?',
			keywords: ['feed', 'rancio', 'stale', 'conector', 'carry', 'carry forward', 'carried', 'sin datos', 'falta de datos', 'abstencion', 'stale_feed'],
			answer:
				'Un feed rancio es un dato, no un diagnóstico: cuando desaparecen los pagos de Seguridad Social el volumen cae a 0,17× y la empresa no dejó de pagar. Lo detectamos con la ratio de filas del último trimestre contra su línea base propia; si falla, la explicación del último mes vivo se copia literal (carry forward), apagamos penas, topes y alertas por ausencia y el mes se abstiene con motivo stale_feed. Nunca cambiamos el número por esto.'
		},
		{
			id: 'no-compensatorio',
			question: '¿Cómo evitamos que un pilar fuerte tape uno roto?',
			keywords: ['pena', 'penalty', 'tope', 'cap', 'limite', 'lambda', 'compensacion', 'pesos', 'contribucion', 'explicacion', 'base', 'identidad'],
			answer:
				'La agregación no compensa: por debajo de 45 puntos, el pilar más débil cuesta la mitad de su desfase, hasta 22,5 puntos; y los topes duros (liquidez negativa ⇒ techo 40) no se compran con otros pilares. Además expone todo: la identidad exacta score = base + Σ contribuciones − pena − tope con error ≤ 1e-9, en décimos enteros que suman en pantalla, con puertas y banderas al lado de cada cifra.'
		},
		{
			id: 'validacion',
			question: '¿Validamos sin etiquetas de resultado?',
			keywords: ['validacion', 'validacion sin etiquetas', 'placebo', 'additividad', 'aditividad', 'invariancia', 'precision', 'acuerdo', 'decisions'],
			answer:
				'No hay verdad terrenal en el dataset, así que no alegamos ninguna precisión de acierto. La validez descansa en la construcción (anclas, identidades, invariancias) y en un protocolo de validación sin etiquetas — additividad, aislamiento, truncamiento, placebos — cuyos resultados viven en artifacts/validation.json. Cada decisión y cada parámetro libre está en DECISIONS.md con su evidencia y sensibilidad.'
		}
	];

	const terms = [
		{ term: 'Pilar', def: 'Uno de los cinco hechos medidos: liquidez 0,30, pagos 0,20, cobros 0,15, actividad 0,20, deuda 0,15. Función pura PanelRow → PillarResult.' },
		{ term: 'Puerta (gate)', def: 'Motivo nombrado por el que un pilar no es observable (buffer_undefined, no_invoices…). None nunca es un 0 ni un 50 imputado.' },
		{ term: 'Días sobre términos (DBT)', def: 'Días de retraso medio ponderado por importe: liquidación − vencimiento, recortado a [−30, 90]; las facturas abiertas siguen envejeciendo hasta fin de mes.' },
		{ term: 'Días de colchón', def: '(Caja + headroom) / salida diaria media del trimestre. Cuántos días de gastos cubre el disponible.' },
		{ term: 'Cobertura operativa', def: 'Σ entradas operativas / Σ (salidas operativas + servicio de deuda), últimos 6 meses.' },
		{ term: 'Bloque espejo / netting', def: 'Emparejamiento 1:1 de movimientos internos del grupo (opuesto, misma cantidad, ±1–3 días) que salen de todas las medidas operativas.' },
		{ term: 'Factura sellada (ERP-stamped)', def: 'Fila con emisión = vencimiento y liquidación = vencimiento: dice nada del comportamiento y se excluye por fila.' },
		{ term: 'Like-for-like', def: 'Toda comparación entre dos ventanas usa solo cuentas que informan en ambas. Los cambios de perímetro no alteran el delta.' },
		{ term: 'Feed vivo / rancio', def: 'Ratio de filas de los 2 últimos meses contra su línea base propia: < 0,5 o cero filas ⇒ mes rancio, se porta adelante el último mes vivo — carried-forward —.' },
		{ term: 'Abstención', def: 'Menos de 4 meses, feed muerto o sin pilar bancario ⇒ se emite el número igualmente, sin alertas, con unlock_hint en español.' },
		{ term: 'Banda', def: 'Crítico < 40, Vigilancia 40–60, Estable 60–80, Sólido ≥ 80, decididos sobre décimos enteros para que pantalla y motor coincidan.' },
		{ term: 'Traza', def: 'Dirección (mejora/deterioro cuando |delta3| ≥ máx(6, 1,5·σ propia)), naturaleza (shock_pending, structural, bump) y perímetro detectado.' }
	];
</script>

<svelte:head>
	<title>Wiki · Embat X-Ray</title>
	<meta name="description" content="Cómo hemos resuelto cada problema de datos y de diseño del motor X-Ray." />
</svelte:head>

<main class="mx-auto max-w-3xl px-6 py-10 text-left">
	<p class="text-muted-foreground text-sm">Wiki</p>
	<h1 class="mt-1 text-3xl font-bold tracking-tight">Cómo lo hemos resuelto</h1>
	<p class="text-muted-foreground mt-2">
		Cada problema que encontramos en los datos, la decisión que tomamos y por qué. Las cifras son
		las medidas en el dataset del reto; el detalle completo vive en
		<span class="font-mono text-xs">docs/engine/ENGINE.md</span>.
	</p>

	<div class="relative mt-8">
		<Search class="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
		<Input
			class="rounded-full py-2 pl-9 pr-9 shadow-none ring-0 focus-visible:ring-0"
			placeholder="Buscar: divisa, facturas, traspasos…"
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
	<p class="text-muted-foreground mt-2 text-xs">
		{#if query.trim() === ''}
			{solutions.length} preguntas · {terms.length} términos
		{:else if matches.length === 0 && matchingTerms.length === 0}
			Sin resultados para «{query}». Prueba con otra palabra.
		{:else}
			{matches.length + matchingTerms.length} resultado
			{matches.length + matchingTerms.length === 1 ? '' : 's'} para «{query}»
		{/if}
	</p>

	<nav class="mt-4">
		<div class="flex flex-wrap gap-2">
			{#each matches as s (s.id)}
				<a href="#{s.id}" class="hover:bg-accent rounded-md border px-2.5 py-1 text-xs">{s.question}</a>
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
					<p class="text-muted-foreground text-sm leading-relaxed">{s.answer}</p>
				</Card.Content>
			</Card.Root>
		{:else}
			<p class="text-muted-foreground text-sm">Ninguna pregunta coincide con «{query}».</p>
		{/each}
	</section>

	<hr class="my-12" />

	<section>
		<h2 class="text-2xl font-bold tracking-tight">Los términos que verás en pantalla</h2>
		<p class="text-muted-foreground mt-1 text-sm">Los códigos exactos (puertas, banderas, topes y motivos) tienen su texto en español en cada bundle, junto a cada dato.</p>
		<div class="mt-6 grid gap-4 sm:grid-cols-2">
			{#each matchingTerms as t (t.term)}
				<div class="rounded-lg border p-4">
					<Badge variant="outline">{t.term}</Badge>
					<p class="text-muted-foreground mt-2 text-sm leading-relaxed">{t.def}</p>
				</div>
			{:else}
				{#if query.trim() !== ''}
					<p class="text-muted-foreground text-sm">Ningún término coincide con «{query}».</p>
				{/if}
			{/each}
		</div>
	</section>

	<footer class="text-muted-foreground mt-12 text-sm">
		Fuente: <span class="font-mono text-xs">docs/engine/ENGINE.md</span> y sus documentos hermanos
		(DECISIONS, DATA_TRAPS, VALIDATION, OPEN_QUESTIONS).
	</footer>
</main>
