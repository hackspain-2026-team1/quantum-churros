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
	import * as Tabs from '$lib/components/ui/tabs/index.js';
	import { Landmark, ShieldAlert, TrendingDown, Wallet } from '@lucide/svelte';
	import type { DemoOverview } from './demo-data.js';
	import {
		formatDays,
		formatEuroCompact,
		formatFeatureValue,
		formatNumber,
		formatPercent,
		formatSigned
	} from '$lib/format.js';
	import CompanyAvatar from './company-avatar.svelte';
	import DebtProductsPanel, { type DebtProduct } from './debt-products-panel.svelte';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let { demo, debtProducts = [] }: { demo: DemoOverview; debtProducts?: DebtProduct[] } = $props();
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
	let products = $derived.by(() => {
		const recs: {
			id: string;
			name: string;
			icon: typeof Landmark;
			why: string;
			impact: string;
			intent: 'danger' | 'warning' | 'neutral';
		}[] = [];
		const dsoSeries = demo.series?.collection_delay_days ?? [];
		const lastDso = dsoSeries.at(-1);
		if (lastDso !== undefined && lastDso >= 45) {
			recs.push({
				id: 'factoring',
				name: 'Factoring / Confirming',
				icon: Landmark,
				why: `Días de cobro en ${formatDays(lastDso)}. Anticipar facturas reduciría el capital inmovilizado en clientes.`,
				impact:
					snapshot.trend === 'deteriorating'
						? 'Alto · acelera caja y corta la fuga del score'
						: 'Medio · mejora DSO y liquidez',
				intent: snapshot.trend === 'deteriorating' ? 'danger' : 'warning'
			});
		}
		if (snapshot.forecast_delta < 0) {
			recs.push({
				id: 'credit-line',
				name: 'Línea de crédito flexible',
				icon: Wallet,
				why: `El modelo anticipa ${formatSigned(snapshot.forecast_delta)} puntos a tres meses. Una línea por debajo del coste del score cubre desfases de tesorería.`,
				impact: `Alto · amortigua hasta ${formatEuroCompact(Math.abs(snapshot.forecast_delta) * 8)} del daño previsto`,
				intent: 'danger'
			});
		}
		if (snapshot.persistence_months >= 3 && snapshot.forecast_delta < 0) {
			recs.push({
				id: 'credit-insurance',
				name: 'Seguro de crédito a clientes',
				icon: ShieldAlert,
				why: `${snapshot.persistence_months} cierres de deterioro sostenido. Cubre el impago de los principales counterparties que arrastra la señal.`,
				impact: 'Medio · protege el fondo, no el score',
				intent: 'warning'
			});
		}
		const invoiceSeries = demo.series?.invoice_amount ?? [];
		if (invoiceSeries.length >= 3) {
			const mean = invoiceSeries.reduce((a, b) => a + b, 0) / invoiceSeries.length;
			const spread =
				Math.max(...invoiceSeries.map((v) => Math.abs(v - mean))) / Math.max(1, Math.abs(mean));
			if (spread > 0.5) {
				recs.push({
					id: 'volatility',
					name: 'Cuenta de remunerada / sweep',
					icon: TrendingDown,
					why: `Facturación muy irregular entre cierres (${formatEuroCompact(Math.min(...invoiceSeries))} a ${formatEuroCompact(Math.max(...invoiceSeries))}). Un sweep suaviza los excedentes.`,
					impact: 'Bajo · estabiliza la travesía',
					intent: 'neutral'
				});
			}
		}
		if (recs.length === 0) {
			recs.push({
				id: 'none',
				name: 'Sin productos prioritarios',
				icon: Landmark,
				why: 'Las señales activas no activan ninguna recomendación de producto en este cierre.',
				impact: 'Sin impacto',
				intent: 'neutral'
			});
		}
		return recs;
	});
	let detectedLabel = $derived(
		snapshot.detected_since
			? new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric' }).format(
					new Date(snapshot.detected_since)
				)
			: 'este cierre'
	);
	const formatDriverValue = (feature: string, value: number) => formatFeatureValue(feature, value);
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
						{company.industry.industry_label}
					</Badge>
				{/if}
			</div>
		</div>
	</div>
	<p class="page-lead">El score separa el estado observado de la salud prevista a tres meses.</p>
	<Alert.Root class="border-[var(--warning)]/35 bg-[var(--warning-soft)]"
		><CalendarClock class="size-4" /><Alert.Title>Señal detectada desde {detectedLabel}</Alert.Title
		><Alert.Description
			>El modelo anticipa {formatSigned(snapshot.forecast_delta)} puntos a tres meses y acumula {snapshot.persistence_months}
			cierres de persistencia.</Alert.Description
		></Alert.Root
	>
	<Tabs.Root value="score" class="space-y-4">
		<Tabs.List>
			<Tabs.Trigger value="score">Score</Tabs.Trigger>
			<Tabs.Trigger value="metrics">Métricas</Tabs.Trigger>
			<Tabs.Trigger value="products">Productos</Tabs.Trigger>
		</Tabs.List>
		<Tabs.Content value="score" class="space-y-4">
			<div class="grid gap-4 lg:grid-cols-[17rem_1fr]">
				<Card.Root
					><Card.Header
						><Badge variant={snapshot.trend === 'deteriorating' ? 'destructive' : 'secondary'}>
							{#if snapshot.trend === 'improving'}<ArrowUpRight
								/>{:else if snapshot.trend === 'deteriorating'}<ArrowDownRight />{:else}<Minus
								/>{/if}
							{trendLabel}
						</Badge></Card.Header
					><Card.Content class="grid place-items-center gap-5"
						><ScoreGauge score={snapshot.score} delta={snapshot.delta} />
						<div class="grid w-full grid-cols-2 gap-3 border-t pt-4">
							<div>
								<span class="metric-label">Confianza</span><strong class="flex items-center gap-1"
									><ShieldCheck class="size-4 text-[var(--signal)]" />
									{formatPercent(snapshot.confidence, 0)}</strong
								>
							</div>
							<div>
								<span class="metric-label">Persistencia</span><strong class="font-data"
									>{snapshot.persistence_months} meses</strong
								>
							</div>
							<div>
								<span class="metric-label">Observado</span><strong class="font-data"
									>{formatNumber(snapshot.observed_score)}</strong
								>
							</div>
							<div>
								<span class="metric-label">Previsto · 3 meses</span><strong class="font-data"
									>{formatNumber(snapshot.predicted_future_score)}</strong
								>
							</div>
						</div></Card.Content
					></Card.Root
				>
				<Card.Root
					><Card.Header
						><Card.Description>Histórico completo</Card.Description><Card.Title
							>Estado actual y trayectoria anticipada</Card.Title
						></Card.Header
					><Card.Content><TrajectoryChart values={trajectory} months={seriesMonths} /></Card.Content
					></Card.Root
				>
			</div>
		</Tabs.Content>
		<Tabs.Content value="metrics" class="space-y-4">
			<Card.Root
				><Card.Header
					><Card.Description>Señales por cierre</Card.Description><Card.Title
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
			<div class="grid gap-3 lg:grid-cols-2">
				{#each snapshot.drivers as driver (driver.feature)}<Card.Root class="overflow-hidden"
						><Card.Header class="pb-3"
							><div class="flex items-start justify-between gap-4">
								<div>
									<Card.Description>Aportación SHAP · predicción a 3 meses</Card.Description
									><Card.Title class="text-base">{driver.label}</Card.Title>
								</div>
								<span
									class:positive={driver.contribution > 0}
									class:negative={driver.contribution < 0}
									class="font-data text-xl font-semibold">{formatSigned(driver.contribution)}</span
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
										>{formatDriverValue(driver.feature, driver.observed)}</strong
									>
								</div>
								<div>
									<span class="metric-label">Baseline</span><strong class="font-data"
										>{formatDriverValue(driver.feature, driver.baseline)}</strong
									>
								</div>
							</div>
							<p class="flex gap-2 text-sm leading-6 text-muted-foreground">
								<FileSearch class="mt-1 size-4 shrink-0" />{driver.evidence}
							</p></Card.Content
						></Card.Root
					>{/each}
			</div>
		</Tabs.Content>
		<Tabs.Content value="products" class="space-y-3">
			{#if debtProducts.length > 0}
				<DebtProductsPanel products={debtProducts} />
			{/if}
			<div class="grid gap-3 lg:grid-cols-2">
				{#each products as product (product.id)}<Card.Root
						><Card.Header class="pb-3"
							><div class="flex items-start justify-between gap-4">
								<div class="flex items-center gap-3">
									<span
										class="grid size-9 shrink-0 place-items-center rounded-lg"
										class:bg-[var(--danger-soft)]={product.intent === 'danger'}
										class:text-[var(--danger)]={product.intent === 'danger'}
										class:bg-[var(--warning-soft)]={product.intent === 'warning'}
										class:text-[var(--warning)]={product.intent === 'warning'}
										class:bg-muted={product.intent === 'neutral'}
										><product.icon class="size-4" /></span
									>
									<Card.Title class="text-base">{product.name}</Card.Title>
								</div>
								<Badge variant={product.intent === 'danger' ? 'destructive' : 'secondary'}
									>{product.impact}</Badge
								>
							</div></Card.Header
						><Card.Content
							><p class="text-sm leading-6 text-muted-foreground">{product.why}</p></Card.Content
						></Card.Root
					>{/each}
			</div>
		</Tabs.Content>
	</Tabs.Root>
</section>
