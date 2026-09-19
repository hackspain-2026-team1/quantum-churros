// What-if arithmetic over the actions the engine exports for an entity-month.
// Nothing here models the score: every number is an uplift the engine computed.

import type { EntityAction, EntityMonth } from './contract.js';

/** Actions of the month, largest uplift first; [] when the bundle carries none. */
export function entryActions(entry: EntityMonth | null | undefined): EntityAction[] {
	return [...(entry?.actions ?? [])].sort((a, b) => b.uplift_tenths - a.uplift_tenths);
}

/** Score (tenths) if every action is followed: the engine's combined run, else the best single action. */
export function fullPlanTenths(entry: EntityMonth): number | null {
	const actions = entryActions(entry);
	if (actions.length === 0) return null;
	if (entry.actions_combined) return entry.actions_combined.new_score;
	return Math.max(...actions.map((action) => action.new_score_tenths));
}

/**
 * Estimated score (tenths) for a subset of actions. One action: the engine's own figure.
 * Several: the sum of their uplifts, never above the engine's combined run. An estimate.
 */
export function projectedTenths(entry: EntityMonth, selected: ReadonlySet<string>): number {
	const chosen = entryActions(entry).filter((action) => selected.has(action.id));
	if (chosen.length === 0) return entry.shown;
	if (chosen.length === 1) return chosen[0].new_score_tenths;
	const sum = chosen.reduce((total, action) => total + action.uplift_tenths, 0);
	const ceiling = entry.actions_combined?.uplift ?? sum;
	return Math.min(1000, entry.shown + Math.min(sum, Math.max(ceiling, 0)));
}
