import { expect, test, type APIRequestContext } from '@playwright/test';

// Smoke of the dashboard (five tabs) and the entity page against whatever bundle is being
// served. Every expected score, id and count is read from /data/v1 during the test.

type Manifest = { months: string[] };
type Portfolio = { months: string[]; groups: { id: string; shown: (number | null)[] }[] };
type Action = { id: string; uplift_tenths: number; new_score_tenths: number };
type EntityMonth = {
	month: string;
	shown: number;
	actions?: Action[];
	actions_combined?: { new_score: number; uplift: number } | null;
};
type GroupFile = { id: string; months: EntityMonth[]; companies: { id: string }[] };

const score = (tenths: number) =>
	new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(
		tenths / 10
	);

async function bundle<T>(request: APIRequestContext, path: string): Promise<T> {
	const response = await request.get(`/data/v1/${path}`);
	expect(response.ok(), `${path} is served`).toBe(true);
	return (await response.json()) as T;
}

/** Groups observed in the last month, lowest score first: the order of the radar. */
function radarOrder(portfolio: Portfolio) {
	const last = portfolio.months.length - 1;
	return portfolio.groups
		.filter((group) => group.shown[last] !== null)
		.sort((a, b) => a.shown[last]! - b.shown[last]! || a.id.localeCompare(b.id));
}

// Copy retired with the demo seeds; none of it may reach a screen again.
const RETIRED_COPY = /COMP_0680|Velasco|4,1 meses|Proyectado: |API conectada|SHAP|CatBoost/i;

test('the five tabs and the entity page render without crashes or retired copy', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const first = radarOrder(portfolio)[0];
	const routes = [
		'/',
		'/?tab=diagnostico',
		'/?tab=escenario',
		'/?tab=acciones',
		'/?tab=tecnico',
		'/?tab=tecnico&section=alertas',
		'/?tab=tecnico&section=recibo',
		`/group/${first.id}`
	];
	const crashes: string[] = [];
	page.on('pageerror', (error) => crashes.push(error.message));
	for (const route of routes) {
		await page.goto(route);
		await expect(page.locator('h1:visible').first(), route).toBeVisible();
		await expect(page.locator('body'), route).not.toContainText(RETIRED_COPY);
	}
	expect(crashes).toEqual([]);
});

test('radar lists the groups of the bundle and opens the entity page', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const last = portfolio.months.length - 1;
	const first = radarOrder(portfolio)[0];

	await page.goto('/');
	await expect(page.getByRole('heading', { level: 1, name: 'Radar financiero' })).toBeVisible();
	const row = page.locator(`[data-testid="radar-table"] [data-group="${first.id}"]`);
	await expect(row.getByTestId('radar-score')).toHaveText(score(first.shown[last]!));

	await row.getByRole('link', { name: `Abrir ${first.id}` }).click();
	await expect(page).toHaveURL(new RegExp(`/group/${first.id}`));
	await expect(page.getByRole('heading', { level: 1, name: first.id })).toBeVisible();
	await expect(page.getByTestId('entity-hero')).toBeVisible();
});

test('the month selector moves the radar to another close', async ({ page, request }) => {
	const manifest = await bundle<Manifest>(request, 'manifest.json');
	test.skip(manifest.months.length < 2, 'single-month bundle');
	await page.goto('/');
	await page.getByRole('button', { name: 'Mes anterior' }).click();
	await expect(page).toHaveURL(new RegExp(`m=${manifest.months.at(-2)}`));
});

test('entity page: actions come from the bundle, or an honest empty state', async ({
	page,
	request
}) => {
	const portfolio = await bundle<Portfolio>(request, 'portfolio.json');
	const groups = await Promise.all(
		radarOrder(portfolio)
			.slice(0, 12)
			.map((group) => bundle<GroupFile>(request, `groups/${group.id}.json`))
	);
	const month = portfolio.months.at(-1)!;
	const entryOf = (group: GroupFile) => group.months.find((entry) => entry.month === month);
	const withActions = groups.find((group) => (entryOf(group)?.actions?.length ?? 0) > 0);
	const group = withActions ?? groups.find((item) => entryOf(item))!;
	const entry = entryOf(group)!;

	await page.goto(`/group/${group.id}?m=${month}`);
	const section = page.getByTestId('entity-actions');
	if (withActions) {
		const actions = entry.actions!;
		const target =
			entry.actions_combined?.new_score ??
			Math.max(...actions.map((action) => action.new_score_tenths));
		await expect(section.getByTestId('actions-headline')).toHaveText(
			`Si sigues estas acciones tu score pasaría de ${score(entry.shown)} a ${score(target)}`
		);
		await expect(section.locator('[data-action]')).toHaveCount(actions.length);
		await expect(page.getByTestId('chart-target')).toContainText(score(target));

		// Local done / pending state.
		const card = section.locator('[data-action]').first();
		await card.getByRole('button', { name: 'Marcar hecha' }).click();
		await expect(card).toContainText('Hecha');

		// Scenario: one action shows the engine's own figure for it.
		const best = [...actions].sort((a, b) => b.uplift_tenths - a.uplift_tenths)[0];
		await page.goto(`/?tab=escenario&focus=${group.id}&m=${month}`);
		await page.locator('[data-testid="scenario-levers"] label').first().click();
		await expect(page.getByLabel(/^Estimado:/)).toContainText(score(best.new_score_tenths));
	} else {
		await expect(section).toContainText('Sin acciones calculadas para este mes');
		await expect(page.getByTestId('chart-target')).toHaveCount(0);
	}
});

test('technical tab keeps the waterfall, the evidence, the alerts and the receipt', async ({
	page
}) => {
	await page.goto('/?tab=tecnico');
	await expect(page.getByTestId('contribution-waterfall')).toBeVisible();
	await expect(page.getByTestId('waterfall-check')).toBeVisible();
	await expect(page.getByTestId('confidence-parts')).toBeVisible();
	await page.getByRole('tab', { name: 'Alertas' }).click();
	await expect(page.getByRole('heading', { name: 'Alertas', exact: true })).toBeVisible();
	await page.getByRole('tab', { name: 'Recibo' }).click();
	await expect(page.getByTestId('receipt-verdict')).toBeVisible();
});
