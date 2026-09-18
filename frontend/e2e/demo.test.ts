import { expect, test } from '@playwright/test';

test('loads API data and completes the decision flow', async ({ page }) => {
	await page.goto('/');
	await expect(page.getByRole('heading', { name: 'Radar financiero' })).toBeVisible();
	await expect(page.getByText('API conectada')).toBeVisible();

	await page.getByRole('tab', { name: 'Diagnóstico' }).first().click();
	await expect(page.getByRole('heading', { name: 'Diagnóstico explicable' })).toBeVisible();

	await page.getByRole('tab', { name: 'Escenarios' }).first().click();
	await expect(page.getByRole('heading', { name: 'Laboratorio de escenarios' })).toBeVisible();
	await expect(page.getByLabel('Proyectado: 74.5 sobre 100')).toBeVisible();
	await page.getByRole('button', { name: 'Convertir en plan' }).click();
	await expect(page.getByText('Escenario guardado como plan de acción.')).toBeVisible();
});
