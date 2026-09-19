import { error, redirect } from '@sveltejs/kit';
import { base } from '$app/paths';
import { loadCompany } from '$lib/xray/bundle.js';
import type { PageLoad } from './$types';

// Short link to a company: the canonical page hangs from its group, and the group
// is only known from companies/<id>.json, a folder the bundle may ship without.
export const load: PageLoad = async ({ fetch, params, url }) => {
	const company = await loadCompany(fetch, params.id);
	if (!company) {
		error(
			404,
			`Este bundle no incluye el detalle de ${params.id}: abre la empresa desde la página de su grupo.`
		);
	}
	redirect(307, `${base}/group/${company.group_id}/company/${company.id}${url.search}`);
};
