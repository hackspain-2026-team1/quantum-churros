<script lang="ts">
	import * as Avatar from '$lib/components/ui/avatar/index.js';

	let {
		name,
		id,
		class: className = 'size-9'
	}: {
		name: string;
		id?: string;
		class?: string;
	} = $props();

	const acronym = $derived(
		name
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((word) => word[0]?.toUpperCase() ?? '')
			.join('') ||
			(id?.slice(-2).toUpperCase() ?? '·')
	);

	const tones = [
		'var(--signal)',
		'var(--success)',
		'var(--warning)',
		'var(--danger)',
		'var(--ink)'
	];
	const seed = $derived(
		`${name}${id ?? ''}`.split('').reduce((total, letter) => total + letter.charCodeAt(0), 0)
	);
	const tone = $derived(tones[seed % tones.length]);
</script>

<Avatar.Root class={className}>
	<Avatar.Fallback
		class="text-xs font-semibold tracking-[0.04em] text-white"
		style={`background: color-mix(in oklch, ${tone} 88%, black);`}
	>
		{acronym}
	</Avatar.Fallback>
</Avatar.Root>
