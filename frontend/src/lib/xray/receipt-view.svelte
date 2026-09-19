<script lang="ts">
	import {
		CircleCheck,
		CircleDashed,
		CircleX,
		FlaskConical,
		Info,
		TriangleAlert
	} from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatNumber, formatTimestamp } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import {
		CHECK_STATUSES,
		CHECK_STATUS_TEXT,
		type CheckStatus,
		type Manifest,
		type Receipt
	} from './contract.js';
	import EmptyState from './empty-state.svelte';
	import ReceiptAbstentions from './receipt-abstentions.svelte';
	import ReceiptCheckCard from './receipt-check-card.svelte';
	import ReceiptSignals from './receipt-signals.svelte';
	import { CHECK_STATUS_TONE, TONE_TEXT } from './tones.js';

	let { receipt, manifest }: { receipt: Receipt; manifest: Manifest } = $props();

	const icons = { pass: CircleCheck, fail: CircleX, info: Info, not_run: CircleDashed } as const;
	const meaning: Record<CheckStatus, string> = {
		pass: 'La propiedad se cumple',
		fail: 'La propiedad no se cumple',
		info: 'Mide, no aprueba ni suspende',
		not_run: 'Fuera de esta exportación'
	};

	const counts = $derived(
		Object.fromEntries(
			CHECK_STATUSES.map((status) => [
				status,
				receipt.checks.filter((check) => check.status === status).length
			])
		) as Record<CheckStatus, number>
	);
	const judged = $derived(counts.pass + counts.fail);
	const failed = $derived(receipt.checks.filter((check) => check.status === 'fail'));
	// The conclusion a reader should leave with, assembled from the statuses of the receipt.
	const conclusion = $derived.by(() => {
		if (judged === 0) return 'Esta exportación no trae pruebas con veredicto';
		if (counts.fail === 0) {
			return judged === 1
				? 'La prueba con veredicto se supera'
				: `Las ${formatNumber(judged)} pruebas con veredicto se superan`;
		}
		return `${formatNumber(counts.fail)} de ${formatNumber(judged)} pruebas con veredicto no ${
			counts.fail === 1 ? 'se supera' : 'se superan'
		}`;
	});

	// The receipt must describe the same run as the bundle on screen.
	const sameRun = $derived(
		receipt.engine_version === manifest.engine_version &&
			receipt.params_hash === manifest.params_hash &&
			receipt.dataset_hash === manifest.dataset_hash
	);
	const fingerprint = $derived([
		{ label: 'Motor', value: receipt.engine_version },
		{ label: 'Parámetros', value: receipt.params_hash },
		{ label: 'Datos', value: receipt.dataset_hash }
	]);
</script>

<section class="space-y-6" aria-labelledby="receipt-heading">
	<div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:items-start">
		<div>
			<h2 id="receipt-heading" class="eyebrow">Recibo</h2>
			<p
				class="text-3xl font-semibold tracking-[-0.045em] text-balance md:text-4xl"
				role="doc-subtitle"
			>
				Por qué puedes fiarte de este número
			</p>
			<p class="page-lead">
				Un score solo vale si se puede comprobar. Este recibo enseña con qué motor, parámetros y
				datos se calculó esta exportación, qué pruebas supera sin usar etiquetas, qué señales deja
				fuera y dónde prefiere no opinar.
			</p>
		</div>

		<Card.Root class="gap-3 py-4" data-testid="receipt-fingerprint" data-same-run={sameRun}>
			<Card.Header class="px-4">
				<Card.Description>Huella de esta ejecución</Card.Description>
			</Card.Header>
			<Card.Content class="space-y-3 px-4">
				<dl class="space-y-2 text-sm">
					{#each fingerprint as stamp (stamp.label)}
						<div class="grid grid-cols-[6rem_1fr] items-baseline gap-3">
							<dt class="text-muted-foreground">{stamp.label}</dt>
							<dd class="font-data text-xs leading-5 font-medium break-all">{stamp.value}</dd>
						</div>
					{/each}
				</dl>
				{#if sameRun}
					<p class="flex items-start gap-2 border-t pt-3 text-xs leading-5 text-muted-foreground">
						<CircleCheck class="mt-0.5 size-4 shrink-0 text-[var(--success)]" aria-hidden="true" />
						<span
							>Coincide con el bundle que ves en el resto de pantallas, generado el {formatTimestamp(
								manifest.generated_at
							)}.</span
						>
					</p>
				{/if}
			</Card.Content>
		</Card.Root>
	</div>

	{#if !sameRun}
		<Alert.Root variant="destructive">
			<TriangleAlert class="size-4" />
			<Alert.Title>El recibo no corresponde a este bundle</Alert.Title>
			<Alert.Description>
				La versión del motor o las huellas del recibo no coinciden con las del manifiesto: estas
				pruebas describen otra ejecución.
			</Alert.Description>
		</Alert.Root>
	{/if}

	<section class="space-y-4" aria-labelledby="receipt-checks-heading">
		<div class="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
			<div>
				<p class="metric-label">Pruebas sin etiquetas</p>
				<h2 id="receipt-checks-heading" class="text-xl font-semibold" data-testid="receipt-verdict">
					{receipt.checks.length === 0 ? 'Exportación sin batería de pruebas' : conclusion}
				</h2>
				{#if failed.length > 0}
					<p class="mt-1 text-sm text-[var(--danger-strong)]">
						No superadas: {failed.map((check) => check.title).join(' · ')}
					</p>
				{/if}
			</div>
			{#if receipt.checks.length > 0}
				<dl class="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4" aria-label="Pruebas por estado">
					{#each CHECK_STATUSES as status (status)}
						{@const Icon = icons[status]}
						<div data-status-count={status}>
							<dt class="metric-label flex items-center gap-1.5">
								<Icon
									class={cn('size-3.5', TONE_TEXT[CHECK_STATUS_TONE[status]])}
									aria-hidden="true"
								/>
								{CHECK_STATUS_TEXT[status]}
							</dt>
							<dd>
								<span
									class={cn(
										'font-data text-2xl leading-none font-semibold tabular-nums',
										counts[status] === 0 && 'text-muted-foreground'
									)}>{formatNumber(counts[status])}</span
								>
								<span class="mt-1 block text-xs leading-4 text-muted-foreground"
									>{meaning[status]}</span
								>
							</dd>
						</div>
					{/each}
				</dl>
			{/if}
		</div>

		{#if receipt.checks.length === 0}
			<EmptyState
				icon={FlaskConical}
				title="Este bundle se exportó sin ejecutar la validación"
				description="Ejecuta la batería de pruebas del motor y vuelve a exportar: aquí aparecerá una tarjeta por prueba, con su resultado y sus medidas."
			/>
		{:else}
			<ul class="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
				{#each receipt.checks as check (check.key)}
					<li><ReceiptCheckCard {check} /></li>
				{/each}
			</ul>
		{/if}
	</section>

	<ReceiptSignals signals={receipt.signals} />

	<ReceiptAbstentions abstentions={receipt.abstentions} {manifest} />
</section>
