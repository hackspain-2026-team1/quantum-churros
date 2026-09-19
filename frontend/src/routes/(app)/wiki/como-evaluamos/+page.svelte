<script lang="ts">
	type Check = {
		name: string;
		tests: string;
		result: string;
		objective?: string;
	};

	type Stage = {
		title: string;
		lead: string;
		checks: Check[];
	};

	const stages: Stage[] = [
		{
			title: '1 · Conciliación',
			lead: '¿Leemos bien el rastro bancario antes de medir nada?',
			checks: [
				{
					name: 'Placebo de traspasos internos',
					tests:
						'Los espejos y reversiones reales entre cuentas del grupo no pueden explicarse emparejando fechas al azar.',
					result: 'superada',
					objective: 'superada'
				},
				{
					name: 'Feed bancario caído',
					tests:
						'Cuántos grupos llegan sin movimientos recientes en el último mes (falta de datos, no mal diagnóstico).',
					result: '12\u00A0% de los grupos',
					objective: 'documentar'
				}
			]
		},
		{
			title: '2 · Normalización',
			lead: '¿El panel respeta el tiempo, la moneda y no favorece a un tipo de empresa?',
			checks: [
				{
					name: 'Sin mirar al futuro',
					tests:
						'Truncar el histórico en un mes pasado no altera las notas de meses anteriores.',
					result: 'superada',
					objective: 'superada'
				},
				{
					name: 'Invarianza de escala',
					tests: 'Multiplicar todos los importes por 1.024 no cambia la nota.',
					result: 'superada',
					objective: 'superada'
				},
				{
					name: 'Cobertura de la cartera',
					tests:
						'Cuántos grupos son puntuables y cuántos tienen cada pilar observable en el último mes.',
					result: '88\u00A0% puntuables · 42\u00A0% con pagos · 34\u00A0% con cobros · 78\u00A0% con deuda'
				},
				{
					name: 'Neutralidad',
					tests:
						'La nota no se explica por el tamaño de la empresa, el ERP, el banco ni el mes del año.',
					result: 'exceso máximo 0,039',
					objective: 'por debajo de 0,06'
				}
			]
		},
		{
			title: '3 · Scoring',
			lead: '¿La nota es estable, explicable y honesta?',
			checks: [
				{
					name: 'Ensayo aislado de 60 grupos',
					tests:
						'Puntuar 60 grupos solos reproduce exactamente las mismas notas que en la cartera completa (aproximación del test oculto del organizador).',
					result: 'superada · 60 grupos · diferencia máxima 0',
					objective: 'superada'
				},
				{
					name: 'Identidad aditiva',
					tests: 'El desglose publicado (base, pilares, penalizaciones, topes) cuadra con la nota final.',
					result: 'superada',
					objective: 'superada'
				},
				{
					name: 'Determinismo',
					tests: 'Misma entrada y mismo orden de datos, misma salida.',
					result: 'superada',
					objective: 'superada'
				},
				{
					name: 'Estabilidad del orden',
					tests: 'Pequeños cambios de peso no reordenan toda la cartera.',
					result: 'superada',
					objective: 'superada'
				},
				{
					name: 'Persistencia de nivel (3 meses)',
					tests: 'Si la nota de hoy predice la nota dentro de tres meses.',
					result: 'correlación 0,62',
					objective: 'alta'
				},
				{
					name: 'Persistencia de pendiente (3 meses)',
					tests:
						'Si el cambio mensual de la nota se repite — suele ser bajo, y lo decimos con claridad.',
					result: 'correlación −0,14',
					objective: 'baja'
				},
				{
					name: 'Origen rodante',
					tests:
						'Re-puntuar solo con datos hasta noviembre de 2025, febrero de 2026 y mayo de 2026.',
					result: 'correlación mínima 1,0',
					objective: '1,0'
				},
				{
					name: 'Deterioros inyectados',
					tests:
						'En grupos sanos simulamos un pico de un mes, un escalón permanente y una rampa lenta.',
					result:
						'7,7\u00A0% de picos confundidos con caída estructural · 1 mes de mediana hasta detectar un escalón · 24,4 alertas por cada 100 grupo-años sin inyección real',
					objective: 'pico ≤ 10\u00A0% · escalón ≤ 3 meses'
				},
				{
					name: 'Anticipación y retardo',
					tests:
						'Separamos si la trayectoria de hoy ordena futuros onsets internos de cuánto tarda el score en reaccionar ante un cambio inyectado con fecha conocida.',
					result:
						'En CI, AUC pareada a 6 meses: 0,944 en escalón y 0,813 en rampa · confirmación estructural del escalón: 2 meses',
					objective: 'AUC ≥ 0,80 · confirmación del escalón ≤ 3 meses'
				}
			]
		}
	];

	const notPromised = [
		'No hay un porcentaje de acierto ni un modelo entrenado con impagos: los datos no traen la respuesta correcta.',
		'La AUC de cartera usa futuros onsets internos, no quiebras; la inyección mide retardo desde el cambio, no predice un shock exógeno.',
		'La pendiente mensual no persiste; la persistencia es de nivel (la nota de hoy sigue siendo informativa a tres meses).',
		'No prometemos predecir el test oculto del organizador: lo aproximamos con el ensayo aislado y parámetros congelados.'
	];
