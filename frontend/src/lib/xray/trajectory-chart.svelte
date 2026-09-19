<script lang="ts">
	import * as ToggleGroup from '$lib/components/ui/toggle-group/index.js';
	import { formatNumber } from '$lib/format.js';

	type ChartMetric = {
		value: string;
		label: string;
		unit?: string;
		format?: (value: number) => string;
	};

	let {
		values,
		projected = [],
		months = [],
		changeIndex = 8,
		compact = false,
		metrics = [],
		metricLabel = 'Score de salud',
		unit = '',
		activeMetric = $bindable<string | undefined>(undefined)
	}: {
		values: number[];
		projected?: number[];
		months?: string[];
		changeIndex?: number;
		compact?: boolean;
		metrics?: ChartMetric[];
		metricLabel?: string;
		unit?: string;
		activeMetric?: string;
	} = $props();
	const width = 760;
	let height = $derived(compact ? 150 : 230);
	const pad = 22;
	let selected = $derived(activeMetric ?? metrics[0]?.value);
	let currentMetric = $derived(metrics.find((metric) => metric.value === selected));
	let currentLabel = $derived(currentMetric?.label ?? metricLabel);
	let currentUnit = $derived(currentMetric?.unit ?? unit);
	const formatValue = (value: number) =>
		currentMetric?.format
			? currentMetric.format(value)
			: `${formatNumber(value, 2)}${currentUnit ? `\u00A0${currentUnit}` : ''}`;
	let all = $derived([...values, ...projected]);
	let min = $derived(Math.min(...all) - 4);
	let max = $derived(Math.max(...all) + 4);
	let total = $derived(Math.max(2, all.length - 1));
	const x = (index: number) => pad + (index / total) * (width - pad * 2);
	const y = (value: number) => height - pad - ((value - min) / (max - min)) * (height - pad * 2);
	let observedPoints = $derived(values.map((value, index) => `${x(index)},${y(value)}`).join(' '));
	let projectedPoints = $derived(
		projected.length
			? [
					`${x(values.length - 1)},${y(values.at(-1) ?? 0)}`,
					...projected.map((value, index) => `${x(values.length + index)},${y(value)}`)
				].join(' ')
			: ''
	);
	const shortMonth = (month: string) => {
		const [year, m] = month.split('-');
		return `${m}/${year.slice(2)}`;
	};
	const pointLabel = (index: number) => {
		if (index < months.length) return shortMonth(months[index]);
		if (months.length) {
			const last = months[months.length - 1];
			const [y0, m0] = last.split('-').map(Number);
			const offset = index - months.length;
			const year = y0 + Math.floor((m0 - 1 + offset) / 12);
			const month = (((m0 - 1 + offset) % 12) + 1).toString().padStart(2, '0');
			return `${month}/${String(year).slice(2)}`;
		}
		return `M${index + 1}`;
	};
	let ticks = $derived.by(() => {
		const step = Math.max(1, Math.ceil(all.length / 8));
		return all
			.map((_, index) => index)
			.filter((index) => index % step === 0 || index === all.length - 1);
	});
	let hoverIndex = $state<number | null>(null);
	const valueAt = (index: number) => all[index];
	const pointHint = (index: number) =>
		index < values.length ? pointLabel(index) : `${pointLabel(index)} (proy.)`;

	function onMove(event: PointerEvent) {
		const target = event.currentTarget as SVGSVGElement;
		const rect = target.getBoundingClientRect();
		const relX = ((event.clientX - rect.left) / rect.width) * width;
		const index = Math.round(((relX - pad) / (width - pad * 2)) * total);
		hoverIndex = Math.min(Math.max(0, Math.min(index, all.length - 1)), all.length - 1);
	}
</script>

