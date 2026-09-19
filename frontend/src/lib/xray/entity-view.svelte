<script lang="ts">
	import { ArrowLeft, CalendarClock, CalendarOff, Wrench } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { formatPercent, formatPeriod } from '$lib/format.js';
	import AbstainedState from './abstained-state.svelte';
	import { fullPlanTenths } from './actions.js';
	import CompanyAvatar from './company-avatar.svelte';
	import type { EntityContext, EntityMonth, InvoicesDue, Series } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import EntityActions from './entity-actions.svelte';
	import InvoiceReminders from './invoice-reminders.svelte';
	import EntityHero from './entity-hero.svelte';
	import MonthSlider from './month-slider.svelte';
	import { monthStore } from './month-store.svelte.js';
	import { entryAt } from './month.js';
	import PillarDrivers from './pillar-drivers.svelte';

	let {
		id,
		eyebrow,
		entries,
		series = [],
		context,
		firstMonth,
		backHref,
		backLabel,
		technicalHref,
		invoicesDue = null,
		children
	}: {
		id: string;
		eyebrow: string;
		entries: EntityMonth[];
		series?: Series[];
		context: EntityContext;
		firstMonth: string;
		backHref: string;
		backLabel: string;
		/** Technical tab of the dashboard focused on this entity's group. */
		technicalHref: string;
		/** Optional: the top overdue open AR invoices of the bundle, for the reminders. */
		invoicesDue: InvoicesDue | null;
		/** Extra blocks below the diagnosis, e.g. the companies of a group. */
		children?: Snippet;
	} = $props();

	const entry = $derived(entryAt(entries, monthStore.month));
	const lastMonth = $derived(entries[entries.length - 1].month);
	const industry = $derived(context.industry);
	const target = $derived(entry ? fullPlanTenths(entry) : null);
</script>

<div class="min-h-screen bg-background text-foreground">
	<div class="mx-auto max-w-[1540px] space-y-5 px-4 py-6 lg:px-8 lg:py-8">
		<Button variant="ghost" size="sm" href={backHref}
			><ArrowLeft class="size-4" /> {backLabel}</Button
		>
		<section class="space-y-5" aria-labelledby="entity-heading">
			<div class="grid gap-4 lg:grid-cols-[1fr_24rem] lg:items-end">
				<div class="flex items-center gap-3">
					<CompanyAvatar name={industry?.label ?? id} {id} />
					<div class="min-w-0">
						<p class="eyebrow">{eyebrow}</p>
						<div class="flex flex-wrap items-center gap-2">
							<h1 id="entity-heading" class="font-data">{id}</h1>
							{#if industry}
								<Badge variant="outline" title={industry.reason}>
									{industry.label} · {formatPercent(industry.confidence, 0)}
								</Badge>
							{/if}
						</div>
					</div>
				</div>
				<MonthSlider />
			</div>
			{#if entry}
				{#if entry.abstain}
					<AbstainedState abstain={entry.abstain} />
				{:else if entry.verdict.detected_since}
					<Alert.Root class="border-[var(--warning)]/35 bg-[var(--warning-soft)]"
						><CalendarClock class="size-4" /><Alert.Title
							>Señal detectada desde {formatPeriod(entry.verdict.detected_since)}</Alert.Title
						><Alert.Description
							>El cambio de trayectoria acumula {entry.verdict.persistence_months}
							{entry.verdict.persistence_months === 1 ? 'cierre' : 'cierres'} de persistencia.</Alert.Description
						></Alert.Root
					>
				{/if}
				<EntityHero {entry} {entries} {series} targetTenths={target} />
				<EntityActions entityId={id} {entry} />
				<InvoiceReminders entityId={id} {invoicesDue} />
				<div class="flex flex-wrap items-end justify-between gap-3 pt-2">
					<div>
						<p class="eyebrow">De dónde sale el score</p>
						<h2 class="text-xl font-semibold tracking-[-0.02em]">Qué aporta y qué resta</h2>
					</div>
					<Button variant="outline" size="sm" href={technicalHref}
						><Wrench /> Ver detalle técnico</Button
					>
				</div>
				<PillarDrivers {entry} />
				{@render children?.()}
			{:else}
				<EmptyState
					icon={CalendarOff}
					title={`Sin datos de ${id} en ${formatPeriod(monthStore.month)}`}
					description={`El primer cierre observado es ${formatPeriod(firstMonth)} y el último, ${formatPeriod(lastMonth)}.`}
				>
					<Button variant="outline" onclick={() => monthStore.select(lastMonth)}>
						Ir al último cierre
					</Button>
				</EmptyState>
			{/if}
		</section>
	</div>
</div>
