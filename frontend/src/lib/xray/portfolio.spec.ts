import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { BUNDLE_FILES, parseBundleFile, type Portfolio } from './contract';
import {
	DELTA_MONTHS,
	closingNotes,
	countryName,
	filterRows,
	normalizeText,
	portfolioRows,
	sortRows,
	summarize,
	type PortfolioFilters
} from './portfolio';

// Synthetic, test-only bundle; the app never serves it.
const root = fileURLToPath(new URL('../../../e2e/fixtures/bundle/v1/', import.meta.url));
const read = (path: string): unknown => JSON.parse(readFileSync(`${root}${path}`, 'utf-8'));
const fixture = parseBundleFile('portfolio', read(BUNDLE_FILES.portfolio));
const fixtureAlerts = parseBundleFile('alerts', read(BUNDLE_FILES.alerts)).alerts;

const NO_FILTERS: PortfolioFilters = { query: '', band: 'all', direction: 'all', movers: false };

// Four months, three groups: A falls, B appears late and abstains, C changes perimeter.
const months = ['2026-01', '2026-02', '2026-03', '2026-04'];
const column = <T>(...values: T[]) => values;
const tiny: Portfolio = {
	schema: 'xray-export-v1',
	kind: 'portfolio',
	months,
	groups: [
		{
			id: 'A',
			n_companies: 3,
			first_month: '2026-01',
			country: 'ES',
			size_band: 'Mediana',
			industry: 'Distribución mayorista',
			shown: column(800, 790, 700, 650),
			band: column('solid', 'stable', 'stable', 'stable'),
			direction: column('stable', 'stable', 'deteriorating', 'deteriorating'),
			nature: column(null, null, 'shock_pending', 'structural'),
			conf: column('high', 'high', 'high', 'high'),
			abstained: column(false, false, false, false),
			perimeter_changed: column(false, false, false, false),
			alerts_fired: column(0, 0, 0, 2),
			alerts_muted: column(0, 0, 0, 0)
		},
		{
			id: 'B',
			n_companies: 1,
			first_month: '2026-03',
			country: null,
			size_band: null,
			industry: null,
			shown: column(null, null, 300, 310),
			band: column(null, null, 'critical', 'critical'),
			direction: column(null, null, 'stable', 'stable'),
			nature: column(null, null, null, null),
			conf: column(null, null, 'low', 'low'),
			abstained: column(null, null, true, true),
			perimeter_changed: column(null, null, false, false),
			alerts_fired: column(0, 0, 0, 0),
			alerts_muted: column(0, 0, 1, 1)
		},
		{
			id: 'C',
			n_companies: 2,
			first_month: '2026-01',
			country: 'PT',
			size_band: 'Pequeña',
			industry: 'Hostelería',
			shown: column(500, 520, 540, 900),
			band: column('watch', 'watch', 'watch', 'solid'),
			direction: column('stable', 'stable', 'stable', 'perimeter_shift'),
			nature: column(null, null, null, null),
			conf: column('medium', 'medium', 'medium', 'medium'),
			abstained: column(false, false, false, false),
			perimeter_changed: column(false, false, false, true),
			alerts_fired: column(0, 0, 0, 0),
			alerts_muted: column(0, 0, 0, 1)
		}
	]
};

describe('portfolio rows', () => {
	it('projects the columnar arrays at the selected month', () => {
		const [a, b, c] = portfolioRows(tiny, '2026-04');
		expect(a).toMatchObject({ shown: 650, band: 'stable', direction: 'deteriorating', fired: 2 });
		expect(a.delta).toBe(650 - 800);
		expect(a.deltaFrom).toBe('2026-01');
		expect(b).toMatchObject({ observed: true, abstained: true, delta: null, deltaFrom: null });
		expect(c).toMatchObject({ perimeterChanged: true, perimeterMonths: [3], muted: 1 });
	});

	it('marks a group as not observed before its first month and outside the window', () => {
		const early = portfolioRows(tiny, '2026-01');
		expect(early[1]).toMatchObject({ observed: false, shown: null, band: null, abstained: false });
		expect(early[0].delta).toBeNull();
		expect(portfolioRows(tiny, '2030-01').every((row) => !row.observed)).toBe(true);
	});

	it('computes the delta as a difference of displayed scores over the fixture', () => {
		fixture.months.forEach((month, index) => {
			for (const row of portfolioRows(fixture, month)) {
				const now = row.group.shown[index];
				const before = index >= DELTA_MONTHS ? row.group.shown[index - DELTA_MONTHS] : null;
				expect(row.delta).toBe(now === null || before === null ? null : now - before);
			}
		});
	});
});

