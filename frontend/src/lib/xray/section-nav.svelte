<script lang="ts">
	import { cn } from '$lib/utils.js';

	let {
		sections,
		label = 'Secciones de esta página',
		class: className
	}: {
		/** Anchors of the page, in reading order; `id` is the id of the target element. */
		sections: { id: string; label: string }[];
		label?: string;
		class?: string;
	} = $props();
</script>

<nav aria-label={label} class={cn('-mx-1 overflow-x-auto px-1 py-1', className)}>
	<ul class="flex w-max items-center gap-1 text-sm">
		{#each sections as section, index (section.id)}
			<li class="flex items-center gap-1">
				{#if index > 0}<span class="text-muted-foreground/50" aria-hidden="true">·</span>{/if}
				<a
					href={`#${section.id}`}
					class="rounded-md px-2 py-1 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
					>{section.label}</a
				>
			</li>
		{/each}
	</ul>
</nav>
