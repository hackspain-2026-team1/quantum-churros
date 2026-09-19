// Pure arithmetic behind the entity page: the waterfall, the month-over-month
// differences and the band scale. Everything stays in integer tenths, so the
// sums on screen are exact and can be asserted.

import { PILLAR_KEYS, type EntityMonth, type Manifest, type PillarKey } from './contract.js';

export type StepKey = 'base' | PillarKey | 'penalty' | 'cap' | 'shown';

export type WaterfallStep = {
	key: StepKey;
	/** Signed tenths added by the step; null for the two absolute rows (base, shown). */
	delta: number | null;
	/** Running total before and after the step, in tenths. */
	start: number;
	end: number;
};

/** base, the five pillars, -penalty, -cap and the score: the last running total equals `shown`. */
export function waterfallSteps(entry: EntityMonth): WaterfallStep[] {
	const steps: WaterfallStep[] = [{ key: 'base', delta: null, start: 0, end: entry.base }];
	let running = entry.base;
	const push = (key: StepKey, delta: number) => {
		steps.push({ key, delta, start: running, end: running + delta });
		running += delta;
	};
	for (const pillar of entry.pillars) push(pillar.key, pillar.contrib);
	push('penalty', -entry.penalty);
	push('cap', -entry.cap.amount);
	steps.push({ key: 'shown', delta: null, start: 0, end: entry.shown });
	return steps;
}

/** Running total after the last additive step minus `shown`; 0 on a valid entity-month. */
export function waterfallGap(entry: EntityMonth): number {
	const steps = waterfallSteps(entry);
	return steps[steps.length - 2].end - entry.shown;
}

/** Available pillar with the lowest score: the one the non-compensatory penalty looks at. */
export function weakestPillar(entry: EntityMonth): { key: PillarKey; score: number } | null {
	let weakest: { key: PillarKey; score: number } | null = null;
	for (const pillar of entry.pillars) {
		if (pillar.score === null) continue;
		if (!weakest || pillar.score < weakest.score)
			weakest = { key: pillar.key, score: pillar.score };
	}
	return weakest;
}

export type ChangeKey = 'base' | PillarKey | 'penalty' | 'cap';

export type ChangeItem = {
	key: ChangeKey;
	/** Signed effect on the score, in tenths. */
	delta: number;
	/** Set when the pillar appears or disappears between the two months. */
	availability: 'gained' | 'lost' | null;
};

export type MonthChanges = {
	from: string;
	to: string;
	/** shown(to) - shown(from), in tenths. */
	total: number;
	items: ChangeItem[];
	/** sum(items) - total; 0 because both months satisfy the waterfall identity. */
	gap: number;
};

/** Integer differences of every waterfall term between two months of the same entity. */
export function monthChanges(current: EntityMonth, previous: EntityMonth): MonthChanges {
	const items: ChangeItem[] = [
		{ key: 'base', delta: current.base - previous.base, availability: null }
	];
	for (const key of PILLAR_KEYS) {
		const now = current.pillars.find((pillar) => pillar.key === key);
		const before = previous.pillars.find((pillar) => pillar.key === key);
		const available = now?.score !== null && now?.score !== undefined;
		const wasAvailable = before?.score !== null && before?.score !== undefined;
		items.push({
			key,
			delta: (now?.contrib ?? 0) - (before?.contrib ?? 0),
			availability: available === wasAvailable ? null : available ? 'gained' : 'lost'
		});
	}
	items.push({
		key: 'penalty',
		delta: -(current.penalty - previous.penalty),
		availability: null
	});
	items.push({
		key: 'cap',
		delta: -(current.cap.amount - previous.cap.amount),
		availability: null
	});
	const total = current.shown - previous.shown;
	const gap = items.reduce((sum, item) => sum + item.delta, 0) - total;
	return { from: previous.month, to: current.month, total, items, gap };
}

/** Entry right before `month` in the entity's own months (ascending), or null on the first one. */
export function previousEntry(entries: readonly EntityMonth[], month: string): EntityMonth | null {
	const index = entries.findIndex((entry) => entry.month === month);
	return index > 0 ? entries[index - 1] : null;
}

/**
 * Change shown beside a verdict, in tenths. When the comparison month is among the entity's own
 * months it is the difference of the two scores on screen (the arithmetic of the portfolio
 * column), so the reader can check it against the trajectory; verdict.delta3 is rounded by the
 * engine from full precision and may sit one tenth away from that difference.
 */
export function verdictDelta(entry: EntityMonth, months: readonly EntityMonth[]): number | null {
	const { compared_to: comparedTo, delta3 } = entry.verdict;
	if (delta3 === null || !comparedTo) return delta3;
	const compared = months.find((item) => item.month === comparedTo);
	return compared ? entry.shown - compared.shown : delta3;
}

/** Whole months from `from` to `to` ('YYYY-MM'); negative when `to` is earlier. */
export function monthsBetween(from: string, to: string): number {
	const [fromYear, fromMonth] = from.split('-').map(Number);
	const [toYear, toMonth] = to.split('-').map(Number);
	return (toYear - fromYear) * 12 + (toMonth - fromMonth);
}

export type BandZone = {
	key: Manifest['bands'][number]['key'];
	label: string;
	/** Inclusive lower bound and exclusive upper bound, in tenths. */
	min: number;
	max: number;
};

export const SCORE_MAX = 1000;

/** manifest.bands as contiguous zones over 0-1000 tenths. */
export function bandZones(bands: Manifest['bands']): BandZone[] {
	const sorted = [...bands].sort((a, b) => a.min - b.min);
	return sorted.map((band, index) => ({
		key: band.key,
		label: band.label,
		min: band.min,
		max: sorted[index + 1]?.min ?? SCORE_MAX
	}));
}

/**
 * Value axis for a score chart: the band thresholds that enclose the data, so
 * the reader always sees which band the line lives in and the next one each way.
 */
export function bandDomain(values: readonly (number | null)[], zones: readonly BandZone[]) {
	const observed = values.filter((value): value is number => value !== null);
	if (observed.length === 0 || zones.length === 0) return { low: 0, high: SCORE_MAX };
	const edges = [...zones.map((zone) => zone.min), SCORE_MAX];
	const low = Math.min(...observed);
	const high = Math.max(...observed);
	// The floor is always a band start, so a score of exactly 100 still gets a band to live in.
	const floor = Math.max(...zones.map((zone) => zone.min).filter((edge) => edge <= low), edges[0]);
	const ceiling = Math.min(...edges.filter((edge) => edge > high), SCORE_MAX);
	return { low: floor, high: ceiling > floor ? ceiling : SCORE_MAX };
}

/** Distance in tenths to the thresholds around a score: next band up and the floor of its own. */
export function bandDistances(tenths: number, zones: readonly BandZone[]) {
	const found = zones.findIndex((zone) => tenths >= zone.min && tenths < zone.max);
	// A score of exactly 100 sits on the closed end of the last band.
	const index = found === -1 ? zones.length - 1 : found;
	const current = zones[index] ?? null;
	const above = zones[index + 1] ?? null;
	const below = index > 0 ? zones[index - 1] : null;
	return {
		current,
		above: above ? { zone: above, distance: above.min - tenths } : null,
		below: below && current ? { zone: below, distance: tenths - current.min } : null
	};
}
