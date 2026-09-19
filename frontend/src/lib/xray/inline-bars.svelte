<script lang="ts">
	import { formatQuantity } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import { TONE_COLOR, type Tone } from './tones.js';

	let {
		bars,
		label,
		tone = 'signal',
		max,
		format = formatQuantity,
		class: className
	}: {
		/** One horizontal bar per entry, in the order given; values may be negative. */
		bars: { label: string; value: number }[];
		/** Accessible name of the chart: what the bars measure. */
		label: string;
		tone?: Tone;
		/** Fixed upper end of the axis (1 for shares); defaults to the largest value. */
		max?: number;
		format?: (value: number) => string;
		class?: string;
	} = $props();

	// One shared axis that always contains zero, so bar lengths compare honestly.
	const low = $derived(Math.min(0, ...bars.map((bar) => bar.value)));
	const high = $derived(Math.max(0, max ?? 0, ...bars.map((bar) => bar.value)));
	const span = $derived(high - low || 1);
	const percent = (value: number) => ((value - low) / span) * 100;
</script>

<ul class={cn('space-y-1.5', className)} aria-label={label}>
	{#each bars as bar, index (index)}
		{@const from = percent(Math.min(bar.value, 0))}
		{@const to = percent(Math.max(bar.value, 0))}
		<li
			class="grid grid-cols-[minmax(4rem,7.5rem)_1fr_minmax(2.5rem,auto)] items-center gap-3 text-xs"
			data-bar={bar.label}
		>
			<span class="leading-4 text-muted-foreground">{bar.label}</span>
			<span class="relative h-4 rounded bg-muted/60" aria-hidden="true">
				{#if bar.value !== 0}
					<span
						class={cn('absolute inset-y-0.5', bar.value > 0 ? 'rounded-r-sm' : 'rounded-l-sm')}
						style={`left: ${from}%; width: max(2px, ${to - from}%); background: ${TONE_COLOR[tone]}`}
					></span>
				{/if}
				{#if low < 0}
					<span class="absolute inset-y-0 w-px bg-foreground/40" style={`left: ${percent(0)}%`}
					></span>
				{/if}
			</span>
			<span class="font-data text-right font-semibold tabular-nums">{format(bar.value)}</span>
		</li>
	{/each}
</ul>
