<script lang="ts">
	import { BellRing, Check, CircleDot, RotateCcw } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import type { RecommendedAction } from './demo-data.js';

	let { actions }: { actions: RecommendedAction[] } = $props();
	let statuses = $derived<Record<string, string>>(
		Object.fromEntries(actions.map((action) => [action.id, action.status]))
	);
	let pending = $state<string | null>(null);
	const advance = async (id: string) => {
		const label = statuses[id] === 'Resuelta' ? 'Reabierta' : 'Resuelta';
		const status = label === 'Resuelta' ? 'resolved' : 'reopened';
		pending = id;
		try {
			const response = await fetch(`/api/v1/actions/${id}`, {
				method: 'PATCH',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ status })
			});
			if (!response.ok) throw new Error('No se pudo actualizar la acción');
			statuses[id] = label;
		} finally {
			pending = null;
		}
	};
</script>

<section class="space-y-5" aria-labelledby="actions-heading">
	<div>
		<p class="eyebrow">Seguimiento operativo</p>
		<h1 id="actions-heading">Centro de acciones</h1>
		<p class="page-lead">
			Cada tarea conserva la señal financiera que la originó y el resultado que debe vigilar.
		</p>
	</div>
	<Alert.Root class="border-[var(--signal)]/30 bg-[var(--signal-soft)]"
		><BellRing class="size-4" /><Alert.Title>Monitor activo</Alert.Title><Alert.Description
			>X-Ray vuelve a evaluar estas acciones en cada cierre y reabre la alerta si la trayectoria no
			responde.</Alert.Description
		></Alert.Root
	>
	<div class="grid gap-3">
		{#each actions as action (action.id)}<Card.Root
				><Card.Content class="grid gap-4 p-5 lg:grid-cols-[auto_1fr_12rem_auto] lg:items-center"
					><Badge variant={action.priority === 'P1' ? 'destructive' : 'outline'}
						>{action.priority}</Badge
					>
					<div>
						<h2 class="font-semibold">{action.title}</h2>
						<p class="mt-1 text-sm leading-6 text-muted-foreground">{action.rationale}</p>
						<div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs">
							<span><span class="text-muted-foreground">Responsable</span> · {action.owner}</span
							><span><span class="text-muted-foreground">Impacto</span> · {action.impact}</span>
						</div>
					</div>
					<div>
						<span class="metric-label">Estado</span><strong class="flex items-center gap-2 text-sm"
							>{#if statuses[action.id] === 'Resuelta'}<Check
									class="size-4 text-[var(--success)]"
								/>{:else if statuses[action.id] === 'Reabierta'}<RotateCcw
									class="size-4 text-[var(--danger)]"
								/>{:else}<CircleDot class="size-4 text-[var(--warning)]" />{/if}{statuses[
								action.id
							]}</strong
						>
					</div>
					<Button
						variant="outline"
						disabled={pending === action.id}
						onclick={() => advance(action.id)}
						>{statuses[action.id] === 'Resuelta' ? 'Reabrir' : 'Resolver'}</Button
					></Card.Content
				></Card.Root
			>{/each}
	</div>
</section>
