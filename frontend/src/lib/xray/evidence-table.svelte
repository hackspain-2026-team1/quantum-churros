<script lang="ts">
	import { CalendarOff, FileSearch, FileX, FileWarning } from '@lucide/svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import {
		formatEvidencePeriod,
		formatNumber,
		formatPeriod,
		formatRatio,
		formatUnitValue
	} from '$lib/format.js';
	import { BundleError, loadEvidence } from './bundle.js';
	import { PILLAR_KEYS, type EvidenceFile, type EvidenceRow, type PillarKey } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { pillarLabel } from './labels.js';
	import { monthStore } from './month-store.svelte.js';
	import { entryAt } from './month.js';

	let {
		entityId,
		month,
		kind = 'group'
	}: {
		/** Group or company id; evidence/<id>.json is read only when the card mounts. */
		entityId: string;
		month: string;
		/** Whose evidence this is; only changes the wording. */
		kind?: 'group' | 'company';
	} = $props();

	type Status =
		| { state: 'loading' }
		| { state: 'ready'; file: EvidenceFile }
		| { state: 'missing' }
		| { state: 'error'; message: string };

	let status = $state<Status>({ state: 'loading' });

	// Lazy: the page renders without waiting for this file; bundle.ts caches it per bundle.
	$effect(() => {
		const id = entityId;
		let cancelled = false;
		status = { state: 'loading' };
		loadEvidence(fetch, id)
			.then((file) => {
				if (!cancelled) status = { state: 'ready', file };
			})
			.catch((reason: unknown) => {
				if (cancelled) return;
				status =
					reason instanceof BundleError && reason.kind === 'missing'
						? { state: 'missing' }
						: {
								state: 'error',
								message: reason instanceof Error ? reason.message : String(reason)
							};
			});
		return () => {
			cancelled = true;
		};
	});

	const manifest = $derived(page.data.manifest);
	const file = $derived(status.state === 'ready' ? status.file : null);
	const covered = $derived(file?.months.map((entry) => entry.month) ?? []);
	const rows = $derived(file ? (entryAt(file.months, month)?.rows ?? null) : null);

	type Section = { key: PillarKey | 'entity'; label: string; rows: EvidenceRow[] };
	// Pillars in contract order, then the facts about the whole entity-month.
	const sections = $derived.by((): Section[] => {
		if (!rows) return [];
		const result: Section[] = PILLAR_KEYS.map((key) => ({
			key,
			label: pillarLabel(manifest, key),
			rows: rows.filter((row) => row.pillar === key)
		}));
		result.push({
			key: 'entity',
			label: kind === 'group' ? 'Todo el grupo' : 'Toda la empresa',
			rows: rows.filter((row) => row.pillar === null)
		});
		return result.filter((section) => section.rows.length > 0);
	});
	const sourceFiles = $derived([...new Set((rows ?? []).map((row) => row.source_file))].sort());
	// A bare ratio reads better without the word 'ratio' after it; every other unit is the shared rule.
	const display = (row: EvidenceRow) =>
		row.unit === 'ratio' && typeof row.value === 'number'
			? formatRatio(row.value)
			: formatUnitValue(row.value, row.unit);
	const summary = $derived(
		[
			'Evidencias',
			formatPeriod(month),
			...(rows
				? [
						`${formatNumber(rows.length)} ${rows.length === 1 ? 'dato agregado' : 'datos agregados'} de ${formatNumber(sourceFiles.length)} ${sourceFiles.length === 1 ? 'fichero' : 'ficheros'}`
					]
				: [])
		].join(' · ')
	);
	const rowCount = (row: EvidenceRow) =>
		row.n_rows === null
			? 'Derivado'
			: `${formatNumber(row.n_rows)} ${row.n_rows === 1 ? 'fila' : 'filas'}`;
</script>

