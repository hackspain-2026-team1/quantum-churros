<script lang="ts">
	import {
		ArrowDownRight,
		ArrowUpRight,
		BellRing,
		ChevronRight,
		Minus,
		SearchX,
		TrendingDown
	} from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { formatNumber, formatPeriod, formatScore, formatScoreDelta } from '$lib/format.js';
	import CompanyAvatar from './company-avatar.svelte';
	import ConfidencePill from './confidence-pill.svelte';
	import { DIRECTION_TEXT, type Manifest, type Portfolio } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { bandLabel } from './labels.js';
	import MonthSlider from './month-slider.svelte';
	import { monthStore } from './month-store.svelte.js';
	import {
		DELTA_MONTHS,
		normalizeText,
		portfolioRows,
		summarize,
		type PortfolioRow
	} from './portfolio.js';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let {
		portfolio,
		manifest,
		rows,
		query,
		onAlerts
	}: {
		portfolio: Portfolio;
		manifest: Manifest;
		/** Groups of the selected month in priority order (lowest score first). */
		rows: PortfolioRow[];
		/** Text typed in the header search; filters the table too. */
		query: string;
		onAlerts: () => void;
	} = $props();

	const PAGE_SIZE = 25;
	let visible = $state(PAGE_SIZE);

	const summary = $derived(summarize(rows));
	// Median displayed score of the portfolio, month by month: the consolidated trajectory.
	const medians = $derived(
		portfolio.months.map((month) => summarize(portfolioRows(portfolio, month)).median)
	);
	const upTo = $derived(monthStore.index + 1);
	const trajectory = $derived(
		medians.slice(0, upTo).map((value) => (value === null ? null : value / 10))
	);
	const medianBefore = $derived(medians[monthStore.index - DELTA_MONTHS] ?? null);
	const medianDelta = $derived(
		summary.median === null || medianBefore === null ? null : (summary.median - medianBefore) / 10
	);
	const needle = $derived(normalizeText(query));
	const filtered = $derived(
		needle
			? rows.filter((row) =>
					normalizeText(
						`${row.id} ${row.group.industry ?? ''} ${row.group.country ?? ''}`
					).includes(needle)
				)
			: rows
	);
	const shownRows = $derived(filtered.slice(0, visible));
	const href = (row: PortfolioRow) => monthStore.href(`/group/${row.id}`);
	const signal = (row: PortfolioRow) =>
		!row.observed || row.band === null
			? 'Sin datos este mes'
			: row.abstained
				? `${bandLabel(manifest, row.band)} · sin veredicto`
				: `${bandLabel(manifest, row.band)} · ${DIRECTION_TEXT[row.direction ?? 'stable']}`;
	const isDanger = (row: PortfolioRow) =>
		row.band === 'critical' || (row.direction === 'deteriorating' && !row.abstained);
</script>

