import { expect, test, type APIRequestContext } from '@playwright/test';
import { humanizeMonths } from '../src/lib/format';

// Group and company pages. Every expectation is derived from the bundle being
// served: no literal scores, names or counts live in this file.

type Pillar = { key: string; score: number | null; contrib: number; gates: string[] };
type EntityMonth = {
	month: string;
	shown: number;
	base: number;
	penalty: number;
	cap: { amount: number };
	pillars: Pillar[];
	abstain: { reason: string; unlock: string } | null;
};
type GroupFile = {
	id: string;
	profile: { key: string; label: string }[];
	months: EntityMonth[];
	companies: { id: string; truth: string | null; inherits_liquidity: boolean }[];
};
type Portfolio = { groups: { id: string }[] };
type Evidence = { months: { month: string; rows: unknown[] }[] };

const score = (tenths: number) =>
	new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(
		tenths / 10
	);

async function bundle<T>(request: APIRequestContext, path: string): Promise<T> {
	const response = await request.get(`/data/v1/${path}`);
	expect(response.ok(), `${path} is served`).toBe(true);
	return (await response.json()) as T;
}

async function groups(request: APIRequestContext): Promise<GroupFile[]> {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	return Promise.all(
		portfolio.groups
			.slice(0, 12)
			.map((group) => bundle<GroupFile>(request, `groups/${group.id}.json`))
	);
}

test('group page: profile, verdict and the month-over-month list come from the bundle', async ({
	page,
	request
}) => {
	const group = (await groups(request)).find((item) => item.months.length > 1);
	test.skip(!group, 'no group with two observed months in this bundle');
	if (!group) return;
	const entry = group.months[group.months.length - 1];
	const previous = group.months[group.months.length - 2];

	await page.goto(`/group/${group.id}?m=${entry.month}`);
	await expect(page.locator('[data-testid="profile-card"] [data-profile]')).toHaveCount(
		group.profile.length
	);
	await expect(page.getByTestId('verdict-headline')).toBeVisible();
	await expect(page.getByTestId('verdict-position')).toContainText(score(entry.shown));
	await expect(page.getByTestId('confidence-parts').locator('dt')).toHaveCount(3);

	const changes = await page
		.locator('[data-testid="score-changes"] [data-change]')
		.evaluateAll((items) => items.map((item) => Number((item as HTMLElement).dataset.tenths)));
	expect(changes.reduce((sum, value) => sum + value, 0)).toBe(entry.shown - previous.shown);
	await expect(page.getByTestId('changes-check')).toContainText('exactamente');
	await expect(page.getByTestId('waterfall-check')).toContainText(score(entry.shown));
});

test('group page: evidence is read on demand for the selected month', async ({ page, request }) => {
	const group = (await groups(request))[0];
	const entry = group.months[group.months.length - 1];
	const response = await request.get(`/data/v1/evidence/${group.id}.json`);
	test.skip(!response.ok(), 'this bundle ships without evidence for the first group');
	const evidence = (await response.json()) as Evidence;
	const rows = evidence.months.find((item) => item.month === entry.month)?.rows ?? [];

	await page.goto(`/group/${group.id}?m=${entry.month}`);
	await expect(
		page.locator('[data-testid="evidence-table"] [data-evidence-row]:visible')
	).toHaveCount(rows.length);
});

test('company page: inherited liquidity is announced and links back to the group', async ({
	page,
	request
}) => {
	const all = await groups(request);
	const group = all.find((item) => item.companies.some((company) => company.inherits_liquidity));
	test.skip(!group, 'no company inherits the group liquidity in this bundle');
	if (!group) return;
	const company = group.companies.find((item) => item.inherits_liquidity)!;
	const entry = group.months[group.months.length - 1];

	await page.goto(`/group/${group.id}/company/${company.id}?m=${entry.month}`);
	await expect(page.getByRole('heading', { name: company.id })).toBeVisible();
	const banner = page.getByTestId('treasury-truth');
	await expect(banner).toBeVisible();
	// Engine sentences quote months as YYYY-MM; the screen spells them out.
	if (company.truth) await expect(banner).toContainText(humanizeMonths(company.truth));
	await expect(page.getByTestId('company-drilldown')).toHaveCount(0);

	await page.getByTestId('back-to-group').click();
	await expect(page.getByRole('heading', { name: group.id })).toBeVisible();
	await expect(page).toHaveURL(new RegExp(`/group/${group.id}(\\?|$)`));
});

test('an abstained month shows the reason and what unlocks it', async ({ page, request }) => {
	const all = await groups(request);
	const group = all.find((item) => item.months.some((entry) => entry.abstain));
	test.skip(!group, 'no abstained group-month in this bundle');
	if (!group) return;
	const entry = group.months.findLast((item) => item.abstain)!;

	await page.goto(`/group/${group.id}?m=${entry.month}`);
	const panel = page.locator(
		`[data-testid="verdict-card"] [data-abstain="${entry.abstain!.reason}"]`
	);
	await expect(panel).toContainText(humanizeMonths(entry.abstain!.unlock));
	await expect(page.locator('[data-step="shown"]')).toContainText(score(entry.shown));
});
