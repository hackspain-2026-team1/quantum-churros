import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { humanizeMonths } from '../src/lib/format';

// Smoke of the whole demo against whatever bundle is being served (the synthetic
// fixture locally, the engine export on the public URL). Every expected score,
// id, count and sentence is read from /data/v1 during the test: nothing on screen
// is compared with a literal written in this file.

type Manifest = { engine_version: string; bundle_id: string; months: string[] };
type Portfolio = {
	months: string[];
	groups: {
		id: string;
		shown: (number | null)[];
		abstained: (boolean | null)[];
		alerts_fired: number[];
		alerts_muted: number[];
	}[];
};
type EntityMonth = {
	month: string;
	shown: number;
	base: number;
	penalty: number;
	cap: { amount: number };
	pillars: { key: string; contrib: number }[];
};
type GroupFile = {
	id: string;
	months: EntityMonth[];
	companies: { id: string; truth: string | null; shown: (number | null)[] }[];
};
type AlertsFile = { alerts: { id: string; state: string; shown: number }[] };

const score = (tenths: number) =>
	new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(
		tenths / 10
	);
const count = (value: number) => new Intl.NumberFormat('es-ES').format(value);

async function bundle<T>(request: APIRequestContext, path: string): Promise<T> {
	const response = await request.get(`/data/v1/${path}`);
	expect(response.ok(), `${path} is served`).toBe(true);
	return (await response.json()) as T;
}

/** First, middle and last index of a list: enough to prove a column follows the slider. */
function sample(length: number): number[] {
	return [...new Set([0, Math.floor((length - 1) / 2), length - 1])].filter((index) => index >= 0);
}

/** Visible score cell of a row: the table and the mobile list both carry data-score-tenths. */
const scoreCell = (page: Page, row: string) => page.locator(`${row} [data-score-tenths]:visible`);

// Copy retired with the demo seeds; none of it may reach a screen again.
const RETIRED_COPY =
	/COMP_0680|Velasco|4,1 meses|Proyectado|API conectada|SHAP|CatBoost|tiempo real/i;

test('every screen answers, renders in Spanish and carries no retired copy', async ({
	page,
	request
}) => {
	const manifest = await bundle<Manifest>(request, 'manifest.json');
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const group = await bundle<GroupFile>(request, `groups/${portfolio.groups[0].id}.json`);
	const company = group.companies[0];
	const routes = [
		'/',
		'/alerts',
		'/receipt',
		`/group/${group.id}`,
		...(company ? [`/group/${group.id}/company/${company.id}`] : [])
	];

	const crashes: string[] = [];
	const brokenAssets: string[] = [];
	page.on('pageerror', (error) => crashes.push(error.message));
	page.on('response', (response) => {
		if (response.status() >= 400 && response.url().includes('/_app/')) {
			brokenAssets.push(`${response.status()} ${response.url()}`);
		}
	});

	for (const route of routes) {
		const response = await page.goto(route);
		expect(response?.status(), `${route} answers`).toBe(200);
		await expect(page.locator('html')).toHaveAttribute('lang', 'es');
		await expect(page.locator('h1'), `${route} has one main heading`).toHaveCount(1);
		await expect(page.locator('h1')).toBeVisible();
		await expect(page).toHaveTitle(/Embat X-Ray$/);
		// The footer names the bundle behind every number of the screen.
		await expect(page.locator('footer')).toContainText(manifest.engine_version);
		await expect(page.locator('footer')).toContainText(manifest.bundle_id.slice(0, 10));
		expect(await page.locator('body').innerText(), `${route} copy`).not.toMatch(RETIRED_COPY);
	}
	expect(crashes, 'uncaught errors').toEqual([]);
	expect(brokenAssets, 'application assets').toEqual([]);
});

test('portfolio shows the scores of the bundle and follows the month slider', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const last = portfolio.months.length - 1;
	const rows = portfolio.groups.slice(0, 8);

	// The same table, read at the first, a middle and the latest close.
	for (const index of sample(portfolio.months.length)) {
		await page.goto(`/?m=${portfolio.months[index]}`);
		await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
		await expect(page.locator('tr[data-group]')).toHaveCount(portfolio.groups.length);
		for (const group of rows) {
			const cell = scoreCell(page, `tr[data-group="${group.id}"]`);
			const shown = group.shown[index];
			if (shown === null) await expect(cell).toHaveCount(0);
			else {
				await expect(cell).toHaveText(score(shown));
				await expect(cell).toHaveAttribute('data-score-tenths', String(shown));
			}
		}
		// Header KPIs are counts over portfolio.json at the selected month.
		const kpi = (name: string) => page.locator(`[data-kpi="${name}"] [data-kpi-value]`);
		await expect(kpi('scored')).toHaveText(
			count(portfolio.groups.filter((group) => group.shown[index] !== null).length)
		);
		await expect(kpi('abstained')).toHaveText(
			count(portfolio.groups.filter((group) => group.abstained[index] === true).length)
		);
		await expect(kpi('alerts')).toHaveText(
			count(portfolio.groups.reduce((total, group) => total + group.alerts_fired[index], 0))
		);
	}

	if (last > 0) {
		await page.goto('/');
		await page.getByRole('slider').focus();
		await page.keyboard.press('ArrowLeft');
		await expect(page).toHaveURL(new RegExp(`[?&]m=${portfolio.months[last - 1]}`));
		const group = portfolio.groups[0];
		const previous = group.shown[last - 1];
		const cell = scoreCell(page, `tr[data-group="${group.id}"]`);
		if (previous === null) await expect(cell).toHaveCount(0);
		else await expect(cell).toHaveText(score(previous));
	}
});

