<script lang="ts">
	const pillars = [
		{
			name: 'Liquidez',
			weight: '30\u00A0%',
			what: 'cuántos días de gastos cubren la caja y las líneas de crédito sin usar'
		},
		{
			name: 'Pagos',
			weight: '20\u00A0%',
			what: 'el retraso medio al pagar a proveedores, según las facturas'
		},
		{
			name: 'Cobros',
			weight: '15\u00A0%',
			what: 'el retraso medio en cobrar de los clientes'
		},
		{
			name: 'Actividad',
			weight: '20\u00A0%',
			what: 'si lo que entra cubre lo que sale, y si los ingresos mejoran o empeoran'
		},
		{
			name: 'Deuda',
			weight: '15\u00A0%',
			what: 'cuánto de lo que entra se dedica a devolver deuda'
		}
	];

	const cleaning = [
		{
			name: 'Traspasos internos',
			why: 'más de la mitad del dinero que sale son movimientos entre cuentas del grupo. Se emparejan (importe idéntico al céntimo, sentido opuesto, fechas casi iguales) y salen de todas las medidas: no son compras ni ventas.'
		},
		{
			name: 'Movimientos sin categoría',
			why: 'uno de cada cuatro llega sin categoría. El signo acierta la familia del flujo nueve de cada diez veces, y unas pocas reglas escritas a mano corrigen los patrones conocidos. Ninguna fila se borra: las dudosas se marcan.'
		},
		{
			name: 'Facturas autoliquidadas',
			why: 'las facturas que el software emite y liquida el mismo día miden el programa, no la conducta de pago, y se excluyen una a una.'
		},
		{
			name: 'Monedas',
			why: 'cada cuenta se convierte a la moneda contable de su empresa con una tabla de tipos de cambio fija. Las monedas no cubiertas cuentan en los recuentos, pero no suman valor.'
		}
	];
</script>

<svelte:head>
	<title>Cómo puntuamos · Rumbo</title>
	<meta
		name="description"
		content="El método de X-Ray de primeras: qué medimos, por qué lo medimos así y qué hacemos cuando falta información."
	/>
</svelte:head>

