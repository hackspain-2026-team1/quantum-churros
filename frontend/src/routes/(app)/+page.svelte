<script lang="ts">
	import PortfolioView from '$lib/xray/portfolio-view.svelte';

	let { data } = $props();
</script>

<svelte:head>
	<title>Cartera · Embat X-Ray</title>
	<meta
		name="description"
		content="Salud financiera de cada grupo empresarial, mes a mes, con su veredicto y su explicación."
	/>
</svelte:head>

<PortfolioView portfolio={data.portfolio} manifest={data.manifest} />
