// Tipos de los ficheros que lee Rumbo, tal y como los escribe el motor (contracts/xray-export-v1)
// y los procesos de datos de Rumbo (products, horizons, params). Nada de aquí se inventa: si un
// campo no está en el fichero, es opcional aquí.

import type { Banda, Confianza, Direccion, Naturaleza, Pilar, TipoAlerta } from './modelo';

export interface Manifiesto {
	schema: 'xray-export-v1';
	bundle_id: string;
	engine_version: string;
	params_hash: string;
	dataset_hash: string;
	generated_at: string;
	months: string[];
	counts: { groups: number; companies: number; alerts: number };
	pillars: { key: Pilar; label: string; weight: number; baseline: number }[];
	bands: { key: Banda; label: string; min: number }[];
	glossary: { gates: Record<string, string>; flags: Record<string, string>; caps: Record<string, string>; reasons: Record<string, string> };
}

export interface PilarMesM { key: Pilar; score: number | null; w_eff: number; contrib: number; gates: string[]; note: string | null }

export interface AccionM {
	id: string;
	pillar: Pilar;
	title: string;
	detail: string;
	current: number;
	target: number;
	unit: 'días' | 'ratio' | '%';
	uplift_tenths: number;
	new_score_tenths: number;
	effort: 'bajo' | 'medio' | 'alto';
}

export interface VeredictoM {
	available: boolean;
	reason: string | null;
	direction: Direccion;
	nature: Naturaleza | null;
	shock_pending?: boolean;
	shock_month?: string | null;
	delta3: number | null;
	sigma: number | null;
	delta3_sigma: number | null;
	compared_to: string | null;
	pillars_moved: string[];
	persistence_months: number;
	detected_since: string | null;
}

export interface MesM {
	month: string;
	shown: number;
	band: Banda;
	level: number;
	base: number;
	pillars: PilarMesM[];
	penalty: number;
	cap: { amount: number; rule: string | null; fired: string[] };
	conf: { value: number; label: Confianza; history: number; coverage: number; quality: number };
	branch: string;
	flags: string[];
	feed_live: boolean;
	months_observed: number;
	perimeter_changed: boolean;
	verdict: VeredictoM;
	abstain: { reason: string; unlock: string } | null;
	actions?: AccionM[];
	actions_combined?: { new_score: number; uplift: number } | null;
}

export interface AtributoM { key: string; label: string; value: string | null; evidence: string | null; coverage: number }
export interface SerieM { key: string; label: string; unit: string; values: (number | null)[] }

export interface AlertaM {
	id: string;
	entity_kind: 'group' | 'company';
	entity_id: string;
	group_id: string;
	month: string;
	kind: TipoAlerta;
	state: 'fired' | 'suppressed' | 'abstained';
	title: string;
	detail: string;
	shown: number;
	suppressed_by: { reason: string; since: string; until: string | null } | null;
}

export interface ContextoM {
	industry: { slug: string; label: string; confidence: number; reason: string } | null;
	benchmark: { text: string; source: string } | null;
}

export interface EmpresaResumenM {
	id: string;
	role: string;
	treasury_class: string | null;
	truth: string | null;
	inherits_liquidity: boolean;
	first_month: string;
	shown: (number | null)[];
	band: (Banda | null)[];
}

interface EntidadBase {
	schema: string;
	kind: 'group' | 'company';
	id: string;
	first_month: string;
	profile: AtributoM[];
	context: ContextoM;
	months: MesM[];
	series: SerieM[];
	alerts: AlertaM[];
}
export interface GrupoM extends EntidadBase { kind: 'group'; companies: EmpresaResumenM[] }
export interface EmpresaM extends EntidadBase {
	kind: 'company';
	group_id: string;
	role: string;
	treasury_class: string | null;
	truth: string | null;
	inherits_liquidity: boolean;
}
export type EntidadM = GrupoM | EmpresaM;

export interface FilaEvidenciaM { pillar: Pilar | null; label: string; value: number | string | null; unit: string; period: string; source_file: string; n_rows: number | null }
export interface EvidenciaM { entity_kind: 'group' | 'company'; entity_id: string; group_id: string; months: { month: string; rows: FilaEvidenciaM[] }[] }

export interface ReciboM {
	engine_version: string;
	params_hash: string;
	dataset_hash: string;
	signals: { name: string; label: string; weight: number; why: string }[];
	abstentions: { entity_kind: string; entity_id: string; group_id: string; month: string; reason: string; unlock: string }[];
	checks: { key: string; title: string; status: 'pass' | 'fail' | 'info' | 'not_run'; summary: string; metrics: { label: string; value: number; unit: string }[]; bars?: { label: string; value: number }[] }[];
}

