<script lang="ts">
	import { ArrowDownRight, ArrowUpRight, Minus, Target } from '@lucide/svelte';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatEuroCompact, formatNumber, formatScore } from '$lib/format.js';
	import ConfidencePill from './confidence-pill.svelte';
	import { DIRECTION_TEXT, NATURE_TEXT, type EntityMonth, type Series } from './contract.js';
	import { entitySeries } from './entity-series.js';
	import { bandLabel } from './labels.js';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let {
		entry,
		entries,
		series = [],
		targetTenths = null,
		targetLabel = 'Objetivo'
	}: {
		entry: EntityMonth;
		entries: readonly EntityMonth[];
		/** Extra monthly series of the entity, aligned with `entries`. */
		series?: Series[];
		/** Score the actions lead to, in tenths; drawn as a dashed target on the chart. */
		targetTenths?: number | null;
		targetLabel?: string;
	} = $props();

	const verdict = $derived(entry.verdict);
	const trajectory = $derived(entitySeries(entries, entry.month));
	const size = $derived(trajectory.months.length);
	let activeMetric = $state('score');
	// The score plus the first monthly series the engine exports for this entity.
	const extra = $derived(series.slice(0, 2));
	const metrics = $derived([
		{ value: 'score', label: 'Score de salud', format: (value: number) => formatNumber(value, 1) },
		...extra.map((item) => ({
			value: item.key,
			label: item.label,
			unit: item.unit === 'EUR' ? '' : item.unit,
			format:
				item.unit === 'EUR'
					? formatEuroCompact
					: (value: number) => `${formatNumber(value, 2)}\u00A0${item.unit}`
		}))
	]);
	const activeSeries = $derived(extra.find((item) => item.key === activeMetric));
	const values = $derived(activeSeries ? activeSeries.values.slice(0, size) : trajectory.values);
	const onScore = $derived(!activeSeries);
	// Engine scenarios of the score three months ahead; the other metrics have none.
	const scenario = $derived(
		onScore && entry.outlook
			? {
					best: entry.outlook.best / 10,
					common: entry.outlook.common / 10,
					worst: entry.outlook.worst / 10
				}
			: null
	);
	const trendLabel = $derived(
		!verdict.available
			? 'Sin veredicto este mes'
			: `${DIRECTION_TEXT[verdict.direction]}${verdict.nature ? ` · ${NATURE_TEXT[verdict.nature].toLowerCase()}` : ''}`
	);
</script>

<div class="grid gap-4 lg:grid-cols-[17rem_1fr]" data-testid="entity-hero">
	<Card.Root
		><Card.Header
			><Badge variant={verdict.direction === 'deteriorating' ? 'destructive' : 'secondary'}>
				{#if verdict.direction === 'improving'}<ArrowUpRight
					/>{:else if verdict.direction === 'deteriorating'}<ArrowDownRight />{:else}<Minus />{/if}
				{trendLabel}
			</Badge></Card.Header
		><Card.Content class="grid place-items-center gap-5"
			><ScoreGauge
				score={entry.shown / 10}
				delta={verdict.delta3 === null ? null : verdict.delta3 / 10}
			/>
			<div class="grid w-full grid-cols-2 gap-3 border-t pt-4">
				<div>
					<span class="metric-label">Confianza</span><ConfidencePill
						label={entry.conf.label}
						value={entry.conf.value}
						compact
					/>
				</div>
				<div>
					<span class="metric-label">Banda</span><strong
						>{bandLabel(page.data.manifest, entry.band)}</strong
					>
				</div>
				<div>
					<span class="metric-label">Persistencia</span><strong class="font-data"
						>{formatNumber(verdict.persistence_months)}
						{verdict.persistence_months === 1 ? 'mes' : 'meses'}</strong
					>
				</div>
				<div>
					<span class="metric-label">Con acciones</span><strong
						class="font-data flex items-center gap-1"
						class:text-[var(--success-strong)]={targetTenths !== null}
						data-testid="hero-target"
						>{#if targetTenths !== null}<Target class="size-4" />{formatScore(
								targetTenths
							)}{:else}—{/if}</strong
					>
				</div>
			</div></Card.Content
		></Card.Root
	>
	<Card.Root
		><Card.Header
			><Card.Description>Histórico completo</Card.Description><Card.Title
				>{onScore
					? targetTenths !== null
						? 'Trayectoria del score y objetivo con acciones'
						: 'Trayectoria del score'
					: activeSeries?.label}</Card.Title
			></Card.Header
		><Card.Content
			><TrajectoryChart
				{values}
				months={trajectory.months}
				changeIndex={onScore ? trajectory.changeIndex : null}
				projected={onScore && targetTenths !== null ? [targetTenths / 10] : []}
				projectedLabel={targetLabel}
				{metrics}
				{scenario}
				bind:activeMetric
			/></Card.Content
		></Card.Root
	>
</div>
