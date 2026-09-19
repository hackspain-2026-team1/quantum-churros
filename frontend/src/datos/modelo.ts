import type { AccionM, HorizontesIndiceM, Manifiesto, ProductoId, ProductosIndiceM } from './contrato';
// Modelo de datos de la interfaz.
// Usa el mismo vocabulario que el contrato del motor (contracts/xray-export-v1.schema.json):
// puntuaciones en décimas enteras (0–1000), bandas, dirección, naturaleza y pilares con sus claves.
// Así, el adaptador del bundle real solo tendrá que copiar campos.

export const PILARES = ['liquidity', 'payments', 'collections', 'activity', 'debt'] as const;
export type Pilar = (typeof PILARES)[number];

export type Banda = 'critical' | 'watch' | 'stable' | 'solid';
export type Direccion = 'improving' | 'stable' | 'deteriorating' | 'perimeter_shift';
export type Naturaleza = 'structural' | 'shock_pending' | 'bump';
export type Confianza = 'high' | 'medium' | 'low';
export type TipoAlerta =
	| 'deterioration_structural'
	| 'improvement_structural'
	| 'deterioration_drift'
	| 'improvement_drift'
	| 'level_critical'
	| 'cap_fired'
	| 'stale_feed';

export interface PilarMes {
	key: Pilar;
	score: number | null; // décimas
	contrib: number; // décimas, con signo
	/** Frase del motor que explica el pilar ese mes (solo con datos reales). */
	note?: string | null;
	/** Compuertas del motor: por qué un pilar no se mide o se mide con reservas. */
	gates?: string[];
}

/** Lo que el motor concluye de un mes (verdict del contrato). */
export interface Veredicto {
	delta3: number | null;
	detected_since: string | null;
	compared_to: string | null;
	persistence_months: number | null;
	pillars_moved: string[];
}

/** Un mes de una entidad. base + Σcontrib − penalty − cap = shown (en décimas). */
export interface MesEntidad {
	shown: number | null;
	band: Banda | null;
	direction: Direccion | null;
	nature: Naturaleza | null;
	conf: Confianza | null;
	abstained: boolean | null;
	perimeter_changed: boolean | null;
	base: number;
	pillars: PilarMes[];
	penalty: number;
	cap: number;
	/** Solo con datos reales. */
	flags?: string[];
	verdict?: Veredicto | null;
	abstain_reason?: string | null;
	/** Acciones que calcula el motor ese mes (solo con datos reales). */
	acciones?: AccionM[];
}

export interface Alerta {
	id: string;
	entity_id: string;
	group_id: string;
	month: number; // índice de mes
	kind: TipoAlerta;
	state: 'fired' | 'suppressed' | 'abstained';
	shown: number;
}

export interface Empresa {
	id: string;
	/** Papel en el grupo y estructura de tesorería, del motor. */
	role?: string;
	treasury_class?: string | null;
	inherits_liquidity?: boolean;
	first_month: number;
	shown: (number | null)[];
	band: (Banda | null)[];
}

/** Huella de un pilar: de qué fichero sale y cuántas filas lo sostienen (forma de evidence/<id>.json). */
export interface Huella { fichero: string; filas: number; detalle: string }

/** Un atributo de la ficha núcleo del motor (profile). */
export interface Atributo { key: string; label: string; value: string | null; evidence: string | null }

export interface Grupo {
	id: string;
	n_companies: number;
	first_month: number;
	country: string | null;
	size_band: string | null;
	industry: string | null;
	meses: MesEntidad[];
	companies: Empresa[];
	alerts: Alerta[];
	/** Con datos sintéticos viene inventada; con datos reales se carga de evidence/<id>.json al abrir el grupo. */
	huella?: Record<Pilar, Huella>;
	/** Ficha núcleo del motor: país, tamaño, ERP, estructura de tesorería, concentración de clientes… */
	perfil?: Record<string, Atributo>;
	/** Cuántas de sus empresas tienen cada producto (products/index.json). */
	tenencia?: Partial<Record<ProductoId, number>>;
}

export interface Cartera {
	origen: 'sintetico' | 'motor';
	/** Datos del bundle real: versión del motor, huella del dataset y fecha de extracción. */
	meta?: { bundle_id: string; engine_version: string; dataset_hash: string; generated_at: string };
	/** Textos del motor para topes, avisos y compuertas. */
	glosario?: Record<string, Record<string, string>>;
	months: string[]; // 'YYYY-MM'
	pillars: { key: Pilar; label: string; weight: number }[];
	groups: Grupo[];
	/** Solo con datos reales. */
	manifiesto?: Manifiesto;
	productos?: ProductosIndiceM | null;
	horizontes?: HorizontesIndiceM | null;
	/** Avisos de empresa (solo con datos reales): los usa el monitor de la portada. */
	alertasEmpresas?: Alerta[];
}

export const NOMBRE_PILAR: Record<Pilar, string> = {
	liquidity: 'Liquidez',
	payments: 'Pagos',
	collections: 'Cobros',
	activity: 'Actividad',
	debt: 'Deuda',
};

export const NOMBRE_BANDA: Record<Banda, string> = {
	critical: 'Crítico',
	watch: 'Vigilancia',
	stable: 'Estable',
	solid: 'Sólido',
};

export const NOMBRE_NATURALEZA: Record<Naturaleza, string> = {
	shock_pending: 'Por confirmar',
	structural: 'Estructural',
	bump: 'Bache',
};

export const NOMBRE_ALERTA: Record<TipoAlerta, string> = {
	deterioration_structural: 'Deterioro estructural',
	improvement_structural: 'Mejora estructural',
	level_critical: 'Nivel crítico',
	cap_fired: 'Tope aplicado',
	deterioration_drift: 'Deriva a la baja',
	improvement_drift: 'Deriva al alza',
	stale_feed: 'Datos sin actualizar',
};

export function bandaDe(decimas: number): Banda {
	if (decimas < 400) return 'critical';
	if (decimas < 600) return 'watch';
	if (decimas < 800) return 'stable';
	return 'solid';
}

/** Avisos que dicen «sube» o «baja» (la deriva lenta llega con la rama de Rubén). */
export const esMejora = (k: TipoAlerta) => k === 'improvement_structural' || k === 'improvement_drift';
export const esDeterioro = (k: TipoAlerta) => k === 'deterioration_structural' || k === 'deterioration_drift' || k === 'level_critical';