test('group page explains the score to the tenth and drills into a company', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const id = portfolio.groups[0].id;
	const group = await bundle<GroupFile>(request, `groups/${id}.json`);

	for (const index of sample(group.months.length)) {
		const entry = group.months[index];
		await page.goto(`/group/${id}?m=${entry.month}`);
		await expect(page.getByRole('heading', { level: 1, name: id })).toBeVisible();

		// Each step on screen is the integer of the file, and the steps add up to the score.
		const steps = await page
			.locator('[data-testid="contribution-waterfall"] [data-step]')
			.evaluateAll((items) =>
				items.map((item) => ({
					key: (item as HTMLElement).dataset.step ?? '',
					tenths: Number((item as HTMLElement).dataset.tenths)
				}))
			);
		const step = (key: string) => steps.find((item) => item.key === key)?.tenths;
		expect(step('base')).toBe(entry.base);
		expect(step('shown')).toBe(entry.shown);
		for (const pillar of entry.pillars) expect(step(pillar.key)).toBe(pillar.contrib);
		const moves = steps.filter((item) => item.key !== 'base' && item.key !== 'shown');
		expect(moves.reduce((sum, item) => sum + item.tenths, entry.base)).toBe(entry.shown);
		expect(moves.reduce((sum, item) => sum + item.tenths, 0)).toBe(
			entry.pillars.reduce((sum, pillar) => sum + pillar.contrib, 0) -
				entry.penalty -
				entry.cap.amount
		);
		await expect(page.locator('[data-step="shown"]')).toContainText(score(entry.shown));
		await expect(page.getByTestId('verdict-position')).toContainText(score(entry.shown));

		// The companies table repeats group.companies[].shown for that month.
		for (const company of group.companies.slice(0, 6)) {
			const cell = scoreCell(page, `tr[data-company="${company.id}"]`);
			const shown = company.shown[index];
			if (shown === null) await expect(cell).toHaveCount(0);
			else await expect(cell).toHaveText(score(shown));
		}
	}

	const company = group.companies[0];
	test.skip(!company, 'the first group lists no companies in this bundle');
	await page.locator(`tr[data-company="${company.id}"] a`).first().click();
	await expect(page.getByRole('heading', { level: 1, name: company.id })).toBeVisible();
	await expect(page).toHaveURL(new RegExp(`/group/${id}/company/${company.id}(\\?|$)`));
	if (company.truth) {
		await expect(page.getByTestId('treasury-truth')).toContainText(humanizeMonths(company.truth));
	}
});

test('the 3-month change reads the same in the portfolio and in the verdict', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const last = portfolio.months.length - 1;

	await page.goto(`/?m=${portfolio.months[last]}`);
	await expect(page.locator('tr[data-group]')).toHaveCount(portfolio.groups.length);
	const moved = page.locator('tr[data-group]').filter({
		has: page.locator('[data-delta-tenths]:not([data-delta-tenths=""])')
	});
	test.skip((await moved.count()) === 0, 'no group with a 3-month change at the latest close');
	const row = moved.first();
	const id = await row.getAttribute('data-group');
	const inPortfolio = await row.locator('[data-delta-tenths]').getAttribute('data-delta-tenths');

	await page.goto(`/group/${id}?m=${portfolio.months[last]}`);
	const card = page.getByTestId('verdict-card');
	await expect(card).toBeVisible();
	// Only comparable when the verdict looks back to the same month as the portfolio column.
	const comparedTo = await card.getAttribute('data-compared-to');
	test.skip(comparedTo !== portfolio.months[last - 3], 'the verdict compares another month');
	await expect(card).toHaveAttribute('data-delta-tenths', String(inPortfolio));
});

