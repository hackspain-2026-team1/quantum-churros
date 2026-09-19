<script lang="ts">
	import { BookOpen } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatNumber, formatPercent, formatUnitValue } from '$lib/format.js';
	import type { EntityContext, ProfileAttribute } from './contract.js';
	import EmptyState from './empty-state.svelte';

	let {
		profile,
		context,
		kind = 'group'
	}: {
		profile: ProfileAttribute[];
		context: EntityContext;
		/** Whose profile this is; only changes the wording. */
		kind?: 'group' | 'company';
	} = $props();

	const COVERAGE_STEPS = 5;
	const coverageSteps = Array.from({ length: COVERAGE_STEPS }, (_, step) => step);
	const inferred = $derived(profile.filter((attribute) => attribute.value !== null).length);
	const hasContext = $derived(context.industry !== null || context.benchmark !== null);
	const filled = (coverage: number) => Math.round(coverage * COVERAGE_STEPS);
</script>

<Card.Root data-testid="profile-card">
	<Card.Header>
		<Card.Description>
			{kind === 'group' ? 'Quién es este grupo' : 'Quién es esta empresa'} · {formatNumber(
				inferred
			)} de {formatNumber(profile.length)} atributos inferidos
		</Card.Description>
		<Card.Title>Ficha inferida de sus propios datos</Card.Title>
	</Card.Header>
	<Card.Content class="@container space-y-5">
		{#if profile.length === 0}
			<EmptyState
				compact
				title="El bundle no trae ficha para esta entidad"
				description="La ficha se exporta con el perfil del motor; vuelve a generar el bundle para verla."
			/>
		{:else}
			<dl class="grid gap-x-8 gap-y-5 @lg:grid-cols-2 @4xl:grid-cols-3 @6xl:grid-cols-4">
				{#each profile as attribute (attribute.key)}
					<div data-profile={attribute.key}>
						<dt class="metric-label flex items-center justify-between gap-2">
							<span>{attribute.label}</span>
							<span
								class="flex shrink-0 items-center gap-1.5 tracking-normal normal-case"
								title="Cobertura: parte de los datos necesarios que estaba disponible para inferir este atributo"
							>
								<span class="flex gap-0.5" aria-hidden="true">
									{#each coverageSteps as step (step)}
										<span
											class={[
												'h-1.5 w-1.5 rounded-full',
												step < filled(attribute.coverage)
													? 'bg-[var(--signal)]'
													: 'bg-muted-foreground/25'
											]}
										></span>
									{/each}
								</span>
								<span class="font-data text-[0.68rem] font-medium"
									><span class="sr-only">Cobertura </span>{formatPercent(
										attribute.coverage,
										0
									)}</span
								>
							</span>
						</dt>
						<dd>
							<span class={['font-semibold', attribute.value === null && 'text-muted-foreground']}
								>{attribute.value === null
									? 'No inferible todavía'
									: formatUnitValue(attribute.value)}</span
							>
							{#if attribute.evidence}
								<span class="mt-0.5 block text-xs leading-5 text-muted-foreground"
									>{attribute.evidence}</span
								>
							{/if}
						</dd>
					</div>
				{/each}
			</dl>
		{/if}
		{#if hasContext}
			<section
				class="space-y-2 rounded-lg border border-dashed bg-muted/30 px-4 py-3"
				aria-label="Contexto"
				data-testid="profile-context"
			>
				<h2 class="flex flex-wrap items-center gap-2 text-sm font-semibold">
					<BookOpen class="size-4 text-muted-foreground" aria-hidden="true" />
					Contexto
					<Badge variant="outline" class="font-normal text-muted-foreground"
						>No entra en el score</Badge
					>
				</h2>
				{#if context.industry}
					<p class="text-sm leading-6">
						<span class="font-medium">Sector estimado: {context.industry.label}</span>
						<span class="font-data text-xs text-muted-foreground">
							· confianza de la clasificación {formatPercent(context.industry.confidence, 0)}</span
						>
						{#if context.industry.reason}
							<span class="block text-xs leading-5 text-muted-foreground"
								>{context.industry.reason}</span
							>
						{/if}
					</p>
				{/if}
				{#if context.benchmark}
					<p class="text-sm leading-6">
						{context.benchmark.text}
						<span class="block text-xs text-muted-foreground"
							>Fuente: {context.benchmark.source}</span
						>
					</p>
				{/if}
			</section>
		{/if}
	</Card.Content>
</Card.Root>
