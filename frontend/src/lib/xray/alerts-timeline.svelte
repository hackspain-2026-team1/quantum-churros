<script lang="ts">
	import { formatAxisMonth, formatNumber, formatPeriod } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import type { MonthlyAlertCount } from './alerts.js';
	import { ALERT_STATES, type AlertState } from './contract.js';
	import { ALERT_STATE_TONE, TONE_COLOR } from './tones.js';

	let {
		counts,
		selected = null,
		onSelect,
		class: className
	}: {
		/** One entry per month of the bundle window, in order. */
		counts: MonthlyAlertCount[];
		/** Month highlighted in the chart (the month the list is scoped to), if any. */
		selected?: string | null;
		onSelect?: (month: string) => void;
		class?: string;
	} = $props();

	// Height of the tallest column, in px; every other column is proportional to it.
	const PLOT_HEIGHT = 64;
	// Stack order from the baseline up; the same in every column.
	const STACK: AlertState[] = [...ALERT_STATES];
	const LEGEND: Record<AlertState, [string, string]> = {
		fired: ['activa', 'activas'],
		suppressed: ['silenciada', 'silenciadas'],
		abstained: ['en abstención', 'en abstención']
	};

	let hovered = $state<string | null>(null);

	const peak = $derived(Math.max(0, ...counts.map((entry) => entry.total)));
	const focus = $derived(
		counts.find((entry) => entry.month === hovered) ??
			counts.find((entry) => entry.month === selected) ??
			null
	);
	const describe = (entry: MonthlyAlertCount) =>
		STACK.map(
			(state) => `${formatNumber(entry[state])} ${LEGEND[state][entry[state] === 1 ? 0 : 1]}`
		).join(', ');
	const segment = (count: number) => (peak === 0 ? 0 : Math.max(3, (count / peak) * PLOT_HEIGHT));
	// Axis labels: first, last and every January in between.
	const labelled = (index: number) =>
		index === 0 || index === counts.length - 1 || counts[index].month.endsWith('-01');
</script>

<figure class={cn('space-y-2', className)} data-testid="alerts-timeline">
	<figcaption class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
		<span class="text-sm" aria-live="polite">
			{#if focus}
				<span class="inline-block font-semibold first-letter:uppercase"
					>{formatPeriod(focus.month)}</span
				>
				<span class="text-muted-foreground">· {describe(focus)}</span>
			{:else}
				<span class="text-muted-foreground"
					>Alertas por mes: elige una columna para ver ese cierre</span
				>
			{/if}
		</span>
		<span class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
			{#each STACK as state (state)}
				<span class="inline-flex items-center gap-1.5">
					<span
						class="size-2 rounded-[2px]"
						style={`background: ${TONE_COLOR[ALERT_STATE_TONE[state]]};`}
						aria-hidden="true"
					></span>
					<span class="inline-block first-letter:uppercase">{LEGEND[state][1]}</span>
				</span>
			{/each}
		</span>
	</figcaption>

	<div>
		<div
			class="flex items-end gap-0.5 border-b"
			style={`height: ${PLOT_HEIGHT + 8}px;`}
			role="group"
			aria-label="Alertas por mes y estado"
		>
			{#each counts as entry (entry.month)}
				{@const active = entry.month === selected}
				{#if entry.total === 0}
					<span class="h-full min-w-0 flex-1" aria-hidden="true"></span>
				{:else}
					<button
						type="button"
						class={cn(
							'group/col flex h-full min-w-0 flex-1 flex-col-reverse items-center gap-0.5 rounded-t-sm pt-1 hover:bg-muted',
							active && 'bg-[var(--signal-soft)] hover:bg-[var(--signal-soft)]'
						)}
						aria-label={`${formatPeriod(entry.month)}: ${describe(entry)}`}
						aria-pressed={active}
						title={`${formatPeriod(entry.month)}: ${describe(entry)}`}
						onclick={() => onSelect?.(entry.month)}
						onpointerenter={() => (hovered = entry.month)}
						onpointerleave={() => (hovered = null)}
						onfocus={() => (hovered = entry.month)}
						onblur={() => (hovered = null)}
						data-month={entry.month}
						data-total={entry.total}
					>
						{#each STACK.filter((state) => entry[state] > 0) as state, index (state)}
							<span
								class={cn(
									'w-full max-w-5 shrink-0',
									index === STACK.filter((key) => entry[key] > 0).length - 1 && 'rounded-t-[4px]'
								)}
								style={`height: ${segment(entry[state])}px; background: ${TONE_COLOR[ALERT_STATE_TONE[state]]};`}
							></span>
						{/each}
					</button>
				{/if}
			{/each}
		</div>
		<div class="font-data mt-1 flex gap-0.5 text-[0.62rem] text-muted-foreground">
			{#each counts as entry, index (entry.month)}
				<span
					class={cn(
						'flex min-w-0 flex-1 whitespace-nowrap',
						index === 0
							? 'justify-start'
							: index === counts.length - 1
								? 'justify-end'
								: 'justify-center',
						entry.month === selected && 'font-bold text-foreground'
					)}
				>
					{#if labelled(index) || entry.month === selected}{formatAxisMonth(entry.month)}{/if}
				</span>
			{/each}
		</div>
	</div>
</figure>
