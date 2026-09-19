<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { cn } from '$lib/utils.js';
	import type { Band } from './contract.js';
	import { bandLabel } from './labels.js';
	import { BAND_TONE, TONE_BADGE, TONE_DOT } from './tones.js';

	let {
		band,
		label,
		class: className
	}: {
		/** null = the entity was not observed that month. */
		band: Band | null;
		/** Overrides the manifest label of the band. */
		label?: string;
		class?: string;
	} = $props();

	const text = $derived(band ? (label ?? bandLabel(page.data.manifest, band)) : null);
</script>

{#if band && text}
	<Badge variant="outline" class={cn(TONE_BADGE[BAND_TONE[band]], className)} data-band={band}>
		<span class={cn('size-1.5 rounded-full', TONE_DOT[BAND_TONE[band]])} aria-hidden="true"></span>
		{text}
	</Badge>
{:else}
	<span class={cn('text-sm text-muted-foreground', className)} aria-label="Sin dato">—</span>
{/if}
