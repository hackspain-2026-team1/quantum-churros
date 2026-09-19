<script lang="ts" module>
	import type { Tone } from './tones.js';

	export type ChartMetric = {
		value: string;
		label: string;
		unit?: string;
		format?: (value: number) => string;
	};
	export type MarkerShape = 'dot' | 'ring' | 'diamond' | 'square';
	export type ChartMarker = {
		/** Index of the month the marker sits on. */
		index: number;
		/** Full sentence for the tooltip, e.g. 'Alerta activa: deterioro estructural'. */
		label: string;
		tone?: Tone;
		shape?: MarkerShape;
		/** Legend entry the marker belongs to; markers without it stay out of the legend. */
		legend?: string;
	};
	/** Horizontal zone of the value axis, e.g. a score band; `from`/`to` in value units. */
	export type ChartZone = { from: number; to: number; label: string; tone: Tone };
</script>

<script lang="ts">
	import * as Select from '$lib/components/ui/select/index.js';
	import * as ToggleGroup from '$lib/components/ui/toggle-group/index.js';
	import { formatAxisMonth, formatNumber, formatPeriodShort } from '$lib/format.js';
	import { TONE_COLOR } from './tones.js';

	let {
		values,
		months = [],
		changeIndex = null,
		changeLabel = 'Cambio detectado',
		markers = [],
		zones = [],
		selectedIndex = null,
		onSelect,
		compact = false,
		metrics = [],
		metricLabel = 'Score de salud',
		unit = '',
		format,
		domain,
		activeMetric = $bindable<string | undefined>(undefined)
	}: {
		/** One value per month; null = not observed (the line breaks there). */
		values: (number | null)[];
		/** 'YYYY-MM' labels aligned with `values`. */
		months?: string[];
		/** Index of the month where the engine detected the change; no line when null. */
		changeIndex?: number | null;
		changeLabel?: string;
		/** Events on the time axis: alerts, perimeter changes, shocks. */
		markers?: ChartMarker[];
		/** Tinted zones with a threshold line between them, e.g. the score bands at 40-60-80. */
		zones?: ChartZone[];
		/** Month highlighted on the chart, usually the month slider's. */
		selectedIndex?: number | null;
		/** Called with the index of the clicked month. */
		onSelect?: (index: number) => void;
		compact?: boolean;
		metrics?: ChartMetric[];
		metricLabel?: string;
		unit?: string;
		/** Formatter for a single-metric chart; metrics[] carry their own. */
		format?: (value: number) => string;
		/** Fixed [min, max] of the value axis; fitted to the data when omitted. */
		domain?: [number, number];
		activeMetric?: string;
	} = $props();

	const uid = $props.id();
	// The SVG is drawn at its real pixel width, so labels keep their size on a phone.
	let measured = $state(0);
	let width = $derived(Math.max(280, measured || 760));
	let height = $derived(compact ? 150 : 240);
	const top = 16;
	const bottom = 26;
	// Zone names sit in a gutter outside the plot, so the line never runs over them.
	let zoneGutter = $derived(zones.length > 0 && width >= 420);
	let right = $derived(
		zoneGutter ? Math.max(...zones.map((zone) => zone.label.length)) * 6.6 + 18 : 14
	);

	let selected = $derived(activeMetric ?? metrics[0]?.value);
	// Deselecting a toggle yields ''; the chart always keeps one metric active.
	const selectMetric = (value: string | undefined) => {
		if (value) activeMetric = value;
	};
	let currentMetric = $derived(metrics.find((metric) => metric.value === selected));
	let currentLabel = $derived(currentMetric?.label ?? metricLabel);
	let currentUnit = $derived(currentMetric?.unit ?? unit);
	const formatValue = (value: number) => {
		const formatter = currentMetric?.format ?? format;
		if (formatter) return formatter(value);
		return `${formatNumber(value, 2)}${currentUnit ? `\u00A0${currentUnit}` : ''}`;
	};

	let observed = $derived(values.filter((value): value is number => value !== null));
	let spread = $derived(observed.length ? Math.max(...observed) - Math.min(...observed) : 0);
	let margin = $derived(spread > 0 ? spread * 0.12 : Math.abs(observed[0] ?? 1) * 0.05 || 1);
	let min = $derived(domain ? domain[0] : observed.length ? Math.min(...observed) - margin : 0);
	let max = $derived(domain ? domain[1] : observed.length ? Math.max(...observed) + margin : 1);

	// Value ticks: the zone thresholds when there are zones, else round numbers over the domain.
	let valueTicks = $derived.by(() => {
		if (zones.length > 0) {
			const edges = zones
				.flatMap((zone) => [zone.from, zone.to])
				.filter((edge) => edge >= min && edge <= max);
			return edges.filter((edge, index) => edges.indexOf(edge) === index).sort((a, b) => a - b);
		}
		const span = max - min;
		if (!(span > 0)) return [];
		const rough = span / 3;
		const magnitude = 10 ** Math.floor(Math.log10(rough));
		const step = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude).find((s) => s >= rough);
		if (!step) return [];
		const ticks: number[] = [];
		for (let tick = Math.ceil(min / step) * step; tick <= max; tick += step) ticks.push(tick);
		return ticks;
	});
	const tickText = (value: number) =>
		zones.length > 0 ? formatNumber(value, Number.isInteger(value) ? 0 : 1) : formatValue(value);
	let left = $derived(
		Math.min(76, Math.max(22, ...valueTicks.map((tick) => tickText(tick).length * 6.2 + 10)))
	);

	let total = $derived(Math.max(1, values.length - 1));
	const x = (index: number) => left + (index / total) * (width - left - right);
	const y = (value: number) =>
		height - bottom - ((value - min) / (max - min || 1)) * (height - top - bottom);
	const clampY = (value: number) => y(Math.min(Math.max(value, min), max));

	// Consecutive observed months form a segment; a null month breaks the line.
	let segments = $derived.by(() => {
		const result: string[] = [];
		let current: string[] = [];
		values.forEach((value, index) => {
			if (value === null) {
				if (current.length) result.push(current.join(' '));
				current = [];
			} else {
				current.push(`${x(index)},${y(value)}`);
			}
		});
		if (current.length) result.push(current.join(' '));
		return result;
	});
	let lastIndex = $derived(values.findLastIndex((value) => value !== null));
	// The header reads out the highlighted month, else the last observed one.
	let readoutIndex = $derived(
		selectedIndex !== null && selectedIndex >= 0 && selectedIndex < values.length
			? selectedIndex
			: lastIndex
	);
	let readoutValue = $derived(readoutIndex >= 0 ? values[readoutIndex] : null);
	const pointLabel = (index: number) =>
		index < months.length ? formatAxisMonth(months[index]) : `M${index + 1}`;
	const pointTitle = (index: number) =>
		index < months.length ? formatPeriodShort(months[index]) : `M${index + 1}`;
	let ticks = $derived.by(() => {
		const slots = Math.max(2, Math.floor((width - left - right) / 58));
		const step = Math.max(1, Math.ceil(values.length / slots));
		const last = values.length - 1;
		return values
			.map((_, index) => index)
			.filter((index) => (index % step === 0 && last - index >= step * 0.6) || index === last);
	});
	const inRange = (index: number | null): index is number =>
		index !== null && index >= 0 && index < values.length;
	const labelAnchor = (index: number) => (index > total * 0.7 ? 'end' : 'start');
	const labelOffset = (index: number) => (index > total * 0.7 ? -8 : 8);
	// The change label goes above or below the line, wherever the months it covers leave more room.
	let changeLabelY = $derived.by(() => {
		const low = height - bottom - 8;
		if (!inRange(changeIndex)) return low;
		const stride = (width - left - right) / total;
		const span = Math.ceil((changeLabel.length * 7.2 + 8) / (stride || 1));
		const from = labelAnchor(changeIndex) === 'start' ? changeIndex : changeIndex - span;
		const covered = values
			.slice(Math.max(0, from), Math.max(0, from) + span + 1)
			.filter((value): value is number => value !== null)
			.map((value) => y(value));
		const stacked = Math.max(
			0,
			...markers
				.filter((marker) => marker.index >= from && marker.index <= from + span)
				.map((marker) => markers.filter((other) => other.index === marker.index).length)
		);
		const high = glyphY(stacked) + 8;
		const room = (position: number) =>
			Math.min(Infinity, ...covered.map((value) => Math.abs(value - position)));
		return room(low) >= room(high) ? low : high;
	});

	// Markers of the same month share one hairline and stack their glyphs.
	let markerColumns = $derived(
		markers
			.filter((marker) => inRange(marker.index))
			.map((marker) => marker.index)
			.filter((index, position, all) => all.indexOf(index) === position)
			.map((index) => ({ index, items: markers.filter((marker) => marker.index === index) }))
	);
	let legend = $derived(
		markers.filter(
			(marker, position) =>
				marker.legend &&
				inRange(marker.index) &&
				markers.findIndex((other) => other.legend === marker.legend && inRange(other.index)) ===
					position
		)
	);
	const glyphY = (order: number) => top + 5 + order * 13;

	let hoverIndex = $state<number | null>(null);
	let hoverMarkers = $derived(
		hoverIndex === null ? [] : markers.filter((marker) => marker.index === hoverIndex)
	);
	const indexAt = (event: PointerEvent | MouseEvent) => {
		const target = event.currentTarget as SVGSVGElement;
		const rect = target.getBoundingClientRect();
		const relX = ((event.clientX - rect.left) / rect.width) * width;
		const index = Math.round(((relX - left) / (width - left - right)) * total);
		return Math.min(Math.max(0, index), values.length - 1);
	};