// ─── Productos (rumbo-products-v1) ───────────────────────────
export type ProductoId = 'linea_credito' | 'factoring' | 'confirming' | 'seguro_credito' | 'cuenta_remunerada' | 'depositos' | 'plan_pensiones';
export interface ItemProductoM { bank: string | null; label: string | null; granted: number | null; outstanding: number | null; available: number | null; usage: number | null; since: string | null; rate: number | null; rate_type: string | null; closed?: boolean; currency?: string; inconsistent?: boolean; balance?: number | null }
export interface TenenciaM {
	product: ProductoId;
	source: 'declarado' | 'movimientos';
	items: ItemProductoM[];
	evidence: { file: string; rows: number | null; first: string | null; last: string | null; amount_12m: number | null; examples: string[] } | { file: string; rows: number | null; first: string | null; last: string | null; amount_12m: number | null; examples: string[] }[];
}
export interface OtraDeudaM { type: string; type_label: string; bank: string | null; label: string | null; granted: number | null; outstanding: number | null; rate: number | null; rate_type: string | null; periods: number | null; next_payment: string | null; since: string | null; closed?: boolean }
export interface ProductosEmpresaM {
	schema: 'rumbo-products-v1';
	company_id: string;
	group_id: string;
	cut: string;
	held: TenenciaM[];
	other_debt: OtraDeudaM[];
	accounts: Record<string, number>;
	totals: Record<string, number>;
}
export interface ProductosGrupoM {
	schema: 'rumbo-products-group-v1';
	group_id: string;
	cut: string;
	companies: { id: string; held: ProductoId[]; sources: Partial<Record<ProductoId, 'declarado' | 'movimientos'>> }[];
	counts: Partial<Record<ProductoId, number>>;
	totals?: Record<string, number>;
}
export interface ProductosIndiceM {
	schema: 'rumbo-products-index-v1';
	cut: string;
	generated_at: string;
	source_files: Record<string, string>;
	rules: Record<string, { declared?: string; inferred?: string; precision_note?: string }>;
	portfolio: Record<string, { companies: number; groups: number; declared: number; inferred: number }>;
	groups: Record<string, Partial<Record<ProductoId, number>>>;
}

// ─── Horizontes (rumbo-horizons-v2): la previsión que entrena el motor (xray_engine.forecast) ──
export interface CuantilesM { p10: number[]; p25: number[]; p50: number[]; p75: number[]; p90: number[] }
export type ProbBandas = Partial<Record<Banda, number>>;
export interface CruceM { dir?: 'up' | 'down'; to: Banda; month: string; prob: number | null }
export interface EscenarioM {
	q: CuantilesM;
	bands: { h3?: ProbBandas; h6?: ProbBandas; h12?: ProbBandas };
	cross: CruceM | null;
	grains: [number, number][];
}
/** «Qué pasaría si»: extrapolaciones explícitas, solo con su mediana. */
export interface SupuestoM { q: { p50: number[] }; cross: CruceM | null; what_if: true; worst_quarter?: number }
export interface HorizonteM {
	schema: 'rumbo-horizons-v2';
	entity_id: string;
	entity_kind: 'group' | 'company';
	group_id?: string;
	cut: string;
	bundle_id: string;
	params_hash: string;
	months: string[];
	shown_at_cut: number | null;
	model?: { version: string; trained_until: string };
	scenarios: { base: EscenarioM; drift?: SupuestoM; stress?: SupuestoM } | null;
	reason_code?: string;
	actions?: (EscenarioM & { id: string; pillar: Pilar; lag_months: number; engine_new_score: number; in_bundle: boolean })[];
	combos?: { ids: string[]; new_score: number }[];
	explain_h6?: { variable: string; points: number }[];
}
/** El futuro visto desde cada corte pasado, con un modelo entrenado solo con lo anterior. */
export interface HorizontesPasadosM {
	schema: 'rumbo-horizons-pasados-v2';
	entity_id: string;
	bundle_id: string;
	cuts: Record<string, { months: string[]; shown_at_cut: number; q: CuantilesM; grains: [number, number][]; trained_until: string }>;
}
export interface ValidacionH { n: number; error_mediana: number; error_sin_cambio: number; error_media_12: number; acierta_50: number; acierta_80: number }
export interface HorizontesIndiceM {
	schema: 'rumbo-horizons-index-v2';
	cut: string;
	bundle_id: string;
	generated_at: string;
	model: { version: string; type: string; target: string; features: string[]; horizons: number[]; train_pairs: Record<string, number>; lags: Record<string, number>; what_if: Record<string, string> };
	validation: { cortes: string[]; por_horizonte: Record<string, ValidacionH>; validado_hasta: number; corte_de_referencia?: { corte: string; horizontes: number[]; n: number; error_mediana: number; error_sin_cambio: number; acierta_80: number } };
	coefficients: Record<string, Record<string, number>>;
	checks: Record<string, string>;
	past_cuts: string[];
	entities: Record<string, { kind: 'group' | 'company'; p50_h6: number | null; p_critical_h6: number | null; cross: CruceM | null; shown_at_cut: number | null }>;
}

// ─── Índice de empresas (rumbo-companies-index-v1) ──────────
export interface IndiceEmpresasM { schema: 'rumbo-companies-index-v1'; bundle_id: string; cut: string; companies: Record<string, { group: string; size: string | null; shown: number | null; band: string | null }> }

// ─── Parámetros del motor (copia verificada de params/reference_v1.json) ──
export type Tabla = [number, number][];
export interface ParametrosM {
	schema: 'rumbo-params-v1';
	sha256: string;
	verified_against_manifest: boolean;
	anchors: Record<string, Tabla>;
	liquidity: { band_anchors: Record<string, Tabla>; month_end_weight: number; intra_min_weight: number; days_per_month?: number; [k: string]: unknown };
	penalty: { lam: number; tau: number };
	caps: Record<string, number>;
	bands: Record<Banda, number>;
	weights: Record<Pilar, number>;
	reference: { medians: Record<Pilar, number> };
	trajectory: Record<string, number>;
	confidence: Record<string, unknown>;
	size_bands: { upper_bounds_eur: number[]; hold_months: number; window_months: number };
	alerts: { critical_score: number };
	invoices: Record<string, unknown>;
	activity: Record<string, number>;
	debt: Record<string, number>;
}
