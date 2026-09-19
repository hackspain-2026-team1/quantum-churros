<script lang="ts">
	import { ArrowLeft, ArrowRight, CalendarOff, FileX, Landmark } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import {
		formatNumber,
		formatPeriod,
		formatScore,
		formatScoreDelta,
		humanizeMonths
	} from '$lib/format.js';
	import BandBadge from '$lib/xray/band-badge.svelte';
	import CompanyAvatar from '$lib/xray/company-avatar.svelte';
	import ContributionWaterfall from '$lib/xray/contribution-waterfall.svelte';
	import { fromTenths } from '$lib/xray/contract.js';
	import EmptyState from '$lib/xray/empty-state.svelte';
	import EntityTrajectory from '$lib/xray/entity-trajectory.svelte';
	import EvidenceTable from '$lib/xray/evidence-table.svelte';
	import { bandDomain, bandZones } from '$lib/xray/explain.js';
	import { glossaryText, pillarLabel } from '$lib/xray/labels.js';
	import MonthSlider from '$lib/xray/month-slider.svelte';
	import { monthStore } from '$lib/xray/month-store.svelte.js';
	import { entryAt } from '$lib/xray/month.js';
	import ProfileCard from '$lib/xray/profile-card.svelte';
	import ScoreCell from '$lib/xray/score-cell.svelte';
	import ScoreChanges from '$lib/xray/score-changes.svelte';
	import SectionNav from '$lib/xray/section-nav.svelte';
	import { BAND_TONE } from '$lib/xray/tones.js';
	import TrajectoryChart from '$lib/xray/trajectory-chart.svelte';
	import VerdictCard from '$lib/xray/verdict-card.svelte';

	let { data } = $props();

	const INHERITED_GATE = 'inherited_from_group';

	const group = $derived(data.group);
	const company = $derived(data.company);
	const summary = $derived(data.summary);
	const manifest = $derived(data.manifest);
	const entry = $derived(company ? entryAt(company.months, monthStore.month) : null);
	const groupEntry = $derived(entryAt(group.months, monthStore.month));
	const groupHref = $derived(monthStore.href(`/group/${group.id}`));
	// Fallback when companies/{id}.json is absent: shown and band align with group.months.
	const groupMonths = $derived(group.months.map((item) => item.month));
	const fallbackIndex = $derived(groupMonths.indexOf(monthStore.month));
	const fallbackScore = $derived(fallbackIndex < 0 ? null : summary.shown[fallbackIndex]);
	const fallbackBand = $derived(fallbackIndex < 0 ? null : summary.band[fallbackIndex]);
	// Same score axis as the full page: the band thresholds that enclose the history.
	const zones = $derived(bandZones(manifest.bands));
	const fallbackDomain = $derived(bandDomain(summary.shown, zones));
	const observed = $derived(company ? entry !== null : fallbackScore !== null);
	const lastMonth = $derived(
		company
			? company.months[company.months.length - 1].month
			: (groupMonths[summary.shown.findLastIndex((value) => value !== null)] ?? summary.first_month)
	);

	// Inherited liquidity is a fact of the selected month when the company file is there.
	const liquidity = $derived(entry?.pillars.find((pillar) => pillar.key === 'liquidity') ?? null);
	const inherits = $derived(
		liquidity ? liquidity.gates.includes(INHERITED_GATE) : summary.inherits_liquidity
	);
	const groupLiquidity = $derived(
		groupEntry?.pillars.find((pillar) => pillar.key === 'liquidity') ?? null
	);
	const sections = [
		{ id: 'veredicto', label: 'Veredicto' },
		{ id: 'desglose', label: 'De dónde sale' },
		{ id: 'evidencias', label: 'Evidencias' },
		{ id: 'ficha', label: 'Quién es' }
	];
</script>

<svelte:head><title>{summary.id} · {group.id} · Embat X-Ray</title></svelte:head>

