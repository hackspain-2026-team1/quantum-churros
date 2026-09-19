// Whole-bundle integrity: every JSON file of a bundle parses against the contract and the
// cross-file promises the screens rely on hold. It always runs on the synthetic fixture and,
// when present, on the bundle the app would actually serve (static/data/v1) or on the folder
// named by XRAY_BUNDLE_DIR, so an engine export is checked with the same rules before a deploy.

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
	BUNDLE_FILES,
	PILLAR_KEYS,
	parseBundleFile,
	type Alert,
	type AlertsFile,
	type BundleKind,
	type CompanyFile,
	type GroupFile,
	type Manifest,
	type Portfolio
} from './contract';

const frontendRoot = fileURLToPath(new URL('../../../', import.meta.url));
const fixtureRoot = join(frontendRoot, 'e2e', 'fixtures', 'bundle', 'v1');

function bundleId(root: string): string | null {
	try {
		return JSON.parse(readFileSync(join(root, BUNDLE_FILES.manifest), 'utf-8')).bundle_id ?? null;
	} catch {
		return null;
	}
}

function bundleRoots(): { name: string; root: string }[] {
	const roots = [{ name: 'fixture', root: fixtureRoot }];
	const candidates = [
		{ name: 'static/data/v1', root: join(frontendRoot, 'static', 'data', 'v1') },
		{ name: 'XRAY_BUNDLE_DIR', root: process.env.XRAY_BUNDLE_DIR ?? '' }
	];
	const seen = new Set([bundleId(fixtureRoot)]);
	for (const candidate of candidates) {
		if (!candidate.root || !existsSync(join(candidate.root, BUNDLE_FILES.manifest))) continue;
		const id = bundleId(candidate.root);
		// static/data/v1 usually holds a copy of the fixture: one pass is enough.
		if (seen.has(id)) continue;
		seen.add(id);
		roots.push(candidate);
	}
	return roots;
}

function jsonFiles(root: string, folder = root): string[] {
	return readdirSync(folder, { withFileTypes: true })
		.flatMap((entry) => {
			const path = join(folder, entry.name);
			if (entry.isDirectory()) return jsonFiles(root, path);
			return entry.name.endsWith('.json') ? [relative(root, path).split(sep).join('/')] : [];
		})
		.sort();
}

/** Kind of a bundle file from its path; null for a file the contract does not know. */
function kindOf(path: string): BundleKind | null {
	if (path === BUNDLE_FILES.manifest) return 'manifest';
	if (path === BUNDLE_FILES.portfolio) return 'portfolio';
	if (path === BUNDLE_FILES.alerts) return 'alerts';
	if (path === BUNDLE_FILES.invoices_due) return 'invoices_due';
	if (path === BUNDLE_FILES.receipt) return 'receipt';
	const [folder, file, ...rest] = path.split('/');
	if (rest.length > 0 || !file) return null;
	if (folder === 'groups') return 'group';
	if (folder === 'companies') return 'company';
	if (folder === 'evidence') return 'evidence';
	return null;
}

type Entity = GroupFile | CompanyFile;

/** An entity-month as written in the file, before zod has had a say. */
type RawMonth = {
	month?: unknown;
	shown?: unknown;
	base?: unknown;
	penalty?: unknown;
	cap?: { amount?: unknown };
	pillars?: { key?: unknown; contrib?: unknown }[];
};
type RawEntity = { path: string; months: RawMonth[] };

