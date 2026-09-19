<script lang="ts">
	import { page } from '$app/state';
	import { formatNumber, formatScore } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import { fromTenths } from './contract.js';
	import { SCORE_MAX, bandZones } from './explain.js';
	import { BAND_TONE, TONE_COLOR } from './tones.js';

	let {
		tenths,
		baseTenths = null,
		muted = false,
		class: className
	}: {
		/** Displayed score in integer tenths. */
		tenths: number;
		/** Reference starting point of the waterfall (entry.base), drawn as a tick. */
		baseTenths?: number | null;
		/** Greys the score marker, e.g. while the engine abstains. */
		muted?: boolean;
		class?: string;
	} = $props();

	// Thresholds and labels come from manifest.bands: nothing about 40-60-80 is written here.
	const zones = $derived(bandZones(page.data.manifest?.bands ?? []));
	// Thresholds read as whole points when they are: '40', not '40,0'.
	const threshold = (value: number) => formatNumber(fromTenths(value), value % 10 === 0 ? 0 : 1);
	const percent = (value: number) => (Math.min(Math.max(value, 0), SCORE_MAX) / SCORE_MAX) * 100;
	const active = $derived(
		zones.find((zone) => tenths >= zone.min && tenths < zone.max) ?? zones[zones.length - 1]
	);
	const spoken = $derived(
		`Escala de bandas: ${zones
			.map((zone) => `${zone.label} desde ${threshold(zone.min)}`)
			.join(', ')}. Score ${formatScore(tenths)}${active ? `, en ${active.label}` : ''}.`
	);
</script>

{#if zones.length > 0}
	<div class={cn('space-y-1', className)} role="img" aria-label={spoken} data-testid="band-scale">
		<div class="relative h-6" aria-hidden="true">
			<span
				class={cn(
					'font-data absolute bottom-0 -translate-x-1/2 rounded-md px-1.5 py-0.5 text-[0.7rem] leading-none font-semibold text-white',
					muted && 'opacity-70'
				)}
				style={`left: clamp(1.4rem, ${percent(tenths)}%, calc(100% - 1.4rem)); background: ${
					muted || !active ? 'var(--muted-foreground)' : TONE_COLOR[BAND_TONE[active.key]]
				}`}>{formatScore(tenths)}</span
			>
		</div>
		<div class="relative" aria-hidden="true">
			<div class="flex h-2 gap-0.5">
				{#each zones as zone (zone.key)}
					<span
						class="h-full first:rounded-l-full last:rounded-r-full"
						style={`width: ${percent(zone.max) - percent(zone.min)}%; background: ${TONE_COLOR[BAND_TONE[zone.key]]}; opacity: ${zone.key === active?.key ? 1 : 0.22}`}
					></span>
				{/each}
			</div>
			<span
				class="absolute -top-1 h-4 w-0.5 -translate-x-1/2 rounded-full bg-[var(--ink)] ring-2 ring-[var(--card)]"
				style={`left: ${percent(tenths)}%`}
			></span>
			{#if baseTenths !== null}
				<span
					class="absolute -top-0.5 size-3 -translate-x-1/2 rotate-45 rounded-[2px] border-2 border-[var(--ink)] bg-[var(--card)]"
					style={`left: ${percent(baseTenths)}%`}
				></span>
			{/if}
		</div>
		<div class="relative h-8 text-[0.62rem] text-muted-foreground" aria-hidden="true">
			{#each zones as zone (zone.key)}
				<span
					class="font-data absolute top-0 -translate-x-1/2 first:translate-x-0"
					style={`left: ${percent(zone.min)}%`}>{threshold(zone.min)}</span
				>
				<span
					class={cn(
						'absolute top-3.5 -translate-x-1/2 truncate font-semibold tracking-[0.03em] uppercase',
						zone.key === active?.key && 'text-foreground'
					)}
					style={`left: ${(percent(zone.min) + percent(zone.max)) / 2}%; max-width: ${percent(zone.max) - percent(zone.min)}%`}
					>{zone.label}</span
				>
			{/each}
			<span class="font-data absolute top-0 right-0">{threshold(SCORE_MAX)}</span>
		</div>
	</div>
{/if}