describe('portfolio summary', () => {
	it('counts bands, directions and abstentions of the month', () => {
		const summary = summarize(portfolioRows(tiny, '2026-04'));
		expect(summary).toMatchObject({
			total: 3,
			scored: 3,
			unobserved: 0,
			median: 650,
			deteriorating: 1,
			deterioratingStructural: 1,
			deterioratingPending: 0,
			improving: 0,
			perimeterShift: 1,
			perimeterChanged: 1,
			abstained: 1,
			fired: 2,
			muted: 2
		});
		expect(summary.bands).toEqual([
			{ key: 'critical', count: 1 },
			{ key: 'watch', count: 0 },
			{ key: 'stable', count: 1 },
			{ key: 'solid', count: 1 }
		]);
	});

	it('rounds the median of an even number of scores and handles an empty month', () => {
		expect(summarize(portfolioRows(tiny, '2026-02')).median).toBe(Math.round((790 + 520) / 2));
		expect(summarize(portfolioRows(tiny, '2030-01'))).toMatchObject({ scored: 0, median: null });
	});

	it('never counts the direction of an abstained group', () => {
		const rows = portfolioRows(tiny, '2026-04').map((row) =>
			row.id === 'A' ? { ...row, abstained: true } : row
		);
		expect(summarize(rows)).toMatchObject({ deteriorating: 0, abstained: 2 });
	});

	it('adds up over every month of the fixture', () => {
		for (const month of fixture.months) {
			const summary = summarize(portfolioRows(fixture, month));
			expect(summary.scored + summary.unobserved).toBe(fixture.groups.length);
			expect(summary.bands.reduce((total, band) => total + band.count, 0)).toBe(summary.scored);
			const dated = fixtureAlerts.filter((alert) => alert.month === month);
			expect(summary.fired).toBe(dated.filter((alert) => alert.state === 'fired').length);
			expect(summary.muted).toBe(dated.filter((alert) => alert.state !== 'fired').length);
		}
	});
});

describe('portfolio filters and order', () => {
	const rows = portfolioRows(tiny, '2026-04');
	const ids = (list: { id: string }[]) => list.map((row) => row.id);

	it('searches id, sector, size and country without accents', () => {
		expect(normalizeText('  Distribución ')).toBe('distribucion');
		expect(ids(filterRows(rows, { ...NO_FILTERS, query: 'distribucion' }))).toEqual(['A']);
		expect(ids(filterRows(rows, { ...NO_FILTERS, query: 'portugal' }))).toEqual(['C']);
		expect(ids(filterRows(rows, { ...NO_FILTERS, query: 'pequeña' }))).toEqual(['C']);
		expect(ids(filterRows(rows, { ...NO_FILTERS, query: 'zzz' }))).toEqual([]);
	});

	it('filters by band, direction, abstention and movers', () => {
		expect(ids(filterRows(rows, { ...NO_FILTERS, band: 'critical' }))).toEqual(['B']);
		expect(ids(filterRows(rows, { ...NO_FILTERS, direction: 'deteriorating' }))).toEqual(['A']);
		expect(ids(filterRows(rows, { ...NO_FILTERS, direction: 'abstained' }))).toEqual(['B']);
		// B is 'stable' in the file but abstained: it has no verdict to filter by.
		expect(ids(filterRows(rows, { ...NO_FILTERS, direction: 'stable' }))).toEqual([]);
		expect(ids(filterRows(rows, { ...NO_FILTERS, movers: true }))).toEqual(['A', 'C']);
	});

	it('sorts both ways with missing values last', () => {
		expect(ids(sortRows(rows, 'shown', 'asc'))).toEqual(['B', 'A', 'C']);
		expect(ids(sortRows(rows, 'shown', 'desc'))).toEqual(['C', 'A', 'B']);
		expect(ids(sortRows(rows, 'delta', 'asc'))).toEqual(['A', 'C', 'B']);
		expect(ids(sortRows(rows, 'delta', 'desc'))).toEqual(['C', 'A', 'B']);
		expect(ids(sortRows(rows, 'move', 'desc'))).toEqual(['C', 'A', 'B']);
		expect(ids(sortRows(rows, 'conf', 'asc'))).toEqual(['B', 'C', 'A']);
		expect(ids(sortRows(rows, 'alerts', 'desc'))).toEqual(['A', 'B', 'C']);
		expect(ids(sortRows(rows, 'id', 'desc'))).toEqual(['C', 'B', 'A']);
		const early = portfolioRows(tiny, '2026-01');
		expect(ids(sortRows(early, 'shown', 'desc'))).toEqual(['A', 'C', 'B']);
	});
});

describe('closing notes', () => {
	it('reads the month with the directions of the engine', () => {
		const notes = closingNotes(portfolioRows(tiny, '2026-04'));
		expect(notes.map((note) => [note.kind, note.row?.id ?? null])).toEqual([
			['fall', 'A'],
			['perimeter', 'C'],
			['abstained', 'B']
		]);
	});

	it('says so when no judged group deteriorates, and stays silent on an empty month', () => {
		const calm = closingNotes(portfolioRows(tiny, '2026-02'));
		expect(calm[0]).toMatchObject({ kind: 'no_fall', row: null });
		expect(calm[1]).toMatchObject({ kind: 'lowest' });
		expect(calm[1].row?.id).toBe('C');
		expect(closingNotes(portfolioRows(tiny, '2030-01'))).toEqual([]);
	});

	it('never returns more than three notes on the fixture', () => {
		for (const month of fixture.months) {
			expect(closingNotes(portfolioRows(fixture, month)).length).toBeLessThanOrEqual(3);
		}
	});
});

describe('countryName', () => {
	it('names ISO codes in Spanish and leaves anything else as written', () => {
		expect(countryName('ES')).toBe('España');
		expect(countryName('pt')).toBe('Portugal');
		expect(countryName('Iberia')).toBe('Iberia');
		expect(countryName(null)).toBeNull();
	});
});