function readBundle(root: string) {
	const paths = jsonFiles(root);
	const unknown: string[] = [];
	const failures: string[] = [];
	const groups: GroupFile[] = [];
	const companies: CompanyFile[] = [];
	const evidenceIds: string[] = [];
	const rawEntities: RawEntity[] = [];
	let manifest: Manifest | null = null;
	let portfolio: Portfolio | null = null;
	let alerts: AlertsFile | null = null;
	let receiptParsed = false;

	for (const path of paths) {
		const kind = kindOf(path);
		if (!kind) {
			unknown.push(path);
			continue;
		}
		try {
			const data: unknown = JSON.parse(readFileSync(join(root, path), 'utf-8'));
			const name = path.slice(path.lastIndexOf('/') + 1, -'.json'.length);
			if (kind === 'group' || kind === 'company') {
				const months = (data as { months?: unknown }).months;
				rawEntities.push({ path, months: Array.isArray(months) ? (months as RawMonth[]) : [] });
			}
			if (kind === 'manifest') manifest = parseBundleFile(kind, data);
			else if (kind === 'portfolio') portfolio = parseBundleFile(kind, data);
			else if (kind === 'alerts') alerts = parseBundleFile(kind, data);
			else if (kind === 'receipt') receiptParsed = Boolean(parseBundleFile(kind, data));
			else if (kind === 'group') {
				const group = parseBundleFile(kind, data);
				if (group.id !== name)
					failures.push(`${path}: id ${group.id} does not match the file name`);
				groups.push(group);
			} else if (kind === 'company') {
				const company = parseBundleFile(kind, data);
				if (company.id !== name) failures.push(`${path}: id ${company.id} does not match`);
				companies.push(company);
			} else if (kind === 'evidence') {
				const evidence = parseBundleFile(kind, data);
				if (evidence.entity_id !== name) failures.push(`${path}: entity_id does not match`);
				evidenceIds.push(evidence.entity_id);
			} else {
				// single files without an entity key (invoices_due, ...)
				parseBundleFile(kind, data);
			}
		} catch (reason) {
			const detail = reason instanceof Error ? reason.message.slice(0, 300) : String(reason);
			failures.push(`${path}: ${detail}`);
		}
	}
	return {
		paths,
		unknown,
		failures,
		groups,
		companies,
		evidenceIds,
		rawEntities,
		manifest,
		portfolio,
		alerts,
		receiptParsed
	};
}

/** The waterfall recomputed step by step, exactly as the screen accumulates it; NaN when malformed. */
function waterfallEnd(entry: RawMonth): number {
	let running = Number(entry.base);
	for (const pillar of entry.pillars ?? []) running += Number(pillar.contrib);
	running -= Number(entry.penalty);
	running -= Number(entry.cap?.amount);
	return running;
}

function bandOf(manifest: Manifest, shown: number): string {
	const sorted = manifest.bands.toSorted((a, b) => a.min - b.min);
	let match = sorted[0].key;
	for (const band of sorted) if (shown >= band.min) match = band.key;
	return match;
}

