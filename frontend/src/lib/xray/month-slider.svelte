<script lang="ts">
	import { ChevronLeft, ChevronRight, History } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Slider } from '$lib/components/ui/slider/index.js';
	import { formatPeriod, formatPeriodShort } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import { monthStore } from './month-store.svelte.js';

	let {
		label = 'Mes de análisis',
		class: className
	}: {
		/** Visible and accessible name of the control. */
		label?: string;
		class?: string;
	} = $props();

	const uid = $props.id();
	const months = $derived(monthStore.months);
	const last = $derived(Math.max(0, months.length - 1));
	const period = $derived(monthStore.month ? formatPeriod(monthStore.month) : '');
</script>

{#if months.length > 0}
	<div class={cn('rounded-xl border bg-card px-4 py-3', className)} data-month={monthStore.month}>
		<div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
			<div>
				<span class="metric-label" id={`${uid}-label`}>{label}</span>
				<strong class="block text-base first-letter:uppercase" aria-live="polite">{period}</strong>
			</div>
			<div class="flex items-center gap-1">
				{#if !monthStore.isLatest}
					<Button variant="ghost" size="sm" onclick={() => monthStore.select(monthStore.latest)}>
						<History /> Último cierre
					</Button>
				{/if}
				<Button
					variant="outline"
					size="icon-sm"
					aria-label="Mes anterior"
					disabled={monthStore.index <= 0}
					onclick={() => monthStore.step(-1)}><ChevronLeft /></Button
				>
				<Button
					variant="outline"
					size="icon-sm"
					aria-label="Mes siguiente"
					disabled={monthStore.index >= last}
					onclick={() => monthStore.step(1)}><ChevronRight /></Button
				>
			</div>
		</div>
		{#if months.length > 1}
			<Slider
				type="single"
				class="mt-3 py-1.5"
				min={0}
				max={last}
				step={1}
				value={monthStore.index}
				onValueChange={(index: number) => monthStore.selectIndex(index)}
				thumbProps={{ 'aria-labelledby': `${uid}-label`, 'aria-valuetext': period }}
			/>
			<div class="font-data mt-1 flex justify-between text-[0.68rem] text-muted-foreground">
				<span>{formatPeriodShort(months[0])}</span>
				<span>{formatPeriodShort(months[last])}</span>
			</div>
		{/if}
	</div>
{/if}
