// Spanish texts that live in the manifest: pillar and band labels, and the
// glossary for open codes (gates, flags, caps, reasons). Closed vocabularies
// (direction, nature, confidence, alert kind/state) are the *_TEXT maps of contract.ts.

import type { Band, Manifest, PillarKey } from './contract.js';

export type GlossaryKind = keyof Manifest['glossary'];

export function bandLabel(manifest: Manifest | undefined, band: Band): string {
	return manifest?.bands.find((entry) => entry.key === band)?.label ?? band;
}

export function pillarLabel(manifest: Manifest | undefined, key: PillarKey): string {
	return manifest?.pillars.find((entry) => entry.key === key)?.label ?? key;
}

/** Text of an open code; falls back to the code itself so nothing is hidden. */
export function glossaryText(
	manifest: Manifest | undefined,
	kind: GlossaryKind,
	code: string
): string {
	return manifest?.glossary[kind][code] ?? code;
}
