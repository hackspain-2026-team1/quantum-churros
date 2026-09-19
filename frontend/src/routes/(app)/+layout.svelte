<script lang="ts">
	import { untrack } from 'svelte';
	import { afterNavigate } from '$app/navigation';
	import * as Tooltip from '$lib/components/ui/tooltip/index.js';
	import { monthStore } from '$lib/xray/month-store.svelte.js';

	let { data, children } = $props();

	// Runs before the first render, so every screen sees the bundle months and ?m=.
	// Only the bundle months re-run it: init() and readUrl() read the selection, and
	// tracking that read would re-adopt the old ?m= on every select() and undo it.
	$effect.pre(() => {
		const months = data.manifest.months;
		untrack(() => {
			monthStore.init(months);
			monthStore.readUrl();
		});
	});

	// Links and back/forward may carry another ?m=; links without it keep the selection.
	afterNavigate(() => {
		monthStore.readUrl();
		monthStore.syncUrl();
	});
</script>

<Tooltip.Provider delayDuration={150}>
	{@render children()}
</Tooltip.Provider>
