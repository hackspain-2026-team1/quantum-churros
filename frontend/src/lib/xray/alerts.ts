// Pure helpers of the alerts inbox: filters, counts per state, month grouping
// and the monthly timeline. Every count is a count over alerts.json.

import {
	ALERT_STATES,
	type Alert,
	type AlertKind,
	type AlertState,
	type Receipt
} from './contract.js';
import { normalizeText } from './portfolio.js';

export type AlertScope = 'history' | 'month';
export type AlertEntityFilter = 'all' | Alert['entity_kind'];
export type AlertKindFilter = 'all' | AlertKind;

export type AlertFilters = {
	scope: AlertScope;
	/** Month under analysis; only applied when scope is 'month'. */
	month: string;
	query: string;
	kind: AlertKindFilter;
	entity: AlertEntityFilter;
};

export type Abstention = Receipt['abstentions'][number];

export type MonthlyAlertCount = { month: string; total: number } & Record<AlertState, number>;

/** Everything but the period: the timeline counts these per month. */
export function filterAlerts(alerts: Alert[], filters: Omit<AlertFilters, 'scope' | 'month'>) {
	const needle = normalizeText(filters.query);
	return alerts.filter((alert) => {
		if (filters.kind !== 'all' && alert.kind !== filters.kind) return false;
		if (filters.entity !== 'all' && alert.entity_kind !== filters.entity) return false;
		if (!needle) return true;
		return [alert.entity_id, alert.group_id].some((id) => normalizeText(id).includes(needle));
	});
}

export function inScope(alerts: Alert[], scope: AlertScope, month: string): Alert[] {
	return scope === 'month' ? alerts.filter((alert) => alert.month === month) : alerts;
}

export function countByState(alerts: Alert[]): Record<AlertState, number> {
	const counts = Object.fromEntries(ALERT_STATES.map((state) => [state, 0])) as Record<
		AlertState,
		number
	>;
	for (const alert of alerts) counts[alert.state] += 1;
	return counts;
}

/** Newest month first; inside a month the group goes before its companies. */
export function sortAlerts(alerts: Alert[]): Alert[] {
	return alerts.toSorted(
		(a, b) =>
			b.month.localeCompare(a.month) ||
			a.group_id.localeCompare(b.group_id) ||
			Number(a.entity_kind === 'company') - Number(b.entity_kind === 'company') ||
			a.id.localeCompare(b.id)
	);
}

/** Consecutive runs of the same month, keeping the order of `alerts`. */
export function groupByMonth(alerts: Alert[]): { month: string; alerts: Alert[] }[] {
	const groups: { month: string; alerts: Alert[] }[] = [];
	for (const alert of alerts) {
		const last = groups.at(-1);
		if (last && last.month === alert.month) last.alerts.push(alert);
		else groups.push({ month: alert.month, alerts: [alert] });
	}
	return groups;
}

/** One entry per month of the bundle window, in order, including months without alerts. */
export function monthlyCounts(alerts: Alert[], months: readonly string[]): MonthlyAlertCount[] {
	const byMonth = new Map<string, MonthlyAlertCount>(
		months.map((month) => [month, { month, total: 0, fired: 0, suppressed: 0, abstained: 0 }])
	);
	for (const alert of alerts) {
		const entry = byMonth.get(alert.month);
		if (!entry) continue;
		entry[alert.state] += 1;
		entry.total += 1;
	}
	return [...byMonth.values()];
}

/** Route of the entity an alert is about. */
export function alertEntityPath(alert: Alert): string {
	return alert.entity_kind === 'group'
		? `/group/${alert.group_id}`
		: `/group/${alert.group_id}/company/${alert.entity_id}`;
}

/**
 * receipt.abstentions lists the entities the engine abstains on in the last month of the
 * window: the entry of the entity of this alert, or null when it is no longer abstained.
 */
export function standingAbstention(alert: Alert, abstentions: Abstention[]): Abstention | null {
	return (
		abstentions.find(
			(entry) => entry.entity_kind === alert.entity_kind && entry.entity_id === alert.entity_id
		) ?? null
	);
}

// Shared with the group and company screens, which quote the same engine sentences.
export { humanizeMonths } from '$lib/format.js';
