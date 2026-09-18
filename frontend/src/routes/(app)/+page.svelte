<script lang="ts">
	import { onMount } from 'svelte';
	import { RotateCw, TriangleAlert } from '@lucide/svelte';
	import * as Alert from '$lib/components/ui/alert/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import XrayDashboard from '$lib/xray/xray-dashboard.svelte';
	import type { DemoOverview } from '$lib/xray/demo-data.js';

	let demo = $state<DemoOverview | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	const loadDemo = async () => {
		loading = true;
		error = null;
		try {
			const response = await fetch('/api/v1/demo');
			if (!response.ok) throw new Error(`La API respondió ${response.status}`);
			demo = (await response.json()) as DemoOverview;
		} catch (reason) {
			error = reason instanceof Error ? reason.message : 'No se pudo cargar X-Ray';
		} finally {
			loading = false;
		}
	};

	onMount(loadDemo);
</script>

<svelte:head
	><title>Embat X-Ray · Salud financiera en movimiento</title><meta
		name="description"
		content="Detecta, explica y actúa sobre cambios en la salud financiera de una empresa."
	/></svelte:head
>

{#if loading}
	<div class="mx-auto grid min-h-screen max-w-[1540px] gap-5 p-6" aria-label="Cargando X-Ray">
		<Skeleton class="h-12 w-full" />
		<div class="grid gap-4 md:grid-cols-3">
			<Skeleton class="h-56" />
			<Skeleton class="h-56 md:col-span-2" />
		</div>
		<Skeleton class="h-80" />
	</div>
{:else if error}
	<div class="grid min-h-screen place-items-center p-6">
		<Alert.Root variant="destructive" class="max-w-lg">
			<TriangleAlert class="size-4" />
			<Alert.Title>No se pudo cargar el radar</Alert.Title>
			<Alert.Description class="space-y-4">
				<p>{error}</p>
				<Button variant="outline" onclick={loadDemo}><RotateCw /> Reintentar</Button>
			</Alert.Description>
		</Alert.Root>
	</div>
{:else if demo}
	<XrayDashboard {demo} />
{/if}
