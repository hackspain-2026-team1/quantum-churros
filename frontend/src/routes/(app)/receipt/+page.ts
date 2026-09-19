import { loadReceipt } from '$lib/xray/bundle.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({ receipt: await loadReceipt(fetch) });
