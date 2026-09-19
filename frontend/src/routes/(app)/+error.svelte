<script lang="ts">
	import { FileWarning } from '@lucide/svelte';
	import { page } from '$app/state';
	import { Button } from '$lib/components/ui/button/index.js';
	import EmptyState from '$lib/xray/empty-state.svelte';
	import { monthStore } from '$lib/xray/month-store.svelte.js';
</script>

<svelte:head><title>No disponible · Embat X-Ray</title></svelte:head>

<EmptyState
	icon={FileWarning}
	tone="danger"
	title={page.status === 404 ? 'Esta página no existe' : 'No se pudo leer este dato del bundle'}
	description={page.error?.message}
>
	<Button href={monthStore.href('/')} variant="outline">Volver a la cartera</Button>
</EmptyState>
