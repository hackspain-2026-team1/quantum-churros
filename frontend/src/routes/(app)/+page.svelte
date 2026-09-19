<script lang="ts">
	import XrayDashboard from '$lib/xray/xray-dashboard.svelte';

	let { data } = $props();
</script>

<svelte:head
	><title>Embat X-Ray · Salud financiera en movimiento</title><meta
		name="description"
		content="Detecta, explica y actúa sobre cambios en la salud financiera de cada grupo empresarial."
	/></svelte:head
>

<XrayDashboard portfolio={data.portfolio} manifest={data.manifest} />
