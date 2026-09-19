// Pure projections of portfolio.json for one month: table rows, header KPIs,
// filters and sorting. Every figure is read from the bundle or is integer
// arithmetic over figures of the bundle (counts, a median, a difference of
// two displayed scores); nothing here is a constant of the product.

import {
	BAND_KEYS,
	type Band,
	type ConfLabel,
	type Direction,
	type Nature,
	type Portfolio,
	type PortfolioGroup
} from './contract.js';

/** Horizon of the score change shown in the table, the same one the verdict looks at. */
export const DELTA_MONTHS = 3;

export type PortfolioRow = {
	group: PortfolioGroup;
	id: string;
	/** false when the group has no score in the selected month. */
	observed: boolean;
	shown: number | null;
	band: Band | null;
	direction: Direction | null;
	nature: Nature | null;
	conf: ConfLabel | null;
	abstained: boolean;
	perimeterChanged: boolean;
	/** shown(month) - shown(month - DELTA_MONTHS), integer tenths; null when either is missing. */
	delta: number | null;
	/** Month the delta compares against. */
	deltaFrom: string | null;
	fired: number;
	muted: number;
	/** Indexes of portfolio.months where the perimeter of the group changed. */
	perimeterMonths: number[];
};

export type PortfolioSummary = {
	total: number;
	scored: number;
	unobserved: number;
	/** Median displayed score of the month, integer tenths. */
	median: number | null;
	bands: { key: Band; count: number }[];
	deteriorating: number;
	deterioratingStructural: number;
	deterioratingPending: number;
	improving: number;
	improvingStructural: number;
	perimeterShift: number;
	perimeterChanged: number;
	abstained: number;
	fired: number;
	muted: number;
};

export type DirectionFilter = 'all' | Direction | 'abstained';
export type BandFilter = 'all' | Band;
export type SortKey = 'id' | 'shown' | 'delta' | 'move' | 'conf' | 'companies' | 'alerts';
export type SortDir = 'asc' | 'desc';

export type PortfolioFilters = {
	query: string;
	band: BandFilter;
	direction: DirectionFilter;
	/** Only groups with a 3-month change, to rank them by its size. */
	movers: boolean;
};

/** One row per group at `month`; columnar arrays align with portfolio.months. */
export function portfolioRows(portfolio: Portfolio, month: string): PortfolioRow[] {
	const index = portfolio.months.indexOf(month);
	const past = index - DELTA_MONTHS;
	return portfolio.groups.map((group) => {
		const shown = index < 0 ? null : (group.shown[index] ?? null);
		const before = index < 0 || past < 0 ? null : (group.shown[past] ?? null);
		const delta = shown === null || before === null ? null : shown - before;
		return {
			group,
			id: group.id,
			observed: shown !== null,
			shown,
			band: index < 0 ? null : (group.band[index] ?? null),
			direction: index < 0 ? null : (group.direction[index] ?? null),
			nature: index < 0 ? null : (group.nature[index] ?? null),
			conf: index < 0 ? null : (group.conf[index] ?? null),
			abstained: index >= 0 && group.abstained[index] === true,
			perimeterChanged: index >= 0 && group.perimeter_changed[index] === true,
			delta,
			deltaFrom: delta === null ? null : portfolio.months[past],
			fired: index < 0 ? 0 : (group.alerts_fired[index] ?? 0),
			muted: index < 0 ? 0 : (group.alerts_muted[index] ?? 0),
			perimeterMonths: group.perimeter_changed.flatMap((changed, at) => (changed ? [at] : []))
		};
	});
}

function median(values: number[]): number | null {
	if (values.length === 0) return null;
	const sorted = values.toSorted((a, b) => a - b);
	const middle = Math.floor(sorted.length / 2);
	return sorted.length % 2 === 1
		? sorted[middle]
		: Math.round((sorted[middle - 1] + sorted[middle]) / 2);
}

/** A trajectory verdict only counts while the engine does not abstain. */
const hasVerdict = (row: PortfolioRow) => row.observed && !row.abstained;

/** Header KPIs of the month. */
export function summarize(rows: PortfolioRow[]): PortfolioSummary {
	const observed = rows.filter((row) => row.observed);
	const judged = observed.filter(hasVerdict);
	const deteriorating = judged.filter((row) => row.direction === 'deteriorating');
	const improving = judged.filter((row) => row.direction === 'improving');
	return {
		total: rows.length,
		scored: observed.length,
		unobserved: rows.length - observed.length,
		median: median(observed.map((row) => row.shown as number)),
		bands: BAND_KEYS.map((key) => ({
			key,
			count: observed.filter((row) => row.band === key).length
		})),
		deteriorating: deteriorating.length,
		deterioratingStructural: deteriorating.filter((row) => row.nature === 'structural').length,
		deterioratingPending: deteriorating.filter((row) => row.nature === 'shock_pending').length,
		improving: improving.length,
		improvingStructural: improving.filter((row) => row.nature === 'structural').length,
		perimeterShift: judged.filter((row) => row.direction === 'perimeter_shift').length,
		perimeterChanged: observed.filter((row) => row.perimeterChanged).length,
		abstained: observed.filter((row) => row.abstained).length,
		fired: rows.reduce((total, row) => total + row.fired, 0),
		muted: rows.reduce((total, row) => total + row.muted, 0)
	};
}