<main class="mx-auto max-w-3xl px-6 py-10 text-left">
	<a class="text-sm text-muted-foreground underline" href="/wiki">← Volver a la wiki</a>

	<p class="mt-6 text-sm text-muted-foreground">Método</p>
	<h1 class="mt-1 text-3xl font-bold tracking-tight">Cómo puntuamos</h1>

	<div class="mt-4 rounded-lg border bg-muted/30 p-4 text-sm leading-relaxed">
		X-Ray <span class="font-semibold">mide</span>: no predice. Cinco hechos observables por grupo y
		mes, notas de 0 a 100 con tablas fijas, combinadas sin que un punto fuerte tape un problema.
		Nada se entrena, nada se inventa y la cuenta siempre sale.
	</div>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Partimos de lo que no hay</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Los datos no traen la respuesta: ni impagos, ni notas de riesgo, ni señales de qué empresa
			acabó bien o mal. Cualquier modelo entrenado con estos datos aprendería nuestra propia opinión
			y nos la devolvería con ruido. Por eso no entrenamos nada: medimos.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Cinco hechos, no una opinión</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Para cada empresa y cada mes, medimos cinco cosas que se pueden observar en las cuentas y en
			las facturas. Cada una pesa distinto en la nota final:
		</p>
		<ul class="mt-3 space-y-2 leading-relaxed text-muted-foreground">
			{#each pillars as p (p.name)}
				<li class="flex gap-2">
					<span class="shrink-0 font-medium text-foreground">{p.name} ({p.weight}):</span>
					<span>{p.what}</span>
				</li>
			{/each}
		</ul>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">De la medida a la nota</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Cada hecho se convierte en una nota de 0 a 100 con tablas de referencia fijas, congeladas
			antes de puntuar. La liquidez se compara con empresas del mismo tramo de facturación (umbrales
			oficiales de la Unión Europea: micro por debajo de 2&nbsp;M€, pequeña por debajo de
			10&nbsp;M€, mediana por debajo de 50&nbsp;M€ y grande a partir de 50&nbsp;M€), porque las
			grandes manejan poco efectivo y viven de líneas de crédito: es estructura, no angustia. En la
			puntualidad, pagar en plazo puntúa 80; con 30 días de retraso la nota baja a 50, y con 90 se
			queda en 30.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">La unidad es el grupo</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Los movimientos grandes cruzan empresas del mismo grupo: las filiales vacían su caja hacia un
			centro de tesorería y la deuda se concentra en un miembro. Medir a una empresa suelta mediría
			esa fontanería interna, no su salud. Por eso primero se suman los movimientos de todo el grupo
			y después se calculan las ratios: la nota de un grupo nunca es un promedio de notas. Cada
			empresa recibe su nota como detalle, y una filial con la cuenta a cero hereda la liquidez del
			grupo: es política de tesorería, no estrés.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Antes de medir, limpiamos</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Cuatro limpiezas, en un orden fijo, antes de calcular nada:
		</p>
		<ul class="mt-3 space-y-2 leading-relaxed text-muted-foreground">
			{#each cleaning as c (c.name)}
				<li class="flex gap-2">
					<span class="shrink-0 font-medium text-foreground">{c.name}:</span>
					<span>{c.why}</span>
				</li>
			{/each}
		</ul>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Lo que no se puede medir, se dice</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Si un hecho no es observable, ese pilar no recibe nota y el motivo se muestra al lado: sin
			facturas, historial corto, caja sin saldo de referencia. Nunca se inventa un cero ni un valor
			intermedio, y los pesos se recalculan sobre lo que sí se puede medir. La confianza de la nota
			(alta, media o baja) refleja esa carencia, y nunca cambia el número.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Un punto fuerte no compra un problema grave</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Las cinco notas se combinan con los pesos de arriba, con una salvedad deliberada: por debajo
			de 45 puntos, el pilar más débil cuesta la mitad de su desfase, hasta 22,5 puntos. Y hay
			techos que no se pueden comprar: con caja negativa sostenida, la nota no pasa de 40. El
			resultado se agrupa en zonas: Crítico por debajo de 40, Vigilancia de 40 a 60, Estable de 60 a
			80 y Sólido a partir de 80.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">La cuenta siempre sale</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Cada nota se publica con su desglose completo: la base, la aportación de cada pilar, las
			penalizaciones y los topes. Las cifras de la pantalla suman exactamente la nota final, en
			décimos: puedes recomputarla a mano.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">El mismo dato, la misma nota</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Todos los pesos, referencias y umbrales están congelados antes de puntuar; el cálculo nunca se
			reajusta con lo que ve. Lo comprobamos: puntuar un subconjunto de empresas reproduce
			exactamente las mismas notas que el cálculo completo, hasta el último decimal. Y ningún dato
			de las demás empresas influye en la nota de una: sin medias del sector ni comparaciones que se
			muevan.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Cuando la información deja de llegar</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Si los últimos meses traen mucha menos información de lo habitual, el mes se marca sin datos
			fiables: se mantiene la explicación del último mes sano, se apagan las alertas por ausencia y
			el mes se abstiene con su motivo a la vista. Falta de datos no es mal diagnóstico: cuando
			desaparecen, por ejemplo, los pagos a la Seguridad Social, el volumen se desploma aunque la
			empresa no haya dejado de pagar. El número no se cambia por esto.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">La tendencia se cuenta aparte</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			La dirección (mejora o deterioro), su naturaleza (bache puntual o cambio estructural) y el
			perímetro afectado se calculan fuera de la nota y siempre mirando al pasado: un veredicto no
			cambia cuando llegan meses nuevos. Si el cambio lo explica la entrada de una cuenta nueva, no
			se llama mejora ni deterioro: se llama cambio de perímetro.
		</p>
	</section>

	<section class="mt-10">
		<h2 class="text-xl font-bold tracking-tight">Cómo lo comprobamos</h2>
		<p class="mt-3 leading-relaxed text-muted-foreground">
			Sin verdad terrenal contra la que comparar, la fiabilidad se demuestra por construcción: las
			partes suman el total (comprobado fila a fila), el resultado no depende del orden ni del
			recorte de los datos, y las pruebas de placebo (fechas al azar, importes inflados) confirman
			que los criterios responden a patrones reales y no a la casualidad. Cada decisión y cada valor
			elegido está documentado, con su evidencia y su análisis de sensibilidad.
		</p>
		<p class="mt-3 text-sm">
			<a class="underline text-muted-foreground" href="/wiki/como-evaluamos"
				>Ver el protocolo de evaluación con resultados y objetivos</a
			>
		</p>
	</section>

	<footer class="mt-12 text-sm text-muted-foreground">
		Este resumen viene de la documentación interna del motor, donde cada constante y cada decisión
		están registradas con su evidencia. ¿Dudas sobre un dato concreto?
		<a class="underline" href="/wiki">Consulta la wiki</a>.
	</footer>
</main>
