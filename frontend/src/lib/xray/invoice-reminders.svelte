<script lang="ts">
	import { BellRing, Check, Send } from '@lucide/svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { Button } from '$lib/components/ui/button/index.js';
	import { formatMoney, formatTimestamp } from '$lib/format.js';
	import type { InvoicesDue } from './contract.js';
	import EmptyState from './empty-state.svelte';

	let {
		entityId,
		invoicesDue
	}: { entityId: string; invoicesDue: InvoicesDue | null | undefined } = $props();

	// The engine only picks the top overdue invoices per entity; the component
	// shows the first five and tracks which reminders were sent (demo state).
	const rows = $derived(
		(invoicesDue?.rows.companies[entityId] ?? invoicesDue?.rows.groups[entityId] ?? []).slice(0, 5)
	);
	const sent = new SvelteSet<string>();
	const scope = $derived(entityId);
	$effect(() => {
		void scope;
		sent.clear();
	});
	const toggle = (operationId: string) =>
		sent.has(operationId) ? sent.delete(operationId) : sent.add(operationId);
</script>

<section class="space-y-3" aria-labelledby="invoice-reminders-heading" data-testid="invoice-reminders">
	<div>
		<p class="eyebrow">Cobrar antes</p>
		<h2 id="invoice-reminders-heading" class="text-xl font-semibold tracking-[-0.02em]">
			Recordatorios de cobro
		</h2>
	</div>
	{#if rows.length > 0}
		<ul class="divide-y rounded-lg border">
			{#each rows as row (row.operation_id)}
				<li class="flex items-center justify-between gap-3 px-3 py-2.5">
					<div class="min-w-0">
						<p class="truncate text-sm font-medium">
							{row.counterparty_id ?? 'Cliente sin identificar'}
						</p>
						<p class="text-xs text-muted-foreground">
							Vence {row.due_date ? formatTimestamp(row.due_date) : '—'} · {row.days_overdue}
							días vencida
						</p>
					</div>
					<div class="flex shrink-0 items-center gap-2 tabular-nums">
						<span class="text-sm font-semibold">{formatMoney(row.amount)}</span>
						{#if sent.has(row.operation_id)}
							<Button
								variant="outline"
								size="sm"
								onclick={() => toggle(row.operation_id)}
								aria-label="Marcar como no enviada"
							>
								<Check class="size-3.5" /> Enviado
							</Button>
						{:else}
							<Button size="sm" onclick={() => toggle(row.operation_id)} aria-label="Enviar recordatorio"
								><Send class="size-3.5" /> Recordar</Button
							>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
		<p class="text-xs text-muted-foreground">
			Las facturas de clientes recurrentes que anticipás o reclamás meten caja: el motor ya suma ese
			efecto en la acción de cobros de arriba.
		</p>
	{:else}
		<EmptyState
			icon={BellRing}
			title="Sin facturas vencidas por reclamar"
			description={`No hay facturas de clientes abiertas y vencidas para ${entityId} en el último cierre, o el feed de facturas no llega a esta entidad.`}
		/>
	{/if}
</section>
