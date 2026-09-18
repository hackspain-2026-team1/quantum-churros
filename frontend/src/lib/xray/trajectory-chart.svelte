<script lang="ts">
	let {
		values,
		projected = [],
		changeIndex = 8,
		compact = false
	}: { values: number[]; projected?: number[]; changeIndex?: number; compact?: boolean } = $props();
	const width = 760;
	let height = $derived(compact ? 150 : 230);
	const pad = 22;
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
</script>

<div
	class="relative w-full overflow-hidden rounded-xl bg-[linear-gradient(to_bottom,transparent_24%,var(--border)_25%,transparent_26%,transparent_49%,var(--border)_50%,transparent_51%,transparent_74%,var(--border)_75%,transparent_76%)]"
>
	<svg
		viewBox={`0 0 ${width} ${height}`}
		role="img"
		aria-label="Trayectoria financiera observada y proyectada"
		class="block w-full"
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
		<text x={x(changeIndex) + 8} y="22" class="change-label">Cambio detectado</text>
		<text x={x(values.length - 1) - 5} y={y(values.at(-1) ?? 0) - 12} class="value-label"
			>{values.at(-1)}</text
		>
	</svg>
</div>

<style>
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
</style>