</script>

{#snippet glyph(marker: ChartMarker, cx: number, cy: number)}
	{@const color = TONE_COLOR[marker.tone ?? 'signal']}
	{#if marker.shape === 'diamond'}
		<rect
			x={cx - 4}
			y={cy - 4}
			width="8"
			height="8"
			transform={`rotate(45 ${cx} ${cy})`}
			class="glyph"
			style={`fill: ${color}`}
		/>
	{:else if marker.shape === 'square'}
		<rect
			x={cx - 4}
			y={cy - 4}
			width="8"
			height="8"
			rx="1.5"
			class="glyph"
			style={`fill: ${color}`}
		/>
	{:else if marker.shape === 'ring'}
		<circle {cx} {cy} r="4.5" class="glyph-halo" />
		<circle {cx} {cy} r="3.5" class="glyph-ring" style={`stroke: ${color}`} />
	{:else}
		<circle {cx} {cy} r="4.5" class="glyph" style={`fill: ${color}`} />
	{/if}
{/snippet}

<div class="space-y-2">
	<div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
		{#if metrics.length > 3}
			<!-- Long metric lists do not fit a segmented control on narrow screens. -->
			<div class="flex min-w-0 items-center gap-2">
				<span class="metric-label mb-0" id={`${uid}-metric`}>Métrica</span>
				<Select.Root type="single" bind:value={() => selected ?? '', selectMetric}>
					<Select.Trigger size="sm" class="min-w-0" aria-labelledby={`${uid}-metric`}>
						<span class="truncate">{currentLabel}</span>
					</Select.Trigger>
					<Select.Content>
						{#each metrics as metric (metric.value)}
							<Select.Item value={metric.value} label={metric.label}>{metric.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>
		{:else if metrics.length > 1}
			<div class="flex items-center gap-2">
				<span class="metric-label mb-0">Métrica</span>
				<ToggleGroup.Root
					type="single"
					variant="outline"
					size="sm"
					bind:value={() => selected ?? '', selectMetric}
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
		{#if readoutIndex >= 0}
			<span class="text-right text-xs text-muted-foreground" data-testid="chart-readout">
				{pointLabel(readoutIndex)} ·
				<span class="font-data font-semibold text-foreground"
					>{readoutValue === null ? 'Sin dato' : formatValue(readoutValue)}</span
				>
			</span>
		{/if}
	</div>
	<div class="relative w-full" bind:clientWidth={measured}>
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_noninteractive_element_interactions -->
		<svg
			{width}
			{height}
			viewBox={`0 0 ${width} ${height}`}
			role="img"
			aria-label={`Trayectoria mensual de ${currentLabel}`}
			class={['block w-full touch-pan-y', onSelect && 'cursor-pointer']}
			onpointermove={(event) => (hoverIndex = indexAt(event))}
			onpointerleave={() => (hoverIndex = null)}
			onclick={(event) => onSelect?.(indexAt(event))}
		>
			{#each zones as zone (zone.label)}
				{@const zoneTop = clampY(zone.to)}
				{@const zoneBottom = clampY(zone.from)}
				{#if zoneBottom - zoneTop > 1}
					<rect
						x={left}
						y={zoneTop}
						width={width - left - right}
						height={zoneBottom - zoneTop}
						class="zone"
						style={`fill: ${TONE_COLOR[zone.tone]}`}
					/>
					{#if zoneGutter && zoneBottom - zoneTop > 12}
						<text x={width - right + 8} y={(zoneTop + zoneBottom) / 2 + 3.5} class="zone-label"
							>{zone.label}</text
						>
					{/if}
				{/if}
			{/each}
			{#each valueTicks as tick (tick)}
				<line x1={left} x2={width - right} y1={y(tick)} y2={y(tick)} class="grid-line" />
				<text x={left - 6} y={y(tick) + 3.5} class="axis-label" text-anchor="end"
					>{tickText(tick)}</text
				>
			{/each}
			{#each markerColumns as column (column.index)}
				<line
					x1={x(column.index)}
					x2={x(column.index)}
					y1={top}
					y2={height - bottom}
					class="marker-line"
					style={`stroke: ${TONE_COLOR[column.items[0].tone ?? 'signal']}`}
				/>
			{/each}
			{#if inRange(changeIndex)}
				<line
					x1={x(changeIndex)}
					x2={x(changeIndex)}
					y1={top}
					y2={height - bottom}
					class="change-line"
				/>
				<text
					x={x(changeIndex) + labelOffset(changeIndex)}
					y={changeLabelY}
					class="change-label"
					text-anchor={labelAnchor(changeIndex)}>{changeLabel}</text
				>
			{/if}
			{#each segments as points, index (index)}
				<polyline {points} fill="none" class="observed-line" />
			{/each}
			{#each values as value, index (index)}
				{#if value !== null}
					<circle
						cx={x(index)}
						cy={y(value)}
						r={index === selectedIndex ? 6 : index === lastIndex ? 4.5 : 2.5}
						class={index === selectedIndex ? 'selected-dot' : 'observed-dot'}
					/>
				{/if}
			{/each}
			{#each markerColumns as column (column.index)}
				{#each column.items as marker, order (`${marker.label}-${order}`)}
					{@render glyph(marker, x(column.index), glyphY(order))}
				{/each}
			{/each}
			{#if hoverIndex !== null}
				<line
					x1={x(hoverIndex)}
					x2={x(hoverIndex)}
					y1={top}
					y2={height - bottom}
					class="hover-line"
				/>
				{#if values[hoverIndex] !== null}
					<circle cx={x(hoverIndex)} cy={y(values[hoverIndex] ?? 0)} r="5" class="hover-dot" />
				{/if}
			{/if}
			{#each ticks as index (index)}
				<text x={x(index)} y={height - 8} class="axis-label" text-anchor="middle"
					>{pointLabel(index)}</text
				>
			{/each}
		</svg>
		{#if hoverIndex !== null}
			{@const hovered = values[hoverIndex]}
			<div
				class="pointer-events-none absolute z-10 max-w-64 rounded-md border bg-background px-2.5 py-1.5 text-xs shadow-md"
				style={`left: ${(x(hoverIndex) / width) * 100}%; top: ${((hovered === null ? height / 2 : y(hovered)) / height) * 100}%; transform: translate(${
					hoverIndex >= values.length / 2 ? 'calc(-100% - 10px)' : '10px'
				}, -50%);`}
			>
				<div class="flex items-baseline justify-between gap-3">
					<span class="font-data font-semibold"
						>{hovered === null ? 'Sin dato' : formatValue(hovered)}</span
					>
					<span class="text-muted-foreground">{pointTitle(hoverIndex)}</span>
				</div>
				{#each hoverMarkers as marker, order (`${marker.label}-${order}`)}
					<div class="mt-1 flex items-start gap-1.5 text-muted-foreground">
						<span
							class="mt-1 size-1.5 shrink-0 rounded-full"
							style={`background: ${TONE_COLOR[marker.tone ?? 'signal']}`}
							aria-hidden="true"
						></span>
						<span>{marker.label}</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
	{#if legend.length > 0 || inRange(changeIndex)}
		<ul
			class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"
			aria-label="Leyenda de hitos"
		>
			{#each legend as marker (marker.legend)}
				<li class="flex items-center gap-1.5">
					<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"
						>{@render glyph(marker, 6, 6)}</svg
					>
					{marker.legend}
				</li>
			{/each}
			{#if inRange(changeIndex)}
				<li class="flex items-center gap-1.5">
					<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"
						><line x1="6" x2="6" y1="0" y2="12" class="change-line" /></svg
					>
					{changeLabel}
				</li>
			{/if}
		</ul>
	{/if}
</div>

<style>
	.observed-line {
		stroke: var(--signal);
		stroke-width: 2.5;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.observed-dot {
		fill: var(--card);
		stroke: var(--signal);
		stroke-width: 2;
	}
	.selected-dot {
		fill: var(--ink);
		stroke: var(--card);
		stroke-width: 2.5;
	}
	.zone {
		opacity: 0.07;
	}
	.zone-label {
		fill: var(--muted-foreground);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.grid-line {
		stroke: var(--border);
		stroke-width: 1;
	}
	.change-line {
		stroke: var(--warning);
		stroke-width: 1.5;
		stroke-dasharray: 4 4;
	}
	.marker-line {
		stroke-width: 1;
		opacity: 0.45;
	}
	.glyph {
		stroke: var(--card);
		stroke-width: 2;
	}
	.glyph-halo {
		fill: var(--card);
	}
	.glyph-ring {
		fill: var(--card);
		stroke-width: 2;
	}
	.change-label {
		fill: var(--foreground);
		font-family: var(--font-data);
		font-size: 11px;
		font-weight: 650;
		paint-order: stroke;
		stroke: var(--card);
		stroke-width: 3px;
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