describe.each(bundleRoots())('bundle integrity · $name', ({ root }) => {
	const bundle = readBundle(root);
	const entities: Entity[] = [...bundle.groups, ...bundle.companies];
	const byId = new Map(entities.map((entity) => [entity.id, entity]));

	it('parses every JSON file of the bundle against the contract', () => {
		expect(bundle.paths.length).toBeGreaterThan(0);
		expect(bundle.unknown, 'files the contract does not know').toEqual([]);
		expect(bundle.failures, 'files that break the contract').toEqual([]);
		expect(bundle.manifest).not.toBeNull();
		expect(bundle.portfolio).not.toBeNull();
		expect(bundle.alerts).not.toBeNull();
		expect(bundle.receiptParsed).toBe(true);
		expect(bundle.manifest?.counts.groups).toBe(bundle.groups.length);
		expect(bundle.manifest?.counts.alerts).toBe(bundle.alerts?.alerts.length);
		expect(bundle.portfolio?.groups.map((group) => group.id).toSorted()).toEqual(
			bundle.groups.map((group) => group.id).toSorted()
		);
	});

	it('ships companies/ complete or not at all', () => {
		const members = bundle.groups.flatMap((group) => group.companies.map((item) => item.id));
		expect(bundle.manifest?.counts.companies).toBe(members.length);
		if (bundle.companies.length === 0) return;
		expect(bundle.companies.map((company) => company.id).toSorted()).toEqual(members.toSorted());
		for (const company of bundle.companies) {
			const group = bundle.groups.find((item) => item.id === company.group_id);
			expect(
				group?.companies.some((item) => item.id === company.id),
				company.id
			).toBe(true);
		}
	});

	// Read from the raw JSON, so the identity is asserted on its own and not through zod.
	it('keeps the integer waterfall identity for every entity-month', () => {
		let checked = 0;
		const broken: string[] = [];
		for (const entity of bundle.rawEntities) {
			for (const entry of entity.months) {
				checked += 1;
				const where = `${entity.path} ${String(entry.month)}`;
				const pillars = entry.pillars ?? [];
				const parts = [
					entry.base,
					entry.penalty,
					entry.cap?.amount,
					entry.shown,
					...pillars.map((pillar) => pillar.contrib)
				];
				if (!parts.every(Number.isInteger)) broken.push(`${where}: not integer tenths`);
				if (waterfallEnd(entry) !== entry.shown) {
					broken.push(
						`${where}: waterfall ends at ${waterfallEnd(entry)}, shown is ${entry.shown}`
					);
				}
				if (pillars.map((pillar) => pillar.key).join() !== PILLAR_KEYS.join()) {
					broken.push(`${where}: pillars out of contract order`);
				}
			}
		}
		expect(checked).toBeGreaterThan(0);
		expect(checked).toBeGreaterThanOrEqual(
			entities.reduce((sum, item) => sum + item.months.length, 0)
		);
		expect(broken).toEqual([]);
	});

	it('gives an unavailable pillar no weight, no contribution and a gate that says why', () => {
		const broken: string[] = [];
		const unexplained = new Set<string>();
		for (const entity of entities) {
			for (const entry of entity.months) {
				for (const pillar of entry.pillars) {
					if (pillar.score !== null) continue;
					if (pillar.w_eff !== 0 || pillar.contrib !== 0 || pillar.gates.length === 0) {
						broken.push(`${entity.id} ${entry.month} ${pillar.key}`);
					}
					for (const gate of pillar.gates) {
						if (!bundle.manifest?.glossary.gates[gate]) unexplained.add(gate);
					}
				}
			}
		}
		expect(broken).toEqual([]);
		expect([...unexplained], 'gates without a Spanish text in manifest.glossary').toEqual([]);
	});

	it('derives the band from the score on screen and explains every abstention', () => {
		const manifest = bundle.manifest;
		expect(manifest).not.toBeNull();
		if (!manifest) return;
		const broken: string[] = [];
		for (const entity of entities) {
			for (const entry of entity.months) {
				if (bandOf(manifest, entry.shown) !== entry.band) {
					broken.push(`${entity.id} ${entry.month}: band ${entry.band} for ${entry.shown}`);
				}
				if (entry.abstain && !manifest.glossary.reasons[entry.abstain.reason]) {
					broken.push(`${entity.id} ${entry.month}: reason ${entry.abstain.reason} has no text`);
				}
				if (entry.abstain && entry.verdict.available) {
					broken.push(`${entity.id} ${entry.month}: abstains and still gives a verdict`);
				}
			}
		}
		expect(broken).toEqual([]);
	});

	it('projects group files into the portfolio, alert counts included', () => {
		const portfolio = bundle.portfolio;
		const alerts = bundle.alerts?.alerts ?? [];
		expect(portfolio).not.toBeNull();
		if (!portfolio) return;
		expect(portfolio.months).toEqual(bundle.manifest?.months);
		const broken: string[] = [];
		for (const row of portfolio.groups) {
			const group = bundle.groups.find((item) => item.id === row.id);
			const months = new Map(group?.months.map((entry) => [entry.month, entry]));
			portfolio.months.forEach((month, index) => {
				const entry = months.get(month);
				if ((entry?.shown ?? null) !== row.shown[index]) broken.push(`${row.id} ${month}: shown`);
				if ((entry?.band ?? null) !== row.band[index]) broken.push(`${row.id} ${month}: band`);
				if ((entry ? entry.abstain !== null : null) !== row.abstained[index]) {
					broken.push(`${row.id} ${month}: abstained`);
				}
				const dated = alerts.filter((alert) => alert.group_id === row.id && alert.month === month);
				const fired = dated.filter((alert) => alert.state === 'fired').length;
				if (fired !== row.alerts_fired[index]) broken.push(`${row.id} ${month}: alerts_fired`);
				if (dated.length - fired !== row.alerts_muted[index]) {
					broken.push(`${row.id} ${month}: alerts_muted`);
				}
			});
		}
		expect(broken).toEqual([]);
	});

	it('only mutes an alert inside a perimeter-change window or in an abstained month', () => {
		const alerts = bundle.alerts?.alerts ?? [];
		const muted = alerts.filter((alert) => alert.suppressed_by !== null);
		const broken: string[] = [];
		const inWindow = (alert: Alert): boolean => {
			const pause = alert.suppressed_by;
			if (!pause) return false;
			return alert.month >= pause.since && (pause.until === null || alert.month <= pause.until);
		};
		const perimeterMonths = (id: string): string[] =>
			(byId.get(id)?.months ?? [])
				.filter((entry) => entry.perimeter_changed)
				.map((entry) => entry.month);

		for (const alert of muted) {
			const pause = alert.suppressed_by;
			if (!pause) continue;
			if (!inWindow(alert)) broken.push(`${alert.id}: dated outside its own window`);
			if (!bundle.manifest?.glossary.reasons[pause.reason]) {
				broken.push(`${alert.id}: reason ${pause.reason} has no text`);
			}
			const entity = byId.get(alert.entity_id);
			// Without companies/ a company alert can only be checked through its group.
			if (!entity && alert.entity_kind === 'company' && bundle.companies.length === 0) continue;
			const entry = entity?.months.find((item) => item.month === alert.month);
			const abstainedMonth = Boolean(entry?.abstain);
			// The perimeter of a company changes with its group, so either file may carry the mark.
			const perimeterWindow = [alert.entity_id, alert.group_id].some((id) =>
				perimeterMonths(id).some((month) => month >= pause.since && month <= alert.month)
			);
			if (!abstainedMonth && !perimeterWindow) {
				broken.push(`${alert.id}: neither a perimeter window nor an abstained month`);
			}
			if (alert.state === 'abstained' && !abstainedMonth) {
				broken.push(`${alert.id}: state abstained, but the entity-month gives a verdict`);
			}
		}
		// A window is set exactly when the alert did not fire.
		for (const alert of alerts) {
			if ((alert.state === 'fired') !== (alert.suppressed_by === null)) {
				broken.push(`${alert.id}: state ${alert.state} does not match its window`);
			}
		}
		expect(broken).toEqual([]);
	});

	it('keeps the alerts of each entity file in step with alerts.json', () => {
		const alerts = bundle.alerts?.alerts ?? [];
		const inbox = new Map(alerts.map((alert) => [alert.id, alert]));
		const broken: string[] = [];
		for (const entity of entities) {
			// The milestones of an entity page and the inbox must tell the same story.
			const ids = (list: Alert[]) =>
				list
					.filter((alert) => alert.entity_id === entity.id)
					.map((alert) => alert.id)
					.toSorted()
					.join();
			if (ids(entity.alerts) !== ids(alerts)) {
				broken.push(`${entity.id}: its own alerts differ from alerts.json`);
			}
			for (const alert of entity.alerts) {
				const listed = inbox.get(alert.id);
				if (!listed) broken.push(`${alert.id}: in ${entity.id} but not in alerts.json`);
				else if (listed.state !== alert.state || listed.shown !== alert.shown) {
					broken.push(`${alert.id}: state or score differ between ${entity.id} and alerts.json`);
				}
			}
		}
		expect(broken).toEqual([]);
		for (const id of bundle.evidenceIds) {
			// Evidence may be partial, but never about an entity the bundle does not describe.
			const known =
				byId.has(id) ||
				bundle.groups.some((group) => group.companies.some((company) => company.id === id));
			expect(known, `evidence/${id}.json`).toBe(true);
		}
	});
});
