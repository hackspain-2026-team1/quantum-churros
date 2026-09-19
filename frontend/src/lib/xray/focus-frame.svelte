<script lang="ts" module>
	import type { GroupFile } from './contract.js';

	export type FocusState =
		| { state: 'idle' }
		| { state: 'loading'; id: string }
		| { state: 'ready'; group: GroupFile }
		| { state: 'error'; id: string; message: string };
</script>

<script lang="ts">
	import { CalendarOff, FileWarning, MousePointerClick } from '@lucide/svelte';
	import type { Snippet } from 'svelte';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';
	import { formatPeriod } from '$lib/format.js';
	import type { EntityMonth } from './contract.js';
	import EmptyState from './empty-state.svelte';
	import { monthStore } from './month-store.svelte.js';
	import { entryAt } from './month.js';

	// Shared loading / error / no-data states of the tabs that look at one group.
	let { focus, children }: { focus: FocusState; children: Snippet<[GroupFile, EntityMonth]> } =
		$props();
</script>

{#if focus.state === 'ready'}
	{@const entry = entryAt(focus.group.months, monthStore.month)}
	{#if entry}
		{@render children(focus.group, entry)}
	{:else}
		<EmptyState
			icon={CalendarOff}
			title={`Sin datos de ${focus.group.id} en ${formatPeriod(monthStore.month)}`}
			description={`Su primer cierre observado es ${formatPeriod(focus.group.first_month)}. Elige otro mes u otro grupo.`}
		/>
	{/if}
{:else if focus.state === 'loading'}
	<div class="grid gap-4 lg:grid-cols-[17rem_1fr]" aria-label="Cargando grupo">
		<Skeleton class="h-72" /><Skeleton class="h-72" />
	</div>
{:else if focus.state === 'error'}
	<EmptyState
		icon={FileWarning}
		tone="danger"
		title={`No se pudo leer ${focus.id}`}
		description={focus.message}
	/>
{:else}
	<EmptyState
		icon={MousePointerClick}
		title="Elige un grupo"
		description="Ningún grupo tiene score en este mes."
	/>
{/if}
