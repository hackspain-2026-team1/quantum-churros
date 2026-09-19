import { loadPortfolio } from '$lib/xray/bundle.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({ portfolio: await loadPortfolio(fetch) });
