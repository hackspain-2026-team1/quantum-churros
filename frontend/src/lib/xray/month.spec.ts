import { describe, expect, it } from 'vitest';
import { entryAt, isMonth, monthIndex, resolveMonth, valueAt } from './month';

const months = ['2026-01', '2026-02', '2026-04', '2026-05'];

describe('month helpers', () => {
	it('recognises YYYY-MM only', () => {
		expect(['2026-01', '2026-12'].every(isMonth)).toBe(true);
		expect(['2026-13', '2026-1', '26-01', '', null, 202601].some(isMonth)).toBe(false);
	});

	it('resolves a request to a month of the bundle', () => {
		expect(resolveMonth(months, null)).toBe('2026-05');
		expect(resolveMonth(months, 'nope')).toBe('2026-05');
		expect(resolveMonth(months, '2026-02')).toBe('2026-02');
		expect(resolveMonth(months, '2026-03')).toBe('2026-02');
		expect(resolveMonth(months, '2025-06')).toBe('2026-01');
		expect(resolveMonth(months, '2027-01')).toBe('2026-05');
		expect(resolveMonth([], '2026-01')).toBe('');
	});

	it('reads aligned columns and entity months', () => {
		expect(monthIndex(months, '2026-04')).toBe(2);
		expect(valueAt(months, [1, null, 3, 4], '2026-04')).toBe(3);
		expect(valueAt(months, [1, null, 3, 4], '2026-02')).toBeNull();
		expect(valueAt(months, [1, null, 3, 4], '2025-01')).toBeNull();
		expect(entryAt([{ month: '2026-01', shown: 500 }], '2026-01')?.shown).toBe(500);
		expect(entryAt([{ month: '2026-01', shown: 500 }], '2026-02')).toBeNull();
	});
});
