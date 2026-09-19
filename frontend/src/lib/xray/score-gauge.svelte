<script lang="ts">
	import { formatNumber } from '$lib/format.js';

	let {
		score,
		label = 'Score',
		delta = 0
	}: { score: number; label?: string; delta?: number } = $props();
	const scoreLabel = $derived(formatNumber(score, Number.isInteger(score) ? 0 : 2));
	const deltaLabel = $derived(
		`${delta > 0 ? '+' : ''}${formatNumber(delta, Number.isInteger(delta) ? 0 : 2)}`
	);
</script>

<div
	class="relative grid size-36 place-items-center rounded-full"
	style={`background: conic-gradient(var(--signal) ${score * 3.6}deg, var(--muted) 0deg)`}
	aria-label={`${label}: ${scoreLabel} sobre 100`}
>
	<div
		class="grid size-[7.6rem] place-items-center rounded-full bg-card shadow-[inset_0_0_0_1px_var(--border)]"
	>
		<div class="text-center">
			<div class="font-data text-4xl font-semibold tracking-[-0.06em]">{scoreLabel}</div>
			<div
				class="mt-1 text-[0.67rem] font-semibold tracking-[0.18em] text-muted-foreground uppercase"
			>
				{label}
			</div>
			{#if delta !== 0}<div
					class:positive={delta > 0}
					class:negative={delta < 0}
					class="font-data mt-1 text-xs font-semibold"
				>
					{deltaLabel}
				</div>{/if}
		</div>
	</div>
</div>
