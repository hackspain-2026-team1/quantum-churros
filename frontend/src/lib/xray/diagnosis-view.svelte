<script lang="ts">
	import { ArrowDownRight, CalendarClock, FileSearch, ShieldCheck } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import type { DemoOverview } from './demo-data.js';
	import ScoreGauge from './score-gauge.svelte';
	import TrajectoryChart from './trajectory-chart.svelte';

	let { demo }: { demo: DemoOverview } = $props();
	let snapshot = $derived(demo.snapshot);
	let trajectory = $derived(demo.trajectory);
	let company = $derived(demo.companies.find((item) => item.id === snapshot.entity_id));
</script>

<section class="space-y-5" aria-labelledby="diagnosis-heading">
	<div>
		<p class="eyebrow">{snapshot.entity_id} · {company?.name ?? 'Empresa'}</p>
		<h1 id="diagnosis-heading">Diagnóstico explicable</h1>
		<p class="page-lead">El nivel sigue siendo aceptable; la trayectoria ya no lo es.</p>
	</div>
	<Alert.Root class="border-[var(--warning)]/35 bg-[var(--warning-soft)]"
		><CalendarClock class="size-4" /><Alert.Title
			>Detectado en mayo, cuatro cierres antes</Alert.Title
		><Alert.Description
			>El cambio aparece cuando el score todavía marcaba 78. La persistencia separa esta señal de un
			bache puntual.</Alert.Description
		></Alert.Root
	>
	<div class="grid gap-4 lg:grid-cols-[17rem_1fr]">
		<Card.Root
			><Card.Header
				><Badge variant="destructive"><ArrowDownRight /> Deterioro persistente</Badge></Card.Header
			><Card.Content class="grid place-items-center gap-5"
				><ScoreGauge score={snapshot.score} delta={snapshot.delta} />
				<div class="grid w-full grid-cols-2 gap-3 border-t pt-4">
					<div>
						<span class="metric-label">Confianza</span><strong class="flex items-center gap-1"
							><ShieldCheck class="size-4 text-[var(--signal)]" />
							{Math.round(snapshot.confidence * 100)} %</strong
						>
					</div>
					<div>
						<span class="metric-label">Persistencia</span><strong class="font-data"
							>{snapshot.persistence_months} meses</strong
						>
					</div>
				</div></Card.Content
			></Card.Root
		>
		<Card.Root
			><Card.Header
				><Card.Description>Score observado · 24 meses</Card.Description><Card.Title
					>De 82 a 68 sin un desplome aislado</Card.Title
				></Card.Header
			><Card.Content><TrajectoryChart values={trajectory} /></Card.Content></Card.Root
		>
	</div>
	<div class="grid gap-3 lg:grid-cols-2">
		{#each snapshot.drivers as driver (driver.feature)}<Card.Root class="overflow-hidden"
				><Card.Header class="pb-3"
					><div class="flex items-start justify-between gap-4">
						<div>
							<Card.Description>Driver observado</Card.Description><Card.Title class="text-base"
								>{driver.label}</Card.Title
							>
						</div>
						<span
							class:positive={driver.contribution > 0}
							class:negative={driver.contribution < 0}
							class="font-data text-xl font-semibold"
							>{driver.contribution > 0 ? '+' : ''}{driver.contribution}</span
						>
					</div></Card.Header
				><Card.Content class="space-y-3"
					><Progress
						value={Math.min(100, Math.abs(driver.contribution) * 11)}
						class={driver.contribution < 0
							? '[&_[data-slot=progress-indicator]]:bg-[var(--danger)]'
							: '[&_[data-slot=progress-indicator]]:bg-[var(--success)]'}
					/>
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div>
							<span class="metric-label">Observado</span><strong class="font-data"
								>{driver.observed}</strong
							>
						</div>
						<div>
							<span class="metric-label">Baseline</span><strong class="font-data"
								>{driver.baseline}</strong
							>
						</div>
					</div>
					<p class="flex gap-2 text-sm leading-6 text-muted-foreground">
						<FileSearch class="mt-1 size-4 shrink-0" />{driver.evidence}
					</p></Card.Content
				></Card.Root
			>{/each}
	</div>
</section>
