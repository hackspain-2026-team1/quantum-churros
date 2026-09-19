<script lang="ts">
	import {
		ArrowDownRight,
		ArrowUpRight,
		CircleSlash,
		Combine,
		Hourglass,
		Minus
	} from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { cn } from '$lib/utils.js';
	import { DIRECTION_TEXT, NATURE_TEXT, type Direction, type Nature } from './contract.js';
	import { DIRECTION_TONE, TONE_BADGE } from './tones.js';

	let {
		direction,
		nature = null,
		shockPending = false,
		available = true,
		class: className
	}: {
		/** null = the entity was not observed that month. */
		direction: Direction | null;
		/** Shown next to the direction when the verdict has one. */
		nature?: Nature | null;
		/** verdict.shock_pending: a fall that still has to be confirmed. */
		shockPending?: boolean;
		/** false when the engine gives no verdict (abstention, short history). */
		available?: boolean;
		class?: string;
	} = $props();

	const icons = {
		improving: ArrowUpRight,
		stable: Minus,
		deteriorating: ArrowDownRight,
		perimeter_shift: Combine
	} as const;
	const pending = $derived(shockPending || nature === 'shock_pending');
	const Icon = $derived(direction ? icons[direction] : Minus);
</script>

{#if direction === null}
	<span class={cn('text-sm text-muted-foreground', className)} aria-label="Sin dato">—</span>
{:else if !available}
	<Badge variant="outline" class={cn(TONE_BADGE.neutral, className)} data-direction="unavailable">
		<CircleSlash aria-hidden="true" /> Sin veredicto
	</Badge>
{:else}
	<span class={cn('inline-flex flex-wrap items-center gap-1', className)}>
		<Badge
			variant="outline"
			class={TONE_BADGE[DIRECTION_TONE[direction]]}
			data-direction={direction}
		>
			<Icon aria-hidden="true" />
			{DIRECTION_TEXT[direction]}
		</Badge>
		{#if pending}
			<Badge variant="outline" class={TONE_BADGE.warning} data-nature="shock_pending">
				<Hourglass aria-hidden="true" />
				{NATURE_TEXT.shock_pending}
			</Badge>
		{:else if nature}
			<Badge variant="outline" data-nature={nature}>{NATURE_TEXT[nature]}</Badge>
		{/if}
	</span>
{/if}
