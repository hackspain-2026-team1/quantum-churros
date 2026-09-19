<script lang="ts">
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import {
		formatDays,
		formatMoney,
		formatNumber,
		formatPercent,
		formatPeriod,
		formatPeriodShort,
		formatRatio,
		formatScore,
		humanizeMonths
	} from '$lib/format.js';
	import {
		ALERT_KIND_TEXT,
		ALERT_STATE_TEXT,
		fromTenths,
		type Alert,
		type AlertState,
		type EntityMonth,
		type Series
	} from './contract.js';
	import { bandDomain, bandZones } from './explain.js';
	import { bandLabel, glossaryText } from './labels.js';
	import { monthStore } from './month-store.svelte.js';
	import { ALERT_STATE_TONE, BAND_TONE, TONE_BADGE } from './tones.js';
	import TrajectoryChart, {
		type ChartMarker,
		type ChartZone,
		type MarkerShape
	} from './trajectory-chart.svelte';

	let {
		months,
		series = [],
		alerts = [],
		month
	}: {
		/** group.months or company.months. */
		months: EntityMonth[];
		/** Monthly series of the same file, aligned with `months`. */
		series?: Series[];
		/** Alerts of the same file (fired, suppressed and abstained); drawn as markers. */
		alerts?: Alert[];
		/** Selected month, highlighted on the chart. */
		month: string;
	} = $props();

	const SCORE = 'score';
	let activeMetric = $state<string | undefined>(SCORE);

	const manifest = $derived(page.data.manifest);
	// One money unit per series, so the axis never mixes k€ and M€.
	const euroFormatter = (values: (number | null)[]) => {
		const peak = Math.max(0, ...values.map((value) => Math.abs(value ?? 0)));
		if (peak >= 1_000_000)
			return (value: number) => `${formatNumber(value / 1_000_000, 2)}\u00A0M€`;
		if (peak >= 1_000) return (value: number) => `${formatNumber(value / 1_000, 0)}\u00A0k€`;
		return (value: number) => formatMoney(value, 0);
	};
	const formatter = (item: Series) => {
		if (item.unit === 'EUR') return euroFormatter(item.values);
		if (item.unit === 'días') return (value: number) => formatDays(value);
		if (item.unit === 'cuota') return (value: number) => formatPercent(value, 1);
		if (item.unit === 'ratio') return (value: number) => formatRatio(value);
		return (value: number) => `${formatNumber(value, 2)}${item.unit ? `\u00A0${item.unit}` : ''}`;
	};
	const metrics = $derived([
		{ value: SCORE, label: 'Score', format: (value: number) => formatNumber(value, 1) },
		...series.map((item) => ({
			value: item.key,
			label: item.label,
			unit: item.unit,
			format: formatter(item)
		}))
	]);
	const isScore = $derived(!activeMetric || activeMetric === SCORE);
	const labels = $derived(months.map((entry) => entry.month));
	const values = $derived(
		isScore
			? months.map((entry) => fromTenths(entry.shown))
			: (series.find((item) => item.key === activeMetric)?.values ?? [])
	);
	const selectedIndex = $derived(labels.indexOf(month));
	const selected = $derived(selectedIndex < 0 ? null : months[selectedIndex]);

	// Score axis: the band thresholds of the manifest that enclose the whole history.
	const zones = $derived(bandZones(manifest?.bands ?? []));
	const scoreDomain = $derived(
		bandDomain(
			months.map((entry) => entry.shown),
			zones
		)
	);
	const chartZones = $derived<ChartZone[]>(
		isScore
			? zones.map((zone) => ({
					from: fromTenths(zone.min),
					to: fromTenths(zone.max),
					label: zone.label,
					tone: BAND_TONE[zone.key]
				}))
			: []
	);

	// The change line follows the verdict of the selected month.
	const detected = $derived(selected?.verdict.available ? selected.verdict.detected_since : null);
	const changeIndex = $derived(detected ? labels.indexOf(detected) : -1);
	const changeLabel = $derived(
		selected?.verdict.direction === 'improving'
			? 'Mejora detectada'
			: selected?.verdict.direction === 'deteriorating'
				? 'Deterioro detectado'
				: 'Cambio detectado'
	);

	const ALERT_GLYPH: Record<AlertState, MarkerShape> = {
		fired: 'dot',
		suppressed: 'ring',
		abstained: 'square'
	};
	const ALERT_LEGEND: Record<AlertState, string> = {
		fired: 'Alerta activa',
		suppressed: 'Alerta suprimida',
		abstained: 'Alerta en abstención'
	};
	const pauseWindow = (pause: NonNullable<Alert['suppressed_by']>) =>
		pause.until
			? `En pausa de ${formatPeriodShort(pause.since)} a ${formatPeriodShort(pause.until)}.`
			: `En pausa desde ${formatPeriodShort(pause.since)}.`;
	type Milestone = {
		key: string;
		month: string;
		title: string;
		detail: string;
		state: AlertState | 'perimeter' | 'shock';
	};
	// Everything that happened on the time axis: alerts, perimeter changes and the pending shock.
	const milestones = $derived.by((): Milestone[] => {
		const list: Milestone[] = alerts.map((alert) => ({
			key: alert.id,
			month: alert.month,
			title: ALERT_KIND_TEXT[alert.kind],
			detail: alert.suppressed_by
				? `No se dispara: ${glossaryText(manifest, 'reasons', alert.suppressed_by.reason)} ${pauseWindow(alert.suppressed_by)}`
				: humanizeMonths(alert.detail),
			state: alert.state
		}));
		for (const entry of months) {
			if (entry.perimeter_changed) {
				list.push({
					key: `${entry.month}:perimeter`,
					month: entry.month,
					title: 'Cambio de perímetro',
					detail: manifest?.glossary.flags.perimeter_changed ?? '',
					state: 'perimeter'
				});
			}
		}
		const shock = selected?.verdict.shock_month;
		if (shock && labels.includes(shock)) {
			list.push({
				key: `${shock}:shock`,
				month: shock,
				title: 'Caída brusca por confirmar',
				detail: 'Solo pasa a estructural si persiste en los meses siguientes.',
				state: 'shock'
			});
		}
		return list.toSorted((a, b) => b.month.localeCompare(a.month) || a.key.localeCompare(b.key));
	});
	const markers = $derived.by((): ChartMarker[] =>
		milestones
			.map((item): ChartMarker => {
				const index = labels.indexOf(item.month);
				if (item.state === 'perimeter') {
					return {
						index,
						label: item.title,
						tone: 'signal',
						shape: 'diamond',
						legend: 'Cambio de perímetro'
					};
				}
				if (item.state === 'shock') {
					return {
						index,
						label: item.title,
						tone: 'warning',
						shape: 'diamond',
						legend: 'Caída brusca por confirmar'
					};
				}
				return {
					index,
					label: `${ALERT_LEGEND[item.state]}: ${item.title.toLowerCase()}`,
					tone: ALERT_STATE_TONE[item.state],
					shape: ALERT_GLYPH[item.state],
					legend: ALERT_LEGEND[item.state]
				};
			})
			.toSorted((a, b) => a.index - b.index)
	);
	const milestoneTone = (state: Milestone['state']) =>
		state === 'perimeter'
			? TONE_BADGE.signal
			: state === 'shock'
				? TONE_BADGE.warning
				: TONE_BADGE[ALERT_STATE_TONE[state]];
	const milestoneText = (state: Milestone['state']) =>
		state === 'perimeter' ? 'Perímetro' : state === 'shock' ? 'Shock' : ALERT_STATE_TEXT[state];
	const MILESTONE_LIMIT = 6;
	let showAll = $state(false);
	const visibleMilestones = $derived(showAll ? milestones : milestones.slice(0, MILESTONE_LIMIT));

	const low = $derived(months.reduce((a, b) => (b.shown < a.shown ? b : a), months[0]));
	const high = $derived(months.reduce((a, b) => (b.shown > a.shown ? b : a), months[0]));
