<script lang="ts">
	import { FileSearch } from '@lucide/svelte';
	import { page } from '$app/state';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import { formatPercent, formatScore, formatScoreDelta } from '$lib/format.js';
	import type { EntityMonth } from './contract.js';
	import { glossaryText, pillarLabel } from './labels.js';

	let { entry }: { entry: EntityMonth } = $props();

	const manifest = $derived(page.data.manifest);
	// Largest absolute contribution first: what moves the score the most reads first.
	const drivers = $derived(
		[...entry.pillars].sort((a, b) => Math.abs(b.contrib) - Math.abs(a.contrib))
	);
	const scale = $derived(Math.max(1, ...entry.pillars.map((pillar) => Math.abs(pillar.contrib))));
	const baseline = (key: string) => manifest?.pillars.find((item) => item.key === key)?.baseline;
	const verb = (contrib: number) => (contrib > 0 ? 'aporta' : contrib < 0 ? 'resta' : 'no mueve');
</script>

<div class="grid gap-3 lg:grid-cols-2" data-testid="pillar-drivers">
	{#each drivers as driver (driver.key)}
		{@const reference = baseline(driver.key)}
		<Card.Root class="overflow-hidden" data-pillar={driver.key}
			><Card.Header class="pb-3"
				><div class="flex items-start justify-between gap-4">
					<div>
						<Card.Description
							>Pilar · {verb(driver.contrib)} · peso efectivo {formatPercent(
								driver.w_eff,
								0
							)}</Card.Description
						><Card.Title class="text-base">{pillarLabel(manifest, driver.key)}</Card.Title>
					</div>
					<span
						class:positive={driver.contrib > 0}
						class:negative={driver.contrib < 0}
						class="font-data text-xl font-semibold">{formatScoreDelta(driver.contrib)}</span
					>
				</div></Card.Header
			><Card.Content class="space-y-3"
				><Progress
					value={Math.min(100, (Math.abs(driver.contrib) / scale) * 100)}
					class={driver.contrib < 0
						? '[&_[data-slot=progress-indicator]]:bg-[var(--danger)]'
						: '[&_[data-slot=progress-indicator]]:bg-[var(--success)]'}
				/>
				<div class="grid grid-cols-2 gap-3 text-sm">
					<div>
						<span class="metric-label">Observado</span><strong class="font-data"
							>{driver.score === null ? 'Sin dato' : formatScore(driver.score)}</strong
						>
					</div>
					<div>
						<span class="metric-label">Referencia</span><strong class="font-data"
							>{reference === undefined ? '—' : formatScore(reference)}</strong
						>
					</div>
				</div>
				{#if driver.note}
					<p class="flex gap-2 text-sm leading-6 text-muted-foreground">
						<FileSearch class="mt-1 size-4 shrink-0" />{driver.note}
					</p>
				{/if}
				{#each driver.gates as gate (gate)}
					<p class="text-xs leading-5 text-muted-foreground">
						{glossaryText(manifest, 'gates', gate)}
					</p>
				{/each}</Card.Content
			></Card.Root
		>
	{/each}
</div>
