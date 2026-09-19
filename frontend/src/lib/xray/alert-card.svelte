<script lang="ts">
	import {
		BellOff,
		BellRing,
		Check,
		ChevronRight,
		Eye,
		EyeOff,
		KeyRound,
		PauseCircle,
		RotateCcw,
		X
	} from '@lucide/svelte';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { formatPeriod, formatPeriodShort, humanizeMonths } from '$lib/format.js';
	import { cn } from '$lib/utils.js';
	import type { Triage } from './alert-state.svelte.js';
	import { alertEntityPath, type Abstention } from './alerts.js';
	import { ALERT_KIND_TEXT, type Alert, type AlertState, type Manifest } from './contract.js';
	import { glossaryText } from './labels.js';
	import { monthStore } from './month-store.svelte.js';
	import ScoreCell from './score-cell.svelte';
	import { ALERT_STATE_TONE, TONE_BADGE } from './tones.js';

	let {
		alert,
		manifest,
		standing = null,
		standingKnown = false,
		triage = null,
		onTriage
	}: {
		alert: Alert;
		manifest: Manifest;
		/** Entry of receipt.abstentions for this entity: still abstained on the last close. */
		standing?: Abstention | null;
		/** false when the receipt could not be read, so nothing is said about the last close. */
		standingKnown?: boolean;
		/** Local mark of the analyst; only fired alerts are triaged. */
		triage?: Triage | null;
		onTriage?: (value: Triage | null) => void;
	} = $props();

	// Inbox wording of the three states; the tabs use the same words.
	const STATE_LABEL: Record<AlertState, string> = {
		fired: 'Activa',
		suppressed: 'Silenciada',
		abstained: 'Abstención'
	};
	const STATE_ICON = { fired: BellRing, suppressed: BellOff, abstained: PauseCircle } as const;
	const StateIcon = $derived(STATE_ICON[alert.state]);

	const scoreCaption = $derived(
		alert.entity_kind === 'company'
			? `${alert.group_id} · ${formatPeriodShort(alert.month)}`
			: `Score en ${formatPeriodShort(alert.month)}`
	);
	const href = $derived(monthStore.href(alertEntityPath(alert), alert.month));
	const muted = $derived(alert.suppressed_by);
	const lastClose = $derived(manifest.months[manifest.months.length - 1]);

	const windowText = $derived.by(() => {
		if (!muted) return '';
		const since = formatPeriodShort(muted.since);
		if (!muted.until) return `desde ${since}`;
		return muted.until === muted.since ? since : `${since} – ${formatPeriodShort(muted.until)}`;
	});

	// What the reason means for the reader. The reason itself is the text of the glossary.
	const explanation = $derived.by(() => {
		if (!muted) return '';
		if (muted.reason === 'perimeter_change') {
			const until = muted.until ? ` hasta ${formatPeriod(muted.until)}` : '';
			return `En ${formatPeriod(muted.since)} se conectó una empresa o una cuenta nueva: el salto del score refleja el perímetro nuevo, no un deterioro del negocio. Las alertas quedan en pausa${until}.`;
		}
		if (muted.reason === 'abstention') {
			return 'Con estos datos el motor no sostiene un veredicto: enseña el número, pero no dispara la alerta.';
		}
		return '';
	});
</script>

<Card.Root
	class={cn('gap-0 py-0 transition-opacity', triage === 'dismissed' && 'opacity-60')}
	data-alert={alert.id}
	data-state={alert.state}
	data-triage={triage ?? 'new'}
