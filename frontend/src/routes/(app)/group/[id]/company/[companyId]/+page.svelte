<script lang="ts">
	import { FileX } from '@lucide/svelte';
	import { ArrowLeft } from '@lucide/svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import EmptyState from '$lib/xray/empty-state.svelte';
	import EntityView from '$lib/xray/entity-view.svelte';
	import { monthStore } from '$lib/xray/month-store.svelte.js';

	let { data } = $props();

	const group = $derived(data.group);
	const company = $derived(data.company);
	const summary = $derived(data.summary);
	const groupHref = $derived(monthStore.href(`/group/${group.id}`));
	const eyebrow = $derived(
		['Empresa', `Grupo ${group.id}`, summary.role, summary.treasury_class]
			.filter(Boolean)
			.join(' · ')
	);
</script>

<svelte:head><title>{summary.id} · Rumbo</title></svelte:head>

{#if company}
	<EntityView
		id={company.id}
		{eyebrow}
		entries={company.months}
		series={company.series}
		context={company.context}
		firstMonth={company.first_month}
		backHref={groupHref}
		backLabel={`Volver a ${group.id}`}
		technicalHref={monthStore.href(`/?tab=tecnico&focus=${group.id}`)}
		invoicesDue={data.invoicesDue}
	/>
{:else}
	<div class="mx-auto max-w-[1540px] space-y-5 px-4 py-6 lg:px-8 lg:py-8">
		<Button variant="ghost" size="sm" href={groupHref}
			><ArrowLeft class="size-4" /> Volver a {group.id}</Button
		>
		<EmptyState
			icon={FileX}
			title={`Este bundle no incluye el detalle de ${summary.id}`}
			description="La exportación trae solo el resumen de la empresa dentro de su grupo. Su score mensual figura en la tabla de empresas del grupo."
		/>
	</div>
{/if}