<Card.Root data-testid="evidence-table">
	<Card.Header>
		<Card.Description>{summary}</Card.Description>
		<Card.Title>Los datos que hay detrás de cada pilar</Card.Title>
	</Card.Header>
	<Card.Content class={['@container', rows && rows.length > 0 && 'px-0']}>
		{#if status.state === 'loading'}
			<div class="space-y-2" role="status" aria-label="Cargando evidencias">
				{#each [0, 1, 2, 3, 4] as line (line)}<Skeleton class="h-8 w-full" />{/each}
			</div>
		{:else if status.state === 'missing'}
			<EmptyState
				compact
				icon={FileX}
				title="Este bundle no incluye evidencias de esta entidad"
				description="Las filas de evidencia se exportan por entidad; el score y los pilares de arriba no dependen de este fichero."
			/>
		{:else if status.state === 'error'}
			<EmptyState
				compact
				icon={FileWarning}
				tone="danger"
				title="No se pudieron leer las evidencias"
				description={status.message}
			/>
		{:else if rows === null}
			<EmptyState
				compact
				icon={CalendarOff}
				title={`Sin evidencias exportadas para ${formatPeriod(month)}`}
				description={covered.length > 0
					? `El bundle guarda las evidencias de ${formatPeriod(covered[0])} a ${formatPeriod(covered[covered.length - 1])}.`
					: 'El fichero de evidencias de esta entidad está vacío.'}
			>
				{#if covered.length > 0}
					<Button
						variant="outline"
						size="sm"
						onclick={() => monthStore.select(covered[covered.length - 1])}
					>
						Ir a {formatPeriod(covered[covered.length - 1])}
					</Button>
				{/if}
			</EmptyState>
		{:else if rows.length === 0}
			<EmptyState
				compact
				icon={FileSearch}
				title="Ningún dato agregado este mes"
				description="El motor no exportó filas de evidencia para este cierre."
			/>
		{:else}
			<div class="divide-y @2xl:hidden">
				{#each sections as section (section.key)}
					<section class="px-6 py-3" aria-label={section.label}>
						<h2 class="metric-label">{section.label}</h2>
						<ul class="space-y-3">
							{#each section.rows as row, index (`${row.label}-${row.period}-${index}`)}
								<li class="grid grid-cols-[1fr_auto] gap-x-3 gap-y-0.5" data-evidence-row>
									<span class="text-sm leading-5">{row.label}</span>
									<span class="font-data text-right text-sm font-semibold tabular-nums"
										>{display(row)}</span
									>
									<span class="col-span-2 text-xs text-muted-foreground">
										{formatEvidencePeriod(row.period)} ·
										<span class="font-data">{row.source_file}</span> · {rowCount(row)}
									</span>
								</li>
							{/each}
						</ul>
					</section>
				{/each}
			</div>
			<div class="hidden @2xl:block">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head class="pl-6">Dato</Table.Head>
							<Table.Head class="text-right">Valor</Table.Head>
							<Table.Head>Periodo</Table.Head>
							<Table.Head>Fichero</Table.Head>
							<Table.Head class="pr-6 text-right">Filas</Table.Head>
						</Table.Row>
					</Table.Header>
					{#each sections as section (section.key)}
						<Table.Body data-evidence-section={section.key}>
							<Table.Row class="bg-muted/40 hover:bg-muted/40">
								<Table.Head colspan={5} scope="rowgroup" class="h-8 pl-6"
									><span class="metric-label mb-0">{section.label}</span></Table.Head
								>
							</Table.Row>
							{#each section.rows as row, index (`${row.label}-${row.period}-${index}`)}
								<Table.Row data-evidence-row>
									<Table.Cell class="pl-6 whitespace-normal">{row.label}</Table.Cell>
									<Table.Cell class="font-data text-right font-semibold tabular-nums"
										>{display(row)}</Table.Cell
									>
									<Table.Cell class="text-muted-foreground"
										>{formatEvidencePeriod(row.period)}</Table.Cell
									>
									<Table.Cell class="font-data text-xs text-muted-foreground"
										>{row.source_file}</Table.Cell
									>
									<Table.Cell class="font-data pr-6 text-right text-xs text-muted-foreground"
										>{rowCount(row)}</Table.Cell
									>
								</Table.Row>
							{/each}
						</Table.Body>
					{/each}
				</Table.Root>
			</div>
			<p class="border-t px-6 pt-3 text-xs leading-5 text-muted-foreground">
				Cada fila es un agregado calculado sobre los ficheros de origen; nunca se muestra un
				movimiento ni una descripción individual.
			</p>
		{/if}
	</Card.Content>
</Card.Root>
