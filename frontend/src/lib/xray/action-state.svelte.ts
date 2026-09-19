// Done / pending state of the recommended actions. It lives in this browser only
// (localStorage): the bundle is read-only and there is no backend to write to.

import { browser } from '$app/environment';
import { SvelteSet } from 'svelte/reactivity';

const STORAGE_KEY = 'xray.actions.done.v1';

class ActionState {
	#done = new SvelteSet<string>();

	constructor() {
		if (!browser) return;
		try {
			const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
			if (Array.isArray(saved)) for (const key of saved) this.#done.add(String(key));
		} catch {
			// Unreadable storage: start with everything pending.
		}
	}

	key(entityId: string, actionId: string): string {
		return `${entityId}:${actionId}`;
	}

	isDone(entityId: string, actionId: string): boolean {
		return this.#done.has(this.key(entityId, actionId));
	}

	toggle(entityId: string, actionId: string): void {
		const key = this.key(entityId, actionId);
		if (this.#done.has(key)) this.#done.delete(key);
		else this.#done.add(key);
		if (!browser) return;
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify([...this.#done]));
		} catch {
			// Storage full or blocked: the state still holds for this session.
		}
	}
}

export const actionState = new ActionState();