>
	<Card.Content class="grid gap-4 px-5 py-4 lg:grid-cols-[1fr_18rem] lg:items-start">
		<div class="min-w-0 space-y-2">
			<div class="flex flex-wrap items-center gap-2">
				<Badge variant="outline" class={TONE_BADGE[ALERT_STATE_TONE[alert.state]]}>
					<StateIcon aria-hidden="true" />
					{STATE_LABEL[alert.state]}
				</Badge>
				{#if ALERT_KIND_TEXT[alert.kind] !== alert.title}
					<Badge variant="outline">{ALERT_KIND_TEXT[alert.kind]}</Badge>
				{/if}
				<span class="font-data text-xs text-muted-foreground lg:hidden">{alert.entity_id}</span>
				{#if triage === 'seen'}
					<Badge variant="secondary"><Check aria-hidden="true" /> Vista</Badge>
				{:else if triage === 'dismissed'}
					<Badge variant="secondary"><EyeOff aria-hidden="true" /> Descartada</Badge>
				{/if}
			</div>
			<h3 class="leading-6 font-semibold">{alert.title}</h3>
			<p class="text-sm leading-6 text-muted-foreground">{humanizeMonths(alert.detail)}</p>

			{#if (alert.actions?.length ?? 0) > 0 || (alert.financing?.length ?? 0) > 0}
				<div class="flex flex-wrap items-center gap-2 pt-1" data-testid="alert-levers">
					<span class="text-xs font-medium text-muted-foreground">Qué hacer:</span>
					{#each alert.actions ?? [] as action (action.id)}
						<a
							class="inline-flex max-w-72 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs hover:bg-muted"
							href={href}
							title={`${action.pillar} · ${action.title}`}
						>
							<span class="truncate">{action.title}</span>
							<ChevronRight class="size-3.5 shrink-0" />
						</a>
					{/each}
					{#each alert.financing ?? [] as item (item.id)}
						<a
							class="inline-flex max-w-72 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs hover:bg-muted"
							href={href}
							title={`${item.kind} · ${item.title}`}
						>
							<span class="truncate">{item.title}</span>
							<ChevronRight class="size-3.5 shrink-0" />
						</a>
					{/each}
				</div>
			{/if}

			{#if muted}
				<div
					class={cn(
						'space-y-1 rounded-lg border-l-2 px-3 py-2 text-sm leading-6',
						alert.state === 'abstained'
							? 'border-[var(--warning)] bg-[var(--warning-soft)]'
							: 'border-[var(--signal)] bg-muted'
					)}
					data-muted-reason={muted.reason}
				>
					<p>
						<span class="font-semibold"
							>{alert.state === 'abstained' ? 'No se dispara' : 'Silenciada'}:</span
						>
						{glossaryText(manifest, 'reasons', muted.reason)}
					</p>
					{#if explanation}<p class="text-foreground/75">{explanation}</p>{/if}
					<p class="text-xs text-muted-foreground">
						<span class="font-semibold">Ventana:</span>
						{windowText}
					</p>
					{#if alert.state === 'abstained' && standing}
						<p class="flex items-start gap-2">
							<KeyRound
								class="mt-1 size-4 shrink-0 text-[var(--warning-strong)]"
								aria-hidden="true"
							/>
							<span>
								<span class="font-semibold"
									>Sigue en abstención en {formatPeriod(standing.month)}. Qué la desbloquea:</span
								>
								{humanizeMonths(standing.unlock)}
							</span>
						</p>
					{:else if alert.state === 'abstained' && standingKnown}
						<p class="text-xs text-muted-foreground">
							En {formatPeriod(lastClose)}, el último cierre, la entidad ya no está en abstención.
						</p>
					{/if}
				</div>
			{/if}

			{#if alert.state === 'fired' && onTriage}
				<div class="-ml-2 flex flex-wrap gap-1" role="group" aria-label={`Triaje de ${alert.id}`}>
					{#if triage === 'dismissed'}
						<Button variant="ghost" size="sm" onclick={() => onTriage(null)}>
							<RotateCcw /> Restaurar
						</Button>
					{:else}
						<Button
							variant="ghost"
							size="sm"
							aria-pressed={triage === 'seen'}
							onclick={() => onTriage(triage === 'seen' ? null : 'seen')}
						>
							{#if triage === 'seen'}<EyeOff /> Marcar como no vista{:else}<Eye /> Marcar como vista{/if}
						</Button>
						<Button variant="ghost" size="sm" onclick={() => onTriage('dismissed')}>
							<X /> Descartar
						</Button>
					{/if}
				</div>
			{/if}
		</div>

		<a
			{href}
			class="flex items-center justify-between gap-4 rounded-lg border px-4 py-3 transition-colors hover:bg-muted"
		>
			<span class="min-w-0">
				<span class="metric-label">{alert.entity_kind === 'group' ? 'Grupo' : 'Empresa'}</span>
				<span class="font-data block font-medium break-all">{alert.entity_id}</span>
				<span class="block text-xs leading-5 text-muted-foreground">{scoreCaption}</span>
			</span>
			<span class="flex shrink-0 items-center gap-2">
				<ScoreCell tenths={alert.shown} muted={alert.state !== 'fired'} />
				<ChevronRight class="size-4 text-muted-foreground" aria-hidden="true" />
			</span>
		</a>
	</Card.Content>
</Card.Root>
