import { expect, test, type APIRequestContext } from '@playwright/test';

// Alerts inbox. Every expectation is derived from the bundle being served:
// no literal scores, names or counts live in this file.

type Alert = {
	id: string;
	entity_id: string;
	month: string;
	state: 'fired' | 'suppressed' | 'abstained';
	title: string;
	suppressed_by: { reason: string; since: string; until: string | null } | null;
};
type Manifest = { months: string[]; glossary: { reasons: Record<string, string> } };

const count = (value: number) => new Intl.NumberFormat('es-ES').format(value);

async function bundle<T>(request: APIRequestContext, path: string): Promise<T> {
	const response = await request.get(`/data/v1/${path}`);
	expect(response.ok(), `${path} is served`).toBe(true);
	return (await response.json()) as T;
}

test('an alert the engine did not fire says why and for how long', async ({ page, request }) => {
	const { alerts } = await bundle<{ alerts: Alert[] }>(request, 'alerts.json');
	const manifest = await bundle<Manifest>(request, 'manifest.json');
	const muted = alerts.filter((alert) => alert.suppressed_by !== null);
	test.skip(muted.length === 0, 'the bundle has no suppressed or abstained alert');

	for (const state of ['suppressed', 'abstained'] as const) {
		const alert = muted.find((candidate) => candidate.state === state);
		if (!alert?.suppressed_by) continue;
		await page.goto(`/alerts?estado=${state}&q=${alert.entity_id}`);
		const card = page.locator(`[data-alert="${alert.id}"]`);
		await expect(card).toContainText(alert.title);
		const reason = card.locator('[data-muted-reason]');
		await expect(reason).toHaveAttribute('data-muted-reason', alert.suppressed_by.reason);
		await expect(reason).toContainText(
			manifest.glossary.reasons[alert.suppressed_by.reason] ?? alert.suppressed_by.reason
		);
		await expect(reason).toContainText('Ventana');
	}
});

test('the month of the portfolio scopes the inbox and the timeline moves it', async ({
	page,
	request
}) => {
	const { alerts } = await bundle<{ alerts: Alert[] }>(request, 'alerts.json');
	test.skip(alerts.length === 0, 'the bundle has no alerts');
	const month = alerts[alerts.length - 1].month;
	const other = alerts.find((alert) => alert.month !== month)?.month;
	const inMonth = (wanted: string, state: Alert['state']) =>
		alerts.filter((alert) => alert.month === wanted && alert.state === state).length;

	await page.goto(`/alerts?ver=mes&m=${month}`);
	for (const state of ['fired', 'suppressed', 'abstained'] as const) {
		await expect(page.locator(`[data-alert-tab="${state}"]`)).toHaveAttribute(
			'data-count',
			String(inMonth(month, state))
		);
	}

	if (other) {
		const column = page.locator(`[data-testid="alerts-timeline"] button[data-month="${other}"]`);
		await column.click();
		await expect(column).toHaveAttribute('aria-pressed', 'true');
		await expect(page.locator('[data-alert-tab="fired"]')).toHaveAttribute(
			'data-count',
			String(inMonth(other, 'fired'))
		);
		await expect(page).toHaveURL(new RegExp(`[?&]m=${other}`));
	}
});

test('triage is kept in this browser only', async ({ page, request }) => {
	const { alerts } = await bundle<{ alerts: Alert[] }>(request, 'alerts.json');
	const fired = alerts.filter((alert) => alert.state === 'fired').length;
	test.skip(fired === 0, 'the bundle has no fired alert');

	await page.goto('/alerts');
	const pending = page.locator('[data-kpi="alerts-pending"] [data-kpi-value]');
	await expect(pending).toHaveText(count(fired));

	await page.getByRole('button', { name: 'Descartar' }).first().click();
	await expect(pending).toHaveText(count(fired - 1));
	// The count of the engine does not move: triage is a note, not data.
	await expect(page.locator('[data-alert-tab="fired"]')).toHaveAttribute(
		'data-count',
		String(fired)
	);

	await page.reload();
	await expect(pending).toHaveText(count(fired - 1));
	await page.getByRole('button', { name: /Ver descartadas/ }).click();
	await expect(page.locator('[data-alert][data-triage="dismissed"]')).toHaveCount(1);
	await page.getByRole('button', { name: 'Restaurar' }).click();
	await expect(pending).toHaveText(count(fired));
});
