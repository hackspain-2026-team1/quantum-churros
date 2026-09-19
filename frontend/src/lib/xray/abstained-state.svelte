<script lang="ts">
	import { KeyRound, PauseCircle } from '@lucide/svelte';
	import { page } from '$app/state';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { humanizeMonths } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import { glossaryText } from './labels.js';

	let {
		abstain,
		title = 'El motor se abstiene este mes',
		class: className
	}: {
		/** entityMonth.abstain or a receipt abstention: the reason code and what unlocks it. */
		abstain: { reason: string; unlock: string };
		title?: string;
		class?: string;
	} = $props();

	const reason = $derived(glossaryText(page.data.manifest, 'reasons', abstain.reason));
</script>

<Alert.Root
	class={cn('border-[var(--warning)]/40 bg-[var(--warning-soft)]', className)}
	data-abstain={abstain.reason}
>
	<PauseCircle class="size-4" />
	<Alert.Title>{title}</Alert.Title>
	<Alert.Description class="space-y-2 text-foreground/80">
		<p>{reason}</p>
		<p class="flex items-start gap-2">
			<KeyRound class="mt-0.5 size-4 shrink-0 text-[var(--warning-strong)]" aria-hidden="true" />
			<span
				><span class="font-semibold">Qué lo desbloquea:</span>
				{humanizeMonths(abstain.unlock)}</span
			>
		</p>
	</Alert.Description>
</Alert.Root>
