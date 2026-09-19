<script lang="ts">
	import { BellRing, FileWarning, ListChecks } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { formatNumber, formatPeriod } from '$lib/format.js';
	import ActionList, { type ActionItem } from './action-list.svelte';
	import { actionState } from './action-state.svelte.js';
	import { entryActions } from './actions.js';
	import { loadGroup } from './bundle.js';
	import EmptyState from './empty-state.svelte';
	import { monthStore } from './month-store.svelte.js';
	import { entryAt } from './month.js';
	import type { PortfolioRow } from './portfolio.js';

	// Actions live in each group file, so the list reads the groups that need them most:
	// the lowest scores of the month. The cap keeps the download bounded on large portfolios.
	const GROUPS_READ = 40;
	const ACTIONS_SHOWN = 30;

	let { rows }: { rows: PortfolioRow[] } = $props();

	type Status =
		{ state: 'loading' } | { state: 'ready'; items: ActionItem[]; read: number; failed: number };

	let status = $state<Status>({ state: 'loading' });
	const month = $derived(monthStore.month);
	const candidates = $derived(rows.filter((row) => row.shown !== null).slice(0, GROUPS_READ));

	$effect(() => {
		const wanted = candidates;
		const at = month;
		let cancelled = false;
		status = { state: 'loading' };
		Promise.allSettled(wanted.map((row) => loadGroup(fetch, row.id))).then((results) => {
			if (cancelled) return;
			const items: ActionItem[] = [];
			let failed = 0;
			for (const result of results) {
				if (result.status === 'rejected') {
					failed += 1;
					continue;
				}
				const group = result.value;
				const entry = entryAt(group.months, at);
				if (!entry) continue;
				for (const action of entryActions(entry)) {
					items.push({
						entityId: group.id,
						href: monthStore.href(`/group/${group.id}`, at),
						shown: entry.shown,
						action
					});
				}
			}
			items.sort((a, b) => b.action.uplift_tenths - a.action.uplift_tenths);
			status = { state: 'ready', items, read: results.length - failed, failed };
		});
		return () => {
			cancelled = true;
		};
	});

	const top = $derived(status.state === 'ready' ? status.items.slice(0, ACTIONS_SHOWN) : []);
	const done = $derived(
		top.filter((item) => actionState.isDone(item.entityId, item.action.id)).length
	);
</script>

<section class="space-y-5" aria-labelledby="actions-heading">
	<div>
		<p class="eyebrow">Seguimiento operativo · {formatPeriod(month)}</p>
		<h1 id="actions-heading">Centro de acciones</h1>
		<p class="page-lead">
			Las acciones que más puntos de score devuelven en la cartera, con el grupo al que pertenecen.
		</p>
	</div>
	{#if status.state === 'loading'}
		<div class="grid gap-3" aria-label="Cargando acciones">
			<Skeleton class="h-28" /><Skeleton class="h-28" /><Skeleton class="h-28" />
		</div>
	{:else}
		<Alert.Root class="border-[var(--signal)]/30 bg-[var(--signal-soft)]"
			><BellRing class="size-4" /><Alert.Title
				>{formatNumber(top.length)} acciones · {formatNumber(done)} hechas</Alert.Title
			><Alert.Description
				>Se han leído los {formatNumber(status.read)} grupos con menor score del mes y se ordenan sus
				acciones por puntos ganados. El estado hecha / pendiente se guarda solo en este navegador.</Alert.Description
			></Alert.Root
		>
		{#if status.failed > 0}
			<Alert.Root variant="destructive"
				><FileWarning class="size-4" /><Alert.Title
					>{formatNumber(status.failed)} grupos no se pudieron leer</Alert.Title
				><Alert.Description>Sus acciones no figuran en esta lista.</Alert.Description></Alert.Root
			>
		{/if}
		{#if top.length > 0}
			<ActionList items={top} />
		{:else}
			<EmptyState
				icon={ListChecks}
				title="Sin acciones calculadas para este mes"
				description="Los grupos leídos no traen acciones en este cierre: o el motor no encontró palancas que suban el score, o esta exportación es anterior al cálculo de acciones."
			/>
		{/if}
	{/if}
</section>
