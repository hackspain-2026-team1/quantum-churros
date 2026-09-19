import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { entryActions, fullPlanTenths, projectedTenths } from './actions.js';
import { parseBundleFile } from './contract.js';

const read = (path: string) =>
	JSON.parse(
		readFileSync(new URL(`../../../e2e/fixtures/bundle/v1/${path}`, import.meta.url), 'utf8')
	);
const group = parseBundleFile('group', read('groups/GROUP_T001.json'));
const entry = group.months.findLast((month) => (month.actions?.length ?? 0) > 1)!;

describe('actions', () => {
	it('parses the optional actions and orders them by uplift', () => {
		const uplifts = entryActions(entry).map((action) => action.uplift_tenths);
		expect(uplifts.length).toBeGreaterThan(1);
		expect(uplifts).toEqual([...uplifts].sort((a, b) => b - a));
	});

	it('treats a month without actions as an empty plan', () => {
		const bare = { ...entry, actions: undefined, actions_combined: undefined };
		expect(entryActions(bare)).toEqual([]);
		expect(fullPlanTenths(bare)).toBeNull();
		expect(projectedTenths(bare, new Set(['anything']))).toBe(entry.shown);
	});

	it('projects none, one and every action from the engine figures', () => {
		const actions = entryActions(entry);
		expect(projectedTenths(entry, new Set())).toBe(entry.shown);
		expect(projectedTenths(entry, new Set([actions[0].id]))).toBe(actions[0].new_score_tenths);
		const all = new Set(actions.map((action) => action.id));
		expect(projectedTenths(entry, all)).toBe(entry.actions_combined!.new_score);
		expect(fullPlanTenths(entry)).toBe(entry.actions_combined!.new_score);
	});

	it('never lets a subset beat the combined run', () => {
		const actions = entryActions(entry);
		const pair = new Set(actions.slice(0, 2).map((action) => action.id));
		expect(projectedTenths(entry, pair)).toBeLessThanOrEqual(entry.actions_combined!.new_score);
	});
});
