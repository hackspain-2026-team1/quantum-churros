<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/state';
	import { RotateCw, TriangleAlert, ArrowLeft } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import DiagnosisView from '$lib/xray/diagnosis-view.svelte';
	import ScoreGauge from '$lib/xray/score-gauge.svelte';
	import TrajectoryChart from '$lib/xray/trajectory-chart.svelte';
	import type { DemoOverview, CompanySignal } from '$lib/xray/demo-data.js';

	const companyId = $derived((page.params.id ?? '').toUpperCase());
	let demo = $state<DemoOverview | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	const loadDemo = async () => {
		loading = true;
		error = null;
		try {
			const response = await fetch('/api/v1/demo');
			if (!response.ok) throw new Error(`La API respondió ${response.status}`);
			demo = (await response.json()) as DemoOverview;
		} catch (reason) {
			error = reason instanceof Error ? reason.message : 'No se pudo cargar la empresa';
		} finally {
			loading = false;
		}
	};

	const company = $derived(demo?.companies.find((item) => item.id === companyId));
	const hasDiagnosis = $derived(demo?.snapshot.entity_id === companyId);

	onMount(loadDemo);
</script>

<svelte:head>
	<title>{company ? `${company.name} · Embat X-Ray` : 'Empresa · Embat X-Ray'}</title>
</svelte:head>

{#if loading}
	<div class="mx-auto grid max-w-[1540px] gap-5 p-6">
		<Skeleton class="h-12 w-64" />
		<div class="grid gap-4 md:grid-cols-2">
			<Skeleton class="h-56" />
			<Skeleton class="h-56" />
		</div>
	</div>
{:else if error}
	<div class="grid min-h-screen place-items-center p-6">
		<Alert.Root variant="destructive" class="max-w-lg">
			<TriangleAlert class="size-4" />
			<Alert.Title>No se pudo cargar la empresa</Alert.Title>
			<Alert.Description class="space-y-4">
				<p>{error}</p>
				<Button variant="outline" onclick={loadDemo}><RotateCw /> Reintentar</Button>
			</Alert.Description>
		</Alert.Root>
	</div>
{:else if demo && company}
	<div class="mx-auto max-w-[1540px] space-y-5 px-4 py-6 lg:px-8 lg:py-8">
		<Button variant="ghost" size="sm" href="/"
			><ArrowLeft class="size-4" /> Volver al radar</Button
		>
		{#if hasDiagnosis}
			<DiagnosisView {demo} />
		{:else}
			{@const info: CompanySignal = company}
			<section class="space-y-5" aria-labelledby="company-heading">
				<div>
					<p class="eyebrow">{info.id}</p>
					<h1 id="company-heading" class="text-2xl font-semibold">{info.name}</h1>
				</div>
				<div class="grid gap-4 md:grid-cols-2">
					<Card.Root>
						<Card.Header>
							<Badge variant={info.intent === 'danger' ? 'destructive' : 'outline'}
								>{info.signal}</Badge
							>
						</Card.Header>
						<Card.Content class="grid place-items-center gap-5">
							<ScoreGauge score={info.score} delta={info.delta} />
							<div class="grid w-full grid-cols-2 gap-3 border-t pt-4">
								<div>
									<span class="metric-label">Confianza</span>
									<strong>{info.confidence}</strong>
								</div>
								<div>
									<span class="metric-label">Grupo</span>
									<strong>{demo.group.name}</strong>
								</div>
							</div>
						</Card.Content>
					</Card.Root>
					<Card.Root>
						<Card.Header>
							<Card.Description>Diagnóstico explicable</Card.Description>
							<Card.Title>Sin análisis completo para esta empresa</Card.Title>
						</Card.Header>
						<Card.Content class="space-y-4">
							<TrajectoryChart values={demo.trajectory} compact />
							<p class="text-sm leading-6 text-muted-foreground">
								El diagnóstico explicable aún no está disponible para esta empresa. El análisis
								detallado ahora mismo corresponde a {demo.snapshot.entity_id}.
							</p>
						</Card.Content>
					</Card.Root>
				</div>
			</section>
		{/if}
	</div>
{:else}
	<div class="grid min-h-screen place-items-center p-6">
		<Alert.Root class="max-w-lg">
			<TriangleAlert class="size-4" />
			<Alert.Title>Empresa no encontrada</Alert.Title>
			<Alert.Description>
				No existe la empresa {companyId} en este grupo.
			</Alert.Description>
		</Alert.Root>
	</div>
{/if}