export type ClosingNote =
	| { kind: 'fall' | 'rise' | 'lowest'; row: PortfolioRow; others: 0 }
	| { kind: 'perimeter' | 'abstained'; row: PortfolioRow; others: number }
	| { kind: 'no_fall'; row: null; others: 0 };

/**
 * Up to three readings of the month, each one pointing at a group: the largest
 * 3-month fall among the groups the engine calls deteriorating, the lowest score
 * with a verdict, and whichever of perimeter change, largest improvement or
 * abstention applies. Directions are the engine's; nothing is re-judged here.
 */
export function closingNotes(rows: PortfolioRow[]): ClosingNote[] {
	const judged = rows.filter(hasVerdict);
	if (rows.every((row) => !row.observed)) return [];
	const notes: ClosingNote[] = [];
	const byDelta = (direction: Direction, sign: 1 | -1) =>
		judged
			.filter((row) => row.direction === direction && row.delta !== null)
			.toSorted(
				(a, b) => sign * ((a.delta as number) - (b.delta as number)) || a.id.localeCompare(b.id)
			)[0] ?? null;

	const fall = byDelta('deteriorating', 1);
	if (fall) notes.push({ kind: 'fall', row: fall, others: 0 });
	else if (judged.length > 0 && !judged.some((row) => row.direction === 'deteriorating')) {
		notes.push({ kind: 'no_fall', row: null, others: 0 });
	}

	const lowest = sortRows(judged, 'shown', 'asc')[0] ?? null;
	if (lowest && lowest.id !== fall?.id) notes.push({ kind: 'lowest', row: lowest, others: 0 });

	const shifted = rows.filter(
		(row) => row.observed && (row.perimeterChanged || row.direction === 'perimeter_shift')
	);
	const rise = byDelta('improving', -1);
	const abstained = rows.filter((row) => row.observed && row.abstained);
	if (shifted.length > 0) {
		notes.push({ kind: 'perimeter', row: shifted[0], others: shifted.length - 1 });
	}
	if (rise) notes.push({ kind: 'rise', row: rise, others: 0 });
	if (abstained.length > 0) {
		notes.push({ kind: 'abstained', row: abstained[0], others: abstained.length - 1 });
	}
	return notes.slice(0, 3);
}

/** Lowercase without diacritics, so 'distribucion' finds 'Distribución'. */
export function normalizeText(text: string): string {
	return text
		.normalize('NFD')
		.replace(/\p{Diacritic}/gu, '')
		.toLowerCase()
		.trim();
}

export function filterRows(rows: PortfolioRow[], filters: PortfolioFilters): PortfolioRow[] {
	const needle = normalizeText(filters.query);
	return rows.filter((row) => {
		if (filters.band !== 'all' && row.band !== filters.band) return false;
		if (filters.direction === 'abstained' && !(row.observed && row.abstained)) return false;
		if (
			filters.direction !== 'all' &&
			filters.direction !== 'abstained' &&
			!(hasVerdict(row) && row.direction === filters.direction)
		) {
			return false;
		}
		if (filters.movers && row.delta === null) return false;
		if (!needle) return true;
		const { id, industry, size_band, country } = row.group;
		return [id, industry, size_band, country, countryName(country)].some(
			(field) => field && normalizeText(field).includes(needle)
		);
	});
}

const CONF_RANK: Record<ConfLabel, number> = { low: 0, medium: 1, high: 2 };

function sortValue(row: PortfolioRow, key: SortKey): number | string | null {
	switch (key) {
		case 'id':
			return row.id;
		case 'shown':
			return row.shown;
		case 'delta':
			return row.delta;
		case 'move':
			return row.delta === null ? null : Math.abs(row.delta);
		case 'conf':
			return row.conf === null ? null : CONF_RANK[row.conf];
		case 'companies':
			return row.group.n_companies;
		case 'alerts':
			return row.observed ? row.fired * 1_000_000 + row.muted : null;
	}
}

/** Sorted copy. Rows without a value for the key always go last; ties break by id. */
export function sortRows(rows: PortfolioRow[], key: SortKey, dir: SortDir): PortfolioRow[] {
	const sign = dir === 'asc' ? 1 : -1;
	return rows.toSorted((a, b) => {
		const left = sortValue(a, key);
		const right = sortValue(b, key);
		if (left === null || right === null) {
			if (left !== right) return left === null ? 1 : -1;
			return a.id.localeCompare(b.id);
		}
		const order =
			typeof left === 'string' || typeof right === 'string'
				? String(left).localeCompare(String(right))
				: left - right;
		return order * sign || a.id.localeCompare(b.id);
	});
}

/** Direction a column sorts in the first time it is clicked. */
export const DEFAULT_SORT_DIR: Record<SortKey, SortDir> = {
	id: 'asc',
	shown: 'asc',
	delta: 'asc',
	move: 'desc',
	conf: 'asc',
	companies: 'desc',
	alerts: 'desc'
};

let regionNames: Intl.DisplayNames | null | undefined;

/** 'ES' -> 'España'; anything that is not an ISO 3166 alpha-2 code is returned as written. */
export function countryName(code: string | null): string | null {
	if (!code) return null;
	if (!/^[A-Za-z]{2}$/.test(code)) return code;
	if (regionNames === undefined) {
		try {
			regionNames = new Intl.DisplayNames('es-ES', { type: 'region', fallback: 'code' });
		} catch {
			regionNames = null;
		}
	}
	try {
		return regionNames?.of(code.toUpperCase()) ?? code;
	} catch {
		return code;
	}
}
