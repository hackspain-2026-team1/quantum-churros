<script lang="ts">
	import { ChevronRight, CircleCheck, KeyRound, PauseCircle } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatNumber, formatPeriod, humanizeMonths } from '$lib/format.js';
	import type { Manifest, Receipt } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { glossaryText } from './labels.js';
	import { monthStore } from './month-store.svelte.js';
	import { TONE_BADGE } from './tones.js';

	type Abstention = Receipt['abstentions'][number];

	let { abstentions, manifest }: { abstentions: Abstention[]; manifest: Manifest } = $props();

	/** Rows shown per reason before 'ver más'; a real portfolio can abstain on hundreds. */
	const PREVIEW = 6;
	let expanded = $state<Record<string, boolean>>({});

	const plural = (count: number, one: string, many: string) =>
		`${formatNumber(count)} ${count === 1 ? one : many}`;
	const countKind = (items: Abstention[], kind: Abstention['entity_kind']) =>
		items.filter((item) => item.entity_kind === kind).length;

	// One block per reason, largest first; groups before their companies inside each block.
	const byReason = $derived.by(() => {
		const blocks: Record<string, Abstention[]> = {};
		for (const item of abstentions) (blocks[item.reason] ??= []).push(item);
		return blocks;
	});
	const reasons = $derived(
		Object.entries(byReason)
			.map(([reason, items]) => ({
				reason,
				text: glossaryText(manifest, 'reasons', reason),
				items: items.toSorted(
					(a, b) =>
						a.group_id.localeCompare(b.group_id) ||
						Number(a.entity_kind !== 'group') - Number(b.entity_kind !== 'group') ||
						a.entity_id.localeCompare(b.entity_id)
				)
			}))
			.toSorted((a, b) => b.items.length - a.items.length || a.reason.localeCompare(b.reason))
	);
	const months = $derived([...new Set(abstentions.map((item) => item.month))].toSorted());
	const summary = $derived.by(() => {
		const parts = [
			plural(countKind(abstentions, 'group'), 'grupo', 'grupos'),
			plural(countKind(abstentions, 'company'), 'empresa', 'empresas')
		].join(' y ');
		return months.length === 1 ? `${parts} en ${formatPeriod(months[0])}` : parts;
	});
	const entityHref = (item: Abstention) =>
		monthStore.href(
			item.entity_kind === 'group'
				? `/group/${item.group_id}`
				: `/group/${item.group_id}/company/${item.entity_id}`,
			item.month
		);
</script>

<Card.Root data-testid="receipt-abstentions">
	<Card.Header>
		<Card.Description>
			{#if abstentions.length > 0}Sin veredicto: {summary}{:else}Último cierre de la exportación{/if}
		</Card.Description>
		<h2 id="receipt-abstentions-heading" class="leading-6 font-semibold">Dónde nos abstenemos</h2>
		<p class="max-w-3xl text-sm leading-6 text-muted-foreground">
			Cuando los datos no alcanzan para defender un veredicto, el motor lo dice en lugar de
			inventarlo: el número se sigue mostrando, no se disparan alertas y queda escrito qué dato
			levanta la abstención.
		</p>
	</Card.Header>
	<Card.Content class="space-y-4">
		{#if abstentions.length === 0}
			<EmptyState
				compact
				icon={CircleCheck}
				tone="success"
				title="Sin abstenciones"
				description="El motor emite veredicto para todas las entidades en el último cierre de esta exportación."
			/>
		{:else}
			{#each reasons as block (block.reason)}
				{@const open = expanded[block.reason] ?? false}
				{@const visible = open ? block.items : block.items.slice(0, PREVIEW)}
				{@const hidden = block.items.length - visible.length}
				<section
					class="overflow-hidden rounded-lg border"
					aria-label={block.text}
					data-abstain-reason={block.reason}
				>
					<div
						class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-[var(--warning)]/30 bg-[var(--warning-soft)] px-4 py-3"
					>
						<p class="flex items-start gap-2 text-sm leading-6 font-semibold">
							<PauseCircle
								class="mt-1 size-4 shrink-0 text-[var(--warning-strong)]"
								aria-hidden="true"
							/>
							{block.text}
						</p>
						<Badge variant="outline" class={TONE_BADGE.warning}>
							{plural(block.items.length, 'entidad', 'entidades')}
						</Badge>
					</div>
					<div
						class="hidden gap-x-6 border-b px-4 py-2 md:grid md:grid-cols-[minmax(0,19rem)_1fr]"
						aria-hidden="true"
					>
						<span class="metric-label mb-0">Entidad</span>
						<span class="metric-label mb-0">Qué lo desbloquea</span>
					</div>
					<ul class="divide-y" id={`abstentions-${block.reason}`}>
						{#each visible as item (`${item.entity_kind}:${item.entity_id}:${item.month}`)}
							<li
								class="grid gap-x-6 gap-y-1 px-4 py-3 md:grid-cols-[minmax(0,19rem)_1fr] md:items-center"
								data-abstention={item.entity_id}
							>
								<a
									href={entityHref(item)}
									class="group flex items-center gap-2 rounded-md text-sm hover:underline"
								>
									<span class="font-data font-medium">{item.entity_id}</span>
									<span class="text-xs text-muted-foreground">
										{item.entity_kind === 'group' ? 'grupo' : `empresa de ${item.group_id}`}
										{#if months.length > 1}· {formatPeriod(item.month)}{/if}
									</span>
									<ChevronRight
										class="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
										aria-hidden="true"
									/>
								</a>
								<p class="flex items-start gap-2 text-sm leading-6">
									<KeyRound
										class="mt-1 size-4 shrink-0 text-[var(--warning-strong)]"
										aria-hidden="true"
									/>
									<span
										><span class="sr-only">Qué lo desbloquea: </span>{humanizeMonths(
											item.unlock
										)}</span
									>
								</p>
							</li>
						{/each}
					</ul>
					{#if block.items.length > PREVIEW}
						<div class="border-t px-2 py-1.5">
							<Button
								variant="ghost"
								size="sm"
								aria-expanded={open}
								aria-controls={`abstentions-${block.reason}`}
								onclick={() => (expanded[block.reason] = !open)}
							>
								{open
									? 'Ver menos'
									: `Ver ${hidden === 1 ? 'la entidad restante' : `las ${formatNumber(hidden)} entidades restantes`}`}
							</Button>
						</div>
					{/if}
				</section>
			{/each}
		{/if}
	</Card.Content>
</Card.Root>
