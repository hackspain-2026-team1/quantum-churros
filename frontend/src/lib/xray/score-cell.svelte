<script lang="ts">
	import { formatScore } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import type { Band } from './contract.js';
	import { BAND_TONE, TONE_DOT } from './tones.js';

	let {
		tenths,
		band = null,
		size = 'md',
		muted = false,
		class: className
	}: {
		/** Displayed score ('shown') in integer tenths; null = not observed. */
		tenths: number | null;
		/** Adds a band-coloured dot before the number. */
		band?: Band | null;
		size?: 'sm' | 'md' | 'lg' | 'xl';
		/** Greys the number, e.g. while the engine abstains. */
		muted?: boolean;
		class?: string;
	} = $props();

	const sizes = {
		sm: 'text-sm',
		md: 'text-xl',
		lg: 'text-3xl tracking-[-0.04em]',
		xl: 'text-5xl tracking-[-0.06em]'
	} as const;
</script>

{#if tenths === null}
	<span class={cn('font-data text-muted-foreground', sizes[size], className)} aria-label="Sin score"
		>—</span
	>
{:else}
	<span
		class={cn(
			'font-data inline-flex items-center gap-2 font-semibold tabular-nums',
			sizes[size],
			muted && 'text-muted-foreground',
			className
		)}
		aria-label={`Score ${formatScore(tenths)} sobre 100`}
		data-score-tenths={tenths}
	>
		{#if band}
			<span class={cn('size-2 shrink-0 rounded-full', TONE_DOT[BAND_TONE[band]])} aria-hidden="true"
			></span>
		{/if}
		{formatScore(tenths)}
	</span>
{/if}
