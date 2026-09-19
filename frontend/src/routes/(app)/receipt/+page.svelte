<script lang="ts">
	import ReceiptView from '$lib/xray/receipt-view.svelte';

	let { data } = $props();
</script>

<svelte:head><title>Recibo · Embat X-Ray</title></svelte:head>

<ReceiptView receipt={data.receipt} manifest={data.manifest} />
