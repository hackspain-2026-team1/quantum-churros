// Local triage of the alerts inbox: 'seen' or 'dismissed' per alert id.
// It is a note of the analyst, kept in localStorage of this browser only:
// it never leaves the device and never changes what the engine exported.

import { browser } from '$app/environment';

export type Triage = 'seen' | 'dismissed';

export const TRIAGE_STORAGE_KEY = 'xray:alert-triage:v1';

const isTriage = (value: unknown): value is Triage => value === 'seen' || value === 'dismissed';

function parse(raw: string | null): Record<string, Triage> {
	if (!raw) return {};
	try {
		const data: unknown = JSON.parse(raw);
		if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
		return Object.fromEntries(
			Object.entries(data as Record<string, unknown>).filter((entry): entry is [string, Triage] =>
				isTriage(entry[1])
			)
		);
	} catch {
		return {};
	}
}

class AlertTriage {
	#marks = $state.raw<Record<string, Triage>>({});
	#ready = false;

	/** Read the saved marks once and follow changes made in other tabs. */
	init(): void {
		if (!browser || this.#ready) return;
		this.#ready = true;
		try {
			this.#marks = parse(window.localStorage.getItem(TRIAGE_STORAGE_KEY));
		} catch {
			// Storage blocked (private mode, policy): triage still works for this visit.
		}
		window.addEventListener('storage', (event) => {
			if (event.key === null || event.key === TRIAGE_STORAGE_KEY) {
				this.#marks = parse(event.key === null ? null : event.newValue);
			}
		});
	}

	get(id: string): Triage | null {
		return this.#marks[id] ?? null;
	}

	/** Set or clear (null) the mark of one alert. */
	set(id: string, value: Triage | null): void {
		const next = { ...this.#marks };
		if (value === null) delete next[id];
		else next[id] = value;
		this.#marks = next;
		this.#save();
	}

	/** How many of `ids` carry `value`. */
	count(ids: readonly string[], value: Triage): number {
		return ids.reduce((total, id) => total + (this.#marks[id] === value ? 1 : 0), 0);
	}

	/** How many of `ids` have no mark yet. */
	pending(ids: readonly string[]): number {
		return ids.reduce((total, id) => total + (this.#marks[id] ? 0 : 1), 0);
	}

	/** Forget the marks of `ids`. */
	reset(ids: readonly string[]): void {
		const next = { ...this.#marks };
		for (const id of ids) delete next[id];
		this.#marks = next;
		this.#save();
	}

	#save(): void {
		if (!browser) return;
		try {
			if (Object.keys(this.#marks).length === 0) window.localStorage.removeItem(TRIAGE_STORAGE_KEY);
			else window.localStorage.setItem(TRIAGE_STORAGE_KEY, JSON.stringify(this.#marks));
		} catch {
			// Quota or blocked storage: keep the marks in memory.
		}
	}
}

export const alertTriage = new AlertTriage();
