<script lang="ts">
	import { ArrowRight, FlaskConical, WandSparkles } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Slider } from '$lib/components/ui/slider/index.js';
	import type { ScenarioResult } from './demo-data.js';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let { trajectory }: { trajectory: number[] } = $props();
	let collection = $state(12);
	let refinance = $state(180);
	let extension = $state(7);
	let result = $state<ScenarioResult | null>(null);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let projectedScore = $derived(result?.projected_score ?? 68);
	let projectedCash = $derived(Math.round((result?.projected_cash ?? 0) / 1000));
	let projection = $derived([70, 72, 74, projectedScore]);
	let saved = $state(false);

	const calculate = async (
		persist = false,
		signal?: AbortSignal,
		assumptions = {
			collection_days: collection,
			refinance_amount: refinance * 1000,
			payment_extension_days: extension
		}
	) => {
		loading = true;
		error = null;
		try {
			const response = await fetch('/api/v1/scenarios', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ ...assumptions, persist }),
				signal
			});
			if (!response.ok) throw new Error('No se pudo calcular el escenario');
			result = (await response.json()) as ScenarioResult;
			if (persist) saved = true;
		} catch (reason) {
			if (reason instanceof DOMException && reason.name === 'AbortError') return;
			error = reason instanceof Error ? reason.message : 'No se pudo calcular el escenario';
		} finally {
			loading = false;
		}
	};

	$effect(() => {
		const assumptions = {
			collection_days: collection,
			refinance_amount: refinance * 1000,
			payment_extension_days: extension
		};
		const controller = new AbortController();
		const timeout = setTimeout(() => calculate(false, controller.signal, assumptions), 120);
		return () => {
			clearTimeout(timeout);
			controller.abort();
		};
	});
</script>

<section class="space-y-5" aria-labelledby="scenario-heading">
	<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
		<div>
			<p class="eyebrow">Velasco Industrial</p>
			<h1 id="scenario-heading">Laboratorio de escenarios</h1>
			<p class="page-lead">
				Mueve decisiones financieras; el histórico observado permanece intacto.
			</p>
		</div>
		<Badge variant="outline"
			><FlaskConical /> {loading ? 'Recalculando' : 'Proyección no aplicada'}</Badge
		>
	</div>
	<div class="grid gap-4 lg:grid-cols-[22rem_1fr]">
		<Card.Root
			><Card.Header
				><Card.Description>Palancas controlables</Card.Description><Card.Title
					>Recuperar margen de caja</Card.Title
				></Card.Header
			><Card.Content class="space-y-7"
				><div class="space-y-3">
					<div class="flex justify-between text-sm">
						<label for="collection">Acelerar cobros</label><strong class="font-data"
							>{collection} días</strong
						>
					</div>
					<Slider type="single" id="collection" bind:value={collection} min={0} max={30} step={1} />
				</div>
				<div class="space-y-3">
					<div class="flex justify-between text-sm">
						<label for="refinance">Refinanciar línea</label><strong class="font-data"
							>{refinance} k€</strong
						>
					</div>
					<Slider type="single" id="refinance" bind:value={refinance} min={0} max={500} step={10} />
				</div>
				<div class="space-y-3">
					<div class="flex justify-between text-sm">
						<label for="extension">Extender pagos no críticos</label><strong class="font-data"
							>{extension} días</strong
						>
					</div>
					<Slider type="single" id="extension" bind:value={extension} min={0} max={21} step={1} />
				</div>
				<Button class="w-full" disabled={loading} onclick={() => calculate(true)}
					><WandSparkles /> Convertir en plan</Button
				>{#if error}<p class="text-center text-sm font-medium text-[var(--danger)]">
						{error}
					</p>{/if}{#if saved}<p class="text-center text-sm font-medium text-[var(--success)]">
						Escenario guardado como plan de acción.
					</p>{/if}</Card.Content
			></Card.Root
		>
		<div class="space-y-4">
			<Card.Root
				><Card.Header
					><Card.Description>Impacto proyectado</Card.Description><Card.Title
						>La trayectoria recuperaría estabilidad</Card.Title
					></Card.Header
				><Card.Content
					><div class="mb-5 flex flex-wrap items-center justify-center gap-5">
						<ScoreGauge score={68} label="Observado" /><ArrowRight
							class="size-6 text-muted-foreground"
						/><ScoreGauge score={projectedScore} label="Proyectado" delta={projectedScore - 68} />
						<div class="min-w-36 border-l pl-5">
							<span class="metric-label">Caja a 90 días</span><strong
								class="font-data block text-3xl tracking-[-0.05em] text-[var(--success)]"
								>+{projectedCash} k€</strong
							><span class="text-xs text-muted-foreground">Rango estimado ±26 k€</span>
						</div>
					</div>
					<TrajectoryChart values={trajectory} projected={projection} compact /></Card.Content
				></Card.Root
			><Alert.Root
				><Alert.Title>Sensibilidad, no promesa</Alert.Title><Alert.Description
					>La proyección muestra cómo responde el modelo a estos supuestos. No sustituye una
					previsión contractual de caja.</Alert.Description
				></Alert.Root
			>
		</div>
	</div>
</section>
