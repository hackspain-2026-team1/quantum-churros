<script lang="ts">
	import {
		ArrowDown,
		ArrowDownRight,
		ArrowUp,
		ArrowUpDown,
		ArrowUpRight,
		BellOff,
		BellRing,
		ChevronRight,
		ChevronsUpDown,
		Combine,
		FilterX,
		PackageOpen,
		SearchX,
		Search
	} from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { Toggle } from '$lib/components/ui/toggle/index.js';
	import * as ToggleGroup from '$lib/components/ui/toggle-group/index.js';
	import {
		formatNumber,
		formatPeriod,
		formatPeriodShort,
		formatScore,
		formatScoreDelta
	} from '$lib/format.js';
	import { IsMobile } from '$lib/hooks/is-mobile.svelte.js';
	import { cn } from '$lib/utils.js';
	import BandBadge from './band-badge.svelte';
	import BandDistribution from './band-distribution.svelte';
	import CompanyAvatar from './company-avatar.svelte';
	import ConfidencePill from './confidence-pill.svelte';
	import {
		BAND_KEYS,
		DIRECTION_TEXT,
		NATURE_TEXT,
		type Manifest,
		type Portfolio
	} from './contract.js';
	import DirectionChip from './direction-chip.svelte';
	import EmptyState from './empty-state.svelte';
	import { bandLabel, glossaryText } from './labels.js';
	import MonthSlider from './month-slider.svelte';
	import { monthStore } from './month-store.svelte.js';
	import { monthIndex } from './month.js';
	import { portfolioView as view } from './portfolio-state.svelte.js';
	import {
		DELTA_MONTHS,
		closingNotes,
		countryName,
		filterRows,
		portfolioRows,
		sortRows,
		summarize,
		type BandFilter,
		type ClosingNote,
		type DirectionFilter,
		type PortfolioRow,
		type SortDir,
		type SortKey
	} from './portfolio.js';
	import ScoreCell from './score-cell.svelte';
	import ScoreSparkline from './score-sparkline.svelte';
	import StatTile from './stat-tile.svelte';
	import { TONE_TEXT } from './tones.js';

	let { portfolio, manifest }: { portfolio: Portfolio; manifest: Manifest } = $props();

	const isMobile = new IsMobile();

	const month = $derived(monthStore.month);
	const period = $derived(month ? formatPeriod(month) : '');
	const selectedIndex = $derived(monthIndex(portfolio.months, month));

	// One row per group at the selected month; every KPI below is a count over these rows.
	const rows = $derived(portfolioRows(portfolio, month));
	const summary = $derived(summarize(rows));
	const notes = $derived(closingNotes(rows));
	const visible = $derived(sortRows(filterRows(rows, view.filters), view.sortKey, view.sortDir));

	const plural = (count: number, one: string, many: string) =>
		`${formatNumber(count)} ${count === 1 ? one : many}`;
	const groupHref = (id: string) => monthStore.href(`/group/${id}`);
	const perimeterText = $derived(glossaryText(manifest, 'flags', 'perimeter_changed'));

	const directionOptions: { value: DirectionFilter; label: string }[] = [
		{ value: 'all', label: 'Todas las direcciones' },
		{ value: 'deteriorating', label: DIRECTION_TEXT.deteriorating },
		{ value: 'improving', label: DIRECTION_TEXT.improving },
		{ value: 'stable', label: DIRECTION_TEXT.stable },
		{ value: 'perimeter_shift', label: DIRECTION_TEXT.perimeter_shift },
		{ value: 'abstained', label: 'En abstención' }
	];
	const directionLabel = $derived(
		directionOptions.find((option) => option.value === view.direction)?.label ?? ''
	);

	const sortOptions: { value: `${SortKey}:${SortDir}`; label: string }[] = [
		{ value: 'shown:asc', label: 'Score, de menor a mayor' },
		{ value: 'shown:desc', label: 'Score, de mayor a menor' },
		{ value: 'delta:asc', label: `Mayor caída a ${DELTA_MONTHS} meses` },
		{ value: 'delta:desc', label: `Mayor subida a ${DELTA_MONTHS} meses` },
		{ value: 'move:desc', label: 'Mayores movimientos' },
		{ value: 'conf:asc', label: 'Confianza, de menor a mayor' },
		{ value: 'conf:desc', label: 'Confianza, de mayor a menor' },
		{ value: 'alerts:desc', label: 'Más alertas en el mes' },
		{ value: 'alerts:asc', label: 'Menos alertas en el mes' },
		{ value: 'companies:desc', label: 'Más empresas' },
		{ value: 'companies:asc', label: 'Menos empresas' },
		{ value: 'id:asc', label: 'Identificador, A-Z' },
		{ value: 'id:desc', label: 'Identificador, Z-A' }
	];
	const sortValue = $derived(`${view.sortKey}:${view.sortDir}`);
	const sortLabel = $derived(sortOptions.find((option) => option.value === sortValue)?.label ?? '');
	function applySort(value: string) {
		const [key, dir] = value.split(':') as [SortKey, SortDir];
		if (key === 'move') view.movers = true;
		else view.setSort(key, dir);
	}
	const ariaSort = (key: SortKey) =>
		view.sortKey !== key ? 'none' : view.sortDir === 'asc' ? 'ascending' : 'descending';

	function openRow(event: MouseEvent, id: string) {
		const target = event.target as HTMLElement | null;
		if (target?.closest('a, button')) return;
		if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
		void goto(groupHref(id));
	}

	const contextLine = (row: PortfolioRow) =>
		[row.group.size_band, countryName(row.group.country)].filter(Boolean).join(' · ');

	const noteTitle: Record<ClosingNote['kind'], string> = {
		fall: `Mayor caída a ${DELTA_MONTHS} meses`,
		no_fall: 'Sin deterioros',
		lowest: 'Score más bajo con veredicto',
		perimeter: 'Cambio de perímetro',
		rise: `Mayor mejora a ${DELTA_MONTHS} meses`,
		abstained: 'En abstención'
	};
	const andOthers = (others: number) =>
		others > 0 ? ` y ${plural(others, 'grupo más', 'grupos más')}` : '';
	/** Sentence that follows the group id in a closing note. */
	function noteText(note: ClosingNote): string {
		const row = note.row;
		if (!row) return '';
		const direction = row.direction ? DIRECTION_TEXT[row.direction] : '';
		if (note.kind === 'fall' || note.kind === 'rise') {
			const versus = row.deltaFrom ? ` frente a ${formatPeriod(row.deltaFrom)}` : '';
			// 'Deterioro estructural', but 'Deterioro: shock por confirmar' and 'Mejora: bache'.
			const label = row.nature ? NATURE_TEXT[row.nature].toLowerCase() : '';
			const nature = label ? (row.nature === 'structural' ? ` ${label}` : `: ${label}`) : '';
			return `: ${formatScoreDelta(row.delta ?? 0)} puntos${versus}. ${direction}${nature}.`;
		}
		if (note.kind === 'lowest') {
			const parts = [
				row.shown === null ? '—' : formatScore(row.shown),
				row.band ? bandLabel(manifest, row.band) : '',
				direction.toLowerCase()
			];
			return `: ${parts.filter(Boolean).join(' · ')}.`;
		}
		if (note.kind === 'perimeter') {
			return `${andOthers(note.others)}: el salto del score refleja el perímetro nuevo, no un deterioro.`;
		}
		return `${andOthers(note.others)}: se enseña el número, no se disparan alertas.`;
	}

	const scoredHints = $derived(
		[
			`de ${plural(summary.total, 'grupo', 'grupos')}`,
			summary.median === null ? '' : `mediana ${formatScore(summary.median)}`,
			summary.unobserved > 0 ? `${formatNumber(summary.unobserved)} sin datos aún` : ''
		].filter(Boolean)
	);
	const lead = $derived(
		[
			`Con score en este cierre: ${formatNumber(summary.scored)} de ${plural(summary.total, 'grupo', 'grupos')}.`,
			`En deterioro ${formatNumber(summary.deteriorating)}${
				summary.deterioratingStructural > 0
					? ` (${formatNumber(summary.deterioratingStructural)} estructural)`
					: ''
			}, en mejora ${formatNumber(summary.improving)}, con cambio de perímetro ${formatNumber(
				summary.perimeterShift
			)} y en abstención ${formatNumber(summary.abstained)}.`,
			`Alertas del mes: ${plural(summary.fired, 'activa', 'activas')} y ${formatNumber(
				summary.muted
			)} sin disparar (silenciadas o en abstención).`
		].join(' ')
	);
