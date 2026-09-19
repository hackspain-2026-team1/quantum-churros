<script lang="ts">
	import { formatNumber, formatSigned } from '$lib/format.js';

	// `score` and `delta` are score points (tenths / 10); null = not observed that month.
	let {
		score: rawScore,
		label = 'Score',
		delta = 0
	}: { score: number | null; label?: string; delta?: number | null } = $props();
	const score = $derived(rawScore ?? 0);
	const text = $derived(rawScore === null ? '—' : formatNumber(rawScore, 1));
</script>

<div
	class="relative grid size-36 place-items-center rounded-full"
	style={`background: conic-gradient(var(--signal) ${score * 3.6}deg, var(--muted) 0deg)`}
	aria-label={`${label}: ${text} sobre 100`}
>
	<div
		class="grid size-[7.6rem] place-items-center rounded-full bg-card shadow-[inset_0_0_0_1px_var(--border)]"
	>
		<div class="text-center">
			<div class="font-data text-4xl font-semibold tracking-[-0.06em]">{text}</div>
			<div
				class="mt-1 text-[0.67rem] font-semibold tracking-[0.18em] text-muted-foreground uppercase"
			>
				{label}
			</div>
			{#if delta}<div
					class:positive={delta > 0}
					class:negative={delta < 0}
					class="font-data mt-1 text-xs font-semibold"
				>
					{formatSigned(delta, 1)}
				</div>{/if}
		</div>
	</div>
</div>
