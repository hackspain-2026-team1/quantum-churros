<script lang="ts">
	import { CircleCheck, CircleDashed, CircleX, Info } from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatPeriodShort, formatUnitValue } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import { CHECK_STATUS_TEXT, type ReceiptCheck } from './contract.js';
	import InlineBars from './inline-bars.svelte';
	import { CHECK_STATUS_TONE, TONE_BADGE, TONE_TEXT } from './tones.js';

	let { check }: { check: ReceiptCheck } = $props();

	const icons = { pass: CircleCheck, fail: CircleX, info: Info, not_run: CircleDashed } as const;
	const Icon = $derived(icons[check.status]);
	const tone = $derived(CHECK_STATUS_TONE[check.status]);
	const headingId = $derived(`check-${check.key}`);

	// The engine writes lists of closes as 'YYYY-MM, YYYY-MM'; show them as dates, not codes.
	const MONTH_LIST = /^\d{4}-(0[1-9]|1[0-2])(\s*,\s*\d{4}-(0[1-9]|1[0-2]))*$/;
	const display = (metric: ReceiptCheck['metrics'][number]) =>
		typeof metric.value === 'string' && MONTH_LIST.test(metric.value)
			? metric.value
					.split(',')
					.map((part) => formatPeriodShort(part.trim()))
					.join(' · ')
			: formatUnitValue(metric.value, metric.unit);
</script>

<Card.Root
	class={cn(
		'h-full',
		check.status === 'fail' && 'border-[var(--danger)]/40',
		check.status === 'not_run' && 'border-dashed bg-card/60 shadow-none'
	)}
	role="group"
	aria-labelledby={headingId}
	data-check={check.key}
	data-status={check.status}
>
	<Card.Header>
		<div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
			<h3 id={headingId} class="flex items-start gap-2 leading-5 font-semibold">
				<Icon class={cn('mt-0.5 size-4 shrink-0', TONE_TEXT[tone])} aria-hidden="true" />
				{check.title}
			</h3>
			<Badge variant="outline" class={TONE_BADGE[tone]}>{CHECK_STATUS_TEXT[check.status]}</Badge>
		</div>
		<Card.Description class="leading-6">{check.summary}</Card.Description>
	</Card.Header>
	{#if check.metrics.length > 0 || check.bars?.length}
		<Card.Content class="space-y-4">
			{#if check.metrics.length > 0}
				<dl class="divide-y divide-dashed border-y border-dashed text-sm">
					{#each check.metrics as metric, index (index)}
						<div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2">
							<dt class="text-muted-foreground">{metric.label}</dt>
							<dd class="font-data ml-auto text-right font-semibold tabular-nums">
								{display(metric)}
							</dd>
						</div>
					{/each}
				</dl>
			{/if}
			{#if check.bars?.length}
				<div>
					<span class="metric-label">Distribución</span>
					<InlineBars bars={check.bars} label={`Distribución de ${check.title}`} />
				</div>
			{/if}
		</Card.Content>
	{/if}
</Card.Root>
