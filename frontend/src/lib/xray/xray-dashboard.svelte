<script lang="ts">
	import {
		Activity,
		BookOpen,
		CircleGauge,
		FlaskConical,
		ListChecks,
		Radar,
		Search,
		Sparkles,
		Wrench
	} from '@lucide/svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Tabs from '$lib/components/ui/tabs/index.js';
	import { formatPeriod, formatScore, shortHash } from '$lib/format.js';
	import ActionsView from './actions-view.svelte';
	import { BundleError, loadGroup } from './bundle.js';
	import type { Manifest, Portfolio } from './contract.js';
	import DiagnosisView from './diagnosis-view.svelte';
	import type { FocusState } from './focus-frame.svelte';
	import FocusPicker from './focus-picker.svelte';
	import { monthStore } from './month-store.svelte.js';
	import { normalizeText, portfolioRows, sortRows } from './portfolio.js';
	import RadarView from './radar-view.svelte';
	import ScenarioView from './scenario-view.svelte';
	import TechnicalView from './technical-view.svelte';

	let { portfolio, manifest }: { portfolio: Portfolio; manifest: Manifest } = $props();

	const tabs = [
		{ value: 'radar', label: 'Radar', icon: Radar },
		{ value: 'diagnostico', label: 'Diagnóstico', icon: CircleGauge },
		{ value: 'escenario', label: 'Escenarios', icon: FlaskConical },
		{ value: 'acciones', label: 'Acciones', icon: ListChecks },
		{ value: 'tecnico', label: 'Técnico', icon: Wrench }
	];
	const SECTIONS = ['desglose', 'alertas', 'recibo'];

	// The URL holds the tab, the focused group and the technical section, so links and
	// reloads land on the same screen: /?tab=tecnico&focus=<group>&section=recibo.
	const param = (name: string) => page.url.searchParams.get(name);
	const setParams = (changes: Record<string, string | null>) => {
		const url = new URL(page.url);
		for (const [name, value] of Object.entries(changes)) {
			if (value) url.searchParams.set(name, value);
			else url.searchParams.delete(name);
		}
		goto(url, { replaceState: true, keepFocus: true, noScroll: true });
	};
	const active = $derived(tabs.find((tab) => tab.value === param('tab'))?.value ?? 'radar');
	const setActive = (value: string) => setParams({ tab: value === 'radar' ? null : value });
	const section = $derived(
		SECTIONS.includes(param('section') ?? '') ? param('section')! : 'desglose'
	);

	// Lowest score first: the groups that need reading open the list.
	const rows = $derived(sortRows(portfolioRows(portfolio, monthStore.month), 'shown', 'asc'));

	let query = $state('');
	let searchFocused = $state(false);
	const matches = $derived(
		query
			? rows
					.filter((row) =>
						normalizeText(`${row.id} ${row.group.industry ?? ''}`).includes(normalizeText(query))
					)
					.slice(0, 8)
			: []
	);
	const openGroup = (id: string) => {
		query = '';
		searchFocused = false;
		goto(monthStore.href(`/group/${id}`));
	};

	// Diagnóstico, Escenarios and Técnico look at one group: the one in ?focus=, else the
	// first group of the priority list that has a score this month.
	const focusId = $derived(
		portfolio.groups.find((group) => group.id === param('focus'))?.id ??
			rows.find((row) => row.shown !== null)?.id ??
			null
	);
	let focus = $state<FocusState>({ state: 'idle' });
	const needsFocus = $derived(active !== 'radar' && active !== 'acciones');
	$effect(() => {
		const id = focusId;
		if (!needsFocus) return;
		if (!id) {
			focus = { state: 'idle' };
			return;
		}
		let cancelled = false;
		focus = { state: 'loading', id };
		loadGroup(fetch, id).then(
			(group) => {
				if (!cancelled) focus = { state: 'ready', group };
			},
			(reason) => {
				if (cancelled) return;
				const message =
					reason instanceof BundleError || reason instanceof Error
						? reason.message
						: String(reason);
				focus = { state: 'error', id, message };
			}
		);
		return () => {
			cancelled = true;
		};
	});
</script>

