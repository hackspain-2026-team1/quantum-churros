<script lang="ts">
	import { page } from '$app/state';
	import { formatNumber, formatPercent } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import type { Band } from './contract.js';
	import { bandLabel } from './labels.js';
	import { BAND_TONE, TONE_COLOR, TONE_DOT } from './tones.js';

	let {
		bands,
		active = 'all',
		onToggle,
		class: className
	}: {
		/** Groups per band in the month, in contract order (critical -> solid). */
		bands: { key: Band; count: number }[];
		/** Band the table is filtered by. */
		active?: Band | 'all';
		/** Makes every legend entry a filter toggle. */
		onToggle?: (band: Band) => void;
		class?: string;
	} = $props();

	const total = $derived(bands.reduce((sum, entry) => sum + entry.count, 0));
	const entries = $derived(
		bands.map((entry) => ({
			...entry,
			label: bandLabel(page.data.manifest, entry.key),
			share: total > 0 ? entry.count / total : 0
		}))
	);
	const legendItem =
		'-mx-1.5 flex w-[calc(100%+0.75rem)] items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-xs';
	const summary = $derived(
		entries.map((entry) => `${entry.label}: ${formatNumber(entry.count)}`).join(', ')
	);
</script>

{#snippet legendEntry(entry: { key: Band; label: string; count: number })}
	<span
		class={cn('size-2 shrink-0 rounded-full', TONE_DOT[BAND_TONE[entry.key]])}
		aria-hidden="true"
	></span>
	<span class="truncate text-muted-foreground">{entry.label}</span>
	<span class="font-data ml-auto font-semibold tabular-nums">{formatNumber(entry.count)}</span>
{/snippet}

<div class={cn('space-y-2', className)} data-testid="band-distribution">
	<!-- Part-to-whole bar: a 2px gap of surface separates the segments, no strokes. -->
	<div class="flex h-2.5 w-full gap-0.5" role="img" aria-label={`Grupos por banda. ${summary}`}>
		{#if total === 0}
			<span class="h-full w-full rounded-full bg-muted"></span>
		{:else}
			{#each entries.filter((entry) => entry.count > 0) as entry (entry.key)}
				<span
					class={cn(
						'h-full min-w-1.5 transition-opacity first:rounded-l-full last:rounded-r-full',
						active !== 'all' && active !== entry.key && 'opacity-30'
					)}
					style={`flex: ${entry.count} 1 0%; background: ${TONE_COLOR[BAND_TONE[entry.key]]};`}
					title={`${entry.label}: ${formatNumber(entry.count)} (${formatPercent(entry.share, 0)})`}
				></span>
			{/each}
		{/if}
	</div>
	<ul class="grid grid-cols-2 gap-x-4">
		{#each entries as entry (entry.key)}
			<li>
				{#if onToggle}
					<button
						type="button"
						aria-pressed={active === entry.key}
						onclick={() => onToggle(entry.key)}
						title={`Filtrar la tabla por ${entry.label.toLowerCase()}`}
						class={cn(
							legendItem,
							'hover:bg-muted',
							active === entry.key && 'bg-[var(--signal-soft)] hover:bg-[var(--signal-soft)]'
						)}
						data-band-count={entry.key}
					>
						{@render legendEntry(entry)}
					</button>
				{:else}
					<span class={legendItem} data-band-count={entry.key}>{@render legendEntry(entry)}</span>
				{/if}
			</li>
		{/each}
	</ul>
</div>
