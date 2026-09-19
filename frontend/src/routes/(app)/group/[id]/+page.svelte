<script lang="ts">
	import { ArrowLeft, CalendarOff } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import { formatNumber, formatPeriod } from '$lib/format.js';
	import CompanyAvatar from '$lib/xray/company-avatar.svelte';
	import CompanyDrilldown from '$lib/xray/company-drilldown.svelte';
	import ContributionWaterfall from '$lib/xray/contribution-waterfall.svelte';
	import EmptyState from '$lib/xray/empty-state.svelte';
	import EntityTrajectory from '$lib/xray/entity-trajectory.svelte';
	import EvidenceTable from '$lib/xray/evidence-table.svelte';
	import MonthSlider from '$lib/xray/month-slider.svelte';
	import { monthStore } from '$lib/xray/month-store.svelte.js';
	import { entryAt } from '$lib/xray/month.js';
	import ProfileCard from '$lib/xray/profile-card.svelte';
	import ScoreChanges from '$lib/xray/score-changes.svelte';
	import SectionNav from '$lib/xray/section-nav.svelte';
	import VerdictCard from '$lib/xray/verdict-card.svelte';

	let { data } = $props();

	const group = $derived(data.group);
	const entry = $derived(entryAt(group.months, monthStore.month));
	const industry = $derived(group.context.industry);
	const lastMonth = $derived(group.months[group.months.length - 1].month);
	// 'Quién es' in one line: the structural attributes of the profile that have a value.
	const IDENTITY_KEYS = ['size_band', 'treasury_structure', 'erp_tier', 'financing_profile'];
	const identity = $derived(
		IDENTITY_KEYS.flatMap((key) => {
			const attribute = group.profile.find((item) => item.key === key);
			return attribute && typeof attribute.value === 'string' && attribute.value
				? [{ key, label: attribute.label, value: attribute.value }]
				: [];
		})
	);
	const sections = [
		{ id: 'veredicto', label: 'Veredicto' },
		{ id: 'desglose', label: 'De dónde sale' },
		{ id: 'evidencias', label: 'Evidencias' },
		{ id: 'empresas', label: 'Empresas' },
		{ id: 'ficha', label: 'Quién es' }
	];
</script>

<svelte:head><title>{group.id} · Embat X-Ray</title></svelte:head>

<section class="space-y-5" aria-labelledby="group-heading">
	<Button href={monthStore.href('/')} variant="ghost" size="sm" class="-ml-2">
		<ArrowLeft /> Cartera
	</Button>
	<div class="grid gap-4 lg:grid-cols-[1fr_24rem] lg:items-end">
		<div class="flex items-start gap-3">
			<CompanyAvatar name={industry?.label ?? group.id} id={group.id} class="mt-1 size-11" />
			<div class="min-w-0">
				<p class="eyebrow">
					Grupo · {formatNumber(group.companies.length)}
					{group.companies.length === 1 ? 'empresa' : 'empresas'} · con datos desde {formatPeriod(
						group.first_month
					)}
				</p>
				<h1 id="group-heading" class="font-data">{group.id}</h1>
				{#if identity.length > 0 || industry}
					<ul class="mt-3 flex flex-wrap gap-1.5" aria-label="Quién es, en una línea">
						{#each identity as item (item.key)}
							<li>
								<Badge variant="secondary" class="max-w-full font-normal" title={item.label}
									><span class="truncate">{item.value}</span></Badge
								>
							</li>
						{/each}
						{#if industry}
							<li>
								<Badge
									variant="outline"
									class="font-normal text-muted-foreground"
									title={industry.reason}>Contexto · {industry.label}</Badge
								>
							</li>
						{/if}
					</ul>
				{/if}
			</div>
		</div>
		<MonthSlider />
	</div>

	{#if entry}
		<SectionNav {sections} />
		<div id="veredicto" class="grid scroll-mt-28 gap-4 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
			<VerdictCard {entry} months={group.months} profile={group.profile} />
			<div class="grid content-start gap-4">
				<EntityTrajectory
					months={group.months}
					series={group.series}
					alerts={group.alerts}
					month={entry.month}
				/>
				<ScoreChanges months={group.months} month={entry.month} />
			</div>
		</div>
		<div id="desglose" class="grid scroll-mt-28 gap-4 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]">
			<ContributionWaterfall {entry} />
			<div id="evidencias" class="scroll-mt-28">
				<EvidenceTable entityId={group.id} month={entry.month} />
			</div>
		</div>
		<div id="empresas" class="scroll-mt-28">
			<CompanyDrilldown {group} month={entry.month} />
		</div>
		<div id="ficha" class="scroll-mt-28">
			<ProfileCard profile={group.profile} context={group.context} />
		</div>
	{:else}
		<EmptyState
			icon={CalendarOff}
			title={`Sin datos de este grupo en ${formatPeriod(monthStore.month)}`}
			description={`El primer cierre observado de ${group.id} es ${formatPeriod(group.first_month)} y el último, ${formatPeriod(lastMonth)}.`}
		>
			<Button variant="outline" onclick={() => monthStore.select(group.first_month)}>
				Ir a {formatPeriod(group.first_month)}
			</Button>
			<Button variant="outline" onclick={() => monthStore.select(lastMonth)}>
				Ir al último cierre del grupo
			</Button>
		</EmptyState>
	{/if}
</section>
