<script lang="ts" module>
	import type { EntityAction } from './contract.js';

	export type ActionItem = {
		entityId: string;
		/** Link to the entity; set on portfolio-level lists. */
		href?: string;
		/** Displayed score of the entity that month, in tenths. */
		shown: number;
		action: EntityAction;
	};
</script>

<script lang="ts">
	import { Check, CircleDot } from '@lucide/svelte';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatNumber, formatScore, formatScoreDelta } from '$lib/format.js';
	import { actionState } from './action-state.svelte.js';
	import { pillarLabel } from './labels.js';

	let { items }: { items: ActionItem[] } = $props();

	const quantity = (value: number, unit?: string | null) =>
		`${formatNumber(value, Number.isInteger(value) ? 0 : 2)}${unit ? `\u00A0${unit}` : ''}`;
</script>

<div class="grid gap-3" data-testid="action-list">
	{#each items as item, index (`${item.entityId}:${item.action.id}`)}
		{@const action = item.action}
		{@const done = actionState.isDone(item.entityId, action.id)}
		<Card.Root data-action={action.id}
			><Card.Content class="grid gap-4 p-5 lg:grid-cols-[auto_1fr_12rem_auto] lg:items-center"
				><Badge
					variant="outline"
					class="font-data border-[var(--success)]/40 bg-[var(--success-soft)] text-sm text-[var(--success-strong)]"
					data-testid="action-uplift">{formatScoreDelta(action.uplift_tenths)} puntos</Badge
				>
				<div>
					<h2 class="font-semibold">
						<span class="font-data mr-1 text-muted-foreground">{index + 1}.</span>{action.title}
					</h2>
					{#if action.detail}
						<p class="mt-1 text-sm leading-6 text-muted-foreground">{action.detail}</p>
					{/if}
					<div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs">
						{#if item.href}
							<span
								><span class="text-muted-foreground">Grupo</span> ·
								<a class="font-data underline-offset-2 hover:underline" href={item.href}
									>{item.entityId}</a
								></span
							>
						{/if}
						{#if action.pillar}
							<span
								><span class="text-muted-foreground">Pilar</span> · {pillarLabel(
									page.data.manifest,
									action.pillar
								)}</span
							>
						{/if}
						{#if action.current != null && action.target != null}
							<span
								><span class="text-muted-foreground">Hoy</span> · {quantity(
									action.current,
									action.unit
								)} <span class="text-muted-foreground">→ objetivo</span>
								{quantity(action.target, action.unit)}</span
							>
						{/if}
						{#if action.effort}
							<span><span class="text-muted-foreground">Esfuerzo</span> · {action.effort}</span>
						{/if}
						<span
							><span class="text-muted-foreground">Score</span> ·
							<span class="font-data"
								>{formatScore(item.shown)} → {formatScore(action.new_score_tenths)}</span
							></span
						>
					</div>
				</div>
				<div>
					<span class="metric-label">Estado</span><strong class="flex items-center gap-2 text-sm"
						>{#if done}<Check class="size-4 text-[var(--success)]" />Hecha{:else}<CircleDot
								class="size-4 text-[var(--warning)]"
							/>Pendiente{/if}</strong
					>
				</div>
				<Button variant="outline" onclick={() => actionState.toggle(item.entityId, action.id)}
					>{done ? 'Reabrir' : 'Marcar hecha'}</Button
				></Card.Content
			></Card.Root
		>
	{/each}
</div>
