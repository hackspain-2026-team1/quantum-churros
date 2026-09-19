// As-of view of an entity for the original hero: the monthly score up to the
// selected month, where the engine detected the change, and the engine's target.

import type { EntityMonth } from './contract.js';

export type EntitySeries = {
	months: string[];
	/** Displayed score in points, one per month up to the selected one. */
	values: number[];
	/** Index of verdict.detected_since within `months`; null when the engine detected nothing. */
	changeIndex: number | null;
};

export function entitySeries(entries: readonly EntityMonth[], month: string): EntitySeries {
	const upTo = entries.filter((entry) => entry.month <= month);
	const months = upTo.map((entry) => entry.month);
	const since = upTo.at(-1)?.verdict.detected_since ?? null;
	const index = since ? months.indexOf(since) : -1;
	return {
		months,
		values: upTo.map((entry) => entry.shown / 10),
		changeIndex: index >= 0 ? index : null
	};
}
