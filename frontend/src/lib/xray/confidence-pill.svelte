<script lang="ts">
	import { ShieldAlert, ShieldCheck, ShieldQuestion } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { formatPercent } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import { CONF_TEXT, type ConfLabel } from './contract.js';
	import { CONF_TONE, TONE_BADGE } from './tones.js';

	let {
		label,
		value = null,
		compact = false,
		class: className
	}: {
		/** conf.label; null = the entity was not observed that month. */
		label: ConfLabel | null;
		/** conf.value (0-1), shown as a percentage when given. */
		value?: number | null;
		/** Drops the word 'Confianza' for table cells that already have that header. */
		compact?: boolean;
		class?: string;
	} = $props();

	const icons = { high: ShieldCheck, medium: ShieldQuestion, low: ShieldAlert } as const;
	const Icon = $derived(label ? icons[label] : ShieldQuestion);
	const text = $derived(
		label ? (compact ? CONF_TEXT[label] : `Confianza ${CONF_TEXT[label].toLowerCase()}`) : null
	);
</script>

{#if label && text}
	<!-- Confidence sits beside the score; it never changes it. -->
	<Badge
		variant="outline"
		class={cn(TONE_BADGE[CONF_TONE[label]], label === 'low' && 'border-dashed', className)}
		title="La confianza acompaña al score y no lo modifica"
		data-confidence={label}
	>
		<Icon aria-hidden="true" />
		{text}{#if value !== null}<span class="font-data"> · {formatPercent(value, 0)}</span>{/if}
	</Badge>
{:else}
	<span class={cn('text-sm text-muted-foreground', className)} aria-label="Sin dato">—</span>
{/if}