{#snippet delta(row: PortfolioRow)}
	{#if row.delta === null}
		<span class="text-sm text-muted-foreground">—</span>
	{:else}
		<span
			class:positive={row.delta > 0}
			class:negative={row.delta < -30}
			class="font-data inline-flex items-center gap-1 font-semibold"
			title={row.deltaFrom ? `Frente a ${formatPeriod(row.deltaFrom)}` : undefined}
			>{#if row.delta > 0}<ArrowUpRight class="size-4" />{:else if row.delta < 0}<ArrowDownRight
					class="size-4"
				/>{:else}<Minus class="size-4" />{/if}{formatScoreDelta(row.delta)}</span
		>
	{/if}
{/snippet}

<section class="space-y-5" aria-labelledby="radar-heading">
	<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
		<div>
			<p class="eyebrow">Cierre de {formatPeriod(monthStore.month)}</p>
			<h1 id="radar-heading">Radar financiero</h1>
			<p class="page-lead">
				Prioriza cambios estructurales antes de que el nivel actual los haga evidentes.
			</p>
		</div>
		<div class="flex flex-col gap-3 sm:flex-row sm:items-end">
			<MonthSlider class="sm:w-80" />
			<Button onclick={onAlerts}><BellRing /> Revisar {formatNumber(summary.fired)} alertas</Button>
		</div>
	</div>
	<div class="grid gap-4 md:grid-cols-3">
		<Card.Root class="md:col-span-1"
			><Card.Header
				><Card.Description>Salud de la cartera</Card.Description><Card.Title
					>{formatNumber(summary.scored)} grupos con score</Card.Title
				></Card.Header
			><Card.Content class="flex items-center justify-between gap-4"
				><ScoreGauge
					score={summary.median === null ? null : summary.median / 10}
					label="Mediana"
					delta={medianDelta}
				/>
				<div class="space-y-3 text-sm">
					<div>
						<span class="metric-label">En deterioro</span><strong
							class="negative flex items-center gap-1"
							><TrendingDown class="size-4" /> {formatNumber(summary.deteriorating)}</strong
						>
					</div>
					<div>
						<span class="metric-label">En mejora</span><strong
							class="positive flex items-center gap-1"
							><ArrowUpRight class="size-4" /> {formatNumber(summary.improving)}</strong
						>
					</div>
					<div>
						<span class="metric-label">Sin veredicto</span><strong class="font-data"
							>{formatNumber(summary.abstained)}</strong
						>
					</div>
				</div></Card.Content
			></Card.Root
		>
		<Card.Root class="md:col-span-2"
			><Card.Header class="flex-row items-start justify-between"
				><div>
					<Card.Description>Trayectoria consolidada</Card.Description><Card.Title
						>Mediana del score de la cartera</Card.Title
					>
				</div>
				<Badge variant="outline">{formatNumber(summary.total)} grupos</Badge></Card.Header
			><Card.Content
				><TrajectoryChart
					values={trajectory}
					months={portfolio.months.slice(0, upTo)}
					metricLabel="Mediana del score"
					format={(value) => formatNumber(value, 1)}
					compact
				/></Card.Content
			></Card.Root
		>
	</div>
	<Card.Root
		><Card.Header
			><Card.Description>Cartera priorizada</Card.Description><Card.Title
				>Grupos que requieren lectura</Card.Title
			></Card.Header
		><Card.Content class="px-0"
			>{#if filtered.length === 0}
				<EmptyState
					compact
					icon={SearchX}
					class="mx-6"
					title="Ningún grupo coincide con la búsqueda"
					description="Prueba con otro identificador, sector o país."
				/>
			{:else}
				<div class="divide-y md:hidden">
					{#each shownRows as row (row.id)}<a
							class="grid w-full grid-cols-[1fr_auto] gap-3 px-6 py-4 text-left"
							href={href(row)}
							><div class="flex items-start gap-3">
								<CompanyAvatar name={row.group.industry ?? row.id} id={row.id} />
								<div>
									<div class="font-data font-medium">{row.id}</div>
									<div class="mt-1 text-xs text-muted-foreground">
										{formatNumber(row.group.n_companies)}
										{row.group.n_companies === 1 ? 'empresa' : 'empresas'}
									</div>
									{#if row.group.industry}
										<Badge class="mt-2" variant="outline">{row.group.industry}</Badge>
									{/if}
									<Badge class="mt-3" variant={isDanger(row) ? 'destructive' : 'outline'}
										>{signal(row)}</Badge
									>
								</div>
							</div>
							<div class="text-right">
								<div class="font-data text-2xl font-semibold">
									{row.shown === null ? '—' : formatScore(row.shown)}
								</div>
								<div class="mt-2">{@render delta(row)}</div>
								{#if row.fired > 0}
									<div class="mt-2 text-xs text-muted-foreground">
										{formatNumber(row.fired)}
										{row.fired === 1 ? 'alerta' : 'alertas'}
									</div>
								{/if}
							</div></a
						>{/each}
				</div>
				<div class="hidden md:block">
					<Table.Root data-testid="radar-table"
						><Table.Header
							><Table.Row
								><Table.Head>Grupo</Table.Head><Table.Head>Sector</Table.Head><Table.Head
									>Score</Table.Head
								><Table.Head>Trayectoria</Table.Head><Table.Head>Señal</Table.Head><Table.Head
									>Confianza</Table.Head
								><Table.Head>Alertas</Table.Head><Table.Head
									><span class="sr-only">Abrir</span></Table.Head
								></Table.Row
							></Table.Header
						><Table.Body
							>{#each shownRows as row (row.id)}<Table.Row class="group" data-group={row.id}
									><Table.Cell
										><a class="flex items-center gap-3" href={href(row)}>
											<CompanyAvatar
												name={row.group.industry ?? row.id}
												id={row.id}
												class="size-8"
											/>
											<div>
												<div class="font-data font-medium">{row.id}</div>
												<div class="text-xs text-muted-foreground">
													{formatNumber(row.group.n_companies)}
													{row.group.n_companies === 1 ? 'empresa' : 'empresas'}
												</div>
											</div>
										</a></Table.Cell
									><Table.Cell
										>{#if row.group.industry}
											<Badge variant="outline">{row.group.industry}</Badge>
										{:else}
											<span class="text-sm text-muted-foreground">—</span>
										{/if}</Table.Cell
									><Table.Cell
										><span class="font-data text-xl font-semibold" data-testid="radar-score"
											>{row.shown === null ? '—' : formatScore(row.shown)}</span
										></Table.Cell
									><Table.Cell>{@render delta(row)}</Table.Cell><Table.Cell
										><Badge variant={isDanger(row) ? 'destructive' : 'outline'}>{signal(row)}</Badge
										></Table.Cell
									><Table.Cell><ConfidencePill label={row.conf} compact /></Table.Cell><Table.Cell
										class="font-data"
										>{row.fired > 0 ? formatNumber(row.fired) : '—'}{#if row.muted > 0}<span
												class="text-xs text-muted-foreground"
												title="Alertas que el motor decidió no disparar"
											>
												· {formatNumber(row.muted)} silenciadas</span
											>{/if}</Table.Cell
									><Table.Cell
										><Button
											variant="ghost"
											size="icon-sm"
											href={href(row)}
											aria-label={`Abrir ${row.id}`}><ChevronRight /></Button
										></Table.Cell
									></Table.Row
								>{/each}</Table.Body
						></Table.Root
					>
				</div>
				{#if filtered.length > visible}
					<div class="flex items-center justify-center gap-3 border-t px-6 pt-4">
						<span class="text-xs text-muted-foreground"
							>{formatNumber(visible)} de {formatNumber(filtered.length)} grupos</span
						>
						<Button variant="outline" size="sm" onclick={() => (visible += PAGE_SIZE * 2)}
							>Mostrar más</Button
						>
					</div>
				{/if}
			{/if}</Card.Content
		></Card.Root
	>
</section>
