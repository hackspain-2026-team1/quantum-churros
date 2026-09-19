<script lang="ts">
	import { CalendarOff, CircleCheck, TriangleAlert } from '@lucide/svelte';
	import { dev } from '$app/environment';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatPeriod, formatScore, formatScoreDelta } from '$lib/format.js';
	import type { EntityMonth } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { monthChanges, monthsBetween, previousEntry, type ChangeKey } from './explain.js';
	import { pillarLabel } from './labels.js';

	let {
		months,
		month
	}: {
		/** group.months or company.months, ascending. */
		months: EntityMonth[];
		/** Selected month; compared against the entry right before it. */
		month: string;
	} = $props();

	const manifest = $derived(page.data.manifest);
	const current = $derived(months.find((entry) => entry.month === month) ?? null);
	const previous = $derived(previousEntry(months, month));
	const changes = $derived(current && previous ? monthChanges(current, previous) : null);

	const label = (key: ChangeKey) => {
		if (key === 'base') return 'Punto de partida';
		if (key === 'penalty') return 'Penalización por pilar débil';
		if (key === 'cap') return 'Tope';
		return pillarLabel(manifest, key);
	};
	// Largest effect first; terms that did not move are folded into one line.
	const moved = $derived(
		(changes?.items ?? [])
			.filter((item) => item.delta !== 0 || item.availability !== null)
			.toSorted((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
	);
	const still = $derived((changes?.items ?? []).filter((item) => !moved.includes(item)));
	const scale = $derived(Math.max(1, ...moved.map((item) => Math.abs(item.delta))));
	const headline = $derived.by(() => {
		if (!changes || !current || !previous) return '';
		if (changes.total === 0) {
			return `El score se mantiene en ${formatScore(current.shown)}`;
		}
		return `El score ${changes.total > 0 ? 'sube' : 'baja'} ${formatScore(Math.abs(changes.total))} puntos: de ${formatScore(previous.shown)} a ${formatScore(current.shown)}`;
	});
	// The base is one per set of available pillars: it moves when that set changes.
	const baseNote = $derived.by(() => {
		const base = changes?.items.find((item) => item.key === 'base');
		if (!base || base.delta === 0 || !current || !previous) return '';
		return current.branch !== previous.branch
			? 'El punto de partida cambia porque cambian los pilares disponibles.'
			: 'El punto de partida varía por el redondeo al décimo que hace cuadrar la suma.';
	});
	const skipped = $derived(changes ? monthsBetween(changes.from, changes.to) > 1 : false);

	$effect(() => {
		if (dev && changes) {
			console.assert(
				changes.gap === 0,
				`[qué cambió] ${changes.from} → ${changes.to}: las diferencias no suman la variación del score (${changes.gap} décimas)`
			);
		}
	});
</script>

<Card.Root data-testid="score-changes">
	<Card.Header>
		<Card.Description>
			Qué cambió{previous ? ` frente a ${formatPeriod(previous.month)}` : ''}
		</Card.Description>
		<Card.Title class="leading-6">
			{changes ? headline : 'Primer mes observado'}
		</Card.Title>
	</Card.Header>
	<Card.Content class="space-y-4">
		{#if !changes}
			<EmptyState
				compact
				icon={CalendarOff}
				title="No hay un mes anterior con el que comparar"
				description="La lista de cambios aparece a partir del segundo mes observado."
			/>
		{:else}
			{#if skipped}
				<p class="text-xs leading-5 text-muted-foreground">
					El mes observado anterior es {formatPeriod(changes.from)}: entre ambos no hay cierres con
					datos.
				</p>
			{/if}
			{#if moved.length === 0}
				<p class="text-sm leading-6 text-muted-foreground">
					Ningún término del score se mueve entre los dos meses.
				</p>
			{:else}
				<ol class="space-y-2.5">
					{#each moved as item (item.key)}
						{@const share = (Math.abs(item.delta) / scale) * 50}
						<li
							class="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1"
							data-change={item.key}
							data-tenths={item.delta}
						>
							<div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium">
								{label(item.key)}
								{#if item.availability}
									<Badge variant="outline" class="font-normal text-muted-foreground">
										{item.availability === 'gained'
											? 'Pasa a estar disponible'
											: 'Deja de estar disponible'}
									</Badge>
								{/if}
							</div>
							<div
								class={[
									'font-data text-right text-sm font-semibold tabular-nums',
									item.delta > 0 && 'positive',
									item.delta < 0 && 'negative'
								]}
							>
								{formatScoreDelta(item.delta)}
							</div>
							<div class="relative col-span-2 h-2 rounded-full bg-muted/70" aria-hidden="true">
								<span class="absolute inset-y-0 left-1/2 w-px bg-[var(--ink)]/40"></span>
								<span
									class={[
										'absolute inset-y-0 rounded-full',
										item.delta < 0 ? 'bg-[var(--danger)]' : 'bg-[var(--success)]'
									]}
									style={item.delta < 0
										? `right: 50%; width: ${share}%`
										: `left: 50%; width: ${share}%`}
								></span>
							</div>
						</li>
					{/each}
				</ol>
			{/if}
			{#if still.length > 0}
				<p class="text-xs leading-5 text-muted-foreground">
					Sin cambio: {still.map((item) => label(item.key).toLowerCase()).join(', ')}.
				</p>
			{/if}
			<p
				class="flex items-start gap-2 border-t pt-3 text-xs leading-5 text-muted-foreground"
				data-testid="changes-check"
			>
				{#if changes.gap === 0}
					<CircleCheck class="mt-0.5 size-4 shrink-0 text-[var(--success)]" aria-hidden="true" />
					<span
						>Las diferencias suman {formatScoreDelta(changes.total)} puntos, exactamente la variación
						del score.{baseNote ? ` ${baseNote}` : ''}</span
					>
				{:else}
					<TriangleAlert class="mt-0.5 size-4 shrink-0 text-[var(--danger)]" aria-hidden="true" />
					<span>Las diferencias no cuadran por {formatScoreDelta(changes.gap)} puntos.</span>
				{/if}
			</p>
		{/if}
	</Card.Content>
</Card.Root>
