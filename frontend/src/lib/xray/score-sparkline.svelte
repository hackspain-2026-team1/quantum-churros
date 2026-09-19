<script lang="ts">
	import { formatPeriod, formatScore } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import type { Band } from './contract.js';
	import { BAND_TONE, TONE_COLOR } from './tones.js';

	let {
		values,
		months,
		selectedIndex = values.length - 1,
		band = null,
		marks = [],
		width = 124,
		height = 32,
		class: className
	}: {
		/** Displayed score ('shown') in integer tenths, aligned with `months`; null = not observed. */
		values: readonly (number | null)[];
		months: readonly string[];
		/** Month under analysis: the line is solid up to it and faint after it. */
		selectedIndex?: number;
		/** Band of the selected month; colours its dot. */
		band?: Band | null;
		/** Indexes with a perimeter change, drawn as a vertical tick. */
		marks?: readonly number[];
		width?: number;
		height?: number;
		class?: string;
	} = $props();

	// The line shows the shape of the score over the window, on the range of the row itself.
	// The range never gets narrower than MIN_SPAN, so month-to-month noise stays flat and only
	// a real move fills the height. The level is read in the score column, not here.
	const SCORE_MAX = 1000;
	const MIN_SPAN = 300;
	const PAD_X = 5;
	const PAD_Y = 5;

	const domain = $derived.by(() => {
		const observed = values.filter((value): value is number => value !== null);
		if (observed.length === 0) return { low: 0, high: SCORE_MAX };
		let low = Math.min(...observed);
		let high = Math.max(...observed);
		const missing = MIN_SPAN - (high - low);
		if (missing > 0) {
			low -= missing / 2;
			high += missing / 2;
			if (low < 0) [low, high] = [0, high - low];
			if (high > SCORE_MAX) [low, high] = [low - (high - SCORE_MAX), SCORE_MAX];
		}
		return { low, high };
	});

	const x = (index: number) =>
		values.length <= 1 ? width / 2 : PAD_X + (index * (width - 2 * PAD_X)) / (values.length - 1);
	const y = (tenths: number) =>
		PAD_Y + (1 - (tenths - domain.low) / (domain.high - domain.low)) * (height - 2 * PAD_Y);
	const point = (index: number) =>
		`${x(index).toFixed(1)},${y(values[index] as number).toFixed(1)}`;

	// Consecutive observed months; a gap in the data is a gap in the line.
	const runs = $derived.by(() => {
		const found: number[][] = [];
		let current: number[] = [];
		values.forEach((value, index) => {
			if (value === null) {
				if (current.length) found.push(current);
				current = [];
			} else current.push(index);
		});
		if (current.length) found.push(current);
		return found;
	});
	const pathOf = (limit: number) =>
		runs
			.map((run) => run.filter((index) => index <= limit))
			.filter((run) => run.length > 1)
			.map((run) => `M${run.map(point).join('L')}`)
			.join('');
	const fullPath = $derived(pathOf(values.length - 1));
	const pastPath = $derived(pathOf(selectedIndex));
	const lonely = $derived(runs.filter((run) => run.length === 1).map((run) => run[0]));

	const selected = $derived(values[selectedIndex] ?? null);
	const first = $derived(values.findIndex((value) => value !== null));
	const label = $derived.by(() => {
		if (first < 0) return 'Sin score en la ventana';
		const start = `${formatScore(values[first] as number)} en ${formatPeriod(months[first])}`;
		if (selected === null || first === selectedIndex) return `Trayectoria del score: ${start}`;
		return `Trayectoria del score: de ${start} a ${formatScore(selected)} en ${formatPeriod(months[selectedIndex])}`;
	});
</script>

<svg
	class={cn('block shrink-0 overflow-visible', className)}
	{width}
	{height}
	viewBox={`0 0 ${width} ${height}`}
	role="img"
	aria-label={label}
	data-sparkline
>
	{#each marks as mark (mark)}
		<line
			x1={x(mark)}
			x2={x(mark)}
			y1={1}
			y2={height - 1}
			stroke="var(--signal)"
			stroke-width="1"
			stroke-opacity={mark <= selectedIndex ? 0.9 : 0.35}
		>
			<title>Cambio de perímetro en {formatPeriod(months[mark])}</title>
		</line>
	{/each}
	<path
		d={fullPath}
		fill="none"
		stroke="var(--foreground)"
		stroke-opacity="0.16"
		stroke-width="1.5"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
	<path
		d={pastPath}
		fill="none"
		stroke="var(--foreground)"
		stroke-opacity="0.62"
		stroke-width="1.5"
		stroke-linecap="round"
		stroke-linejoin="round"
	/>
	{#each lonely as index (index)}
		<circle
			cx={x(index)}
			cy={y(values[index] as number)}
			r="1.5"
			fill="var(--foreground)"
			fill-opacity={index <= selectedIndex ? 0.62 : 0.16}
		/>
	{/each}
	{#if selected !== null}
		<circle
			cx={x(selectedIndex)}
			cy={y(selected)}
			r="3.5"
			fill={band ? TONE_COLOR[BAND_TONE[band]] : 'var(--foreground)'}
			stroke="var(--card)"
			stroke-width="1.5"
		/>
	{/if}
</svg>
