<script lang="ts">
	import { ArrowRight, FlaskConical, ListChecks } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { formatNumber, formatPeriod, formatScoreDelta } from '$lib/format.js';
	import { entryActions, projectedTenths } from './actions.js';
	import type { EntityMonth } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { entitySeries } from './entity-series.js';
	import FocusFrame, { type FocusState } from './focus-frame.svelte';
	import { monthStore } from './month-store.svelte.js';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let { focus, picker }: { focus: FocusState; picker: Snippet } = $props();

	// Selection is per group and month: action ids are only meaningful within one entity-month.
	const selected = new SvelteSet<string>();
	const scope = $derived(`${focus.state === 'ready' ? focus.group.id : ''}:${monthStore.month}`);
	$effect(() => {
		void scope;
		selected.clear();
	});
	const toggle = (id: string, on: boolean) => (on ? selected.add(id) : selected.delete(id));
	const selectAll = (entry: EntityMonth) =>
		entryActions(entry).forEach((action) => selected.add(action.id));
</script>

<section class="space-y-5" aria-labelledby="scenario-heading">
	<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
		<div>
			<p class="eyebrow">
				{focus.state === 'ready' ? focus.group.id : 'Grupo'} · {formatPeriod(monthStore.month)}
			</p>
			<h1 id="scenario-heading">Laboratorio de escenarios</h1>
			<p class="page-lead">
				Activa las acciones que el motor calculó para este grupo; el histórico observado permanece
				intacto.
			</p>
		</div>
		<div class="flex flex-wrap items-center gap-3">
			{@render picker()}
			<Badge variant="outline"><FlaskConical /> Estimación no aplicada</Badge>
		</div>
	</div>
	<FocusFrame {focus}>
		{#snippet children(group, entry)}
			{@const actions = entryActions(entry)}
			{@const projected = projectedTenths(entry, selected)}
			{@const trajectory = entitySeries(group.months, entry.month)}
			{#if actions.length === 0}
				<EmptyState
					icon={ListChecks}
					title="Sin acciones con las que construir un escenario"
					description={`El bundle no trae acciones para ${group.id} en ${formatPeriod(entry.month)}. El laboratorio solo usa mejoras recalculadas por el motor: no inventa palancas ni resultados.`}
				/>
			{:else}
				<div class="grid gap-4 lg:grid-cols-[24rem_1fr]">
					<Card.Root
						><Card.Header
							><Card.Description>Palancas calculadas por el motor</Card.Description><Card.Title
								>Elige qué acciones seguir</Card.Title
							></Card.Header
						><Card.Content class="space-y-4" data-testid="scenario-levers"
							>{#each actions as action (action.id)}
								<label
									class="flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/40 has-[[data-state=checked]]:border-[var(--success)]/50 has-[[data-state=checked]]:bg-[var(--success-soft)]"
								>
									<Checkbox
										class="mt-0.5"
										bind:checked={() => selected.has(action.id), (on) => toggle(action.id, on)}
									/>
									<span class="min-w-0 flex-1 text-sm">
										<span class="block font-medium">{action.title}</span>
										{#if action.current != null && action.target != null}
											<span class="font-data mt-1 block text-xs text-muted-foreground"
												>{formatNumber(action.current, 1)} → {formatNumber(action.target, 1)}
												{action.unit ?? ''}</span
											>
										{/if}
									</span>
									<strong class="font-data text-sm whitespace-nowrap text-[var(--success-strong)]"
										>{formatScoreDelta(action.uplift_tenths)}</strong
									>
								</label>
							{/each}
							<div class="grid grid-cols-2 gap-2">
								<Button variant="outline" onclick={() => selectAll(entry)}>Activar todas</Button>
								<Button
									variant="ghost"
									disabled={selected.size === 0}
									onclick={() => selected.clear()}>Limpiar</Button
								>
							</div></Card.Content
						></Card.Root
					>
					<div class="space-y-4">
						<Card.Root
							><Card.Header
								><Card.Description>Impacto estimado</Card.Description><Card.Title
									>{selected.size === 0
										? 'Activa una acción para ver su efecto'
										: `${formatNumber(selected.size)} de ${formatNumber(actions.length)} acciones activas`}</Card.Title
								></Card.Header
							><Card.Content
								><div class="mb-5 flex flex-wrap items-center justify-center gap-5">
									<ScoreGauge score={entry.shown / 10} label="Observado" /><ArrowRight
										class="size-6 text-muted-foreground"
									/><ScoreGauge
										score={projected / 10}
										label="Estimado"
										delta={(projected - entry.shown) / 10}
									/>
								</div>
								<TrajectoryChart
									values={trajectory.values}
									months={trajectory.months}
									changeIndex={trajectory.changeIndex}
									projected={selected.size > 0 ? [projected / 10] : []}
									projectedLabel="Estimación"
									format={(value) => formatNumber(value, 1)}
									compact
								/></Card.Content
							></Card.Root
						><Alert.Root
							><Alert.Title>Estimación, no promesa</Alert.Title><Alert.Description
								>Con una sola acción se muestra el score que el motor recalculó para ella. Con
								varias, se suman sus mejoras sin superar el resultado que el motor obtuvo al
								aplicarlas todas a la vez.</Alert.Description
							></Alert.Root
						>
					</div>
				</div>
			{/if}
		{/snippet}
	</FocusFrame>
</section>
