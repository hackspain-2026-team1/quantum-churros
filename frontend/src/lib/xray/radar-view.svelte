<script lang="ts">
	import {
		ArrowDownRight,
		ArrowUpRight,
		BellRing,
		ChevronRight,
		ShieldCheck
	} from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import type { DemoOverview } from './demo-data.js';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let { demo, onInspect }: { demo: DemoOverview; onInspect: () => void } = $props();
	let { group, companies, trajectory } = $derived(demo);</script>

<section class="space-y-5" aria-labelledby="radar-heading">
	<div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
		<div>
			<p class="eyebrow">Cierre de septiembre</p>
			<h1 id="radar-heading">Radar financiero</h1>
			<p class="page-lead">
				Prioriza cambios estructurales antes de que el nivel actual los haga evidentes.
			</p>
		</div>
		<Button onclick={onInspect}><BellRing /> Revisar {companies.length} alertas</Button>
	</div>
	<div class="grid gap-4 md:grid-cols-3">
		<Card.Root class="md:col-span-1"
			><Card.Header
				><Card.Description>Salud del grupo</Card.Description><Card.Title>{group.name}</Card.Title
				></Card.Header
			><Card.Content class="flex items-center justify-between gap-4"
				><ScoreGauge score={group.score} delta={group.delta} />
				<div class="space-y-3 text-sm">
					<div>
						<span class="metric-label">Dirección</span><strong
							class="negative flex items-center gap-1"
							><ArrowDownRight class="size-4" /> Deterioro</strong
						>
					</div>
					<div>
						<span class="metric-label">Confianza</span><strong class="flex items-center gap-1"
							><ShieldCheck class="size-4 text-[var(--signal)]" /> 92 %</strong
						>
					</div>
				</div></Card.Content
			></Card.Root
		>
		<Card.Root class="md:col-span-2"
			><Card.Header class="flex-row items-start justify-between"
				><div>
					<Card.Description>Trayectoria consolidada</Card.Description><Card.Title
						>La señal cambió antes que el score</Card.Title
					>
				</div>
				<Badge variant="outline">4,1 meses de anticipación</Badge></Card.Header
			><Card.Content><TrajectoryChart values={trajectory} months={demo.trajectory_months} compact /></Card.Content></Card.Root
		>
	</div>
	<Card.Root
		><Card.Header
			><Card.Description>Cartera priorizada</Card.Description><Card.Title
				>Empresas que requieren lectura</Card.Title
			></Card.Header
		><Card.Content class="px-0"
			><div class="divide-y md:hidden">
				{#each companies as company (company.id)}<button
						class="grid w-full grid-cols-[1fr_auto] gap-3 px-6 py-4 text-left"
						onclick={onInspect}
						><div>
							<div class="font-medium">{company.name}</div>
							<div class="font-data mt-1 text-xs text-muted-foreground">{company.id}</div>
							<Badge class="mt-3" variant={company.intent === 'danger' ? 'destructive' : 'outline'}
								>{company.signal}</Badge
							>
						</div>
						<div class="text-right">
							<div class="font-data text-2xl font-semibold">{company.score}</div>
							<span
								class:positive={company.delta > 0}
								class:negative={company.delta < -3}
								class="font-data mt-2 inline-flex items-center gap-1 text-sm font-semibold"
								>{#if company.delta > 0}<ArrowUpRight class="size-4" />{:else}<ArrowDownRight
										class="size-4"
									/>{/if}{company.delta > 0 ? '+' : ''}{company.delta}</span
							>
							<div class="mt-2 text-xs text-muted-foreground">
								Confianza {company.confidence.toLowerCase()}
							</div>
						</div></button
					>{/each}
			</div>
			<div class="hidden md:block">
				<Table.Root
					><Table.Header
						><Table.Row
							><Table.Head>Empresa</Table.Head><Table.Head>Score</Table.Head><Table.Head
								>Trayectoria</Table.Head
							><Table.Head>Señal</Table.Head><Table.Head>Confianza</Table.Head><Table.Head
								><span class="sr-only">Abrir</span></Table.Head
							></Table.Row
						></Table.Header
					><Table.Body
						>{#each companies as company (company.id)}<Table.Row class="group"
								><Table.Cell
									><div class="font-medium">{company.name}</div>
									<div class="font-data text-xs text-muted-foreground">
										{company.id}
									</div></Table.Cell
								><Table.Cell
									><span class="font-data text-xl font-semibold">{company.score}</span></Table.Cell
								><Table.Cell
									><span
										class:positive={company.delta > 0}
										class:negative={company.delta < -3}
										class="font-data inline-flex items-center gap-1 font-semibold"
										>{#if company.delta > 0}<ArrowUpRight class="size-4" />{:else}<ArrowDownRight
												class="size-4"
											/>{/if}{company.delta > 0 ? '+' : ''}{company.delta}</span
									></Table.Cell
								><Table.Cell
									><Badge variant={company.intent === 'danger' ? 'destructive' : 'outline'}
										>{company.signal}</Badge
									></Table.Cell
								><Table.Cell>{company.confidence}</Table.Cell><Table.Cell
									><Button
										variant="ghost"
										size="icon-sm"
										onclick={onInspect}
										aria-label={`Abrir ${company.name}`}><ChevronRight /></Button
									></Table.Cell
								></Table.Row
							>{/each}</Table.Body
					></Table.Root
				>
			</div></Card.Content
		></Card.Root
	>
</section>
