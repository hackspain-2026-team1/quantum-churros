import { beforeAll, describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import { formatNumber, formatPercent, formatUnitValue } from '$lib/format.js';
import manifestJson from '../../../e2e/fixtures/bundle/v1/manifest.json';
import receiptJson from '../../../e2e/fixtures/bundle/v1/receipt.json';
import { CHECK_STATUSES, parseBundleFile, type Receipt } from './contract.js';
import { monthStore } from './month-store.svelte.js';
import ReceiptView from './receipt-view.svelte';

// Synthetic, test-only bundle. Every expectation below is derived from it: no literal
// counts, scores or names, so the spec keeps holding when the fixture changes.
const manifest = parseBundleFile('manifest', manifestJson);
const receipt = parseBundleFile('receipt', receiptJson);

const all = (selector: string) => [...document.querySelectorAll<HTMLElement>(selector)];
const one = (selector: string) => {
	const found = document.querySelector<HTMLElement>(selector);
	if (!found) throw new Error(`missing ${selector}`);
	return found;
};

describe('receipt view', () => {
	// The app layout does this with the manifest it loads.
	beforeAll(() => monthStore.init(manifest.months));

	it('names the page and shows the fingerprint of the run', async () => {
		const screen = render(ReceiptView, { receipt, manifest });

		await expect
			.element(screen.getByRole('heading', { name: 'Recibo', exact: true }))
			.toBeVisible();
		await expect.element(screen.getByText('Por qué puedes fiarte de este número')).toBeVisible();
		const fingerprint = one('[data-testid="receipt-fingerprint"]');
		for (const value of [receipt.engine_version, receipt.params_hash, receipt.dataset_hash]) {
			expect(fingerprint.textContent).toContain(value);
		}
		expect(fingerprint.dataset.sameRun).toBe('true');
		expect(document.body.textContent).not.toContain('El recibo no corresponde a este bundle');
	});

	it('renders one card per check with its status and every metric', async () => {
		const screen = render(ReceiptView, { receipt, manifest });
		await expect.element(screen.getByTestId('receipt-verdict')).toBeVisible();

		expect(all('[data-check]').map((card) => card.dataset.check)).toEqual(
			receipt.checks.map((check) => check.key)
		);
		for (const check of receipt.checks) {
			const card = one(`[data-check="${check.key}"]`);
			expect(card.dataset.status).toBe(check.status);
			expect(card.textContent).toContain(check.title);
			expect(card.textContent).toContain(check.summary);
			for (const metric of check.metrics) {
				expect(card.textContent).toContain(metric.label);
				if (typeof metric.value === 'number') {
					expect(card.textContent).toContain(formatUnitValue(metric.value, metric.unit));
				}
			}
			const bars = [...card.querySelectorAll<HTMLElement>('[data-bar]')];
			expect(bars.map((bar) => bar.dataset.bar)).toEqual(
				(check.bars ?? []).map((bar) => bar.label)
			);
		}
	});

	it('counts the checks by status and concludes from them', async () => {
		const screen = render(ReceiptView, { receipt, manifest });
		await expect.element(screen.getByTestId('receipt-verdict')).toBeVisible();

		const count = (status: string) =>
			receipt.checks.filter((check) => check.status === status).length;
		for (const status of CHECK_STATUSES) {
			expect(one(`[data-status-count="${status}"] dd`).textContent).toContain(
				formatNumber(count(status))
			);
		}
		const judged = count('pass') + count('fail');
		expect(one('[data-testid="receipt-verdict"]').textContent).toContain(formatNumber(judged));
	});

	it('flags failed checks by name', async () => {
		const failing: Receipt = {
			...receipt,
			checks: receipt.checks.map((check, index) =>
				index === 0 ? { ...check, status: 'fail' } : check
			)
		};
		const screen = render(ReceiptView, { receipt: failing, manifest });

		await expect.element(screen.getByText(/^No superadas:/)).toBeVisible();
		expect(one('[data-testid="receipt-verdict"]').textContent).toContain('no se supera');
		expect(screen.getByText(/^No superadas:/).element().textContent).toContain(
			failing.checks[0].title
		);
	});

	it('separates the signals that weigh from the ones kept at weight 0', async () => {
		const screen = render(ReceiptView, { receipt, manifest });
		await expect.element(screen.getByTestId('receipt-signals')).toBeVisible();

		expect(all('[data-signal]')).toHaveLength(receipt.signals.length);
		const unused = one('[aria-labelledby="receipt-unused-heading"]');
		const used = one('[aria-labelledby="receipt-used-heading"]');
		for (const signal of receipt.signals) {
			const home = signal.weight === 0 ? unused : used;
			const row = home.querySelector<HTMLElement>(`[data-signal="${signal.name}"]`);
			expect(row, signal.name).not.toBeNull();
			expect(row?.textContent).toContain(signal.label);
			expect(row?.textContent).toContain(signal.why);
			expect(row?.textContent).toContain(formatPercent(signal.weight, 0));
		}
	});

	it('lists every abstention with what unlocks it and a link to the entity', async () => {
		const screen = render(ReceiptView, { receipt, manifest });
		await expect.element(screen.getByTestId('receipt-abstentions')).toBeVisible();

		expect(all('[data-abstention]')).toHaveLength(receipt.abstentions.length);
		for (const item of receipt.abstentions) {
			const row = one(`[data-abstention="${item.entity_id}"]`);
			expect(row.textContent).toContain(item.unlock);
			const href = row.querySelector('a')?.getAttribute('href') ?? '';
			expect(href).toContain(`/group/${item.group_id}`);
			expect(href).toContain(`m=${item.month}`);
			const block = row.closest<HTMLElement>('[data-abstain-reason]');
			expect(block?.dataset.abstainReason).toBe(item.reason);
			expect(block?.textContent).toContain(manifest.glossary.reasons[item.reason] ?? item.reason);
		}
	});

	it('folds long abstention lists behind a button', async () => {
		const [template] = receipt.abstentions;
		const many: Receipt = {
			...receipt,
			abstentions: Array.from({ length: 9 }, (_, index) => ({
				...template,
				entity_kind: 'company' as const,
				entity_id: `COMP_T9${index}`
			}))
		};
		const screen = render(ReceiptView, { receipt: many, manifest });

		const more = screen.getByRole('button', { name: /restantes/ });
		await expect.element(more).toBeVisible();
		const folded = all('[data-abstention]').length;
		expect(folded).toBeLessThan(many.abstentions.length);
		await more.click();
		await expect.element(screen.getByRole('button', { name: 'Ver menos' })).toBeVisible();
		expect(all('[data-abstention]')).toHaveLength(many.abstentions.length);
	});

	it('says so when the receipt belongs to another run', async () => {
		const other: Receipt = { ...receipt, dataset_hash: `${receipt.dataset_hash}-other` };
		const screen = render(ReceiptView, { receipt: other, manifest });

		await expect.element(screen.getByText('El recibo no corresponde a este bundle')).toBeVisible();
		expect(one('[data-testid="receipt-fingerprint"]').dataset.sameRun).toBe('false');
	});

	it('explains an export without validation, signals at weight 0 or abstentions', async () => {
		const bare: Receipt = {
			...receipt,
			checks: [],
			abstentions: [],
			signals: receipt.signals.filter((signal) => signal.weight > 0)
		};
		const screen = render(ReceiptView, { receipt: bare, manifest });

		await expect
			.element(screen.getByText('Este bundle se exportó sin ejecutar la validación'))
			.toBeVisible();
		await expect.element(screen.getByText('Ninguna señal con peso 0')).toBeVisible();
		await expect.element(screen.getByText('Sin abstenciones')).toBeVisible();
		expect(all('[data-check]')).toHaveLength(0);
	});
});
