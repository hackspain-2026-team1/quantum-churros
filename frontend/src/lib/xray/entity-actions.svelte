<script lang="ts">
	import { ListChecks, Sparkles } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { formatPeriod, formatScore, formatScoreDelta } from '$lib/format.js';
	import ActionList from './action-list.svelte';
	import { entryActions, fullPlanTenths } from './actions.js';
	import type { EntityMonth } from './contract.js';
	import EmptyState from './empty-state.svelte';

	let { entityId, entry }: { entityId: string; entry: EntityMonth } = $props();

	const actions = $derived(entryActions(entry));
	const target = $derived(fullPlanTenths(entry));
	const items = $derived(actions.map((action) => ({ entityId, shown: entry.shown, action })));
</script>

<section class="space-y-4" aria-labelledby="entity-actions-heading" data-testid="entity-actions">
	<div>
		<p class="eyebrow">Qué hacer ahora</p>
		<h2 id="entity-actions-heading" class="text-xl font-semibold tracking-[-0.02em]">
			Acciones para subir el score
		</h2>
	</div>
	{#if actions.length > 0 && target !== null}
		<Alert.Root class="border-[var(--success)]/35 bg-[var(--success-soft)]"
			><Sparkles class="size-4" /><Alert.Title data-testid="actions-headline"
				>Si sigues estas acciones tu score pasaría de {formatScore(entry.shown)} a {formatScore(
					target
				)}</Alert.Title
			><Alert.Description
				>{formatScoreDelta(target - entry.shown)} puntos en total. Cada acción indica lo que suma por
				sí sola, recalculado por el motor con los datos de {formatPeriod(entry.month)}; los efectos
				no siempre se suman íntegros.</Alert.Description
			></Alert.Root
		>
		{#if entry.actions_plan && entry.actions_plan.stages.length > 1}
			<div class="flex flex-wrap items-center gap-2" data-testid="actions-ladder">
				{#each entry.actions_plan.stages as stage (stage.number)}
					<span
						class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs tabular-nums"
					>
						<span class="font-medium">Etapa {stage.number}</span>
						<span>{formatScore(stage.score_tenths)}</span>
						<span class="text-[var(--success)]">({formatScoreDelta(stage.uplift_tenths)})</span>
					</span>
				{/each}
			</div>
			<p class="text-xs text-muted-foreground">
				Cada etapa se calcula sobre el mes que deja la anterior: el mejor score alcanzable con estas
				palancas es {formatScore(entry.actions_plan.max_score_tenths)}, y las acciones de la etapa 1
				son las de arriba. Cuando ni así se llega a un score sano, el motor lo dice: hace falta
				financiación, no gestión.
			</p>
		{/if}
		<ActionList {items} />
	{:else}
		<EmptyState
			icon={ListChecks}
			title="Sin acciones calculadas para este mes"
			description={`El bundle no trae acciones para ${entityId} en ${formatPeriod(entry.month)}: o el motor no encontró palancas que suban el score, o esta exportación es anterior al cálculo de acciones.`}
		/>
	{/if}
</section>
