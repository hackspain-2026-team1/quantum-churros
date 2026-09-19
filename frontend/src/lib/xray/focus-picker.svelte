<script lang="ts">
	import * as Select from '$lib/components/ui/select/index.js';
	import { formatScore } from '$lib/format.js';
	import type { PortfolioRow } from './portfolio.js';

	let {
		rows,
		value,
		onChange
	}: {
		/** Groups of the month, already in priority order. */
		rows: PortfolioRow[];
		value: string | null;
		onChange: (id: string) => void;
	} = $props();

	const uid = $props.id();
</script>

<div class="flex min-w-0 items-center gap-2" data-testid="focus-picker">
	<span class="metric-label mb-0" id={`${uid}-label`}>Grupo</span>
	<Select.Root type="single" bind:value={() => value ?? '', (next) => next && onChange(next)}>
		<Select.Trigger class="min-w-44" aria-labelledby={`${uid}-label`}>
			<span class="font-data truncate">{value ?? 'Elegir grupo'}</span>
		</Select.Trigger>
		<Select.Content class="max-h-80">
			{#each rows as row (row.id)}
				<Select.Item value={row.id} label={row.id}>
					<span class="font-data">{row.id}</span>
					<span class="font-data ml-auto pl-4 text-muted-foreground"
						>{row.shown === null ? '—' : formatScore(row.shown)}</span
					>
				</Select.Item>
			{/each}
		</Select.Content>
	</Select.Root>
</div>
