// The month under analysis, shared by every screen. The store is the source of
// truth; the URL mirrors it as ?m=YYYY-MM (omitted for the latest close) so a
// reload or a shared link lands on the same month.

import { browser } from '$app/environment';
import { replaceState } from '$app/navigation';
import { base } from '$app/paths';
import { page } from '$app/state';
import { MONTH_PARAM, isMonth, resolveMonth } from './month.js';

const URL_WRITE_DELAY_MS = 200;

class MonthStore {
	#months = $state.raw<string[]>([]);
	#selected = $state<string | null>(null);
	#timer: ReturnType<typeof setTimeout> | null = null;

	/** Months of the bundle (manifest.months), ascending. */
	get months(): string[] {
		return this.#months;
	}

	/** Latest monthly close of the bundle; '' before init. */
	get latest(): string {
		return this.#months.at(-1) ?? '';
	}

	/** Selected month, always one of `months`; '' before init. */
	get month(): string {
		return this.#selected ?? this.latest;
	}

	get index(): number {
		return Math.max(0, this.#months.indexOf(this.month));
	}

	get isLatest(): boolean {
		return this.month === this.latest;
	}

	/** Called by the app layout with manifest.months. */
	init(months: string[]): void {
		this.#months = months;
		if (this.#selected !== null) {
			this.#selected = months.includes(this.#selected) ? this.#selected : null;
		}
	}

	/** Select a month (clamped to the bundle range) and mirror it in the URL. */
	select(month: string): void {
		const resolved = resolveMonth(this.#months, month);
		this.#selected = resolved === this.latest ? null : resolved;
		this.syncUrl();
	}

	selectIndex(index: number): void {
		const month = this.#months[Math.min(Math.max(0, index), this.#months.length - 1)];
		if (month) this.select(month);
	}

	step(delta: number): void {
		this.selectIndex(this.index + delta);
	}

	/** Adopt ?m= from the address bar (or a given URL) when it names a valid month. */
	readUrl(url?: URL): void {
		if (!url && !browser) return;
		const wanted = (url ?? new URL(window.location.href)).searchParams.get(MONTH_PARAM);
		if (!isMonth(wanted)) return;
		const resolved = resolveMonth(this.#months, wanted);
		this.#selected = resolved === this.latest ? null : resolved;
	}

	/** Write the selection to the address bar; debounced, never adds history entries. */
	syncUrl(): void {
		if (!browser) return;
		if (this.#timer) clearTimeout(this.#timer);
		this.#timer = setTimeout(() => {
			this.#timer = null;
			const url = new URL(window.location.href);
			const current = url.searchParams.get(MONTH_PARAM);
			const wanted = this.isLatest ? null : this.month;
			if (current === wanted) return;
			if (wanted) url.searchParams.set(MONTH_PARAM, wanted);
			else url.searchParams.delete(MONTH_PARAM);
			try {
				replaceState(url, page.state);
			} catch {
				// Router not started yet, or the browser throttled history updates.
			}
		}, URL_WRITE_DELAY_MS);
	}

	/**
	 * Internal link that keeps the selected month: href('/group/G1') -> '/group/G1?m=2026-03'.
	 * Pass `month` to point at another month, e.g. the month of an alert.
	 */
	href(path: string, month?: string): string {
		const target = `${base}${path}`;
		const wanted = month ? resolveMonth(this.#months, month) : this.month;
		// An explicit month is always written, so the link also leads back to the latest close.
		if (!wanted || (!month && wanted === this.latest)) return target;
		return `${target}${target.includes('?') ? '&' : '?'}${MONTH_PARAM}=${wanted}`;
	}
}

export const monthStore = new MonthStore();
