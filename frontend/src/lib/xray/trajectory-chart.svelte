<script lang="ts">
	import * as ToggleGroup from '$lib/components/ui/toggle-group/index.js';
	import { formatNumber } from '$lib/format.js';

	type ChartMetric = {
		value: string;
		label: string;
		unit?: string;
		format?: (value: number) => string;
	};

	/** Best / common / worst of the score three months ahead, computed by the engine. */
	type ChartScenario = {
		best: number;
		common: number;
		worst: number;
	};

	let {
		values,
		projected = [],
		months = [],
		changeIndex = null,
		changeLabel = 'Cambio detectado',
		projectedLabel = 'Objetivo',
		format,
		compact = false,
		metrics = [],
		metricLabel = 'Score de salud',
		unit = '',
		activeMetric = $bindable<string | undefined>(undefined),
		scenario = null
	}: {
		/** One value per month; null = not observed (the line breaks there). */
		values: (number | null)[];
		projected?: number[];
		months?: string[];
		/** Index of the month where the engine detected the change; no line when null. */
		changeIndex?: number | null;
		changeLabel?: string;
		/** Label of the dashed target point drawn after the last observed month. */
		projectedLabel?: string;
		format?: (value: number) => string;
		compact?: boolean;
		metrics?: ChartMetric[];
		metricLabel?: string;
		unit?: string;
		activeMetric?: string;
		/** Engine scenarios at t+3: shaded band between best and worst, no band when null. */
		scenario?: ChartScenario | null;
	} = $props();
	const width = 760;
	let height = $derived(compact ? 150 : 230);
	const pad = 22;
	let selected = $derived(activeMetric ?? metrics[0]?.value);
	let currentMetric = $derived(metrics.find((metric) => metric.value === selected));
	let currentLabel = $derived(currentMetric?.label ?? metricLabel);
	let currentUnit = $derived(currentMetric?.unit ?? unit);
	const formatValue = (value: number) =>
		(currentMetric?.format ?? format)
			? (currentMetric?.format ?? format)!(value)
			: `${formatNumber(value, 2)}${currentUnit ? `\u00A0${currentUnit}` : ''}`;
	let lastIndex = $derived(values.findLastIndex((value) => value !== null));
	let lastValue = $derived(lastIndex >= 0 ? (values[lastIndex] as number) : 0);
	let hasChange = $derived(changeIndex !== null && changeIndex >= 0 && changeIndex < values.length);
	// The scenario points sit at t+3; the axis holds one slot per future month.
	let futureSlots = $derived(Math.max(projected.length, scenario ? 3 : 0));
	let all = $derived<(number | null)[]>([
		...values,
		...Array<number | null>(futureSlots).fill(null)
	]);
	let known = $derived(
		[...values, ...projected, ...(scenario ? [scenario.best, scenario.common, scenario.worst] : [])].filter(
			(value): value is number => value !== null
		)
	);
	let spread = $derived(known.length ? Math.max(...known) - Math.min(...known) : 0);
	let margin = $derived(Math.max(spread * 0.15, Math.abs(known[0] ?? 1) * 0.04, 0.5));
	let min = $derived((known.length ? Math.min(...known) : 0) - margin);
	let max = $derived((known.length ? Math.max(...known) : 1) + margin);
	let total = $derived(Math.max(2, all.length - 1));
	const x = (index: number) => pad + (index / total) * (width - pad * 2);
	const y = (value: number) => height - pad - ((value - min) / (max - min)) * (height - pad * 2);
	// Consecutive observed months form a segment; a month without data breaks the line.
	let observedSegments = $derived.by(() => {
		const result: string[] = [];
		let current: string[] = [];
		values.forEach((value, index) => {
			if (value === null) {
				if (current.length) result.push(current.join(' '));
				current = [];
			} else current.push(`${x(index)},${y(value)}`);
		});
		if (current.length) result.push(current.join(' '));
		return result;
	});
	let projectedPoints = $derived(
		projected.length && lastIndex >= 0
			? [
					`${x(lastIndex)},${y(lastValue)}`,
					...projected.map((value, index) => `${x(values.length + index)},${y(value)}`)
				].join(' ')
			: ''
	);
	// t+3: three months after the last observed one, where the engine places the scenarios.
	let scenarioIndex = $derived(values.length + 2);
	let scenarioBand = $derived(
		scenario && lastIndex >= 0
			? `${x(lastIndex)},${y(lastValue)} ${x(scenarioIndex)},${y(scenario.best)} ${x(scenarioIndex)},${y(scenario.worst)}`
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
	const valueAt = (index: number) =>
		scenario && index === scenarioIndex ? scenario.common : all[index];
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
			<div class="flex min-w-0 items-center gap-2 overflow-x-auto">
				<span class="metric-label">Métrica</span>
				<ToggleGroup.Root
					type="single"
					variant="outline"
					size="sm"
					bind:value={selected}
					aria-label="Seleccionar métrica"
				>
					{#each metrics as metric (metric.value)}
						<ToggleGroup.Item value={metric.value} class="flex-none px-3"
							>{metric.label}</ToggleGroup.Item
						>
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
			{#if hasChange && changeIndex !== null}
				<line
					x1={x(changeIndex)}
					x2={x(changeIndex)}
					y1="10"
					y2={height - 10}
					class="change-line"
				/>
			{/if}
			{#each observedSegments as points, index (index)}
				<polyline {points} fill="none" class="observed-line" />
			{/each}
			{#if projectedPoints}<polyline
					points={projectedPoints}
					fill="none"
					class="projected-line"
				/>{/if}
			{#each values as value, index (index)}
				{#if value !== null}
					<circle
						cx={x(index)}
						cy={y(value)}
						r={index === lastIndex ? 5 : 2.5}
						class="observed-dot"
					/>
				{/if}
			{/each}
			{#if projected.length}
				{@const targetIndex = values.length + projected.length - 1}
				{@const targetValue = projected[projected.length - 1]}
				<line
					x1={pad}
					x2={width - pad}
					y1={y(targetValue)}
					y2={y(targetValue)}
					class="target-line"
				/>
				<circle cx={x(targetIndex)} cy={y(targetValue)} r="6" class="target-dot" />
				<text
					x={x(targetIndex) - 10}
					y={y(targetValue) - 12}
					class="value-label target-label"
					text-anchor="end"
					data-testid="chart-target">{projectedLabel} {formatValue(targetValue)}</text
				>
			{/if}
			{#if scenario && lastIndex >= 0}
				<polygon points={scenarioBand} class="scenario-band" />
				<line
					x1={x(lastIndex)}
					y1={y(lastValue)}
					x2={x(scenarioIndex)}
					y2={y(scenario.common)}
					class="scenario-line"
				/>
				<circle cx={x(scenarioIndex)} cy={y(scenario.best)} r="3.5" class="scenario-dot" />
				<circle cx={x(scenarioIndex)} cy={y(scenario.common)} r="4.5" class="scenario-dot common" />
				<circle cx={x(scenarioIndex)} cy={y(scenario.worst)} r="3.5" class="scenario-dot" />
				<text
					x={x(scenarioIndex) - 10}
					y={y(scenario.best) - 8}
					text-anchor="end"
					class="value-label scenario-label"
					data-testid="chart-scenario-best">Mejor {formatValue(scenario.best)}</text
				>
				<text
					x={x(scenarioIndex) - 10}
					y={y(scenario.common) + 4}
					text-anchor="end"
					class="value-label scenario-label"
					data-testid="chart-scenario-common">Común {formatValue(scenario.common)}</text
				>
				<text
					x={x(scenarioIndex) - 10}
					y={y(scenario.worst) + 16}
					text-anchor="end"
					class="value-label scenario-label"
					data-testid="chart-scenario-worst">Peor {formatValue(scenario.worst)}</text
				>
			{/if}
			{#if hoverIndex !== null}
				<line
					x1={x(hoverIndex)}
					x2={x(hoverIndex)}
					y1="10"
					y2={height - pad + 4}
					class="hover-line"
				/>
				{#if valueAt(hoverIndex) !== null}
					<circle cx={x(hoverIndex)} cy={y(valueAt(hoverIndex) ?? 0)} r="5" class="hover-dot" />
				{/if}
			{/if}
			{#if hasChange && changeIndex !== null}
				<text
					x={x(changeIndex) + (changeIndex > total * 0.7 ? -8 : 8)}
					y="22"
					text-anchor={changeIndex > total * 0.7 ? 'end' : 'start'}
					class="change-label">{changeLabel}</text
				>
			{/if}
			{#if lastIndex >= 0}
				<text
					x={x(lastIndex) - 5}
					y={y(lastValue) +
						(projected.length && projected[projected.length - 1] >= lastValue ? 20 : -12)}
					text-anchor="end"
					class="value-label">{formatValue(lastValue)}</text
				>
			{/if}
			{#each ticks as index (index)}
				<text x={x(index)} y={height - 8} class="axis-label" text-anchor="middle"
					>{pointLabel(index)}</text
				>
			{/each}
		</svg>
		{#if hoverIndex !== null}
			<div
				class="hover-tooltip pointer-events-none absolute z-10 rounded-md border bg-background px-2 py-1 text-xs shadow-md"
				style={`left: ${(x(hoverIndex) / width) * 100}%; top: ${(y(valueAt(hoverIndex) ?? (min + max) / 2) / height) * 100}%; transform: translate(${
					hoverIndex >= all.length / 2 ? 'calc(-100% - 8px)' : '8px'
				}, -50%);`}
			>
				<span class="font-semibold">{pointHint(hoverIndex)}</span>
				{#if scenario && hoverIndex === scenarioIndex}
					<span class="font-data ml-2 font-semibold"
						>Mejor {formatValue(scenario.best)} · Común {formatValue(scenario.common)} · Peor {formatValue(
							scenario.worst
						)}</span
					>
				{:else}
					<span class="font-data ml-2 font-semibold"
						>{valueAt(hoverIndex) === null ? 'Sin dato' : formatValue(valueAt(hoverIndex) ?? 0)}</span
					>
				{/if}
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
	.target-line {
		stroke: var(--success);
		stroke-width: 1;
		stroke-dasharray: 3 6;
		opacity: 0.6;
	}
	.target-dot {
		fill: var(--success);
		stroke: var(--card);
		stroke-width: 2.5;
	}
	.target-label {
		fill: var(--success-strong);
	}
	.scenario-band {
		fill: var(--signal);
		stroke: none;
		opacity: 0.08;
	}
	.scenario-line {
		stroke: var(--signal);
		stroke-width: 2;
		stroke-dasharray: 2 6;
		stroke-linecap: round;
		opacity: 0.75;
	}
	.scenario-dot {
		fill: var(--card);
		stroke: var(--signal);
		stroke-width: 2;
	}
	.scenario-dot.common {
		fill: var(--signal);
	}
	.scenario-label {
		fill: var(--signal-strong);
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
