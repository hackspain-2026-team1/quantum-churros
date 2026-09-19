// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
import type { Manifest } from '$lib/xray/contract';

declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		interface PageData {
			/** Set by the (app) layout load; missing only on the root error page. */
			manifest?: Manifest;
		}
		// interface PageState {}
		// interface Platform {}
	}
}

export {};
