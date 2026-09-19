<script lang="ts">
	import { Ban, Scale } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatNumber, formatPercent } from '$lib/format.js';
	import type { Receipt } from './contract.js';
	import EmptyState from './empty-state.svelte';

	let { signals }: { signals: Receipt['signals'] } = $props();

	const weighted = $derived(signals.filter((signal) => signal.weight > 0));
	const unweighted = $derived(signals.filter((signal) => signal.weight === 0));
	const total = $derived(weighted.reduce((sum, signal) => sum + signal.weight, 0));
	// Whole percentages stay whole ('30 %'); anything finer keeps one decimal ('12,5 %').
	const share = (weight: number) =>
		formatPercent(weight, Math.round(weight * 1000) % 10 === 0 ? 0 : 1);
	const plural = (count: number, one: string, many: string) =>
		`${formatNumber(count)} ${count === 1 ? one : many}`;
</script>

<div class="grid gap-4 lg:grid-cols-2" data-testid="receipt-signals">
	<Card.Root>
		<Card.Header>
			<Card.Description>
				{plural(weighted.length, 'señal con peso', 'señales con peso')} · suman {share(total)}
			</Card.Description>
			<h2 id="receipt-used-heading" class="leading-6 font-semibold">
				Lo que sí entra en el número
			</h2>
		</Card.Header>
		<Card.Content>
			{#if weighted.length === 0}
				<EmptyState
					compact
					icon={Scale}
					title="Ninguna señal con peso"
					description="El recibo de esta exportación no declara los pesos del score."
				/>
			{:else}
				<ul class="space-y-4" aria-labelledby="receipt-used-heading">
					{#each weighted as signal (signal.name)}
						<li class="space-y-1.5" data-signal={signal.name} data-weight={signal.weight}>
							<div class="flex items-baseline justify-between gap-3">
								<span class="text-sm font-semibold">{signal.label}</span>
								<span class="font-data text-sm font-semibold tabular-nums"
									>{share(signal.weight)}</span
								>
							</div>
							<!-- The track is the whole score (100 %), so each bar reads as its share of it. -->
							<div class="h-2 rounded bg-muted/60" aria-hidden="true">
								<div
									class="h-full rounded-r-sm bg-[var(--signal)]"
									style={`width: ${signal.weight * 100}%`}
								></div>
							</div>
							<p class="text-xs leading-5 text-muted-foreground">{signal.why}</p>
						</li>
					{/each}
				</ul>
			{/if}
		</Card.Content>
	</Card.Root>

	<Card.Root>
		<Card.Header>
			<Card.Description>
				{#if unweighted.length === 0}
					Señales declaradas con peso 0
				{:else}
					{plural(unweighted.length, 'señal con peso 0', 'señales con peso 0')}: no mueven el score
					de ningún grupo
				{/if}
			</Card.Description>
			<h2 id="receipt-unused-heading" class="leading-6 font-semibold">
				Señales que <span
					class="underline decoration-[var(--signal)] decoration-2 underline-offset-4">no</span
				> usamos y por qué
			</h2>
		</Card.Header>
		<Card.Content>
			{#if unweighted.length === 0}
				<EmptyState
					compact
					icon={Ban}
					title="Ninguna señal con peso 0"
					description="Todas las señales que declara el motor entran en el score."
				/>
			{:else}
				<ul class="divide-y" aria-labelledby="receipt-unused-heading">
					{#each unweighted as signal (signal.name)}
						<li
							class="space-y-1 py-3 first:pt-0 last:pb-0"
							data-signal={signal.name}
							data-weight={signal.weight}
						>
							<div class="flex flex-wrap items-center justify-between gap-2">
								<span class="flex items-center gap-2 text-sm font-semibold">
									<Ban class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
									{signal.label}
								</span>
								<Badge variant="outline" class="font-data text-muted-foreground"
									>Peso {share(signal.weight)}</Badge
								>
							</div>
							<p class="text-sm leading-6 text-muted-foreground">{signal.why}</p>
						</li>
					{/each}
				</ul>
			{/if}
		</Card.Content>
	</Card.Root>
</div>
