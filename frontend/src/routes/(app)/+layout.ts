import { loadManifest } from '$lib/xray/bundle.js';
import type { LayoutLoad } from './$types';

// The app is a static SPA: every number comes from the export bundle under
// /data/v1, read in the browser. Nothing renders on a server.
// A BundleError thrown by any load reaches +error.svelte through hooks.client.ts.
export const ssr = false;
export const prerender = false;

export const load: LayoutLoad = async ({ fetch }) => ({ manifest: await loadManifest(fetch) });
