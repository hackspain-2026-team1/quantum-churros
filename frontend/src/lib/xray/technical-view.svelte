<script lang="ts">
	import { FileWarning } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import * as Tabs from '$lib/components/ui/tabs/index.js';
	import { formatPercent, formatPeriod } from '$lib/format.js';
	import AbstainedState from './abstained-state.svelte';
	import AlertsInbox from './alerts-inbox.svelte';
	import { BundleError, loadAlerts, loadReceipt } from './bundle.js';
	import ConfidencePill from './confidence-pill.svelte';
	import ContributionWaterfall from './contribution-waterfall.svelte';
	import type { Alert, Manifest, Receipt } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import EvidenceTable from './evidence-table.svelte';
	import FocusFrame, { type FocusState } from './focus-frame.svelte';
	import { monthStore } from './month-store.svelte.js';
	import ReceiptView from './receipt-view.svelte';

	let {
		manifest,
		focus,
		picker,
		section = $bindable('desglose')
	}: { manifest: Manifest; focus: FocusState; picker: Snippet; section?: string } = $props();

	type Loaded<T> =
		{ state: 'loading' } | { state: 'ready'; value: T } | { state: 'error'; message: string };
	let alerts = $state<Loaded<Alert[]>>({ state: 'loading' });
	let receipt = $state<Loaded<Receipt>>({ state: 'loading' });

	const message = (reason: unknown) =>
		reason instanceof BundleError || reason instanceof Error ? reason.message : String(reason);

	// Read once, when the tab mounts: neither file is needed by the other tabs.
	$effect(() => {
		loadAlerts(fetch).then(
			(file) => (alerts = { state: 'ready', value: file.alerts }),
			(reason) => (alerts = { state: 'error', message: message(reason) })
		);
		loadReceipt(fetch).then(
			(value) => (receipt = { state: 'ready', value }),
			(reason) => (receipt = { state: 'error', message: message(reason) })
		);
	});

	const parts = [
		{ key: 'history', label: 'Historia' },
		{ key: 'coverage', label: 'Cobertura' },
		{ key: 'quality', label: 'Calidad' }
	] as const;
</script>

<section class="space-y-5" aria-labelledby="technical-heading">
	<div>
		<p class="eyebrow">Trazabilidad · {formatPeriod(monthStore.month)}</p>
		<h1 id="technical-heading">Detalle técnico</h1>
		<p class="page-lead">
			De dónde sale cada punto del score, con qué datos, qué alertas disparó o calló el motor y el
			recibo de la ejecución.
		</p>
	</div>
	<Tabs.Root bind:value={section}>
		<Tabs.List>
			<Tabs.Trigger value="desglose">Desglose y evidencias</Tabs.Trigger>
			<Tabs.Trigger value="alertas">Alertas</Tabs.Trigger>
			<Tabs.Trigger value="recibo">Recibo</Tabs.Trigger>
		</Tabs.List>
		<Tabs.Content value="desglose" class="space-y-4 pt-4">
			<div class="flex justify-end">{@render picker()}</div>
			<FocusFrame {focus}>
				{#snippet children(group, entry)}
					{#if entry.abstain}
						<AbstainedState abstain={entry.abstain} />
					{/if}
					<div class="grid gap-4 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
						<ContributionWaterfall {entry} />
						<div class="grid content-start gap-4">
							<Card.Root data-testid="confidence-parts"
								><Card.Header
									><Card.Description>Confianza del mes</Card.Description><Card.Title
										class="flex items-center gap-2"
										><ConfidencePill
											label={entry.conf.label}
											value={entry.conf.value}
										/></Card.Title
									></Card.Header
								><Card.Content class="grid grid-cols-3 gap-3 text-sm"
									>{#each parts as part (part.key)}
										<div>
											<span class="metric-label">{part.label}</span><strong class="font-data"
												>{formatPercent(entry.conf[part.key], 0)}</strong
											>
										</div>
									{/each}
									<p class="col-span-3 text-xs leading-5 text-muted-foreground">
										La confianza acompaña al score y nunca lo modifica. {entry.months_observed}
										{entry.months_observed === 1 ? 'mes observado' : 'meses observados'}.
									</p></Card.Content
								></Card.Root
							>
							<EvidenceTable entityId={group.id} month={entry.month} />
						</div>
					</div>
				{/snippet}
			</FocusFrame>
		</Tabs.Content>
		<Tabs.Content value="alertas" class="pt-4">
			{#if alerts.state === 'ready'}
				<AlertsInbox
					alerts={alerts.value}
					{manifest}
					abstentions={receipt.state === 'ready' ? receipt.value.abstentions : null}
				/>
			{:else if alerts.state === 'error'}
				<EmptyState
					icon={FileWarning}
					tone="danger"
					title="No se pudieron leer las alertas"
					description={alerts.message}
				/>
			{:else}
				<Skeleton class="h-72" />
			{/if}
		</Tabs.Content>
		<Tabs.Content value="recibo" class="pt-4">
			{#if receipt.state === 'ready'}
				<ReceiptView receipt={receipt.value} {manifest} />
			{:else if receipt.state === 'error'}
				<EmptyState
					icon={FileWarning}
					tone="danger"
					title="No se pudo leer el recibo"
					description={receipt.message}
				/>
			{:else}
				<Skeleton class="h-72" />
			{/if}
		</Tabs.Content>
	</Tabs.Root>
</section>
