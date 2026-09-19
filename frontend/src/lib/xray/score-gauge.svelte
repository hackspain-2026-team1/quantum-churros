<script lang="ts">
	import { formatScore, formatScoreDelta } from '$lib/format.js';
	import type { Band } from './contract.js';
	import { BAND_TONE, TONE_COLOR } from './tones.js';

	let {
		tenths,
		label = 'Score',
		band = null,
		deltaTenths = null,
		abstained = false
	}: {
		/** Displayed score ('shown') in integer tenths; null = not observed. */
		tenths: number | null;
		label?: string;
		/** Colours the ring with the band tone. */
		band?: Band | null;
		/** Change against the comparison month, in tenths (verdict.delta3). */
		deltaTenths?: number | null;
		/** The engine abstains: the number stays visible but the ring is muted. */
		abstained?: boolean;
	} = $props();

	const color = $derived(
		abstained || tenths === null
			? 'var(--muted-foreground)'
			: band
				? TONE_COLOR[BAND_TONE[band]]
				: 'var(--signal)'
	);
	const degrees = $derived(tenths === null ? 0 : (tenths / 1000) * 360);
	const spoken = $derived(
		tenths === null ? `${label}: sin dato` : `${label}: ${formatScore(tenths)} sobre 100`
	);
</script>

<div
	class="relative grid size-36 shrink-0 place-items-center rounded-full"
	class:opacity-70={abstained}
	style={`background: conic-gradient(${color} ${degrees}deg, var(--muted) 0deg)`}
	role="img"
	aria-label={abstained ? `${spoken}, en abstención` : spoken}
>
	<div
		class="grid size-[7.6rem] place-items-center rounded-full bg-card shadow-[inset_0_0_0_1px_var(--border)]"
	>
		<div class="text-center">
			<div
				class="font-data text-4xl font-semibold tracking-[-0.06em]"
				class:text-muted-foreground={abstained || tenths === null}
			>
				{tenths === null ? '—' : formatScore(tenths)}
			</div>
			<div
				class="mt-1 text-[0.67rem] font-semibold tracking-[0.18em] text-muted-foreground uppercase"
			>
				{label}
			</div>
			{#if abstained}
				<div
					class="mt-1 text-[0.6rem] font-semibold tracking-[0.14em] text-[var(--warning-strong)] uppercase"
				>
					Abstención
				</div>
			{:else if deltaTenths !== null && deltaTenths !== 0}
				<div
					class:positive={deltaTenths > 0}
					class:negative={deltaTenths < 0}
					class="font-data mt-1 text-xs font-semibold"
				>
					{formatScoreDelta(deltaTenths)}
				</div>
			{/if}
		</div>
	</div>
</div>