</script>

{#snippet sortHead(
	key: SortKey,
	label: string,
	options: { right?: boolean; title?: string; class?: string } = {}
)}
	{@const active = view.sortKey === key}
	<Table.Head aria-sort={ariaSort(key)} class={cn(options.right && 'text-right', options.class)}>
		<button
			type="button"
			class={cn(
				'-mx-1.5 inline-flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-muted',
				active && 'text-[var(--signal-strong)]'
			)}
			title={options.title}
			onclick={() => view.sortBy(key)}
		>
			{label}
			{#if !active}
				<ChevronsUpDown class="size-3.5 text-muted-foreground/70" aria-hidden="true" />
			{:else if view.sortDir === 'asc'}
				<ArrowUp class="size-3.5" aria-hidden="true" />
			{:else}
				<ArrowDown class="size-3.5" aria-hidden="true" />
			{/if}
		</button>
	</Table.Head>
{/snippet}

{#snippet deltaCell(row: PortfolioRow, stacked: boolean)}
	{#if row.delta === null}
		<span class="text-sm text-muted-foreground" aria-label="Sin variación calculable">—</span>
	{:else}
		{@const Icon = row.delta > 0 ? ArrowUpRight : row.delta < 0 ? ArrowDownRight : null}
		<span
			class={cn('inline-flex items-center gap-1', stacked && 'flex-col items-end gap-0')}
			title={row.deltaFrom
				? `Score de ${period} menos score de ${formatPeriod(row.deltaFrom)}`
				: undefined}
			data-delta-tenths={row.delta}
		>
			<span class="font-data inline-flex items-center gap-1 text-sm font-semibold tabular-nums">
				{#if Icon}
					<Icon
						class={cn('size-3.5', row.delta > 0 ? TONE_TEXT.success : TONE_TEXT.danger)}
						aria-hidden="true"
					/>
				{/if}
				{formatScoreDelta(row.delta)}
			</span>
			{#if row.deltaFrom}
				<span class="text-[0.68rem] text-muted-foreground"
					>vs. {formatPeriodShort(row.deltaFrom)}</span
				>
			{/if}
		</span>
	{/if}
{/snippet}

{#snippet perimeterDot(row: PortfolioRow)}
	{#if row.perimeterChanged}
		<span
			class="inline-flex items-center gap-1 rounded-full border border-[var(--signal)]/30 bg-[var(--signal-soft)] px-1.5 py-0.5 text-[0.65rem] font-medium text-[var(--signal-strong)]"
			title={perimeterText}
			data-perimeter-changed
		>
			<Combine class="size-3" aria-hidden="true" /> Perímetro
		</span>
	{/if}
{/snippet}

{#snippet alertCounts(row: PortfolioRow)}
	<span class="font-data inline-flex items-center gap-3 text-sm">
		<span
			class={cn('inline-flex items-center gap-1', row.fired === 0 && 'text-muted-foreground')}
			title="Alertas activas del grupo y sus empresas este mes"
		>
			<BellRing class="size-3.5" aria-hidden="true" /><span class="sr-only">Activas:</span>
			{formatNumber(row.fired)}
		</span>
		<span
			class="inline-flex items-center gap-1 text-muted-foreground"
			title="Alertas silenciadas o en abstención este mes"
		>
			<BellOff class="size-3.5" aria-hidden="true" /><span class="sr-only">Sin disparar:</span>
			{formatNumber(row.muted)}
		</span>
	</span>
{/snippet}

<section class="space-y-5" aria-labelledby="portfolio-heading">
	<div class="grid gap-4 lg:grid-cols-[1fr_24rem] lg:items-end">
		<div>
			<p class="eyebrow">Cierre de {period}</p>
			<h1 id="portfolio-heading">Cartera de grupos</h1>
			<p class="page-lead" data-testid="portfolio-lead">{lead}</p>
		</div>
		<MonthSlider />
	</div>

	{#if portfolio.groups.length === 0}
		<EmptyState
			icon={PackageOpen}
			title="El bundle no contiene grupos"
			description="Exporta el motor sobre un dataset con al menos un grupo para ver la cartera."
		/>
	{:else}
		<div
			class="grid grid-cols-2 gap-3 md:grid-cols-12 xl:grid-cols-[minmax(21rem,2fr)_repeat(5,minmax(0,1fr))]"
			aria-label={`Indicadores de la cartera en ${period}`}
			role="group"
		>
			<StatTile
				class="col-span-2 md:col-span-8 xl:col-span-1"
				label="Grupos con score"
				value={formatNumber(summary.scored)}
				hints={scoredHints}
				kpi="scored"
			>
				<BandDistribution
					bands={summary.bands}
					active={view.band}
					onToggle={(band) => view.toggleBand(band)}
				/>
			</StatTile>
			<StatTile
				class="md:order-3 md:col-span-3 xl:order-none xl:col-span-1"
				label="En deterioro"
				tone="danger"
				value={formatNumber(summary.deteriorating)}
				hints={[
					`${formatNumber(summary.deterioratingStructural)} estructural`,
					`${formatNumber(summary.deterioratingPending)} por confirmar`
				]}
				pressed={view.direction === 'deteriorating'}
				onclick={() => view.toggleDirection('deteriorating')}
				kpi="deteriorating"
			/>
			<StatTile
				class="md:order-3 md:col-span-3 xl:order-none xl:col-span-1"
				label="En mejora"
				tone="success"
				value={formatNumber(summary.improving)}
				hints={[`${formatNumber(summary.improvingStructural)} estructural`]}
				pressed={view.direction === 'improving'}
				onclick={() => view.toggleDirection('improving')}
				kpi="improving"
			/>
			<StatTile
				class="md:order-3 md:col-span-3 xl:order-none xl:col-span-1"
				label="Perímetro"
				tone="signal"
				value={formatNumber(summary.perimeterShift)}
				hints={['cambio de perímetro', 'el salto no es deterioro']}
				pressed={view.direction === 'perimeter_shift'}
				onclick={() => view.toggleDirection('perimeter_shift')}
				kpi="perimeter"
			/>
			<StatTile
				class="md:order-3 md:col-span-3 xl:order-none xl:col-span-1"
				label="En abstención"
				tone="warning"
				value={formatNumber(summary.abstained)}
				hints={['número visible, alertas en pausa']}
				pressed={view.direction === 'abstained'}
				onclick={() => view.toggleDirection('abstained')}
				kpi="abstained"
			/>
			<StatTile
				label="Alertas activas"
				icon={BellRing}
				value={formatNumber(summary.fired)}
				hints={[`${formatNumber(summary.muted)} sin disparar`, 'ver la bandeja del mes']}
				href={monthStore.href('/alerts?ver=mes')}
				class="col-span-2 md:order-2 md:col-span-4 xl:order-none xl:col-span-1"
				kpi="alerts"
			/>
		</div>

		{#if notes.length > 0}
			<ul
				class="grid gap-3 md:auto-cols-fr md:grid-flow-col"
				aria-label={`Lectura del cierre de ${period}`}
				data-testid="closing-notes"
			>
				{#each notes as note (note.kind)}
					<li class="min-w-0">
						{#if note.row}
							{@const row = note.row}
							<a
								href={groupHref(row.id)}
								class="group/note flex h-full items-start justify-between gap-3 rounded-xl border border-dashed bg-card/60 px-4 py-3 transition-colors hover:border-[var(--signal)]/50 hover:bg-card"
								data-note={note.kind}
							>
								<span class="min-w-0">
									<span class="metric-label">{noteTitle[note.kind]}</span>
									<span class="block text-sm leading-6">
										<span class="font-data font-semibold">{row.id}</span>{noteText(note)}
									</span>
								</span>
								<ChevronRight
									class="mt-1 size-4 shrink-0 text-muted-foreground transition-transform group-hover/note:translate-x-0.5"
									aria-hidden="true"
								/>
							</a>
						{:else}
							<div
								class="h-full rounded-xl border border-dashed bg-card/60 px-4 py-3"
								data-note={note.kind}
							>
								<span class="metric-label">{noteTitle[note.kind]}</span>
								<span class="block text-sm leading-6"
									>Ningún grupo con veredicto está en deterioro en {period}.</span
								>
							</div>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}

		<Card.Root>
			<Card.Header class="gap-4">
				<div class="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
					<div>
						<Card.Description>
							{sortLabel}
							· {formatNumber(visible.length)} de {plural(rows.length, 'grupo', 'grupos')}
						</Card.Description>
						<Card.Title>Grupos que requieren lectura</Card.Title>
					</div>
					{#if view.filtered}
						<Button variant="ghost" size="sm" onclick={() => view.clearFilters()}>
							<FilterX /> Limpiar filtros
						</Button>
					{/if}
				</div>
				<div
					class="flex min-w-0 flex-wrap items-center gap-2"
					role="group"
					aria-label="Filtros de la tabla"
				>
					<div class="relative min-w-52 flex-1 basis-60">
						<Search
							class="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
							aria-hidden="true"
						/>
						<Input
							class="pl-9"
							type="search"
							placeholder="Buscar grupo, sector, tamaño o país"
							aria-label="Buscar grupo, sector, tamaño o país"
							autocomplete="off"
							bind:value={view.query}
						/>
					</div>
					<div class="max-w-full overflow-x-auto py-0.5">
						<ToggleGroup.Root
							type="single"
							variant="outline"
							size="sm"
							value={view.band}
							onValueChange={(value) => (view.band = (value || 'all') as BandFilter)}
							aria-label="Filtrar por banda"
						>
							<ToggleGroup.Item value="all" class="flex-none px-3">Todas</ToggleGroup.Item>
							{#each BAND_KEYS as key (key)}
								<ToggleGroup.Item value={key} class="flex-none px-3"
									>{bandLabel(manifest, key)}</ToggleGroup.Item
								>
							{/each}
						</ToggleGroup.Root>
					</div>
					<Select.Root
						type="single"
						value={view.direction}
						onValueChange={(value) => (view.direction = (value || 'all') as DirectionFilter)}
					>
						<Select.Trigger size="sm" class="w-52" aria-label="Filtrar por dirección"
							>{directionLabel}</Select.Trigger
						>
						<Select.Content>
							{#each directionOptions as option (option.value)}
								<Select.Item value={option.value} label={option.label} />
							{/each}
						</Select.Content>
					</Select.Root>
					<Toggle
						variant="outline"
						size="sm"
						class="px-3 data-[state=on]:border-[var(--signal)]/50 data-[state=on]:bg-[var(--signal-soft)] data-[state=on]:text-[var(--signal-strong)]"
						bind:pressed={view.movers}
						title={`Ordena por el tamaño de la variación a ${DELTA_MONTHS} meses, suba o baje`}
					>
						<ArrowUpDown /> Mayores movimientos
					</Toggle>
					<Select.Root type="single" value={sortValue} onValueChange={applySort}>
						<Select.Trigger size="sm" class="w-full md:hidden" aria-label="Ordenar"
							>{sortLabel}</Select.Trigger
						>
						<Select.Content>
							{#each sortOptions as option (option.value)}
								<Select.Item value={option.value} label={option.label} />
							{/each}
						</Select.Content>
					</Select.Root>
				</div>
			</Card.Header>
			<Card.Content class="px-0">
				{#if visible.length === 0}
					<div class="px-6">
						<EmptyState
							compact
							icon={SearchX}
							title="Ningún grupo coincide con los filtros"
							description="Prueba con otro identificador, sector o banda, o limpia los filtros."
						>
							<Button variant="outline" size="sm" onclick={() => view.clearFilters()}>
								<FilterX /> Limpiar filtros
							</Button>
						</EmptyState>
					</div>
				{:else if isMobile.current}
					<ul class="divide-y border-t">
						{#each visible as row (row.id)}
							<li data-group={row.id}>
								<a href={groupHref(row.id)} class="grid gap-3 px-5 py-4">
									<span class="flex items-start justify-between gap-3">
										<span class="flex min-w-0 items-start gap-3">
											<CompanyAvatar name={row.group.industry ?? row.id} id={row.id} />
											<span class="min-w-0">
												<span class="font-data block font-medium break-all">{row.id}</span>
												<span class="block text-xs leading-5 text-muted-foreground">
													{row.group.industry ?? 'Sector sin clasificar'} · {plural(
														row.group.n_companies,
														'empresa',
														'empresas'
													)}
												</span>
												{#if !row.observed}
													<span class="block text-xs leading-5 text-muted-foreground"
														>Primer cierre: {formatPeriod(row.group.first_month)}</span
													>
												{/if}
											</span>
										</span>
										<span class="shrink-0 text-right">
											<ScoreCell tenths={row.shown} muted={row.abstained} />
											<span class="mt-1 block">{@render deltaCell(row, false)}</span>
										</span>
									</span>
									{#if row.observed}
										<span class="flex flex-wrap items-center gap-1">
											<BandBadge band={row.band} />
											<DirectionChip
												direction={row.direction}
												nature={row.nature}
												available={!row.abstained}
											/>
											<ConfidencePill label={row.conf} />
											{@render perimeterDot(row)}
										</span>
										<span class="flex items-center justify-between gap-3">
											<ScoreSparkline
												values={row.group.shown}
												months={portfolio.months}
												{selectedIndex}
												band={row.band}
												marks={row.perimeterMonths}
											/>
											{@render alertCounts(row)}
										</span>
									{/if}
								</a>
							</li>
						{/each}
					</ul>
				{:else}
					<Table.Root>
						<Table.Header>
							<Table.Row class="hover:[&>th]:bg-transparent">
								{@render sortHead('id', 'Grupo', { class: 'pl-6' })}
								<Table.Head class="hidden xl:table-cell">Contexto</Table.Head>
								{@render sortHead('shown', 'Score', { right: true })}
								<Table.Head>Banda</Table.Head>
								<Table.Head>Dirección</Table.Head>
								{@render sortHead('delta', `Δ ${DELTA_MONTHS} meses`, {
									right: true,
									title: `Score del mes menos el score de ${DELTA_MONTHS} meses antes`
								})}
								{@render sortHead('conf', 'Confianza')}
								<Table.Head>Trayectoria</Table.Head>
								{@render sortHead('alerts', 'Alertas')}
								<Table.Head class="pr-6"><span class="sr-only">Abrir</span></Table.Head>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{#each visible as row (row.id)}
								<Table.Row
									class={cn('group cursor-pointer', !row.observed && 'text-muted-foreground')}
									data-group={row.id}
									onclick={(event: MouseEvent) => openRow(event, row.id)}
								>
									<Table.Cell class="pl-6">
										<a href={groupHref(row.id)} class="flex items-center gap-3 rounded-md">
											<CompanyAvatar
												name={row.group.industry ?? row.id}
												id={row.id}
												class="size-8"
											/>
											<span class="min-w-0">
												<span class="flex items-center gap-2">
													<span class="font-data font-medium group-hover:underline">{row.id}</span>
													{@render perimeterDot(row)}
												</span>
												<span class="block text-xs text-muted-foreground">
													{plural(row.group.n_companies, 'empresa', 'empresas')}
													<span class="xl:hidden">
														· {row.group.industry ?? 'Sector sin clasificar'}</span
													>
													{#if !row.observed}
														· primer cierre en {formatPeriod(row.group.first_month)}
													{/if}
												</span>
											</span>
										</a>
									</Table.Cell>
									<Table.Cell class="hidden max-w-64 xl:table-cell">
										<span class="block truncate"
											>{row.group.industry ?? 'Sector sin clasificar'}</span
										>
										<span class="block truncate text-xs text-muted-foreground"
											>{contextLine(row) || '—'}</span
										>
									</Table.Cell>
									<Table.Cell class="text-right">
										<ScoreCell tenths={row.shown} muted={row.abstained} />
									</Table.Cell>
									<Table.Cell><BandBadge band={row.band} /></Table.Cell>
									<Table.Cell>
										<DirectionChip
											direction={row.direction}
											nature={row.nature}
											available={!row.abstained}
										/>
									</Table.Cell>
									<Table.Cell class="text-right">{@render deltaCell(row, true)}</Table.Cell>
									<Table.Cell><ConfidencePill label={row.conf} compact /></Table.Cell>
									<Table.Cell>
										<ScoreSparkline
											values={row.group.shown}
											months={portfolio.months}
											{selectedIndex}
											band={row.band}
											marks={row.perimeterMonths}
										/>
									</Table.Cell>
									<Table.Cell>
										{#if !row.observed}
											<span class="text-sm text-muted-foreground">—</span>
										{:else if row.fired + row.muted > 0}
											<a
												href={monthStore.href(`/alerts?ver=mes&q=${row.id}`)}
												class="-mx-1.5 inline-flex rounded-md px-1.5 py-1 hover:bg-muted"
												aria-label={`Ver las alertas de ${row.id} en ${period}`}
												>{@render alertCounts(row)}</a
											>
										{:else}
											{@render alertCounts(row)}
										{/if}
									</Table.Cell>
									<Table.Cell class="pr-6 text-right">
										<a
											href={groupHref(row.id)}
											class="inline-grid size-8 place-items-center rounded-md hover:bg-muted"
											aria-label={`Abrir ${row.id}`}
											tabindex="-1"><ChevronRight class="size-4" aria-hidden="true" /></a
										>
									</Table.Cell>
								</Table.Row>
							{/each}
						</Table.Body>
					</Table.Root>
				{/if}
			</Card.Content>
			<Card.Footer class="flex-col items-start gap-1 text-xs leading-5 text-muted-foreground">
				<p>
					Δ {DELTA_MONTHS} meses es el score del mes menos el score de {DELTA_MONTHS} meses antes, en
					puntos. La trayectoria enseña la forma del score en la ventana, hasta el mes elegido; la línea
					vertical marca un cambio de perímetro.
				</p>
				<p>
					Sector, tamaño y país son contexto para leer el grupo: no entran en el score. La confianza
					acompaña al score y no lo modifica.
				</p>
			</Card.Footer>
		</Card.Root>
	{/if}
</section>