<section class="space-y-5" aria-labelledby="company-heading">
	<Button href={groupHref} variant="ghost" size="sm" class="-ml-2" data-testid="back-to-group">
		<ArrowLeft /> Volver al grupo {group.id}
	</Button>
	<div class="grid gap-4 lg:grid-cols-[1fr_24rem] lg:items-end">
		<div class="flex items-start gap-3">
			<CompanyAvatar name={summary.role ?? summary.id} id={summary.id} class="mt-1 size-11" />
			<div class="min-w-0">
				<p class="eyebrow">
					Empresa del grupo {group.id} · con datos desde {formatPeriod(summary.first_month)}
				</p>
				<h1 id="company-heading" class="font-data">{summary.id}</h1>
				<ul class="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Papel en el grupo">
					{#if summary.role}
						<li><Badge variant="secondary" class="font-normal">{summary.role}</Badge></li>
					{/if}
					{#if summary.treasury_class && summary.treasury_class !== summary.role}
						<li>
							<Badge variant="secondary" class="font-normal"
								>Tesorería: {summary.treasury_class.toLowerCase()}</Badge
							>
						</li>
					{/if}
					{#if groupEntry}
						<li>
							<a
								href={groupHref}
								class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs text-muted-foreground hover:bg-muted"
							>
								Grupo {group.id}:
								<span class="font-data font-semibold text-foreground"
									>{formatScore(groupEntry.shown)}</span
								>
								<ArrowRight class="size-3" aria-hidden="true" />
							</a>
						</li>
					{/if}
				</ul>
			</div>
		</div>
		<MonthSlider />
	</div>

	{#if inherits || summary.truth}
		<Alert.Root
			class="border-[var(--signal)]/30 bg-[var(--signal-soft)]"
			data-testid="treasury-truth"
			data-inherits-liquidity={inherits}
		>
			<Landmark class="size-4" />
			<Alert.Title>
				{inherits
					? 'La liquidez de esta empresa es la del grupo'
					: 'Lectura de tesorería dentro del grupo'}
			</Alert.Title>
			<Alert.Description class="space-y-1.5 text-foreground/80">
				{#if summary.truth}<p>{humanizeMonths(summary.truth)}</p>{/if}
				{#if inherits}
					<p>
						{glossaryText(manifest, 'gates', INHERITED_GATE)}
						{#if liquidity && liquidity.score !== null && groupLiquidity?.score === liquidity.score}
							En {formatPeriod(monthStore.month)} el pilar de {pillarLabel(
								manifest,
								'liquidity'
							).toLowerCase()} marca {formatScore(liquidity.score)}, el mismo valor que en el grupo,
							y aporta {formatScoreDelta(liquidity.contrib)} puntos al score de esta empresa.
						{/if}
					</p>
					<p>
						<a href={`${groupHref}#desglose`} class="font-medium underline underline-offset-4"
							>Ver la liquidez en el grupo {group.id}</a
						>
					</p>
				{/if}
			</Alert.Description>
		</Alert.Root>
	{/if}

	{#if !observed}
		<EmptyState
			icon={CalendarOff}
			title={`Sin datos de esta empresa en ${formatPeriod(monthStore.month)}`}
			description={`El primer cierre observado de ${summary.id} es ${formatPeriod(summary.first_month)} y el último, ${formatPeriod(lastMonth)}.`}
		>
			<Button variant="outline" onclick={() => monthStore.select(summary.first_month)}>
				Ir a {formatPeriod(summary.first_month)}
			</Button>
			<Button variant="outline" onclick={() => monthStore.select(lastMonth)}>
				Ir al último cierre de la empresa
			</Button>
		</EmptyState>
	{:else if company && entry}
		<SectionNav {sections} />
		<div id="veredicto" class="grid scroll-mt-28 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
			<VerdictCard {entry} months={company.months} kind="company" profile={company.profile} />
			<div class="grid content-start gap-4">
				<EntityTrajectory
					months={company.months}
					series={company.series}
					alerts={company.alerts}
					month={entry.month}
				/>
				<ScoreChanges months={company.months} month={entry.month} />
			</div>
		</div>
		<div id="desglose" class="grid scroll-mt-28 gap-4 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
			<ContributionWaterfall {entry} />
			<div id="evidencias" class="scroll-mt-28">
				<EvidenceTable entityId={company.id} month={entry.month} kind="company" />
			</div>
		</div>
		<div id="ficha" class="scroll-mt-28">
			<ProfileCard profile={company.profile} context={company.context} kind="company" />
		</div>
	{:else}
		<div class="grid gap-4 xl:grid-cols-[20rem_1fr]">
			<Card.Root>
				<Card.Header>
					<Card.Description>Score · {formatPeriod(monthStore.month)}</Card.Description>
					<Card.Title><ScoreCell tenths={fallbackScore} size="xl" /></Card.Title>
				</Card.Header>
				<Card.Content><BandBadge band={fallbackBand} /></Card.Content>
			</Card.Root>
			<Card.Root>
				<Card.Header><Card.Title>Trayectoria mensual</Card.Title></Card.Header>
				<Card.Content>
					<TrajectoryChart
						values={summary.shown.map((value) => (value === null ? null : fromTenths(value)))}
						months={groupMonths}
						selectedIndex={fallbackIndex}
						metricLabel="Score"
						format={(value) => formatNumber(value, 1)}
						zones={zones.map((zone) => ({
							from: fromTenths(zone.min),
							to: fromTenths(zone.max),
							label: zone.label,
							tone: BAND_TONE[zone.key]
						}))}
						domain={[fromTenths(fallbackDomain.low), fromTenths(fallbackDomain.high)]}
						onSelect={(index) => monthStore.select(groupMonths[index])}
					/>
				</Card.Content>
			</Card.Root>
		</div>
		<EmptyState
			compact
			icon={FileX}
			title="Este bundle no incluye el detalle por empresa"
			description="El score y la banda vienen del fichero del grupo. El veredicto y los pilares de la empresa se muestran cuando la exportación incluye la carpeta de empresas."
		>
			<Button href={groupHref} variant="outline" size="sm">Volver al grupo {group.id}</Button>
		</EmptyState>
	{/if}
</section>
