<script lang="ts">
	import { Landmark } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatEuroCompact } from '$lib/format.js';

	export interface DebtProduct {
		product_id: string;
		type: string;
		type_label: string;
		label: string;
		bank_name: string;
		currency: string;
		granted: number | null;
		outstanding: number | null;
	}

	const BANK_DOMAINS: { match: string; domain: string; name: string }[] = [
		{ match: 'santander', domain: 'santander.com', name: 'Banco Santander' },
		{ match: 'caixabank', domain: 'caixabank.es', name: 'CaixaBank' },
		{ match: 'bbva', domain: 'bbva.com', name: 'BBVA' },
		{ match: 'sabadell', domain: 'bancsabadell.com', name: 'Banco Sabadell' },
		{ match: 'bankinter', domain: 'bankinter.com', name: 'Bankinter' },
		{ match: 'banca march', domain: 'bancamarch.es', name: 'Banca March' },
		{ match: 'ing', domain: 'ing.es', name: 'ING' },
		{ match: 'santander consumer', domain: 'santanderconsumer.es', name: 'Santander Consumer' },
		{ match: 'wizink', domain: 'wizink.es', name: 'Wizink' },
		{ match: 'evo', domain: 'evobanco.com', name: 'Evo Banco' },
		{ match: 'unnicajacas', domain: 'unnicajacas.es', name: 'Unicaja' },
		{ match: 'kutxabank', domain: 'kutxabank.es', name: 'Kutxabank' },
		{ match: 'abanca', domain: 'abanca.com', name: 'Abanca' },
		{ match: 'ibercaja', domain: 'ibercaja.es', name: 'Ibercaja' }
	];

	interface BankFavicon {
		domain: string;
		name: string;
	}

	const resolveBank = (bankName: string): BankFavicon => {
		const normalized = bankName.toLowerCase();
		const found = BANK_DOMAINS.find((bank) => normalized.includes(bank.match));
		return found ?? { domain: 'example.com', name: bankName };
	};

	const faviconUrl = (domain: string) =>
		`https://www.google.com/s2/favicons?domain=${domain}&sz=32`;

	let { products }: { products: DebtProduct[] } = $props();
</script>

<Card.Root>
	<Card.Header class="pb-3">
		<div class="flex items-center gap-2">
			<Landmark class="size-4 text-muted-foreground" />
			<Card.Title class="text-base">Financiación contratada</Card.Title>
		</div>
		<Card.Description>Productos de deuda activos en el cierre actual.</Card.Description>
	</Card.Header>
	<Card.Content>
		{#if products.length === 0}
			<p class="text-sm text-muted-foreground">Sin productos de financiación registrados.</p>
		{:else}
			<ul class="divide-y">
				{#each products as product (product.product_id)}
					{@const bank = resolveBank(product.bank_name)}
					<li class="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
						<div class="flex gap-3">
							<img
								src={faviconUrl(bank.domain)}
								alt={bank.name}
								width="20"
								height="20"
								class="mt-0.5 size-5 shrink-0 rounded-sm"
								onerror={(event) => {
									const target = event.currentTarget as HTMLImageElement;
									target.style.display = 'none';
								}}
							/>
							<div class="space-y-1">
								<div class="flex flex-wrap items-center gap-2">
									<Badge variant="outline">{product.type_label}</Badge>
									<span class="font-medium">{product.label}</span>
								</div>
								<p class="text-sm text-muted-foreground">{product.bank_name}</p>
							</div>
						</div>
						<dl class="grid shrink-0 gap-1 text-right text-sm">
							{#if product.granted != null}
								<div>
									<dt class="text-muted-foreground">Concedido</dt>
									<dd class="font-data">{formatEuroCompact(product.granted)}</dd>
								</div>
							{/if}
							{#if product.outstanding != null}
								<div>
									<dt class="text-muted-foreground">Pendiente</dt>
									<dd class="font-data">{formatEuroCompact(product.outstanding)}</dd>
								</div>
							{/if}
						</dl>
					</li>
				{/each}
			</ul>
		{/if}
	</Card.Content>
</Card.Root>
