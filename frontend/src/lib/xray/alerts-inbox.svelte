<script lang="ts">
	import {
		BellOff,
		BellRing,
		ChevronDown,
		EyeOff,
		FilterX,
		PauseCircle,
		ReceiptText,
		Search
	} from '@lucide/svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Select from '$lib/components/ui/select/index.js';
	import * as Tabs from '$lib/components/ui/tabs/index.js';
	import { Toggle } from '$lib/components/ui/toggle/index.js';
	import * as ToggleGroup from '$lib/components/ui/toggle-group/index.js';
	import { formatNumber, formatPercent, formatPeriod } from '$lib/format.js';
	import AlertCard from './alert-card.svelte';
	import { alertTriage } from './alert-state.svelte.js';
	import {
		countByState,
		filterAlerts,
		groupByMonth,
		inScope,
		monthlyCounts,
		sortAlerts,
		standingAbstention,
		type Abstention,
		type AlertEntityFilter,
		type AlertKindFilter,
		type AlertScope
	} from './alerts.js';
	import AlertsTimeline from './alerts-timeline.svelte';
	import {
		ALERT_KINDS,
		ALERT_KIND_TEXT,
		ALERT_STATES,
		type Alert,
		type AlertState,
		type Manifest
	} from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { glossaryText } from './labels.js';
	import MonthSlider from './month-slider.svelte';
	import { monthStore } from './month-store.svelte.js';
	import StatTile from './stat-tile.svelte';
	import { ALERT_STATE_TONE } from './tones.js';

	let {
		alerts,
		manifest,
		abstentions = null
	}: {
		alerts: Alert[];
		manifest: Manifest;
		/** receipt.abstentions; null when the receipt could not be read. */
		abstentions?: Abstention[] | null;
	} = $props();

	// Cards rendered per step; the rest of a long history sits behind 'Mostrar más'.
	const PAGE_SIZE = 40;

	const TAB: Record<AlertState, { label: string; icon: typeof BellRing; empty: string }> = {
		fired: {
			label: 'Activas',
			icon: BellRing,
			empty: 'El motor no disparó ninguna alerta'
		},
		suppressed: {
			label: 'Silenciadas',
			icon: BellOff,
			empty: 'El motor no silenció ninguna alerta'
		},
		abstained: {
			label: 'Abstenciones',
			icon: PauseCircle,
			empty: 'Ninguna alerta quedó sin disparar por abstención'
		}
	};
	const isState = (value: string | null): value is AlertState =>
		ALERT_STATES.includes(value as AlertState);

	// ?ver=mes opens the inbox on the month under analysis, ?estado= on a tab, ?q= on an entity.
	const params = page.url.searchParams;
	const startInMonth = params.get('ver') === 'mes';
	const wantedTab = params.get('estado');
	// Coming from a month of the portfolio, open on the first tab that has something to read.
	function firstTab(): AlertState {
		if (isState(wantedTab)) return wantedTab;
		if (!startInMonth) return 'fired';
		const wanted = filterAlerts(alerts, {
			query: params.get('q') ?? '',
			kind: 'all',
			entity: 'all'
		});
		const found = countByState(inScope(wanted, 'month', monthStore.month));
		return ALERT_STATES.find((state) => found[state] > 0) ?? 'fired';
	}
	let scope = $state<AlertScope>(startInMonth ? 'month' : 'history');
	let tab = $state<AlertState>(firstTab());
	let query = $state(params.get('q') ?? '');
	let kind = $state<AlertKindFilter>('all');
	let entity = $state<AlertEntityFilter>('all');
	let showDismissed = $state(false);
	let limit = $state(PAGE_SIZE);

	alertTriage.init();

	const month = $derived(monthStore.month);
	const period = $derived(month ? formatPeriod(month) : '');
	const range = $derived(
		manifest.months.length === 1
			? `En ${formatPeriod(manifest.months[0])}`
			: `Entre ${formatPeriod(manifest.months[0])} y ${formatPeriod(manifest.months[manifest.months.length - 1])}`
	);

	const kindsPresent = $derived(ALERT_KINDS.filter((key) => alerts.some((a) => a.kind === key)));
	const kindLabel = $derived(kind === 'all' ? 'Todos los tipos' : ALERT_KIND_TEXT[kind]);

	// Filters first, then the period: the timeline shows every month, the list only the scope.
	const matching = $derived(filterAlerts(alerts, { query, kind, entity }));
	const scoped = $derived(inScope(matching, scope, month));
	const counts = $derived(countByState(scoped));
	const timeline = $derived(monthlyCounts(matching, manifest.months));
	const notFired = $derived(counts.suppressed + counts.abstained);

	const firedIds = $derived(scoped.filter((a) => a.state === 'fired').map((a) => a.id));
	const pendingCount = $derived(alertTriage.pending(firedIds));
	const dismissedCount = $derived(alertTriage.count(firedIds, 'dismissed'));

	const inTab = $derived(sortAlerts(scoped.filter((a) => a.state === tab)));
	const listed = $derived(
		tab === 'fired' && !showDismissed
			? inTab.filter((a) => alertTriage.get(a.id) !== 'dismissed')
			: inTab
	);
	const sections = $derived(groupByMonth(listed.slice(0, limit)));
	const filtered = $derived(query.trim() !== '' || kind !== 'all' || entity !== 'all');

	// A new filter, tab or period starts again from the first page.
	$effect(() => {
		void [tab, scope, month, query, kind, entity, showDismissed];
		limit = PAGE_SIZE;
	});

	// Why the alerts of a state were not fired, in the words of the glossary when they share a reason.
	function reasonHint(state: AlertState, fallback: string): string {
		const reasons = new Set(
			scoped.flatMap((a) => (a.state === state && a.suppressed_by ? [a.suppressed_by.reason] : []))
		);
		if (reasons.size === 0) return fallback;
		if (reasons.size > 1) return 'por varios motivos';
		const [reason] = reasons;
		return glossaryText(manifest, 'reasons', reason).replace(/\.$/, '').toLowerCase();
	}
	const tileHint = $derived<Record<AlertState, string>>({
		fired: 'requieren lectura',
		suppressed: reasonHint('suppressed', 'alertas en pausa'),
		abstained: reasonHint('abstained', 'número visible, sin alerta')
	});

	const plural = (count: number, one: string, many: string) =>
		`${formatNumber(count)} ${count === 1 ? one : many}`;
	const lead = $derived.by(() => {
		const where = scope === 'month' ? `En ${period}` : range;
		if (scoped.length === 0) {
			return `${where} el motor no evaluó ninguna alerta${filtered ? ' con estos filtros' : ''}.`;
		}
		const evaluated = `${where} el motor evaluó ${plural(scoped.length, 'alerta', 'alertas')}`;
		if (notFired === 0) {
			return `${evaluated} y ${scoped.length === 1 ? 'la disparó' : 'las disparó todas'}: ninguna quedó silenciada ni en abstención.`;
		}
		const breakdown = `${plural(counts.suppressed, 'silenciada', 'silenciadas')} y ${formatNumber(counts.abstained)} en abstención`;
		const shown = 'Las que no se disparan también se enseñan, con su motivo y su ventana.';
		if (counts.fired === 0) return `${evaluated} y no disparó ninguna: ${breakdown}. ${shown}`;
		const share = formatPercent(notFired / scoped.length, 0);
		return `${evaluated}: disparó ${formatNumber(counts.fired)} y dejó sin disparar ${formatNumber(notFired)} (${share}): ${breakdown}. ${shown}`;
	});

	function clearFilters() {
		query = '';
		kind = 'all';
		entity = 'all';
	}
	function selectMonth(next: string) {
		monthStore.select(next);
		scope = 'month';
	}
