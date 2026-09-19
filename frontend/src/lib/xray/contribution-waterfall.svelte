<script lang="ts">
	import { CircleCheck, CircleSlash, TriangleAlert } from '@lucide/svelte';
	import { dev } from '$app/environment';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import {
		formatNumber,
		formatPercent,
		formatPeriod,
		formatScore,
		formatScoreDelta
	} from '$lib/format.js';
	import { fromTenths, type EntityMonth } from './contract.js';
	import { waterfallGap, waterfallSteps, weakestPillar, type WaterfallStep } from './explain.js';
	import { glossaryText, pillarLabel } from './labels.js';

	let { entry }: { entry: EntityMonth } = $props();

	const manifest = $derived(page.data.manifest);
	const baseline = (key: string) => {
		const pillar = manifest?.pillars.find((item) => item.key === key);
		return pillar ? formatScore(pillar.baseline) : '—';
	};

	type Row = WaterfallStep & {
		label: string;
		detail: string | null;
		note: string | null;
		/** Glossary sentences shown as chips: gates of a pillar, cap rules that hold. */
		chips: { code: string; text: string }[];
		muted: boolean;
	};

	// Integer tenths all the way: base + contributions - penalty - cap === shown.
	const rows = $derived.by((): Row[] => {
		const weakest = weakestPillar(entry);
		return waterfallSteps(entry).map((step) => {
			const pillar = entry.pillars.find((item) => item.key === step.key);
			if (pillar) {
				const available = pillar.score !== null;
				return {
					...step,
					label: pillarLabel(manifest, pillar.key),
					detail:
						pillar.score === null
							? 'No disponible este mes: su peso se reparte entre los demás pilares'
							: `Pilar en ${formatScore(pillar.score)} · referencia ${baseline(pillar.key)} · peso efectivo ${formatPercent(pillar.w_eff, 0)}`,
					note: pillar.note,
					chips: pillar.gates.map((code) => ({
						code,
						text: glossaryText(manifest, 'gates', code)
					})),
					muted: !available
				};
			}
			if (step.key === 'base') {
				return {
					...step,
					label: 'Punto de partida',
					detail:
						'Mediana de referencia de los pilares disponibles, ponderada por su peso efectivo',
					note: null,
					chips: [],
					muted: false
				};
			}
			if (step.key === 'penalty') {
				return {
					...step,
					label: 'Penalización por pilar débil',
					detail:
						entry.penalty > 0 && weakest
							? `No compensatoria: ${pillarLabel(manifest, weakest.key).toLowerCase()} es el pilar más bajo (${formatScore(weakest.score)}) y resta aunque los demás compensen`
							: 'Sin penalización este mes',
					note: null,
					chips: [],
					muted: entry.penalty === 0
				};
			}
			if (step.key === 'cap') {
				return {
					...step,
					label: 'Tope',
					detail:
						entry.cap.amount > 0
							? 'Una regla limita el score máximo aunque el resto de pilares sea alto'
							: 'Ningún tope recorta el score este mes',
					note: null,
					chips: entry.cap.fired.map((code) => ({
						code,
						text: glossaryText(manifest, 'caps', code)
					})),
					muted: entry.cap.amount === 0
				};
			}
			return {
				...step,
				label: 'Score mostrado',
				detail: null,
				note: null,
				chips: [],
				muted: false
			};
		});
	});

	// Zoomed axis so contributions of a few tenths stay visible; the ticks say where it starts.
	const bounds = $derived.by(() => {
		const points = rows.flatMap((row) => (row.delta === null ? [row.end] : [row.start, row.end]));
		const low = Math.min(...points);
		const high = Math.max(...points);
		const padding = Math.max(30, (high - low) * 0.12);
		return { low: Math.max(0, low - padding), high: Math.min(1000, high + padding) };
	});
	const position = (tenths: number) =>
		((Math.min(Math.max(tenths, bounds.low), bounds.high) - bounds.low) /
			(bounds.high - bounds.low || 1)) *
		100;
	const ticks = $derived.by(() => {
		const span = bounds.high - bounds.low;
		const step = [10, 20, 50, 100, 200, 250, 500].find((size) => span / size <= 6) ?? 500;
		const result: number[] = [];
		for (let tick = Math.ceil(bounds.low / step) * step; tick <= bounds.high; tick += step) {
			result.push(tick);
		}
		return result;
	});
	const tickLabel = (tenths: number) => formatNumber(fromTenths(tenths), tenths % 10 === 0 ? 0 : 1);

	const gap = $derived(waterfallGap(entry));
	$effect(() => {
		if (dev) {
			console.assert(
				gap === 0,
				`[waterfall] ${entry.month}: base + contribuciones - penalización - tope difiere de shown en ${gap} décimas`
			);
		}
	});
</script>

