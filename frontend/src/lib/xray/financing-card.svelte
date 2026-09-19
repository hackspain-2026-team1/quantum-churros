<script lang="ts">
	import { Banknote, Landmark, LineChart } from '@lucide/svelte';
	import { formatMoney, formatScore, formatScoreDelta } from '$lib/format.js';
	import type { EntityMonth } from './contract.js';

	let { entry }: { entry: EntityMonth } = $props();

	const items = $derived(entry.financing ?? []);

	const ICONS: Record<string, typeof Landmark> = {
		factoring: Banknote,
		confirming: Landmark,
		line: LineChart,
		restructure: Landmark,
		sweep: Banknote
	};
</script>

{#if items.length > 0}
	<section class="space-y-3" aria-labelledby="financing-heading" data-testid="financing">
		<div>
			<p class="eyebrow">Cuando la gestión no alcanza</p>
			<h2 id="financing-heading" class="text-xl font-semibold tracking-[-0.02em]">
				Financiación a medida
			</h2>
		</div>
		<ul class="space-y-3">
			{#each items as item (item.id)}
				<li class="rounded-lg border p-4">
					<div class="flex flex-wrap items-center justify-between gap-2">
						<p class="font-medium">{item.title}</p>
						<span class="inline-flex items-center gap-1.5 text-sm text-[var(--success)] tabular-nums">
							{formatScoreDelta(item.uplift_tenths)} → {formatScore(item.new_score_tenths)}
						</span>
					</div>
					<p class="mt-1 text-sm text-muted-foreground">{item.detail}</p>
					{#if item.amount !== null}
						<p class="mt-2 text-xs text-muted-foreground tabular-nums">
							Importe del instrumento: {formatMoney(item.amount)}
						</p>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}
