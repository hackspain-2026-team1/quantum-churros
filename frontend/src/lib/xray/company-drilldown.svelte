<script lang="ts">
	import { ChevronRight, Landmark } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import * as Table from '$lib/components/ui/table/index.js';
	import { formatNumber, formatPeriod, formatPeriodShort, humanizeMonths } from '$lib/format.js';
	import type { GroupFile } from './contract.js';
	import BandBadge from './band-badge.svelte';
	import CompanyAvatar from './company-avatar.svelte';
	import EmptyState from './empty-state.svelte';
	import { monthStore } from './month-store.svelte.js';
	import ScoreCell from './score-cell.svelte';
	import ScoreSparkline from './score-sparkline.svelte';
	import { TONE_BADGE } from './tones.js';

	let { group, month }: { group: GroupFile; month: string } = $props();

	const plural = (count: number, one: string, many: string) =>
		`${formatNumber(count)} ${count === 1 ? one : many}`;
	// companies[].shown and band align with group.months.
	const labels = $derived(group.months.map((entry) => entry.month));
	const index = $derived(labels.indexOf(month));
	const rows = $derived(
		group.companies
			.map((company) => ({
				...company,
				score: index < 0 ? null : company.shown[index],
				bandNow: index < 0 ? null : company.band[index]
			}))
			// Lowest score first, like the portfolio; companies not observed that month go last.
			.toSorted((a, b) => (a.score ?? Infinity) - (b.score ?? Infinity) || a.id.localeCompare(b.id))
	);
	const observed = $derived(rows.filter((row) => row.score !== null).length);
	const inheriting = $derived(rows.filter((row) => row.inherits_liquidity).length);
	const summary = $derived(
		[
			plural(group.companies.length, 'empresa', 'empresas'),
			`${formatNumber(observed)} con datos en ${formatPeriod(month)}`,
			...(inheriting > 0
				? [`${plural(inheriting, 'hereda', 'heredan')} la liquidez del grupo`]
				: [])
		].join(' · ')
	);
	const href = (companyId: string) => monthStore.href(`/group/${group.id}/company/${companyId}`);
</script>

<Card.Root data-testid="company-drilldown">
	<Card.Header>
		<Card.Description>{summary}</Card.Description>
		<Card.Title>Empresas del grupo y su papel en la tesorería</Card.Title>
	</Card.Header>
	<Card.Content class={['@container', rows.length > 0 && 'px-0']}>
		{#if rows.length === 0}
			<EmptyState
				compact
				title="El bundle no lista empresas para este grupo"
				description="El desglose aparece cuando la exportación incluye los miembros del grupo."
			/>
		{:else}
			<ul class="divide-y @4xl:hidden">
				{#each rows as company (company.id)}
					<li data-company-card={company.id}>
						<a href={href(company.id)} class="grid gap-2 px-6 py-4 hover:bg-muted/40">
							<div class="flex items-center justify-between gap-3">
								<span class="flex min-w-0 items-center gap-3">
									<CompanyAvatar name={company.role ?? company.id} id={company.id} class="size-8" />
									<span class="min-w-0">
										<span class="font-data block font-medium">{company.id}</span>
										<span class="block truncate text-xs text-muted-foreground">
											{company.role ?? 'Sin papel inferido'}
										</span>
									</span>
								</span>
								<span class="flex shrink-0 items-center gap-4">
									<ScoreSparkline
										class="hidden @md:block"
										values={company.shown}
										months={labels}
										selectedIndex={index}
										band={company.bandNow}
									/>
									<ScoreCell tenths={company.score} band={company.bandNow} />
								</span>
							</div>
							<div class="flex flex-wrap items-center gap-2">
								<BandBadge band={company.bandNow} />
								{#if company.treasury_class && company.treasury_class !== company.role}
									<Badge variant="outline">Tesorería: {company.treasury_class.toLowerCase()}</Badge>
								{/if}
								{#if company.inherits_liquidity}
									<Badge variant="outline" class={TONE_BADGE.signal}>
										<Landmark aria-hidden="true" /> Hereda la liquidez del grupo
									</Badge>
								{/if}
							</div>
							{#if company.truth}
								<p class="text-sm leading-6 text-muted-foreground">
									{humanizeMonths(company.truth)}
								</p>
							{/if}
						</a>
					</li>
				{/each}
			</ul>
			<div class="hidden @4xl:block">
				<Table.Root>
					<Table.Header>
						<Table.Row>
							<Table.Head class="pl-6">Empresa</Table.Head>
							<Table.Head>Papel y tesorería</Table.Head>
							<Table.Head class="text-right">Score</Table.Head>
							<Table.Head>Banda</Table.Head>
							<Table.Head>
								Trayectoria · {formatPeriodShort(labels[0])} – {formatPeriodShort(
									labels[labels.length - 1]
								)}
							</Table.Head>
							<Table.Head class="w-[38%]">Lectura de tesorería dentro del grupo</Table.Head>
							<Table.Head class="pr-6"><span class="sr-only">Abrir</span></Table.Head>
						</Table.Row>
					</Table.Header>
					<Table.Body>
						{#each rows as company (company.id)}
							<Table.Row class="group align-top" data-company={company.id}>
								<Table.Cell class="pl-6">
									<a href={href(company.id)} class="flex items-center gap-3 rounded-md">
										<CompanyAvatar
											name={company.role ?? company.id}
											id={company.id}
											class="size-8"
										/>
										<span class="font-data font-medium group-hover:underline">{company.id}</span>
									</a>
								</Table.Cell>
								<Table.Cell>
									<span class="block">{company.role ?? 'Sin papel inferido'}</span>
									{#if company.treasury_class && company.treasury_class !== company.role}
										<span class="block text-xs text-muted-foreground"
											>Tesorería: {company.treasury_class.toLowerCase()}</span
										>
									{/if}
								</Table.Cell>
								<Table.Cell class="text-right"><ScoreCell tenths={company.score} /></Table.Cell>
								<Table.Cell><BandBadge band={company.bandNow} /></Table.Cell>
								<Table.Cell>
									<ScoreSparkline
										values={company.shown}
										months={labels}
										selectedIndex={index}
										band={company.bandNow}
									/>
								</Table.Cell>
								<Table.Cell class="space-y-1.5 text-sm leading-6 whitespace-normal">
									{#if company.inherits_liquidity}
										<Badge variant="outline" class={TONE_BADGE.signal} data-inherits-liquidity>
											<Landmark aria-hidden="true" /> Hereda la liquidez del grupo
										</Badge>
									{/if}
									<p class="text-muted-foreground">
										{company.truth
											? humanizeMonths(company.truth)
											: 'Sin lectura de tesorería para esta empresa.'}
									</p>
								</Table.Cell>
								<Table.Cell class="pr-6 text-right">
									<a
										href={href(company.id)}
										class="inline-grid size-8 place-items-center rounded-md hover:bg-muted"
										aria-label={`Abrir ${company.id}`}><ChevronRight class="size-4" /></a
									>
								</Table.Cell>
							</Table.Row>
						{/each}
					</Table.Body>
				</Table.Root>
			</div>
		{/if}
	</Card.Content>
</Card.Root>
