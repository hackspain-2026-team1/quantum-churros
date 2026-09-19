import { loadGroup, loadInvoicesDue } from '$lib/xray/bundle.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => ({
	group: await loadGroup(fetch, params.id),
	invoicesDue: await loadInvoicesDue(fetch)
});