</script>

<Card.Root data-testid="entity-trajectory">
	<Card.Header>
		<Card.Description>
			{formatPeriod(labels[0])} – {formatPeriod(labels[labels.length - 1])} · {formatNumber(
				months.length
			)}
			{months.length === 1 ? 'mes observado' : 'meses observados'}
		</Card.Description>
		<Card.Title class="leading-6">
			Trayectoria mensual: score entre {formatScore(low.shown)} ({formatPeriodShort(low.month)}) y
			{formatScore(high.shown)} ({formatPeriodShort(high.month)})
		</Card.Title>
	</Card.Header>
	<Card.Content class="space-y-4">
		<TrajectoryChart
			{values}
			months={labels}
			{metrics}
			bind:activeMetric
			{selectedIndex}
			changeIndex={changeIndex < 0 ? null : changeIndex}
			{changeLabel}
			{markers}
			zones={chartZones}
			domain={isScore ? [fromTenths(scoreDomain.low), fromTenths(scoreDomain.high)] : undefined}
			onSelect={(index) => monthStore.select(labels[index])}
		/>

		{#if milestones.length > 0}
			<section class="border-t pt-3" aria-label="Hitos de la trayectoria">
				<h2 class="metric-label">
					Hitos · {formatNumber(milestones.length)}
				</h2>
				<ul class="divide-y">
					{#each visibleMilestones as item (item.key)}
						<li>
							<button
								type="button"
								class="grid w-full grid-cols-[4.5rem_1fr] items-start gap-x-3 rounded-md px-2 py-2 text-left hover:bg-muted/50 aria-[current=true]:bg-muted/40 sm:grid-cols-[4.5rem_auto_1fr]"
								aria-current={item.month === month ? 'true' : undefined}
								onclick={() => monthStore.select(item.month)}
								data-milestone={item.state}
							>
								<span
									class={[
										'font-data text-xs leading-6',
										item.month === month ? 'font-semibold text-foreground' : 'text-muted-foreground'
									]}>{formatPeriodShort(item.month)}</span
								>
								<span class="flex flex-wrap items-center gap-1.5">
									<Badge variant="outline" class={milestoneTone(item.state)}
										>{milestoneText(item.state)}</Badge
									>
									<span class="text-sm font-medium">{item.title}</span>
								</span>
								<span
									class="col-start-2 text-xs leading-5 text-muted-foreground sm:col-start-3 sm:leading-6"
									>{item.detail}</span
								>
							</button>
						</li>
					{/each}
				</ul>
				{#if milestones.length > MILESTONE_LIMIT}
					<button
						type="button"
						class="mt-1 rounded-md text-xs font-medium text-[var(--signal-strong)] hover:underline"
						onclick={() => (showAll = !showAll)}
					>
						{showAll
							? 'Ver solo los más recientes'
							: `Ver los ${formatNumber(milestones.length)} hitos`}
					</button>
				{/if}
			</section>
		{/if}

		<details class="group border-t pt-3 text-sm">
			<summary
				class="cursor-pointer rounded-md text-xs font-medium text-muted-foreground hover:text-foreground"
			>
				Ver la trayectoria del score como tabla
			</summary>
			<div class="mt-2 max-h-72 overflow-y-auto rounded-lg border">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head class="pl-4">Mes</Table.Head>
							<Table.Head class="text-right">Score</Table.Head>
							<Table.Head>Banda</Table.Head>
							<Table.Head class="pr-4">Hitos</Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each months.toReversed() as entry (entry.month)}
							<Table.Row data-state={entry.month === month ? 'selected' : undefined}>
								<Table.Cell class="pl-4">{formatPeriodShort(entry.month)}</Table.Cell>
								<Table.Cell class="font-data text-right tabular-nums"
									>{formatScore(entry.shown)}</Table.Cell
								>
								<Table.Cell>{bandLabel(manifest, entry.band)}</Table.Cell>
								<Table.Cell class="pr-4 text-xs whitespace-normal text-muted-foreground">
									{milestones
										.filter((item) => item.month === entry.month)
										.map((item) => `${milestoneText(item.state)}: ${item.title.toLowerCase()}`)
										.join(' · ') || '—'}
								</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			</div>
		</details>
	</Card.Content>
</Card.Root>