test('a short company link lands on the company inside its group', async ({ page, request }) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const group = await bundle<GroupFile>(request, `groups/${portfolio.groups[0].id}.json`);
	const company = group.companies[0];
	const detail = company ? await request.get(`/data/v1/companies/${company.id}.json`) : null;
	test.skip(!detail?.ok(), 'this bundle ships without the companies folder');

	await page.goto(`/company/${company.id}`);
	await expect(page).toHaveURL(new RegExp(`/group/${group.id}/company/${company.id}(\\?|$)`));
	await expect(page.getByRole('heading', { level: 1, name: company.id })).toBeVisible();
	const entry = ((await detail!.json()) as { months: EntityMonth[] }).months.at(-1)!;
	await page.goto(`/company/${company.id}?m=${entry.month}`);
	await expect(page.locator('[data-step="shown"]')).toContainText(score(entry.shown));
});

test('alerts inbox and receipt list what the bundle holds', async ({ page, request }) => {
	const alerts = await bundle<AlertsFile>(request, 'alerts.json');
	const receipt = await bundle<{ checks: unknown[]; signals: unknown[] }>(request, 'receipt.json');

	await page.goto('/alerts');
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	// One tab per state; each tab counts and lists the alerts of alerts.json in that state.
	for (const state of ['fired', 'suppressed', 'abstained']) {
		const expected = alerts.alerts.filter((alert) => alert.state === state);
		const tab = page.locator(`[data-alert-tab="${state}"]`);
		await expect(tab).toHaveAttribute('data-count', String(expected.length));
		await tab.click();
		await expect(page.locator(`[data-alert]:not([data-state="${state}"])`)).toHaveCount(0);
		const cards = page.locator(`[data-alert][data-state="${state}"]`);
		if (expected.length === 0) {
			await expect(cards).toHaveCount(0);
			continue;
		}
		// A long history is paged: the list says how many cards it renders per step.
		const pageSize = Number(
			await page.locator(`[data-alert-list="${state}"]`).getAttribute('data-page-size')
		);
		const rendered = Math.min(expected.length, pageSize);
		await expect(cards).toHaveCount(rendered);
		// Whatever the engine did not fire says why.
		await expect(cards.locator('[data-muted-reason]')).toHaveCount(
			state === 'fired' ? 0 : rendered
		);
		// The score on a card is the score of the alert in alerts.json.
		const first = cards.first();
		const id = await first.getAttribute('data-alert');
		const alert = expected.find((item) => item.id === id);
		expect(alert, `${id} comes from alerts.json`).toBeDefined();
		await expect(first.locator('[data-score-tenths]')).toHaveText(score(alert!.shown));
	}

	await page
		.getByRole('navigation', { name: 'Principal' })
		.getByRole('link', { name: 'Recibo' })
		.click();
	await expect(page).toHaveURL(/\/receipt(\?|$)/);
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	await expect(page.locator('[data-check]')).toHaveCount(receipt.checks.length);
	await expect(page.locator('[data-signal]')).toHaveCount(receipt.signals.length);
});

test('an address outside the app says so in Spanish and leads back to the portfolio', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const missing = `${portfolio.groups[0].id}-no-existe`;

	await page.goto('/pantalla-que-no-existe');
	await expect(page.getByRole('status')).toBeVisible();
	await expect(page.getByRole('status')).not.toContainText('Not Found');
	await page.getByRole('link').first().click();
	await expect(page.locator('tr[data-group]')).toHaveCount(portfolio.groups.length);

	// A group the bundle does not hold fails inside the shell and names the missing file.
	await page.goto(`/group/${missing}`);
	await expect(page.getByRole('status')).toContainText(`groups/${missing}.json`);
	await expect(page.getByRole('navigation', { name: 'Principal' })).toBeVisible();
});

test('no link of the app leads to an error screen', async ({ page, baseURL }) => {
	// Bounded crawl from the portfolio: on a large bundle it still visits every kind of screen.
	const LIMIT = 30;
	const origin = new URL(baseURL ?? '').origin;
	const queue = ['/'];
	const seen = new Set(queue);
	const broken: string[] = [];
	let visited = 0;

	while (queue.length > 0 && visited < LIMIT) {
		const path = queue.shift()!;
		visited += 1;
		await page.goto(path);
		await expect(page.locator('h1, [role="status"]').first()).toBeVisible();
		const title = await page.title();
		if ((await page.locator('h1').count()) === 0) broken.push(`${path} -> ${title}`);
		const links = await page
			.locator('a[href]')
			.evaluateAll((items) => items.map((item) => (item as HTMLAnchorElement).href));
		// One link per kind of screen and entity is enough; month variants of a page are the same page.
		for (const link of links) {
			const url = new URL(link);
			if (url.origin !== origin || url.pathname.startsWith('/data/')) continue;
			const key = url.pathname;
			if (seen.has(key)) continue;
			seen.add(key);
			queue.push(`${url.pathname}${url.search}`);
		}
	}
	expect(visited).toBeGreaterThan(1);
	expect(broken, 'links that end on an error screen').toEqual([]);
});
