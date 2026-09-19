<script lang="ts">
	import { Gauge, Info, Lock } from '@lucide/svelte';
	import { page } from '$app/state';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import {
		formatNumber,
		formatPercent,
		formatPeriod,
		formatScore,
		formatScoreDelta,
		formatSigned
	} from '$lib/format.js';
	import {
		DIRECTION_TEXT,
		NATURE_TEXT,
		fromTenths,
		type EntityMonth,
		type ProfileAttribute
	} from './contract.js';
	import AbstainedState from './abstained-state.svelte';
	import BandBadge from './band-badge.svelte';
	import BandScale from './band-scale.svelte';
	import ConfidencePill from './confidence-pill.svelte';
	import DirectionChip from './direction-chip.svelte';
	import { bandDistances, bandZones, monthsBetween, verdictDelta } from './explain.js';
	import { glossaryText, pillarLabel } from './labels.js';
	import ScoreGauge from './score-gauge.svelte';

	let {
		entry,
		months = [],
		kind = 'group',
		profile = []
	}: {
		entry: EntityMonth;
		/** Months of the same entity: the change is read as a difference of two scores on screen. */
		months?: EntityMonth[];
		/** Whose verdict this is; only changes the wording. */
		kind?: 'group' | 'company';
		/** Profile of the same entity: its size band names the reference it is measured against. */
		profile?: ProfileAttribute[];
	} = $props();

	const uid = $props.id();
	const manifest = $derived(page.data.manifest);
	const verdict = $derived(entry.verdict);
	const delta = $derived(verdictDelta(entry, months));
	const plural = (count: number, one: string, many: string) =>
		`${formatNumber(count)} ${count === 1 ? one : many}`;
	const list = (items: string[]) =>
		items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} y ${items.at(-1)}`;

	const moved = $derived(
		list(verdict.pillars_moved.map((key) => pillarLabel(manifest, key).toLowerCase()))
	);
	// The conclusion is assembled from verdict fields only; no free text is invented here.
	const headline = $derived.by(() => {
		if (!verdict.available) {
			const reason = verdict.reason ? glossaryText(manifest, 'reasons', verdict.reason) : '';
			return `Sin veredicto de trayectoria. ${reason}`.trim();
		}
		const direction = DIRECTION_TEXT[verdict.direction];
		let text =
			verdict.nature === 'structural' && verdict.direction !== 'perimeter_shift'
				? `${direction} estructural`
				: verdict.nature
					? `${direction} · ${NATURE_TEXT[verdict.nature].toLowerCase()}`
					: direction;
		if (delta !== null && verdict.compared_to) {
			text += `: ${formatScoreDelta(delta)} puntos frente a ${formatPeriod(verdict.compared_to)}`;
		}
		if (verdict.persistence_months > 0) {
			text += `, ${plural(verdict.persistence_months, 'mes seguido', 'meses seguidos')}`;
		}
		return `${text}.`;
	});

	// Where the score sits between the band thresholds of the manifest.
	const zones = $derived(bandZones(manifest?.bands ?? []));
	const distances = $derived(bandDistances(entry.shown, zones));
	const position = $derived.by(() => {
		const parts: string[] = [];
		if (distances.above) {
			parts.push(
				`a ${formatScore(distances.above.distance)} puntos de ${distances.above.zone.label}`
			);
		}
		if (distances.below) {
			parts.push(
				`${formatScore(distances.below.distance)} puntos por encima de ${distances.below.zone.label}`
			);
		}
		return list(parts);
	});
	const anchors = $derived(
		zones.length > 1
			? `Las anclas ${list(zones.slice(1).map((zone) => formatNumber(fromTenths(zone.min), zone.min % 10 === 0 ? 0 : 1)))} separan ${list(zones.map((zone) => zone.label))}.`
			: ''
	);

	// What pulls the level down or up the most, read straight from the waterfall terms.
	const drivers = $derived.by(() => {
		const terms = [
			...entry.pillars
				.filter((pillar) => pillar.score !== null)
				.map((pillar) => ({
					label: pillarLabel(manifest, pillar.key).toLowerCase(),
					delta: pillar.contrib
				})),
			{ label: 'la penalización por pilar débil', delta: -entry.penalty },
			{ label: 'el tope', delta: -entry.cap.amount }
		];
		const name = (term: (typeof terms)[number]) =>
			`${term.label} (${formatScoreDelta(term.delta)})`;
		const down = terms
			.filter((term) => term.delta < 0)
			.toSorted((a, b) => a.delta - b.delta)
			.slice(0, 2);
		const up = terms
			.filter((term) => term.delta > 0)
			.toSorted((a, b) => b.delta - a.delta)
			.slice(0, 1);
		const parts: string[] = [];
		if (down.length > 0) parts.push(`resta sobre todo ${list(down.map(name))}`);
		if (up.length > 0) parts.push(`suma ${list(up.map(name))}`);
		return parts.join('; ');
	});

	const horizon = $derived(
		verdict.compared_to ? monthsBetween(verdict.compared_to, entry.month) : null
	);
	const facts = $derived([
		{
			label: horizon ? `Variación en ${plural(horizon, 'mes', 'meses')}` : 'Variación',
			value: delta === null ? '—' : `${formatScoreDelta(delta)} puntos`,
			detail: verdict.compared_to
				? `Frente a ${formatPeriod(verdict.compared_to)}`
				: 'Sin mes de comparación'
		},
		{
			label: 'Frente a su propio ruido',
			value: verdict.delta3_sigma === null ? '—' : `${formatSigned(verdict.delta3_sigma, 2)} σ`,
			detail:
				verdict.sigma === null
					? 'Sin σ propia todavía'
					: `σ propia: ${formatScore(verdict.sigma)} puntos al mes`
		},
		{
			label: 'Persistencia',
			value:
				verdict.persistence_months > 0
					? plural(verdict.persistence_months, 'mes seguido', 'meses seguidos')
					: '—',
			detail: verdict.detected_since
				? `Desde ${formatPeriod(verdict.detected_since)}`
				: 'Sin racha en curso'
		},
		{
			label: 'Historia observada',
			value: plural(entry.months_observed, 'mes', 'meses'),
			detail: entry.feed_live ? 'Feed bancario con datos' : 'Feed bancario sin datos recientes'
		}
	]);

	// 'Comparado contra qué': the size band comes from the profile, the rest from the month.
	const sizeBand = $derived.by(() => {
		const value = profile.find((attribute) => attribute.key === 'size_band')?.value;
		return typeof value === 'string' && value ? value : null;
	});
	const liquidityGates = $derived(
		entry.pillars.find((pillar) => pillar.key === 'liquidity')?.gates ?? []
	);
	const absoluteScale = $derived(liquidityGates.includes('absolute_anchors'));
	const inheritedLiquidity = $derived(liquidityGates.includes('inherited_from_group'));
	const reference = $derived([
		{
			label: 'Nivel',
			value: sizeBand
				? kind === 'group'
					? `Grupos de tamaño ${sizeBand}`
					: `Referencia de tamaño ${sizeBand}`
				: 'Tamaño no inferido',
			detail: inheritedLiquidity
				? glossaryText(manifest, 'gates', 'inherited_from_group')
				: absoluteScale
					? glossaryText(manifest, 'gates', 'absolute_anchors')
					: sizeBand
						? 'La liquidez se mide con la escala de su tramo de tamaño, no contra toda la cartera.'
						: 'Sin tramo de tamaño no hay escala segmentada de liquidez.'
		},
		{
			label: 'Punto de partida',
			value: `${formatScore(entry.base)} puntos`,
			detail:
				'Lo que marcaría la mediana de referencia con estos mismos pilares; cada pilar suma o resta frente a ella.'
		},
		{
			label: 'Trayectoria',
			value: kind === 'group' ? 'La propia historia del grupo' : 'La propia historia de la empresa',
			detail:
				verdict.available && verdict.compared_to
					? `El cambio se mide frente a ${formatPeriod(verdict.compared_to)} y se expresa en su ruido mensual habitual (σ), no en el de otros.`
					: 'Todavía no hay meses suficientes para medir su ruido mensual habitual (σ).'
		}
	]);

	const confidence = $derived([
		{ label: 'Historia', value: entry.conf.history, detail: 'Meses observados' },
		{ label: 'Cobertura', value: entry.conf.coverage, detail: 'Pilares disponibles' },
		{ label: 'Calidad', value: entry.conf.quality, detail: 'Calidad del dato' }
	]);
	// The three parts multiply into conf.value; the formula is only printed when it holds.
	const isProduct = $derived(
		Math.abs(entry.conf.history * entry.conf.coverage * entry.conf.quality - entry.conf.value) <
			0.005
	);
</script>

<Card.Root
	data-testid="verdict-card"
	data-delta-tenths={delta}
	data-compared-to={verdict.compared_to}
>
	<Card.Header>
		<Card.Description>
			{kind === 'group' ? 'Veredicto del grupo' : 'Veredicto de la empresa'} · {formatPeriod(
				entry.month
			)}
		</Card.Description>
		<Card.Title class="text-lg leading-7" data-testid="verdict-headline">{headline}</Card.Title>
	</Card.Header>
	<Card.Content class="space-y-5">
		{#if entry.abstain}<AbstainedState abstain={entry.abstain} />{/if}
		<div class="flex flex-wrap items-center gap-x-6 gap-y-4">
			<ScoreGauge
				tenths={entry.shown}
				band={entry.band}
				deltaTenths={verdict.available ? delta : null}
				abstained={entry.abstain !== null}
			/>
			<div class="min-w-0 flex-1 basis-64 space-y-3">
				<dl class="flex flex-wrap gap-x-5 gap-y-3">
					<div>
						<dt class="metric-label">Banda</dt>
						<dd><BandBadge band={entry.band} /></dd>
					</div>
					<div>
						<dt class="metric-label">Dirección y naturaleza</dt>
						<dd>
							<DirectionChip
								direction={verdict.direction}
								nature={verdict.nature}
								shockPending={verdict.shock_pending}
								available={verdict.available}
							/>
						</dd>
					</div>
					<div>
						<dt class="metric-label">Confianza</dt>
						<dd><ConfidencePill label={entry.conf.label} value={entry.conf.value} compact /></dd>
					</div>
				</dl>
				<ul class="space-y-1.5 text-sm leading-6 text-muted-foreground">
					{#if position}
						<li data-testid="verdict-position">
							<span class="font-medium text-foreground"
								>{formatScore(entry.shown)} en {distances.current?.label}:</span
							>
							{position}.
						</li>
					{/if}
					{#if drivers}
						<li data-testid="verdict-drivers">
							<span class="font-medium text-foreground"
								>Frente al punto de partida de {formatScore(entry.base)}:</span
							>
							{drivers}.
						</li>
					{/if}
					{#if verdict.available && moved}
						<li>
							<span class="font-medium text-foreground">Pilares que mueven la trayectoria:</span>
							{moved}.
						</li>
					{/if}
					{#if verdict.shock_pending && verdict.shock_month}
						<li>
							Caída brusca en {formatPeriod(verdict.shock_month)}: se confirma como estructural solo
							si persiste.
						</li>
					{/if}
					{#if entry.cap.amount > 0 && entry.cap.rule}
						<li class="flex items-start gap-2">
							<Lock class="mt-1 size-4 shrink-0 text-[var(--danger)]" aria-hidden="true" />
							<span
								><span class="font-medium text-foreground">Tope aplicado:</span>
								{glossaryText(manifest, 'caps', entry.cap.rule)}</span
							>
						</li>
					{/if}
				</ul>
			</div>
		</div>

		<dl class="grid grid-cols-2 gap-x-4 gap-y-4 border-t pt-4 xl:grid-cols-4">
			{#each facts as fact (fact.label)}
				<div>
					<dt class="metric-label">{fact.label}</dt>
					<dd class="font-data text-sm font-semibold">{fact.value}</dd>
					<dd class="mt-0.5 text-xs leading-5 text-muted-foreground">{fact.detail}</dd>
				</div>
			{/each}
		</dl>

		<section class="space-y-3 border-t pt-4" aria-labelledby={`${uid}-compared`}>
			<h2 id={`${uid}-compared`} class="flex items-center gap-2 text-sm font-semibold">
				<Gauge class="size-4 text-[var(--signal-strong)]" aria-hidden="true" /> Comparado contra qué
			</h2>
			<dl class="grid gap-x-5 gap-y-3 md:grid-cols-3" data-testid="verdict-reference">
				{#each reference as item (item.label)}
					<div>
						<dt class="metric-label">{item.label}</dt>
						<dd class="text-sm font-semibold">{item.value}</dd>
						<dd class="mt-0.5 text-xs leading-5 text-muted-foreground">{item.detail}</dd>
					</div>
				{/each}
			</dl>
			<div class="rounded-lg border bg-muted/30 px-4 pt-3 pb-2">
				<BandScale tenths={entry.shown} baseTenths={entry.base} muted={entry.abstain !== null} />
				<p class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
					<span class="flex items-center gap-1.5">
						<span class="h-3 w-0.5 rounded-full bg-[var(--ink)]" aria-hidden="true"></span> Score
					</span>
					<span class="flex items-center gap-1.5">
						<span
							class="size-2 rotate-45 rounded-[1px] border-[1.5px] border-[var(--ink)]"
							aria-hidden="true"
						></span>
						Punto de partida
					</span>
					<span>{anchors}</span>
				</p>
			</div>
		</section>

		<section class="space-y-3 border-t pt-4" aria-labelledby={`${uid}-confidence`}>
			<div class="flex flex-wrap items-center justify-between gap-2">
				<h2 id={`${uid}-confidence`} class="text-sm font-semibold">
					Confianza: acompaña al score, nunca lo modifica
				</h2>
				<ConfidencePill label={entry.conf.label} value={entry.conf.value} />
			</div>
			<dl class="grid gap-4 sm:grid-cols-3" data-testid="confidence-parts">
				{#each confidence as part (part.label)}
					<div>
						<dt class="metric-label flex items-baseline justify-between gap-2">
							<span>{part.label}</span>
							<span class="font-data text-xs tracking-normal text-foreground"
								>{formatPercent(part.value, 0)}</span
							>
						</dt>
						<dd>
							<Progress
								value={Math.round(part.value * 100)}
								class="h-1.5 [&_[data-slot=progress-indicator]]:bg-[var(--signal)]"
								aria-label={`${part.label}: ${formatPercent(part.value, 0)}`}
							/>
							<span class="mt-1 block text-xs text-muted-foreground">{part.detail}</span>
						</dd>
					</div>
				{/each}
			</dl>
			{#if isProduct}
				<p class="font-data text-xs text-muted-foreground">
					{confidence.map((part) => formatPercent(part.value, 0)).join(' × ')} = {formatPercent(
						entry.conf.value,
						0
					)}
				</p>
			{/if}
		</section>

		{#if entry.flags.length > 0}
			<section class="border-t pt-4" aria-labelledby={`${uid}-flags`}>
				<h2 id={`${uid}-flags`} class="metric-label">Avisos de lectura</h2>
				<ul class="space-y-1.5 text-sm leading-6 text-muted-foreground">
					{#each entry.flags as flag (flag)}
						<li class="flex items-start gap-2" data-flag={flag}>
							<Info class="mt-1 size-4 shrink-0" aria-hidden="true" />
							{glossaryText(manifest, 'flags', flag)}
						</li>
					{/each}
				</ul>
			</section>
		{/if}
	</Card.Content>
</Card.Root>
