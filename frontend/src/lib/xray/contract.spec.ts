import { readdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
	BUNDLE_FILES,
	entityMonthSchema,
	identityGap,
	parseBundleFile,
	type CompanyFile,
	type EntityMonth,
	type GroupFile
} from './contract';

// Synthetic, test-only bundle; the app never serves it.
const root = fileURLToPath(new URL('../../../e2e/fixtures/bundle/v1/', import.meta.url));

function read(path: string): unknown {
	return JSON.parse(readFileSync(`${root}${path}`, 'utf-8'));
}

function ids(folder: string): string[] {
	return readdirSync(`${root}${folder}`)
		.filter((name) => name.endsWith('.json'))
		.map((name) => name.slice(0, -'.json'.length))
		.sort();
}

const manifest = parseBundleFile('manifest', read(BUNDLE_FILES.manifest));
const portfolio = parseBundleFile('portfolio', read(BUNDLE_FILES.portfolio));
const alerts = parseBundleFile('alerts', read(BUNDLE_FILES.alerts)).alerts;
const receipt = parseBundleFile('receipt', read(BUNDLE_FILES.receipt));
const groups: GroupFile[] = ids('groups').map((id) =>
	parseBundleFile('group', read(BUNDLE_FILES.group(id)))
);
const companies: CompanyFile[] = ids('companies').map((id) =>
	parseBundleFile('company', read(BUNDLE_FILES.company(id)))
);
const entityMonths: EntityMonth[] = [...groups, ...companies].flatMap((entity) => entity.months);

describe('export bundle contract', () => {
	it('parses every file of the fixture bundle', () => {
		for (const id of ids('evidence')) {
			const evidence = parseBundleFile('evidence', read(BUNDLE_FILES.evidence(id)));
			expect(evidence.entity_id).toBe(id);
		}
		expect(manifest.counts).toEqual({
			groups: groups.length,
			companies: companies.length,
			alerts: alerts.length
		});
		expect(portfolio.months).toEqual(manifest.months);
		expect(receipt.params_hash).toBe(manifest.params_hash);
	});

	it('keeps the waterfall exact in integer tenths', () => {
		expect(entityMonths.length).toBeGreaterThan(0);
		for (const entry of entityMonths) {
			expect(identityGap(entry)).toBe(0);
		}
		const broken = { ...entityMonths[0], shown: entityMonths[0].shown + 1 };
		expect(entityMonthSchema.safeParse(broken).success).toBe(false);
	});

	it('projects every group file into the portfolio', () => {
		expect(portfolio.groups.map((group) => group.id)).toEqual(groups.map((group) => group.id));
		for (const group of groups) {
			const row = portfolio.groups.find((item) => item.id === group.id);
			const byMonth = new Map(group.months.map((entry) => [entry.month, entry]));
			expect(row?.shown).toEqual(manifest.months.map((month) => byMonth.get(month)?.shown ?? null));
			expect(row?.band).toEqual(manifest.months.map((month) => byMonth.get(month)?.band ?? null));
		}
	});

	it('keeps suppressed alerts inside a perimeter window', () => {
		const suppressed = alerts.filter((alert) => alert.suppressed_by?.reason === 'perimeter_change');
		expect(suppressed.length).toBeGreaterThan(0);
		for (const alert of suppressed) {
			const since = alert.suppressed_by?.since ?? '';
			const until = alert.suppressed_by?.until ?? alert.month;
			const entity = [...groups, ...companies].find((item) => item.id === alert.entity_id);
			const change = entity?.months.find((entry) => entry.month === since);
			expect(change?.perimeter_changed).toBe(true);
			expect(alert.month >= since && alert.month <= until).toBe(true);
		}
	});

	it('covers the states the screens must handle', () => {
		const last = groups.map((group) => group.months[group.months.length - 1]);
		expect(last.some((entry) => entry.abstain !== null)).toBe(true);
		expect(alerts.map((alert) => alert.state)).toEqual(
			expect.arrayContaining(['fired', 'suppressed', 'abstained'])
		);
		expect(entityMonths.some((entry) => entry.penalty > 0)).toBe(true);
		expect(entityMonths.some((entry) => entry.cap.amount > 0)).toBe(true);
		expect(entityMonths.some((entry) => entry.verdict.direction === 'perimeter_shift')).toBe(true);
		expect(entityMonths.some((entry) => entry.verdict.nature === 'bump')).toBe(true);
		const swept = companies.filter((company) => company.inherits_liquidity);
		expect(swept.length).toBeGreaterThan(0);
		for (const company of swept) {
			const liquidity = company.months[0].pillars[0];
			expect(liquidity.gates).toContain('inherited_from_group');
		}
	});
});
