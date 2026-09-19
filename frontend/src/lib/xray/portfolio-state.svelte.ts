// View state of the portfolio table (search, filters, order). It lives in a
// module so it survives opening a group and coming back; it is never persisted.

import {
	DEFAULT_SORT_DIR,
	type BandFilter,
	type DirectionFilter,
	type PortfolioFilters,
	type SortDir,
	type SortKey
} from './portfolio.js';

type PortfolioViewState = PortfolioFilters & { sortKey: SortKey; sortDir: SortDir };

const initial = (): PortfolioViewState => ({
	query: '',
	band: 'all',
	direction: 'all',
	movers: false,
	sortKey: 'shown',
	sortDir: DEFAULT_SORT_DIR.shown
});

class PortfolioView {
	#state = $state<PortfolioViewState>(initial());

	get query(): string {
		return this.#state.query;
	}
	set query(value: string) {
		this.#state.query = value;
	}

	get band(): BandFilter {
		return this.#state.band;
	}
	set band(value: BandFilter) {
		this.#state.band = value;
	}

	get direction(): DirectionFilter {
		return this.#state.direction;
	}
	set direction(value: DirectionFilter) {
		this.#state.direction = value;
	}

	get movers(): boolean {
		return this.#state.movers;
	}
	set movers(value: boolean) {
		this.#state.movers = value;
	}

	/** Order applied to the table: the movers ranking overrides the column order. */
	get sortKey(): SortKey {
		return this.#state.movers ? 'move' : this.#state.sortKey;
	}

	get sortDir(): SortDir {
		return this.#state.movers ? DEFAULT_SORT_DIR.move : this.#state.sortDir;
	}

	get filters(): PortfolioFilters {
		const { query, band, direction, movers } = this.#state;
		return { query, band, direction, movers };
	}

	get filtered(): boolean {
		const { query, band, direction, movers } = this.#state;
		return query.trim() !== '' || band !== 'all' || direction !== 'all' || movers;
	}

	/** Click on a column: first its natural direction, then the opposite one. */
	sortBy(key: SortKey): void {
		const same = !this.#state.movers && this.#state.sortKey === key;
		this.#state.sortDir = same
			? this.#state.sortDir === 'asc'
				? 'desc'
				: 'asc'
			: DEFAULT_SORT_DIR[key];
		this.#state.sortKey = key;
		this.#state.movers = false;
	}

	setSort(key: SortKey, dir: SortDir): void {
		this.#state.sortKey = key;
		this.#state.sortDir = dir;
		this.#state.movers = false;
	}

	toggleBand(band: BandFilter): void {
		this.#state.band = this.#state.band === band ? 'all' : band;
	}

	toggleDirection(direction: DirectionFilter): void {
		this.#state.direction = this.#state.direction === direction ? 'all' : direction;
	}

	clearFilters(): void {
		const { sortKey, sortDir } = this.#state;
		this.#state = { ...initial(), sortKey, sortDir };
	}
}

export const portfolioView = new PortfolioView();