{#snippet picker()}
	<FocusPicker {rows} value={focusId} onChange={(id) => setParams({ focus: id })} />
{/snippet}

<div class="min-h-screen bg-background text-foreground">
	<header class="sticky top-0 z-30 border-b bg-background/92 backdrop-blur-xl">
		<div class="mx-auto flex h-16 max-w-[1540px] items-center gap-4 px-4 lg:px-7">
			<div class="flex items-center gap-3">
				<div class="grid size-9 place-items-center rounded-lg bg-[var(--ink)] text-white">
					<Activity class="size-5" />
				</div>
				<div>
					<div class="leading-none font-semibold tracking-[-0.02em]">Embat X-Ray</div>
					<div
						class="mt-1 text-[0.62rem] font-semibold tracking-[0.18em] text-muted-foreground uppercase"
					>
						Decision intelligence
					</div>
				</div>
			</div>
			<div class="relative ml-auto w-44 sm:w-72">
				<Search
					class="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
				/><Input
					class="pl-9"
					placeholder="Buscar grupo o sector"
					aria-label="Buscar grupo o sector"
					bind:value={query}
					autocomplete="off"
					onfocus={() => (searchFocused = true)}
					onblur={() => setTimeout(() => (searchFocused = false), 150)}
					onkeydown={(event) => {
						if (event.key === 'Enter' && matches[0]) openGroup(matches[0].id);
						if (event.key === 'Escape') searchFocused = false;
					}}
				/>
				{#if searchFocused && matches.length > 0}
					<ul
						class="absolute top-full left-0 z-40 mt-1 w-full rounded-md border bg-background py-1 shadow-md"
						role="listbox"
						aria-label="Resultados de grupo"
					>
						{#each matches as row (row.id)}
							<li>
								<button
									type="button"
									class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-muted"
									onmousedown={() => openGroup(row.id)}
								>
									<span>
										<span class="font-data block font-medium">{row.id}</span>
										<span class="block text-xs text-muted-foreground"
											>{row.group.industry ?? 'Sin sector'}</span
										>
									</span>
									<span
										class="font-data text-lg font-semibold"
										class:text-[var(--danger)]={row.band === 'critical'}
										>{row.shown === null ? '—' : formatScore(row.shown)}</span
									>
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
			<Badge variant="outline" class="hidden sm:flex" title={manifest.bundle_id}
				><Sparkles /> Bundle {shortHash(manifest.bundle_id, 8)}</Badge
			>
		</div>
	</header>
	<div class="mx-auto grid max-w-[1540px] lg:grid-cols-[13rem_1fr]">
		<aside class="hidden min-h-[calc(100vh-4rem)] border-r px-3 py-6 lg:block">
			<div class="mb-7 px-3">
				<span class="metric-label">Workspace</span><strong class="mt-1 block text-sm"
					>Cartera de {manifest.counts.groups} grupos</strong
				><span
					class="text-xs text-muted-foreground first-letter:uppercase"
					data-testid="shell-month">{formatPeriod(monthStore.month)}</span
				>
			</div>
			<Tabs.Root bind:value={() => active, setActive} orientation="vertical"
				><Tabs.List class="h-auto w-full flex-col items-stretch bg-transparent p-0"
					>{#each tabs as tab (tab.value)}<Tabs.Trigger
							value={tab.value}
							class="justify-start gap-3 px-3 py-2.5 data-[state=active]:bg-[var(--signal-soft)] data-[state=active]:text-[var(--signal-strong)]"
							><tab.icon class="size-4" />{tab.label}</Tabs.Trigger
						>{/each}</Tabs.List
				>
			</Tabs.Root>
			<a
				href={monthStore.href('/wiki')}
				class="mt-4 flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent"
			>
				<BookOpen class="size-4" />Wiki · cómo lo resolvimos
			</a>
			<div class="mx-3 mt-8 border-t pt-5">
				<div class="flex items-center gap-2 text-xs text-muted-foreground">
					<span
						class="size-2 rounded-full bg-[var(--success)] shadow-[0_0_0_4px_var(--success-soft)]"
					></span>Motor {manifest.engine_version}
				</div>
				<div class="font-data mt-2 text-[0.68rem] text-muted-foreground">
					parámetros {shortHash(manifest.params_hash, 8)} · datos {shortHash(
						manifest.dataset_hash,
						8
					)}
				</div>
			</div>
		</aside>
		<main class="min-w-0 px-4 py-6 lg:px-8 lg:py-8">
			<Tabs.Root bind:value={() => active, setActive}
				><Tabs.List class="mb-6 grid h-auto grid-cols-5 lg:hidden"
					>{#each tabs as tab (tab.value)}<Tabs.Trigger value={tab.value} class="gap-2 px-2"
							><tab.icon class="size-4" /><span class="hidden sm:inline">{tab.label}</span
							></Tabs.Trigger
						>{/each}</Tabs.List
				>
				<!-- Inactive tab panels stay mounted, so each view is only created while its tab is open. -->
				<Tabs.Content value="radar">
					{#if active === 'radar'}
						<RadarView
							{portfolio}
							{manifest}
							{rows}
							{query}
							onAlerts={() => setParams({ tab: 'tecnico', section: 'alertas' })}
						/>
					{/if}
				</Tabs.Content>
				<Tabs.Content value="diagnostico">
					{#if active === 'diagnostico'}<DiagnosisView {focus} {picker} />{/if}
				</Tabs.Content>
				<Tabs.Content value="escenario">
					{#if active === 'escenario'}<ScenarioView {focus} {picker} />{/if}
				</Tabs.Content>
				<Tabs.Content value="acciones">
					{#if active === 'acciones'}<ActionsView {rows} />{/if}
				</Tabs.Content>
				<Tabs.Content value="tecnico">
					{#if active === 'tecnico'}
						<TechnicalView
							{manifest}
							{focus}
							{picker}
							bind:section={() => section, (value) => setParams({ section: value })}
						/>
					{/if}
				</Tabs.Content></Tabs.Root
			>
		</main>
	</div>
</div>
