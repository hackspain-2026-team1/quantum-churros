// Pure month helpers shared by the month store and the screens.
// Months are 'YYYY-MM', so plain string comparison orders them.

export const MONTH_PARAM = 'm';

const MONTH_PATTERN = /^[0-9]{4}-(0[1-9]|1[0-2])$/;

export function isMonth(value: unknown): value is string {
	return typeof value === 'string' && MONTH_PATTERN.test(value);
}

/**
 * The month of `months` (ascending) that answers a request: the month itself,
 * else the closest earlier one, clamped to the range. No request means the latest.
 */
export function resolveMonth(months: readonly string[], wanted: string | null | undefined): string {
	const latest = months.at(-1) ?? '';
	if (!isMonth(wanted) || months.length === 0) return latest;
	if (months.includes(wanted)) return wanted;
	if (wanted < months[0]) return months[0];
	let match = months[0];
	for (const month of months) {
		if (month <= wanted) match = month;
	}
	return match;
}

/** Index of `month` in the months of a given file, -1 when that file does not cover it. */
export function monthIndex(months: readonly string[], month: string): number {
	return months.indexOf(month);
}

/** Entity-month (group.months[], company.months[], evidence.months[]) for `month`, or null. */
export function entryAt<T extends { month: string }>(
	entries: readonly T[],
	month: string
): T | null {
	return entries.find((entry) => entry.month === month) ?? null;
}

/** Value of a columnar array aligned with `months`; null when not observed or not covered. */
export function valueAt<T>(
	months: readonly string[],
	values: readonly (T | null)[],
	month: string
): T | null {
	const index = months.indexOf(month);
	return index === -1 ? null : (values[index] ?? null);
}