</script>

<svelte:head>
	<title>Cómo evaluamos · Rumbo</title>
	<meta
		name="description"
		content="Cómo comprobamos el motor de X-Ray sin etiquetas: conciliación, normalización y scoring, con qué se prueba cada métrica."
	/>
</svelte:head>

<main class="mx-auto max-w-3xl px-6 py-10 text-left">
	<a class="text-sm text-muted-foreground underline" href="/wiki">← Volver a la wiki</a>

	<p class="mt-6 text-sm text-muted-foreground">Evaluación</p>
	<h1 class="mt-1 text-3xl font-bold tracking-tight">Cómo evaluamos el motor</h1>

	<div class="mt-4 rounded-lg border bg-muted/30 p-4 text-sm leading-relaxed">
		X-Ray <span class="font-semibold">no se evalúa con aciertos</span>: no hay impagos ni notas de
		riesgo contra las que medir. Evaluamos si el sistema hace lo que promete — leer bien los datos,
		respetar el tiempo y publicar una nota explicable — en tres etapas encadenadas. Cada prueba lleva
		un nombre claro, una frase sobre <span class="font-semibold">qué se está probando</span> y el
		resultado frente a un objetivo cuando existe.
	</div>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Tres etapas, un solo informe</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Cada cambio del motor se vuelve a ejecutar sobre el dataset del reto (ventana septiembre de
			2024 → agosto de 2026). El resultado queda sellado con la huella del dataset, la huella de
			parámetros y la fecha del run. Las cifras de abajo son la última medición publicada; el equipo
			compara fila a fila en el historial interno para detectar regresiones.
		</p>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Para el método de puntuación en sí, consulta
			<a class="underline" href="/wiki/como-puntuamos">cómo puntuamos</a>.
		</p>
	</section>

	{#each stages as stage (stage.title)}
		<section class="mt-10">
			<h2 class="text-xl font-bold tracking-tight">{stage.title}</h2>
			<p class="mt-2 text-sm text-muted-foreground">{stage.lead}</p>
			<ul class="mt-4 space-y-4">
				{#each stage.checks as check (check.name)}
					<li class="rounded-lg border p-4">
						<p class="font-medium text-foreground">{check.name}</p>
						<p class="mt-2 text-sm leading-relaxed text-muted-foreground">
							<span class="font-medium text-foreground">Qué se prueba:</span>
							{check.tests}
						</p>
						<p class="mt-2 text-sm leading-relaxed">
							<span class="font-medium text-foreground">Resultado:</span>
							{check.result}
							{#if check.objective}
								<span class="text-muted-foreground">
									· objetivo: {check.objective}</span
								>
							{/if}
						</p>
					</li>
				{/each}
			</ul>
		</section>
	{/each}

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Qué no prometemos</h2>
		<ul class="mt-3 space-y-2 leading-relaxed text-muted-foreground">
			{#each notPromised as line (line)}
				<li class="flex gap-2">
					<span class="shrink-0 text-foreground">·</span>
					<span>{line}</span>
				</li>
			{/each}
		</ul>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Cómo interpretar una mejora</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Tras cada cambio, las pruebas obligatorias deben seguir superadas (traspasos, sin mirar al
			futuro, escala, ensayo aislado, identidad aditiva, determinismo). Además miramos que la
			cobertura no caiga sin motivo, que la persistencia de nivel se mantenga alta, que un pico de
			un mes no se confunda con una caída estructural y que un escalón permanente se detecte en pocos
			meses.
		</p>
	</section>

	<footer class="mt-12 text-sm text-muted-foreground">
		Las pruebas detalladas y el historial de runs viven en la documentación interna del motor. ¿Dudas
		sobre un dato concreto del producto?
		<a class="underline" href="/wiki">Consulta la wiki</a>.
	</footer>
</main>