<div class="space-y-2">
	<div class="flex items-center justify-between gap-3">
		{#if metrics.length > 1}
			<div class="flex items-center gap-2">
				<span class="metric-label">Métrica</span>
				<ToggleGroup.Root
					type="single"
					variant="outline"
					size="sm"
					bind:value={selected}
					aria-label="Seleccionar métrica"
				>
					{#each metrics as metric (metric.value)}
						<ToggleGroup.Item value={metric.value}>{metric.label}</ToggleGroup.Item>
					{/each}
				</ToggleGroup.Root>
			</div>
		{:else}
			<span class="metric-label">{currentLabel}</span>
		{/if}
		{#if currentUnit}
			<span class="text-xs text-muted-foreground">Unidad · {currentUnit}</span>
		{/if}
	</div>
	<div
		class="chart relative w-full overflow-visible rounded-xl bg-[linear-gradient(to_bottom,transparent_24%,var(--border)_25%,transparent_26%,transparent_49%,var(--border)_50%,transparent_51%,transparent_74%,var(--border)_75%,transparent_76%)]"
	>
		<svg
			viewBox={`0 0 ${width} ${height}`}
			role="img"
			aria-label={`Trayectoria de ${currentLabel} observada y proyectada`}
			class="block w-full"
			onpointermove={onMove}
			onpointerleave={() => (hoverIndex = null)}
		>
			<line x1={x(changeIndex)} x2={x(changeIndex)} y1="10" y2={height - 10} class="change-line" />
			<polyline points={observedPoints} fill="none" class="observed-line" />
			{#if projectedPoints}<polyline
					points={projectedPoints}
					fill="none"
					class="projected-line"
				/>{/if}
			{#each values as value, index (index)}
				<circle
					cx={x(index)}
					cy={y(value)}
					r={index === values.length - 1 ? 5 : 2.5}
					class="observed-dot"
				/>
			{/each}
			{#if hoverIndex !== null}
				<line
					x1={x(hoverIndex)}
					x2={x(hoverIndex)}
					y1="10"
					y2={height - pad + 4}
					class="hover-line"
				/>
				<circle cx={x(hoverIndex)} cy={y(valueAt(hoverIndex))} r="5" class="hover-dot" />
			{/if}
			<text x={x(changeIndex) + 8} y="22" class="change-label">Cambio detectado</text>
			<text x={x(values.length - 1) - 5} y={y(values.at(-1) ?? 0) - 12} class="value-label"
				>{formatValue(values.at(-1) ?? 0)}</text
			>
			{#each ticks as index (index)}
				<text x={x(index)} y={height - 8} class="axis-label" text-anchor="middle"
					>{pointLabel(index)}</text
				>
			{/each}
		</svg>
		{#if hoverIndex !== null}
			<div
				class="hover-tooltip pointer-events-none absolute z-10 rounded-md border bg-background px-2 py-1 text-xs shadow-md"
				style={`left: ${(x(hoverIndex) / width) * 100}%; top: ${(y(valueAt(hoverIndex)) / height) * 100}%; transform: translate(${
					hoverIndex >= all.length / 2 ? 'calc(-100% - 8px)' : '8px'
				}, -50%);`}
			>
				<span class="font-semibold">{pointHint(hoverIndex)}</span>
				<span class="font-data ml-2 font-semibold">{formatValue(valueAt(hoverIndex))}</span>
			</div>
		{/if}
	</div>
</div>

<style>
	.chart:hover .hover-line {
		opacity: 1;
	}
	.observed-line {
		stroke: var(--signal);
		stroke-width: 3.5;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.projected-line {
		stroke: var(--success);
		stroke-width: 3;
		stroke-dasharray: 8 7;
		stroke-linecap: round;
	}
	.observed-dot {
		fill: var(--card);
		stroke: var(--signal);
		stroke-width: 2;
	}
	.change-line {
		stroke: var(--warning);
		stroke-width: 1.5;
		stroke-dasharray: 4 5;
	}
	.change-label,
	.value-label {
		fill: var(--foreground);
		font-family: var(--font-data);
		font-size: 12px;
		font-weight: 650;
	}
	.axis-label {
		fill: var(--muted-foreground);
		font-family: var(--font-data);
		font-size: 10px;
	}
	.hover-line {
		stroke: var(--foreground);
		stroke-width: 1;
		opacity: 0.35;
	}
	.hover-dot {
		fill: var(--signal);
		stroke: var(--card);
		stroke-width: 2;
	}
</style>
