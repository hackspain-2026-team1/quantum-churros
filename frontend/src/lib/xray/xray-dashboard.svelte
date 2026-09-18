<script lang="ts">
	import {
		Activity,
		Building2,
		CircleGauge,
		FlaskConical,
		ListChecks,
		Radar,
		Search,
		Sparkles
	} from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Input } from '$lib/components/ui/input/index.js';
	import * as Tabs from '$lib/components/ui/tabs/index.js';
	import ActionsView from './actions-view.svelte';
	import DiagnosisView from './diagnosis-view.svelte';
	import RadarView from './radar-view.svelte';
	import ScenarioView from './scenario-view.svelte';
	import type { DemoOverview } from './demo-data.js';

	let { demo }: { demo: DemoOverview } = $props();
	let active = $state('radar');
	const tabs = [
		{ value: 'radar', label: 'Radar', icon: Radar },
		{ value: 'diagnosis', label: 'Diagnóstico', icon: CircleGauge },
		{ value: 'scenario', label: 'Escenarios', icon: FlaskConical },
		{ value: 'actions', label: 'Acciones', icon: ListChecks }
	];
</script>

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
			<div class="relative ml-auto hidden w-72 md:block">
				<Search
					class="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
				/><Input
					class="pl-9"
					placeholder="Buscar empresa o grupo"
					aria-label="Buscar empresa o grupo"
				/>
			</div>
			<Badge variant="outline" class="hidden sm:flex"><Sparkles /> API conectada</Badge><Button
				variant="ghost"
				size="icon"
				aria-label="Cambiar grupo"><Building2 /></Button
			>
		</div>
	</header>
	<div class="mx-auto grid max-w-[1540px] lg:grid-cols-[13rem_1fr]">
		<aside class="hidden min-h-[calc(100vh-4rem)] border-r px-3 py-6 lg:block">
			<div class="mb-7 px-3">
				<span class="metric-label">Workspace</span><strong class="mt-1 block text-sm"
					>{demo.group.name}</strong
				><span class="text-xs text-muted-foreground">{demo.group.period}</span>
			</div>
			<Tabs.Root bind:value={active} orientation="vertical"
				><Tabs.List class="h-auto w-full flex-col items-stretch bg-transparent p-0"
					>{#each tabs as tab (tab.value)}<Tabs.Trigger
							value={tab.value}
							class="justify-start gap-3 px-3 py-2.5 data-[state=active]:bg-[var(--signal-soft)] data-[state=active]:text-[var(--signal-strong)]"
							><tab.icon class="size-4" />{tab.label}</Tabs.Trigger
						>{/each}</Tabs.List
				></Tabs.Root
			>
			<div class="mx-3 mt-8 border-t pt-5">
				<div class="flex items-center gap-2 text-xs text-muted-foreground">
					<span
						class="size-2 rounded-full bg-[var(--success)] shadow-[0_0_0_4px_var(--success-soft)]"
					></span>Motor actualizado
				</div>
				<div class="font-data mt-2 text-[0.68rem] text-muted-foreground">
					{demo.snapshot.model_version} · {demo.snapshot.feature_version}
				</div>
			</div>
		</aside>
		<main class="min-w-0 px-4 py-6 lg:px-8 lg:py-8">
			<Tabs.Root bind:value={active}
				><Tabs.List class="mb-6 grid h-auto grid-cols-4 lg:hidden"
					>{#each tabs as tab (tab.value)}<Tabs.Trigger value={tab.value} class="gap-2 px-2"
							><tab.icon class="size-4" /><span class="hidden sm:inline">{tab.label}</span
							></Tabs.Trigger
						>{/each}</Tabs.List
				><Tabs.Content value="radar"
					><RadarView {demo} onInspect={() => (active = 'diagnosis')} /></Tabs.Content
				><Tabs.Content value="diagnosis"><DiagnosisView {demo} /></Tabs.Content><Tabs.Content
					value="scenario"><ScenarioView trajectory={demo.trajectory} /></Tabs.Content
				><Tabs.Content value="actions"><ActionsView actions={demo.actions} /></Tabs.Content
				></Tabs.Root
			>
		</main>
	</div>
</div>
