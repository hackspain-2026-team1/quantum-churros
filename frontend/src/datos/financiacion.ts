export type RolFinanciacion = 'consultant' | 'company' | 'provider';

export interface IdentidadFinanciacion {
	user_id: string;
	organization_id: string;
	role: RolFinanciacion;
}

export interface CasoFinanciacion {
	id: string;
	funding_need_id: string;
	consultant_org_id: string;
	company_org_id: string;
	objective: string;
	amount: number;
	term_months: number;
	product_types_json: string[];
	status: 'in_review' | 'authorized' | 'published' | 'shortlisted' | 'accepted' | 'closed';
	version: number;
	created_at: string;
	updated_at: string;
}

export interface NecesidadFinanciacion {
	id: string;
	entity_id: string;
	score: number;
	previous_score: number;
	amount_low: number;
	amount_high: number;
	needed_from: string;
	needed_to: string;
	confidence: number;
	source_month: string;
	detected_since: string | null;
	trajectory: string;
	trajectory_nature: string | null;
	model_version: string;
	params_hash: string;
	dataset_hash: string;
	explanation_method: string;
	drivers_json: Record<string, string>;
	profile_json: { country?: string; industry?: string; size?: string };
}

export interface OportunidadFinanciacion {
	id: string;
	case_id: string;
	public_code: string;
	teaser_json: Record<string, unknown>;
	status: string;
}

export interface OfertaFinanciacion {
	id: string;
	opportunity_id: string;
	provider_org_id: string;
	amount: number;
	annual_rate: number;
	term_months: number;
	opening_fee: number;
	guarantee: string;
	terms_json: Record<string, unknown>;
	status: string;
	valid_until: string;
}

export interface ExpedienteFinanciacion {
	case: CasoFinanciacion;
	need: NecesidadFinanciacion;
	opportunity: OportunidadFinanciacion | null;
	offers: { offer: OfertaFinanciacion; provider_name: string }[];
	company_name: string;
	consultant_name: string;
}

export interface OportunidadProveedor {
	opportunity: OportunidadFinanciacion;
	case_version: number;
	teaser: Record<string, unknown>;
	own_offer: OfertaFinanciacion | null;
}

export interface EspacioFinanciacion {
	role: RolFinanciacion;
	cases: ExpedienteFinanciacion[];
	opportunities: OportunidadProveedor[];
}

export interface IdentidadesDemo {
	scenario: string;
	identities: Record<string, IdentidadFinanciacion>;
}

const RAIZ = '/api/v1/financing';

export function cabecerasFinanciacion(identity: IdentidadFinanciacion, version?: number): Record<string, string> {
	return {
		'Content-Type': 'application/json',
		'X-Rumbo-User': identity.user_id,
		'X-Rumbo-Organization': identity.organization_id,
		'X-Rumbo-Role': identity.role,
		...(version === undefined ? {} : { 'If-Match': String(version) }),
	};
}

async function peticion<T>(ruta: string, init: RequestInit = {}, identity?: IdentidadFinanciacion, version?: number): Promise<T> {
	const response = await fetch(`${RAIZ}${ruta}`, { ...init, headers: { ...(identity ? cabecerasFinanciacion(identity, version) : {}), ...(init.headers ?? {}) } });
	if (!response.ok) {
		const body = await response.json().catch(() => ({ detail: response.statusText }));
		const detail = typeof body.detail === 'string' ? body.detail : body.detail?.message ?? response.statusText;
		throw new Error(detail);
	}
	return response.json() as Promise<T>;
}

export const financiacionApi = {
	identidades: () => peticion<IdentidadesDemo>('/demo/identities'),
	iniciar: () => peticion<{ case_id: string; identities: Record<string, IdentidadFinanciacion> }>('/demo/FIN-024/start', { method: 'POST' }),
	espacio: (identity: IdentidadFinanciacion) => peticion<EspacioFinanciacion>('/workspace', {}, identity),
	autorizar: (identity: IdentidadFinanciacion, caso: CasoFinanciacion, scope: Record<string, unknown>) => peticion<CasoFinanciacion>(`/cases/${caso.id}/authorize`, { method: 'POST', body: JSON.stringify({ scope, expires_at: dentroDe(30) }) }, identity, caso.version),
	publicar: (identity: IdentidadFinanciacion, caso: CasoFinanciacion) => peticion<OportunidadFinanciacion>(`/cases/${caso.id}/publish`, { method: 'POST' }, identity, caso.version),
	oferta: (identity: IdentidadFinanciacion, oportunidadId: string, values: { amount: number; annual_rate: number; term_months: number; opening_fee: number; guarantee: string }) => peticion<OfertaFinanciacion>(`/opportunities/${oportunidadId}/offers`, { method: 'POST', body: JSON.stringify({ ...values, terms: { amortization: 'monthly', kind: 'indicative' }, valid_until: dentroDe(21) }) }, identity),
	preseleccionar: (identity: IdentidadFinanciacion, caso: CasoFinanciacion, providerOrgId: string) => peticion<CasoFinanciacion>(`/cases/${caso.id}/shortlist`, { method: 'POST', body: JSON.stringify({ provider_org_ids: [providerOrgId], scope: { identity: true, operations: 'aggregated', documents: ['KYC'] }, expires_at: dentroDe(14) }) }, identity, caso.version),
	aceptar: (identity: IdentidadFinanciacion, caso: CasoFinanciacion, offerId: string) => peticion<CasoFinanciacion>(`/cases/${caso.id}/accept`, { method: 'POST', body: JSON.stringify({ offer_id: offerId }) }, identity, caso.version),
	revocar: (identity: IdentidadFinanciacion, caso: CasoFinanciacion) => peticion<CasoFinanciacion>(`/cases/${caso.id}/revoke`, { method: 'POST' }, identity, caso.version),
};

function dentroDe(days: number): string {
	return new Date(Date.now() + days * 86_400_000).toISOString();
}
