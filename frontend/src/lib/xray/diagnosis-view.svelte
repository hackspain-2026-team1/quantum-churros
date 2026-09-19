<script lang="ts">
	import { ArrowRight, CalendarClock } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { formatPercent, formatPeriod } from '$lib/format.js';
	import AbstainedState from './abstained-state.svelte';
	import { fullPlanTenths } from './actions.js';
	import CompanyAvatar from './company-avatar.svelte';
	import EntityHero from './entity-hero.svelte';
	import FocusFrame, { type FocusState } from './focus-frame.svelte';
	import { monthStore } from './month-store.svelte.js';
	import PillarDrivers from './pillar-drivers.svelte';

	let { focus, picker }: { focus: FocusState; picker: Snippet } = $props();

	const group = $derived(focus.state === 'ready' ? focus.group : null);
	const industry = $derived(group?.context.industry ?? null);
</script>

<section class="space-y-5" aria-labelledby="diagnosis-heading">
	<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
		<div class="flex items-center gap-3">
			<CompanyAvatar name={industry?.label ?? group?.id ?? 'Grupo'} id={group?.id ?? 'grupo'} />
			<div>
				<p class="eyebrow">
					{group ? `${group.id} · ${formatPeriod(monthStore.month)}` : 'Grupo'}
				</p>
				<div class="flex flex-wrap items-center gap-2">
					<h1 id="diagnosis-heading">Diagnóstico explicable</h1>
					{#if industry}
						<Badge variant="outline" title={industry.reason}>
							{industry.label} · {formatPercent(industry.confidence, 0)}
						</Badge>
					{/if}
				</div>
			</div>
		</div>
		{@render picker()}
	</div>
	<p class="page-lead">
		El score se descompone en cinco pilares: cada uno aporta o resta puntos sobre la base.
	</p>
	<FocusFrame {focus}>
		{#snippet children(group, entry)}
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
			<EntityHero
				{entry}
				entries={group.months}
				series={group.series}
				targetTenths={fullPlanTenths(entry)}
			/>
			<PillarDrivers {entry} />
			<div class="flex justify-end">
				<Button variant="outline" href={monthStore.href(`/group/${group.id}`)}
					>Abrir {group.id} y sus acciones <ArrowRight /></Button
				>
			</div>
		{/snippet}
	</FocusFrame>
</section>
