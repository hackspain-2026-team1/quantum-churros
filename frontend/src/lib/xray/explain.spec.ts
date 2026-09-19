import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { BUNDLE_FILES, parseBundleFile, type EntityMonth } from './contract';
import {
	bandDistances,
	bandDomain,
	bandZones,
	monthChanges,
	monthsBetween,
	previousEntry,
	verdictDelta,
	waterfallGap,
	waterfallSteps,
	weakestPillar
} from './explain';

// Synthetic, test-only bundle; the app never serves it.
const root = fileURLToPath(new URL('../../../e2e/fixtures/bundle/v1/', import.meta.url));
const read = (path: string): unknown => JSON.parse(readFileSync(`${root}${path}`, 'utf-8'));
const ids = (folder: string) =>
	readdirSync(`${root}${folder}`)
		.filter((name) => name.endsWith('.json'))
		.map((name) => name.slice(0, -'.json'.length))
		.sort();

const manifest = parseBundleFile('manifest', read(BUNDLE_FILES.manifest));
const entities: EntityMonth[][] = [
	...ids('groups').map((id) => parseBundleFile('group', read(BUNDLE_FILES.group(id))).months),
	...ids('companies').map((id) => parseBundleFile('company', read(BUNDLE_FILES.company(id))).months)
];

describe('waterfall', () => {
	it('walks from the base to the score in integer tenths for every entity-month', () => {
		expect(entities.flat().length).toBeGreaterThan(0);
		for (const entry of entities.flat()) {
			const steps = waterfallSteps(entry);
			expect(steps.map((step) => step.key)).toEqual([
				'base',
				...entry.pillars.map((pillar) => pillar.key),
				'penalty',
				'cap',
				'shown'
			]);
			expect(steps.every((step) => Number.isInteger(step.end))).toBe(true);
			expect(steps[steps.length - 2].end).toBe(entry.shown);
			expect(waterfallGap(entry)).toBe(0);
		}
	});

	it('names the lowest available pillar', () => {
		for (const entry of entities.flat()) {
			const scores = entry.pillars.flatMap((pillar) => (pillar.score === null ? [] : pillar.score));
			const weakest = weakestPillar(entry);
			if (scores.length === 0) expect(weakest).toBeNull();
			else expect(weakest?.score).toBe(Math.min(...scores));
		}
	});
});

describe('month-over-month changes', () => {
	it('adds up to the change of the score for every pair of consecutive months', () => {
		let pairs = 0;
		for (const months of entities) {
			for (const entry of months) {
				const previous = previousEntry(months, entry.month);
				if (!previous) continue;
				const changes = monthChanges(entry, previous);
				expect(changes.gap).toBe(0);
				expect(changes.items.reduce((sum, item) => sum + item.delta, 0)).toBe(
					entry.shown - previous.shown
				);
				expect(changes.items).toHaveLength(8);
				pairs += 1;
			}
		}
		expect(pairs).toBeGreaterThan(0);
	});

	it('flags a pillar that appears or disappears', () => {
		const entry = entities.flat()[0];
		const without: EntityMonth = {
			...entry,
			pillars: entry.pillars.map((pillar, index) =>
				index === 0 ? { ...pillar, score: null, w_eff: 0, contrib: 0 } : pillar
			)
		};
		const first = entry.pillars[0];
		const expected = first.score === null ? null : 'lost';
		expect(monthChanges(without, entry).items[1].availability).toBe(expected);
		expect(previousEntry([entry], entry.month)).toBeNull();
	});

	it('counts whole months between two closes', () => {
		expect(monthsBetween('2026-05', '2026-08')).toBe(3);
		expect(monthsBetween('2025-11', '2026-02')).toBe(3);
		expect(monthsBetween('2026-02', '2026-02')).toBe(0);
		expect(monthsBetween('2026-03', '2025-12')).toBe(-3);
	});
});

describe('band scale', () => {
	const zones = bandZones(manifest.bands);

	it('turns manifest.bands into contiguous zones', () => {
		expect(zones[0].min).toBe(0);
		expect(zones[zones.length - 1].max).toBe(1000);
		zones.slice(1).forEach((zone, index) => expect(zone.min).toBe(zones[index].max));
	});

	it('frames a score chart with the thresholds around the data', () => {
		const inside = zones[1];
		const domain = bandDomain([inside.min + 1, null, inside.max - 1], zones);
		expect(domain).toEqual({ low: inside.min, high: inside.max });
		expect(bandDomain([], zones)).toEqual({ low: 0, high: 1000 });
		expect(bandDomain([1000], zones).high).toBe(1000);
		expect(bandDomain([1000], zones).low).toBeLessThan(1000);
	});

	it('measures the distance to the neighbouring bands', () => {
		const zone = zones[1];
		const distances = bandDistances(zone.min + 7, zones);
		expect(distances.current?.key).toBe(zone.key);
		expect(distances.above?.distance).toBe(zone.max - zone.min - 7);
		expect(distances.below?.distance).toBe(7);
		expect(bandDistances(zones[0].min, zones).below).toBeNull();
		expect(bandDistances(1000, zones).above).toBeNull();
	});
});

describe('verdict change', () => {
	it('is the difference of the two scores on screen whenever the compared month is there', () => {
		let checked = 0;
		for (const months of entities) {
			for (const entry of months) {
				const delta = verdictDelta(entry, months);
				const compared = months.find((item) => item.month === entry.verdict.compared_to);
				if (entry.verdict.delta3 === null || !compared) {
					expect(delta).toBe(entry.verdict.delta3);
					continue;
				}
				checked += 1;
				expect(delta).toBe(entry.shown - compared.shown);
				// The engine rounds its own delta from full precision: never more than a tenth away.
				expect(Math.abs(delta! - entry.verdict.delta3)).toBeLessThanOrEqual(1);
			}
		}
		expect(checked).toBeGreaterThan(0);
	});

	it('keeps the delta of the engine when the compared month is not in the file', () => {
		const months = entities.find((list) => list.some((entry) => entry.verdict.delta3 !== null))!;
		const entry = months.find((item) => item.verdict.delta3 !== null)!;
		expect(verdictDelta(entry, [])).toBe(entry.verdict.delta3);
	});
});
