<script lang="ts">
	import type { Snippet } from 'svelte';
	import { Activity, BellRing, Building2, ReceiptText } from '@lucide/svelte';
	import { base } from '$app/paths';
	import { navigating, page } from '$app/state';
	import { formatPeriod, formatTimestamp, shortHash } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import type { Manifest } from './contract.js';
	import { monthStore } from './month-store.svelte.js';

	let { manifest, children }: { manifest: Manifest; children: Snippet } = $props();

	const items = [
		{ path: '/', label: 'Cartera', icon: Building2, match: ['/', '/group'] },
		{ path: '/alerts', label: 'Alertas', icon: BellRing, match: ['/alerts'] },
		{ path: '/receipt', label: 'Recibo', icon: ReceiptText, match: ['/receipt'] }
	];
	const pathname = $derived(page.url.pathname.slice(base.length) || '/');
	const isActive = (match: string[]) =>
		match.some((prefix) =>
			prefix === '/' ? pathname === '/' : pathname === prefix || pathname.startsWith(`${prefix}/`)
		);
	const stamps = $derived([
		{ label: 'Motor', value: manifest.engine_version, title: manifest.engine_version },
		{ label: 'Parámetros', value: shortHash(manifest.params_hash), title: manifest.params_hash },
		{ label: 'Datos', value: shortHash(manifest.dataset_hash), title: manifest.dataset_hash },
		{ label: 'Bundle', value: shortHash(manifest.bundle_id), title: manifest.bundle_id },
		{
			label: 'Generado',
			value: formatTimestamp(manifest.generated_at),
			title: manifest.generated_at
		}
	]);
	const range = $derived(
		`${formatPeriod(manifest.months[0])} – ${formatPeriod(manifest.months[manifest.months.length - 1])}`
	);
</script>

<div class="flex min-h-screen flex-col bg-background text-foreground">
	<a
		href="#contenido"
		class="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:shadow-md"
		>Saltar al contenido</a
	>
	<header class="sticky top-0 z-30 border-b bg-background/92 backdrop-blur-xl">
		{#if navigating.to}
			<div class="nav-progress absolute inset-x-0 top-0 h-0.5" aria-hidden="true"></div>
		{/if}
		<div
			class="mx-auto flex max-w-[1540px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 lg:px-7"
		>
			<a href={monthStore.href('/')} class="flex items-center gap-3 rounded-lg">
				<div class="grid size-9 place-items-center rounded-lg bg-[var(--ink)] text-white">
					<Activity class="size-5" aria-hidden="true" />
				</div>
				<div>
					<div class="leading-none font-semibold tracking-[-0.02em]">Embat X-Ray</div>
					<div
						class="mt-1 text-[0.62rem] font-semibold tracking-[0.18em] text-muted-foreground uppercase"
					>
						Salud financiera por grupo
					</div>
				</div>
			</a>
			<nav
				aria-label="Principal"
				class="order-last grid w-full grid-cols-3 gap-1 sm:order-none sm:flex sm:w-auto"
			>
				{#each items as item (item.path)}
					{@const active = isActive(item.match)}
					<a
						href={monthStore.href(item.path)}
						aria-current={active ? 'page' : undefined}
						class={cn(
							'inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
							active &&
								'bg-[var(--signal-soft)] text-[var(--signal-strong)] hover:bg-[var(--signal-soft)]'
						)}
					>
						<item.icon class="size-4" aria-hidden="true" />{item.label}
					</a>
				{/each}
			</nav>
			<div class="ml-auto hidden text-right text-xs text-muted-foreground sm:block">
				<span class="metric-label mb-0">Mes de análisis</span>
				<span class="font-medium text-foreground first-letter:uppercase" data-testid="shell-month"
					>{monthStore.month ? formatPeriod(monthStore.month) : ''}</span
				>
			</div>
		</div>
	</header>

	<main
		id="contenido"
		class="mx-auto w-full max-w-[1540px] min-w-0 flex-1 px-4 py-6 lg:px-8 lg:py-8"
	>
		{@render children()}
	</main>

	<footer class="border-t bg-card/60">
		<div
			class="mx-auto flex max-w-[1540px] flex-col gap-3 px-4 py-4 text-xs text-muted-foreground lg:flex-row lg:items-center lg:justify-between lg:px-8"
		>
			<p class="max-w-xl leading-5">
				Cada cifra procede del bundle exportado por el motor: cierres mensuales de {range}. La
				confianza acompaña al score y nunca lo modifica.
			</p>
			<dl class="flex flex-wrap gap-x-5 gap-y-1" aria-label="Procedencia de los datos">
				{#each stamps as stamp (stamp.label)}
					<div class="flex items-baseline gap-1.5">
						<dt>{stamp.label}</dt>
						<dd class="font-data text-foreground" title={stamp.title}>{stamp.value}</dd>
					</div>
				{/each}
			</dl>
		</div>
	</footer>
</div>

<style>
	.nav-progress {
		background: linear-gradient(90deg, transparent, var(--signal), transparent);
		background-size: 50% 100%;
		background-repeat: no-repeat;
		animation: nav-progress 1s linear infinite;
	}
	@keyframes nav-progress {
		from {
			background-position: -50% 0;
		}
		to {
			background-position: 150% 0;
		}
	}
</style>
