import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
	alertEntityPath,
	countByState,
	filterAlerts,
	groupByMonth,
	humanizeMonths,
	inScope,
	monthlyCounts,
	sortAlerts,
	standingAbstention
} from './alerts';
import { ALERT_STATES, BUNDLE_FILES, parseBundleFile, type Alert } from './contract';

// Synthetic, test-only bundle; the app never serves it.
const root = fileURLToPath(new URL('../../../e2e/fixtures/bundle/v1/', import.meta.url));
const read = (path: string): unknown => JSON.parse(readFileSync(`${root}${path}`, 'utf-8'));
const manifest = parseBundleFile('manifest', read(BUNDLE_FILES.manifest));
const alerts = parseBundleFile('alerts', read(BUNDLE_FILES.alerts)).alerts;
const receipt = parseBundleFile('receipt', read(BUNDLE_FILES.receipt));

const NO_FILTERS = { query: '', kind: 'all', entity: 'all' } as const;

const alert = (partial: Partial<Alert> & Pick<Alert, 'entity_id' | 'month'>): Alert => ({
	id: `${partial.entity_id}:${partial.month}:level_critical`,
	entity_kind: 'group',
	group_id: partial.entity_id,
	kind: 'level_critical',
	state: 'fired',
	title: 'Nivel crítico',
	detail: 'Detalle',
	shown: 300,
	suppressed_by: null,
	...partial
});

describe('alert filters and counts', () => {
	it('counts every alert of the bundle in exactly one state', () => {
		const counts = countByState(alerts);
		expect(ALERT_STATES.reduce((total, state) => total + counts[state], 0)).toBe(alerts.length);
		for (const state of ALERT_STATES) {
			expect(counts[state]).toBe(alerts.filter((entry) => entry.state === state).length);
		}
	});

	it('filters by entity, kind and a search over entity and group ids', () => {
		const companies = filterAlerts(alerts, { ...NO_FILTERS, entity: 'company' });
		expect(companies.every((entry) => entry.entity_kind === 'company')).toBe(true);
		const caps = filterAlerts(alerts, { ...NO_FILTERS, kind: 'cap_fired' });
		expect(caps.every((entry) => entry.kind === 'cap_fired')).toBe(true);
		const group = alerts[0].group_id;
		const found = filterAlerts(alerts, { ...NO_FILTERS, query: group.toLowerCase() });
		expect(found.length).toBe(alerts.filter((entry) => entry.group_id === group).length);
		expect(filterAlerts(alerts, { ...NO_FILTERS, query: 'no-such-entity' })).toEqual([]);
	});

	it('scopes the list to one month only when asked', () => {
		const month = alerts[0].month;
		expect(inScope(alerts, 'history', month)).toBe(alerts);
		expect(inScope(alerts, 'month', month).every((entry) => entry.month === month)).toBe(true);
		expect(inScope(alerts, 'month', '1999-01')).toEqual([]);
	});

	it('builds a timeline with one entry per bundle month that adds up to the file', () => {
		const timeline = monthlyCounts(alerts, manifest.months);
		expect(timeline.map((entry) => entry.month)).toEqual(manifest.months);
		expect(timeline.reduce((total, entry) => total + entry.total, 0)).toBe(alerts.length);
		for (const entry of timeline) {
			expect(entry.fired + entry.suppressed + entry.abstained).toBe(entry.total);
		}
	});
});

describe('alert order and grouping', () => {
	it('puts the newest month first and the group before its companies', () => {
		const sorted = sortAlerts([
			alert({ entity_id: 'C1', entity_kind: 'company', group_id: 'G1', month: '2026-02' }),
			alert({ entity_id: 'G1', month: '2026-02' }),
			alert({ entity_id: 'G2', month: '2026-03' }),
			alert({ entity_id: 'G0', month: '2026-01' })
		]);
		expect(sorted.map((entry) => entry.entity_id)).toEqual(['G2', 'G1', 'C1', 'G0']);
		expect(groupByMonth(sorted).map((group) => [group.month, group.alerts.length])).toEqual([
			['2026-03', 1],
			['2026-02', 2],
			['2026-01', 1]
		]);
	});

	it('links a group alert to the group and a company alert to its drill-down', () => {
		expect(alertEntityPath(alert({ entity_id: 'G1', month: '2026-02' }))).toBe('/group/G1');
		expect(
			alertEntityPath(
				alert({ entity_id: 'C1', entity_kind: 'company', group_id: 'G1', month: '2026-02' })
			)
		).toBe('/group/G1/company/C1');
	});
});

describe('abstentions and sentences', () => {
	it('finds the standing abstention of the entity of an alert, by kind and id', () => {
		for (const entry of alerts.filter((candidate) => candidate.state === 'abstained')) {
			const expected =
				receipt.abstentions.find(
					(item) => item.entity_id === entry.entity_id && item.entity_kind === entry.entity_kind
				) ?? null;
			expect(standingAbstention(entry, receipt.abstentions)).toEqual(expected);
		}
		expect(standingAbstention(alert({ entity_id: 'NOPE', month: '2026-02' }), [])).toBeNull();
	});

	it('writes the months an engine sentence quotes as periods, and nothing else', () => {
		expect(humanizeMonths('frente a 2025-09; se mueven: pagos')).toBe(
			'frente a septiembre de 2025; se mueven: pagos'
		);
		expect(humanizeMonths('corte del 2025-09-30')).toBe('corte del 2025-09-30');
		expect(humanizeMonths('baja de 35 puntos')).toBe('baja de 35 puntos');
	});
});
