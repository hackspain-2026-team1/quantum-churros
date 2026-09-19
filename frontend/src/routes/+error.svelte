<script lang="ts">
	import { FileWarning, RotateCw, SearchX } from '@lucide/svelte';
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button/index.js';
	import EmptyState from '$lib/xray/empty-state.svelte';

	// An address outside the app lands here without the shell; anything else at this
	// level means the manifest of the bundle could not be read.
	const notFound = $derived(page.status === 404);
</script>

<svelte:head>
	<title>{notFound ? 'Página no encontrada' : 'Sin datos'} · Embat X-Ray</title>
</svelte:head>

<main class="grid min-h-screen place-items-center p-6">
	{#if notFound}
		<EmptyState
			class="w-full max-w-lg"
			icon={SearchX}
			title="Esta página no existe"
			description="La dirección no corresponde a ninguna pantalla. La cartera de grupos es el punto de entrada a todo lo demás."
		>
			<Button href={`${base}/`} variant="outline">Ir a la cartera</Button>
		</EmptyState>
	{:else}
		<EmptyState
			class="w-full max-w-lg"
			icon={FileWarning}
			tone="danger"
			title="No se pudo cargar el bundle de datos"
			description={`${page.error?.message ?? ''} La aplicación solo muestra lo que exporta el motor en /data/v1; sin ese bundle no hay nada que enseñar.`.trim()}
		>
			<Button variant="outline" onclick={() => window.location.reload()}
				><RotateCw /> Reintentar</Button
			>
		</EmptyState>
	{/if}
</main>
