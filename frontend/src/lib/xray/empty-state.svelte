<script lang="ts">
	import type { Component, Snippet } from 'svelte';
	import { Inbox } from '@lucide/svelte';
	import { cn } from '$lib/utils.js';
	import { TONE_TEXT, type Tone } from './tones.js';

	let {
		title,
		description,
		icon: Icon = Inbox,
		tone = 'neutral',
		compact = false,
		class: className,
		children
	}: {
		/** What is missing. */
		title: string;
		/** What to do next, or why it is missing. */
		description?: string;
		icon?: Component<{ class?: string }>;
		tone?: Tone;
		/** Tighter padding for table bodies and cards. */
		compact?: boolean;
		class?: string;
		/** Optional actions under the text. */
		children?: Snippet;
	} = $props();
</script>

<div
	class={cn(
		'grid place-items-center rounded-xl border border-dashed bg-card/60 text-center',
		compact ? 'gap-2 px-4 py-6' : 'gap-3 px-6 py-12',
		className
	)}
	role="status"
>
	<div class={cn('grid size-10 place-items-center rounded-full bg-muted', TONE_TEXT[tone])}>
		<Icon class="size-5" />
	</div>
	<div class="max-w-md space-y-1">
		<p class="font-semibold">{title}</p>
		{#if description}<p class="text-sm leading-6 text-muted-foreground">{description}</p>{/if}
	</div>
	{#if children}<div class="flex flex-wrap justify-center gap-2">{@render children()}</div>{/if}
</div>