<Card.Root data-testid="contribution-waterfall">
	<Card.Header>
		<Card.Description>De dónde sale el número · {formatPeriod(entry.month)}</Card.Description>
		<Card.Title>Cada pilar suma o resta puntos hasta el score</Card.Title>
	</Card.Header>
	<Card.Content class="space-y-3">
		<div
			class="hidden gap-x-4 text-[0.63rem] font-semibold tracking-[0.14em] text-muted-foreground uppercase md:grid md:grid-cols-[15rem_1fr_4.5rem_5rem]"
			aria-hidden="true"
		>
			<span>Paso</span>
			<span class="relative h-4">
				{#each ticks as tick (tick)}
					<span
						class="font-data absolute top-0 -translate-x-1/2 tracking-normal"
						style={`left: ${position(tick)}%`}>{tickLabel(tick)}</span
					>
				{/each}
			</span>
			<span class="text-right">Puntos</span>
			<span class="text-right">Acumulado</span>
		</div>
		<ol class="space-y-3">
			{#each rows as row (row.key)}
				{@const absolute = row.delta === null}
				{@const barLeft = position(absolute ? bounds.low : Math.min(row.start, row.end))}
				{@const barRight = position(absolute ? row.end : Math.max(row.start, row.end))}
				<li
					class={[
						'grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 md:grid-cols-[15rem_1fr_4.5rem_5rem] md:items-center',
						row.key === 'shown' && 'border-t pt-3'
					]}
					data-step={row.key}
					data-tenths={row.delta ?? row.end}
				>
					<div class={['min-w-0', row.muted && 'text-muted-foreground']}>
						<div class="flex items-center gap-1.5 text-sm font-semibold">
							{#if row.muted && row.key !== 'penalty' && row.key !== 'cap'}
								<CircleSlash class="size-3.5 shrink-0" aria-hidden="true" />
							{/if}
							{row.label}
						</div>
						{#if row.detail}
							<div class="text-xs leading-5 text-muted-foreground">{row.detail}</div>
						{/if}
					</div>
					<div
						class="relative order-3 col-span-2 h-5 rounded bg-muted/60 md:order-none md:col-span-1"
						aria-hidden="true"
					>
						{#each ticks as tick (tick)}
							<span class="absolute inset-y-0 w-px bg-border" style={`left: ${position(tick)}%`}
							></span>
						{/each}
						<div
							class={[
								'absolute inset-y-[3px] rounded-[4px]',
								absolute
									? 'bg-[var(--ink)]'
									: (row.delta ?? 0) < 0
										? 'bg-[var(--danger)]'
										: 'bg-[var(--success)]'
							]}
							style={`left: ${barLeft}%; width: ${Math.max(barRight - barLeft, row.delta === 0 ? 0 : 0.6)}%`}
						></div>
						{#if !absolute}
							<span
								class="absolute inset-y-0 w-0.5 -translate-x-1/2 rounded-full bg-[var(--ink)]"
								style={`left: ${position(row.end)}%`}
							></span>
						{/if}
					</div>
					<div
						class={[
							'font-data text-right text-sm font-semibold tabular-nums',
							row.delta !== null && row.delta > 0 && 'positive',
							row.delta !== null && row.delta < 0 && 'negative',
							row.muted && 'text-muted-foreground',
							absolute && 'md:col-span-2'
						]}
					>
						{row.delta === null ? formatScore(row.end) : formatScoreDelta(row.delta)}
						{#if !absolute}
							<span class="block text-xs font-normal text-muted-foreground md:hidden"
								>→ {formatScore(row.end)}</span
							>
						{/if}
					</div>
					{#if !absolute}
						<div
							class="font-data hidden text-right text-sm text-muted-foreground tabular-nums md:block"
						>
							{formatScore(row.end)}
						</div>
					{/if}
					{#if row.note || row.chips.length > 0}
						<div class="order-4 col-span-2 space-y-1.5 md:order-none md:col-span-4">
							{#if row.note}
								<p class="text-xs leading-5 text-muted-foreground">{row.note}</p>
							{/if}
							{#if row.chips.length > 0}
								<ul
									class="flex flex-wrap gap-1.5"
									aria-label={row.key === 'cap' ? 'Reglas de tope' : 'Condiciones del pilar'}
								>
									{#each row.chips as chip (chip.code)}
										<li>
											<Badge
												variant="outline"
												class="h-auto max-w-full justify-start rounded-md py-1 text-left font-normal whitespace-normal text-muted-foreground"
												data-gate={chip.code}>{chip.text}</Badge
											>
										</li>
									{/each}
								</ul>
							{/if}
						</div>
					{/if}
				</li>
			{/each}
		</ol>
		<p
			class="flex items-start gap-2 border-t pt-3 text-xs leading-5 text-muted-foreground"
			data-testid="waterfall-check"
		>
			{#if gap === 0}
				<CircleCheck class="mt-0.5 size-4 shrink-0 text-[var(--success)]" aria-hidden="true" />
				<span
					>{formatScore(entry.base)} de partida, más las aportaciones de los pilares, menos penalización
					y tope, da exactamente {formatScore(entry.shown)}: la suma cuadra al décimo y la confianza
					no interviene.</span
				>
			{:else}
				<TriangleAlert class="mt-0.5 size-4 shrink-0 text-[var(--danger)]" aria-hidden="true" />
				<span>La suma no cuadra por {formatScoreDelta(gap)} puntos.</span>
			{/if}
		</p>
	</Card.Content>
</Card.Root>
