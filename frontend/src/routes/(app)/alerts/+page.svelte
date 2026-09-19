<script lang="ts">
	import AlertsInbox from '$lib/xray/alerts-inbox.svelte';

	let { data } = $props();
</script>

<svelte:head>
	<title>Alertas · Embat X-Ray</title>
	<meta
		name="description"
		content="Alertas que el motor disparó y alertas que decidió no disparar, con el motivo y la ventana de cada una."
	/>
</svelte:head>

<AlertsInbox alerts={data.alerts} manifest={data.manifest} abstentions={data.abstentions} />