</script>

<section class="space-y-5" aria-labelledby="alerts-heading">
	<div class="grid gap-4 lg:grid-cols-[1fr_24rem] lg:items-end">
		<div>
			<p class="eyebrow">Bandeja de alertas</p>
			<h1 id="alerts-heading">Alertas</h1>
			<p class="page-lead" data-testid="alerts-lead">{lead}</p>
		</div>
		<div class="space-y-2">
			<ToggleGroup.Root
				type="single"
				variant="outline"
				size="sm"
				class="w-full"
				value={scope}
				onValueChange={(value) => (scope = (value || 'history') as AlertScope)}
				aria-label="Periodo de la bandeja"
			>
				<ToggleGroup.Item value="history" class="px-3">Todo el histórico</ToggleGroup.Item>
				<ToggleGroup.Item value="month" class="px-3">Solo el mes de análisis</ToggleGroup.Item>
			</ToggleGroup.Root>
			{#if scope === 'month'}<MonthSlider />{/if}
		</div>
	</div>

	<div class="flex min-w-0 flex-wrap items-center gap-2" role="group" aria-label="Filtros">
		<div class="relative min-w-52 flex-1 basis-60">
			<Search
				class="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
				aria-hidden="true"
			/>
			<Input
				class="bg-card pl-9"
				type="search"
				placeholder="Buscar por grupo o empresa"
				aria-label="Buscar por grupo o empresa"
				autocomplete="off"
				bind:value={query}
			/>
		</div>
		<ToggleGroup.Root
			type="single"
			variant="outline"
			size="sm"
			class="bg-card"
			value={entity}
			onValueChange={(value) => (entity = (value || 'all') as AlertEntityFilter)}
			aria-label="Filtrar por tipo de entidad"
		>
			<ToggleGroup.Item value="all" class="flex-none px-3">Todo</ToggleGroup.Item>
			<ToggleGroup.Item value="group" class="flex-none px-3">Grupos</ToggleGroup.Item>
			<ToggleGroup.Item value="company" class="flex-none px-3">Empresas</ToggleGroup.Item>
		</ToggleGroup.Root>
		<Select.Root
			type="single"
			value={kind}
			onValueChange={(value) => (kind = (value || 'all') as AlertKindFilter)}
		>
			<Select.Trigger size="sm" class="w-52 bg-card" aria-label="Filtrar por tipo de alerta"
				>{kindLabel}</Select.Trigger
			>
			<Select.Content>
				<Select.Item value="all" label="Todos los tipos" />
				{#each kindsPresent as key (key)}
					<Select.Item value={key} label={ALERT_KIND_TEXT[key]} />
				{/each}
			</Select.Content>
		</Select.Root>
		{#if filtered}
			<Button variant="ghost" size="sm" onclick={clearFilters}><FilterX /> Limpiar filtros</Button>
		{/if}
	</div>

	<div class="grid grid-cols-2 gap-3 lg:grid-cols-4" role="group" aria-label="Alertas por estado">
		{#each ALERT_STATES as key (key)}
			<StatTile
				label={TAB[key].label}
				tone={ALERT_STATE_TONE[key]}
				value={formatNumber(counts[key])}
				hints={[tileHint[key]]}
				pressed={tab === key}
				onclick={() => (tab = key)}
				kpi={`alerts-${key}`}
			/>
		{/each}
		<StatTile
			label="Sin revisar"
			icon={EyeOff}
			value={formatNumber(pendingCount)}
			hints={[
				`de ${plural(counts.fired, 'activa', 'activas')}`,
				'triaje guardado solo en este navegador'
			]}
			kpi="alerts-pending"
		/>
	</div>

	<Card.Root>
		<Card.Content>
			<AlertsTimeline
				counts={timeline}
				selected={scope === 'month' ? month : null}
				onSelect={selectMonth}
			/>
		</Card.Content>
	</Card.Root>

	<Tabs.Root bind:value={tab} class="gap-4">
		<div class="flex flex-wrap items-center justify-between gap-3">
			<Tabs.List class="grid h-auto w-full grid-cols-3 sm:inline-flex sm:w-fit">
				{#each ALERT_STATES as key (key)}
					{@const Icon = TAB[key].icon}
					<Tabs.Trigger
						value={key}
						class="px-3 py-1.5"
						data-alert-tab={key}
						data-count={counts[key]}
					>
						<Icon aria-hidden="true" class="hidden sm:block" />
						{TAB[key].label}
						<span class="font-data text-xs text-muted-foreground">{formatNumber(counts[key])}</span>
					</Tabs.Trigger>
				{/each}
			</Tabs.List>
			{#if tab === 'fired' && dismissedCount > 0}
				<Toggle variant="outline" size="sm" class="bg-card px-3" bind:pressed={showDismissed}>
					<EyeOff /> Ver descartadas · {formatNumber(dismissedCount)}
				</Toggle>
			{/if}
		</div>

		{#each ALERT_STATES as key (key)}
			<Tabs.Content value={key} class="space-y-5">
				{#if tab === key}
					{#if listed.length === 0}
						<EmptyState
							icon={TAB[key].icon}
							title={`${TAB[key].empty}${scope === 'month' ? ` en ${period}` : ''}`}
							description={inTab.length > 0
								? 'Todas las alertas activas de este periodo están descartadas en este navegador.'
								: filtered
									? 'Ninguna alerta coincide con los filtros. Límpialos o amplía el periodo.'
									: scope === 'month'
										? 'Elige otro mes en la línea temporal o amplía la bandeja a todo el histórico.'
										: 'El bundle no contiene alertas en este estado.'}
						>
							{#each ALERT_STATES.filter((state) => state !== key && counts[state] > 0) as state (state)}
								<Button variant="outline" size="sm" onclick={() => (tab = state)}>
									{TAB[state].label} · {formatNumber(counts[state])}
								</Button>
							{/each}
							{#if inTab.length > 0}
								<Button variant="outline" size="sm" onclick={() => (showDismissed = true)}>
									Ver descartadas
								</Button>
							{:else if filtered}
								<Button variant="outline" size="sm" onclick={clearFilters}>
									<FilterX /> Limpiar filtros
								</Button>
							{:else if scope === 'month'}
								<Button variant="outline" size="sm" onclick={() => (scope = 'history')}>
									Ver todo el histórico
								</Button>
							{/if}
						</EmptyState>
					{:else}
						<div class="space-y-6" data-alert-list={key} data-page-size={PAGE_SIZE}>
							{#each sections as section (section.month)}
								<section class="space-y-3" aria-label={formatPeriod(section.month)}>
									<h2
										class="flex items-baseline gap-2 text-sm font-semibold text-muted-foreground first-letter:uppercase"
									>
										<span class="text-foreground first-letter:uppercase"
											>{formatPeriod(section.month)}</span
										>
										<span class="font-data text-xs font-normal"
											>{plural(section.alerts.length, 'alerta', 'alertas')}</span
										>
									</h2>
									<ul class="grid gap-3">
										{#each section.alerts as alert (alert.id)}
											<li>
												<AlertCard
													{alert}
													{manifest}
													standing={abstentions ? standingAbstention(alert, abstentions) : null}
													standingKnown={abstentions !== null}
													triage={alertTriage.get(alert.id)}
													onTriage={(value) => alertTriage.set(alert.id, value)}
												/>
											</li>
										{/each}
									</ul>
								</section>
							{/each}
						</div>
						{#if listed.length > limit}
							<div class="flex flex-col items-center gap-2">
								<p class="text-xs text-muted-foreground">
									Mostrando {formatNumber(limit)} de {formatNumber(listed.length)}
								</p>
								<Button variant="outline" onclick={() => (limit += PAGE_SIZE)}>
									<ChevronDown /> Mostrar {formatNumber(Math.min(PAGE_SIZE, listed.length - limit))} más
								</Button>
							</div>
						{/if}
						{#if key === 'abstained'}
							<p class="flex items-start gap-2 text-sm leading-6 text-muted-foreground">
								<ReceiptText class="mt-1 size-4 shrink-0" aria-hidden="true" />
								<span>
									El
									<a
										class="font-medium text-foreground underline underline-offset-4"
										href={monthStore.href('/receipt')}>recibo</a
									>
									lista todas las entidades en abstención en el último cierre y qué dato las desbloquea.
								</span>
							</p>
						{/if}
					{/if}
				{/if}
			</Tabs.Content>
		{/each}
	</Tabs.Root>
</section>
