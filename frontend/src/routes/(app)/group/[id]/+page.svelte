<script lang="ts">
	import { formatNumber, formatPeriod } from '$lib/format.js';
	import CompanyDrilldown from '$lib/xray/company-drilldown.svelte';
	import EntityView from '$lib/xray/entity-view.svelte';
	import ProfileCard from '$lib/xray/profile-card.svelte';
	import { monthStore } from '$lib/xray/month-store.svelte.js';

	let { data } = $props();

	const group = $derived(data.group);
	const count = $derived(group.companies.length);
</script>

<svelte:head><title>{group.id} · Embat X-Ray</title></svelte:head>

<EntityView
	id={group.id}
	eyebrow={`Grupo · ${formatNumber(count)} ${count === 1 ? 'empresa' : 'empresas'} · con datos desde ${formatPeriod(group.first_month)}`}
	entries={group.months}
	series={group.series}
	context={group.context}
	firstMonth={group.first_month}
	backHref={monthStore.href('/')}
	backLabel="Volver al radar"
	technicalHref={monthStore.href(`/?tab=tecnico&focus=${group.id}`)}
	invoicesDue={data.invoicesDue}
>
	<CompanyDrilldown {group} month={monthStore.month} />
	<ProfileCard profile={group.profile} context={group.context} />
</EntityView>
