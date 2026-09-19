import { expect, test, type APIRequestContext } from '@playwright/test';

// Portfolio screen. Every expectation is derived from the bundle being served:
// no literal scores, names or counts live in this file.

type Portfolio = {
	months: string[];
	groups: {
		id: string;
		shown: (number | null)[];
		band: (string | null)[];
		direction: (string | null)[];
		abstained: (boolean | null)[];
	}[];
};

const count = (value: number) => new Intl.NumberFormat('es-ES').format(value);
const delta = (tenths: number) =>
	new Intl.NumberFormat('es-ES', {
		minimumFractionDigits: 1,
		maximumFractionDigits: 1,
		signDisplay: 'exceptZero'
	}).format(tenths / 10);

async function portfolioFile(request: APIRequestContext): Promise<Portfolio> {
	const response = await request.get('/data/v1/portfolio.json');
	expect(response.ok(), 'portfolio.json is served').toBe(true);
	return (await response.json()) as Portfolio;
}

test('band counts come from the bundle and filter the table', async ({ page, request }) => {
	const portfolio = await portfolioFile(request);
	const last = portfolio.months.length - 1;
	const bands = new Map<string, number>();
	for (const group of portfolio.groups) {
		const band = group.band[last];
		if (band) bands.set(band, (bands.get(band) ?? 0) + 1);
	}

	await page.goto('/');
	for (const [band, expected] of bands) {
		await expect(page.locator(`[data-band-count="${band}"]`)).toContainText(count(expected));
	}

	const [band, expected] = [...bands.entries()][0];
	await page.locator(`[data-band-count="${band}"]`).click();
	await expect(page.locator('tr[data-group]')).toHaveCount(expected);
	await expect(page.locator(`tr[data-group] [data-band]:not([data-band="${band}"])`)).toHaveCount(
		0
	);

	await page.getByRole('button', { name: 'Limpiar filtros' }).first().click();
	await expect(page.locator('tr[data-group]')).toHaveCount(portfolio.groups.length);
});

test('direction tiles count verdicts, never abstained groups', async ({ page, request }) => {
	const portfolio = await portfolioFile(request);
	const last = portfolio.months.length - 1;
	const judged = (direction: string) =>
		portfolio.groups.filter(
			(group) =>
				group.shown[last] !== null &&
				group.abstained[last] !== true &&
				group.direction[last] === direction
		).length;

	await page.goto('/');
	for (const [kpi, direction] of [
		['deteriorating', 'deteriorating'],
		['improving', 'improving'],
		['perimeter', 'perimeter_shift']
	]) {
		await expect(page.locator(`[data-kpi="${kpi}"] [data-kpi-value]`)).toHaveText(
			count(judged(direction))
		);
	}

	await page.locator('[data-kpi="deteriorating"]').click();
	await expect(page.locator('tr[data-group]')).toHaveCount(judged('deteriorating'));
});

test('movers rank groups by the size of their 3-month change', async ({ page, request }) => {
	const portfolio = await portfolioFile(request);
	const last = portfolio.months.length - 1;
	const horizon = 3;
	test.skip(last < horizon, 'the window is shorter than the horizon of the change');

	const movers = portfolio.groups
		.flatMap((group) => {
			const now = group.shown[last];
			const before = group.shown[last - horizon];
			return now === null || before === null ? [] : [{ id: group.id, change: now - before }];
		})
		.sort((a, b) => Math.abs(b.change) - Math.abs(a.change) || a.id.localeCompare(b.id));
	test.skip(movers.length === 0, 'no group has both months');

	await page.goto('/');
	await page.getByRole('button', { name: 'Mayores movimientos' }).click();
	const rows = page.locator('tr[data-group]');
	await expect(rows).toHaveCount(movers.length);
	await expect(rows.first()).toHaveAttribute('data-group', movers[0].id);
	const cell = rows.first().locator('[data-delta-tenths]');
	await expect(cell).toHaveAttribute('data-delta-tenths', String(movers[0].change));
	await expect(cell).toContainText(delta(movers[0].change));
});

test('search narrows the table and a row opens its group on the same month', async ({
	page,
	request
}) => {
	const portfolio = await portfolioFile(request);
	const last = portfolio.months.length - 1;
	const month = portfolio.months[Math.max(0, last - 1)];
	const target = portfolio.groups[portfolio.groups.length - 1];

	await page.goto(`/?m=${month}`);
	await page.getByRole('searchbox').fill(target.id.toLowerCase());
	await expect(page.locator('tr[data-group]')).toHaveCount(
		portfolio.groups.filter((group) => group.id.toLowerCase().includes(target.id.toLowerCase()))
			.length
	);

	await page.locator(`tr[data-group="${target.id}"] a`).first().click();
	await expect(page).toHaveURL(new RegExp(`/group/${target.id}(\\?|$)`));
	if (last > 0) await expect(page).toHaveURL(new RegExp(`[?&]m=${month}`));
	await expect(page.getByRole('heading', { name: target.id })).toBeVisible();
});

test('the slider leaves a month that came in the URL', async ({ page, request }) => {
	const portfolio = await portfolioFile(request);
	const last = portfolio.months.length - 1;
	test.skip(last < 2, 'the window has fewer than three months');
	const group = portfolio.groups[0];

	await page.goto(`/?m=${portfolio.months[last - 1]}`);
	await expect(page.getByTestId('shell-month')).toBeVisible();
	await page.getByRole('slider').focus();
	await page.keyboard.press('ArrowLeft');
	await expect(page).toHaveURL(new RegExp(`[?&]m=${portfolio.months[last - 2]}`));
	const cell = page.locator(`tr[data-group="${group.id}"] [data-score-tenths]`);
	const shown = group.shown[last - 2];
	if (shown === null) await expect(cell).toHaveCount(0);
	else await expect(cell).toHaveAttribute('data-score-tenths', String(shown));
});
