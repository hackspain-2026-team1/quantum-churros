<script lang="ts">
	import {
		ArrowDownRight,
		ArrowUpRight,
		CalendarClock,
		FileSearch,
		Minus,
		ShieldCheck
	} from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import type { DemoOverview } from './demo-data.js';
	import { formatDays, formatEuroCompact, formatPercent } from '$lib/format.js';
	import CompanyAvatar from './company-avatar.svelte';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let { demo }: { demo: DemoOverview } = $props();
	let snapshot = $derived(demo.snapshot);
	let trajectory = $derived(demo.trajectory);
	let company = $derived(demo.companies.find((item) => item.id === snapshot.entity_id));
	let activeMetric = $state('health');
	let seriesMonths = $derived(demo.series?.months ?? demo.trajectory_months ?? []);
	let hasInvoices = $derived(
		(demo.series?.invoice_amount.length ?? 0) > 0 &&
			demo.series?.months.length === trajectory.length
	);
	let metrics = $derived.by(() => {
		const available: {
			value: string;
			label: string;
			unit?: string;
			format?: (value: number) => string;
		}[] = [{ value: 'health', label: 'Score de salud', unit: '' }];
		if (hasInvoices) {
			available.push(
				{ value: 'invoices', label: 'Facturas', format: formatEuroCompact },
				{ value: 'dso', label: 'DSO', unit: 'días', format: (value: number) => formatDays(value) }
			);
		}
		return available;
	});
	let activeValues = $derived.by(() => {
		if (!demo.series) return trajectory;
		if (activeMetric === 'invoices') return demo.series.invoice_amount;
		if (activeMetric === 'dso') return demo.series.collection_delay_days;
		return trajectory;
	});
	let metricTitle = $derived(
		activeMetric === 'invoices'
			? 'Facturación mensual'
			: activeMetric === 'dso'
				? 'Días de cobro (DSO)'
				: 'Estado actual y trayectoria anticipada'
	);
	let trendLabel = $derived(
		snapshot.trend === 'improving'
			? 'Mejora prevista'
			: snapshot.trend === 'deteriorating'
				? 'Deterioro previsto'
				: 'Trayectoria estable'
	);
	let detectedLabel = $derived(
		snapshot.detected_since
			? new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric' }).format(
					new Date(snapshot.detected_since)
				)
			: 'este cierre'
	);
</script>

<section class="space-y-5" aria-labelledby="diagnosis-heading">
	<div class="flex items-center gap-3">
		<CompanyAvatar name={company?.name ?? snapshot.entity_id} id={snapshot.entity_id} />
		<div>
			<p class="eyebrow">{snapshot.entity_id} · {company?.name ?? 'Empresa'}</p>
			<div class="flex flex-wrap items-center gap-2">
				<h1 id="diagnosis-heading">Diagnóstico explicable</h1>
				{#if company?.industry}
					<Badge variant="outline" title={company.industry.reason}>
						{company.industry.industry_label} · {formatPercent(company.industry.confidence)}
					</Badge>
				{/if}
			</div>
		</div>
	</div>
	<p class="page-lead">El score separa el estado observado de la salud prevista a tres meses.</p>
	<Alert.Root class="border-[var(--warning)]/35 bg-[var(--warning-soft)]"
		><CalendarClock class="size-4" /><Alert.Title>Señal detectada desde {detectedLabel}</Alert.Title
		><Alert.Description
			>El modelo anticipa {snapshot.forecast_delta > 0 ? '+' : ''}{snapshot.forecast_delta} puntos a tres
			meses y acumula {snapshot.persistence_months} cierres de persistencia.</Alert.Description
		></Alert.Root
	>
	<div class="grid gap-4 lg:grid-cols-[17rem_1fr]">
		<Card.Root
			><Card.Header
				><Badge variant={snapshot.trend === 'deteriorating' ? 'destructive' : 'secondary'}>
					{#if snapshot.trend === 'improving'}<ArrowUpRight
						/>{:else if snapshot.trend === 'deteriorating'}<ArrowDownRight />{:else}<Minus />{/if}
					{trendLabel}
				</Badge></Card.Header
			><Card.Content class="grid place-items-center gap-5"
				><ScoreGauge score={snapshot.score} delta={snapshot.delta} />
				<div class="grid w-full grid-cols-2 gap-3 border-t pt-4">
					<div>
						<span class="metric-label">Confianza</span><strong class="flex items-center gap-1"
							><ShieldCheck class="size-4 text-[var(--signal)]" />
							{Math.round(snapshot.confidence * 100)} %</strong
						>
					</div>
					<div>
						<span class="metric-label">Persistencia</span><strong class="font-data"
							>{snapshot.persistence_months} meses</strong
						>
					</div>
					<div>
						<span class="metric-label">Observado</span><strong class="font-data"
							>{snapshot.observed_score}</strong
						>
					</div>
					<div>
						<span class="metric-label">Previsto · 3 meses</span><strong class="font-data"
							>{snapshot.predicted_future_score}</strong
						>
					</div>
				</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Header
				><Card.Description>Histórico completo</Card.Description><Card.Title
					>{metricTitle}</Card.Title
				></Card.Header
			><Card.Content
				><TrajectoryChart
					values={activeValues}
					months={seriesMonths}
					{metrics}
					bind:activeMetric
				/></Card.Content
			></Card.Root
		>
	</div>
	<div class="grid gap-3 lg:grid-cols-2">
		{#each snapshot.drivers as driver (driver.feature)}<Card.Root class="overflow-hidden"
				><Card.Header class="pb-3"
					><div class="flex items-start justify-between gap-4">
						<div>
							<Card.Description>Aportación SHAP · predicción a 3 meses</Card.Description><Card.Title
								class="text-base">{driver.label}</Card.Title
							>
						</div>
						<span
							class:positive={driver.contribution > 0}
							class:negative={driver.contribution < 0}
							class="font-data text-xl font-semibold"
							>{driver.contribution > 0 ? '+' : ''}{driver.contribution}</span
						>
					</div></Card.Header
				><Card.Content class="space-y-3"
					><Progress
						value={Math.min(100, Math.abs(driver.contribution) * 11)}
						class={driver.contribution < 0
							? '[&_[data-slot=progress-indicator]]:bg-[var(--danger)]'
							: '[&_[data-slot=progress-indicator]]:bg-[var(--success)]'}
					/>
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div>
							<span class="metric-label">Observado</span><strong class="font-data"
								>{driver.observed}</strong
							>
						</div>
						<div>
							<span class="metric-label">Baseline</span><strong class="font-data"
								>{driver.baseline}</strong
							>
						</div>
					</div>
					<p class="flex gap-2 text-sm leading-6 text-muted-foreground">
						<FileSearch class="mt-1 size-4 shrink-0" />{driver.evidence}
					</p></Card.Content
				></Card.Root
			>{/each}
	</div>
</section>
