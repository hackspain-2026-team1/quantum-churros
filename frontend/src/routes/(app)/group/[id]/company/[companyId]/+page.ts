import { error } from '@sveltejs/kit';
import { loadCompany, loadGroup, loadInvoicesDue } from '$lib/xray/bundle.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, params }) => {
	const [group, company, invoicesDue] = await Promise.all([
		loadGroup(fetch, params.id),
		// null when the bundle ships without companies/: the page falls back to group.companies[].
		loadCompany(fetch, params.companyId),
		loadInvoicesDue(fetch)
	]);
	const summary = group.companies.find((item) => item.id === params.companyId);
	if (!summary) error(404, `La empresa ${params.companyId} no pertenece al grupo ${params.id}.`);
	return { group, company, summary, invoicesDue };
};
