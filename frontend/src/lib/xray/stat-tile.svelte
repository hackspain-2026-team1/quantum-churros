<script lang="ts">
	import type { Component, Snippet } from 'svelte';
	import { cn } from '$lib/utils.js';
	import { TONE_DOT, type Tone } from './tones.js';

	let {
		label,
		value,
		hints = [],
		tone,
		icon: Icon,
		href,
		pressed,
		onclick,
		kpi,
		class: className,
		children
	}: {
		/** Short noun, sentence case. */
		label: string;
		/** Already formatted with $lib/format. */
		value: string;
		/** Short lines of context under the value. */
		hints?: string[];
		/** Coloured dot before the label; the value itself stays in ink. */
		tone?: Tone;
		icon?: Component<{ class?: string }>;
		/** Renders the tile as a link. */
		href?: string;
		/** Renders the tile as a toggle button (a filter shortcut) in this state. */
		pressed?: boolean;
		onclick?: () => void;
		/** Stable hook for tests: data-kpi on the tile, data-kpi-value on the figure. */
		kpi?: string;
		class?: string;
		/** Breakdown shown beside the figure; only for tiles that are neither link nor button. */
		children?: Snippet;
	} = $props();

	const surface =
		'min-w-0 rounded-xl border bg-card px-4 py-4 text-left text-card-foreground shadow-sm';
	const interactive = 'transition-colors hover:border-[var(--signal)]/50 hover:bg-muted/40';
</script>

{#snippet figure()}
	<span class="flex min-w-0 flex-col">
		<span class="metric-label flex items-center gap-2">
			{#if tone}
				<span class={cn('size-2 shrink-0 rounded-full', TONE_DOT[tone])} aria-hidden="true"></span>
			{/if}
			{#if Icon}<Icon class="size-3.5 shrink-0" />{/if}
			<span class="truncate">{label}</span>
		</span>
		<strong class="font-data text-3xl leading-tight font-semibold tracking-[-0.04em]" data-kpi-value
			>{value}</strong
		>
		{#each hints as hint, index (index)}
			<span class={cn('block text-xs leading-5 text-muted-foreground', index === 0 && 'mt-1')}
				>{hint}</span
			>
		{/each}
	</span>
{/snippet}

{#if href}
	<a {href} class={cn(surface, 'flex', interactive, className)} data-kpi={kpi}>{@render figure()}</a
	>
{:else if pressed !== undefined}
	<button
		type="button"
		class={cn(
			surface,
			'flex',
			interactive,
			pressed &&
				'border-[var(--signal)]/60 bg-[var(--signal-soft)]/60 hover:bg-[var(--signal-soft)]/60',
			className
		)}
		aria-pressed={pressed}
		data-kpi={kpi}
		{onclick}
	>
		{@render figure()}
	</button>
{:else}
	<div class={cn(surface, 'flex items-center gap-5', className)} data-kpi={kpi}>
		{@render figure()}
		{#if children}<div class="min-w-0 flex-1">{@render children()}</div>{/if}
	</div>
{/if}
