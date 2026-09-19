// El monitor de la portada (propuesta 08): la cartera entera en el corte, con el orden de gravedad,
// los filtros, el resumen del mes y el flujo entre bandas. Todo sale de la cartera ya cargada
// (portfolio, ficheros de grupo, avisos, horizontes e índice de empresas); nada se escribe a mano.
// La misma «entidad» sirve para organizaciones y para empresas.

import type { IndiceEmpresasM, ProductoId } from './contrato';
import { CORTE_SCORE, PAISES, type Zona } from './consulta';
import { tendencia } from './derivados';
import { encajaAGrupo } from './encaje';
import { f } from './formato';
import type { Alerta, Banda, Cartera, Direccion, Naturaleza, TipoAlerta } from './modelo';

export type Unidad = 'organizaciones' | 'empresas';
export type Forma = 'ranking' | 'bandas' | 'plano' | 'tapiz' | 'flujo' | 'avisos' | 'horizonte';
export type Modo = 'arena' | 'tabla';
export type OrdenM = 'gravedad' | 'score' | 'cambio' | 'cambio3' | 'horizonte' | 'avisos' | 'tamano';
export type MovM = 'entra_critico' | 'baja_banda' | 'sube_banda' | 'cae' | 'crece' | 'deterioro' | 'mejora' | 'hacia_critico' | 'por_confirmar' | 'avisos' | 'sin_datos';

export interface FiltrosM {
	banda?: Banda;
	zona?: Zona;
	mov?: MovM;
	sector?: string;
	pais?: string;
	tamano?: string;
	producto?: { id: ProductoId; modo: 'tiene' | 'encaja' };
	grupo?: string;
}

export interface EstadoMonitor { forma: Forma; modo: Modo; unidad: Unidad; orden: OrdenM; filtros: FiltrosM }

export const ESTADO_INICIAL: EstadoMonitor = { forma: 'ranking', modo: 'arena', unidad: 'organizaciones', orden: 'gravedad', filtros: {} };

export const BANDAS: Banda[] = ['critical', 'watch', 'stable', 'solid'];
export const TAMANOS = ['Micro', 'Pequeña', 'Mediana', 'Grande'];

export const FORMAS: { id: Forma; nombre: string; explica: string }[] = [
	{ id: 'ranking', nombre: 'Ranking', explica: 'Una fila por entidad, en el orden elegido' },
	{ id: 'bandas', nombre: 'Bandas', explica: 'Un montón por banda; se ve quién entra y quién sale' },
	{ id: 'plano', nombre: 'Plano', explica: 'Nivel y ritmo: las cuatro zonas' },
	{ id: 'tapiz', nombre: 'Tapiz', explica: 'Cada entidad, mes a mes' },
	{ id: 'flujo', nombre: 'Flujo', explica: 'De la banda del mes pasado a la de este' },
	{ id: 'avisos', nombre: 'Avisos', explica: 'Los avisos del motor, mes a mes y por tipo' },
	{ id: 'horizonte', nombre: 'Horizonte', explica: 'De hoy a seis meses, si nada cambia' },
];

export const ORDENES: { id: OrdenM; nombre: string }[] = [
	{ id: 'gravedad', nombre: 'por gravedad' },
	{ id: 'score', nombre: 'por score, de menor a mayor' },
	{ id: 'cambio', nombre: 'por lo que cambian este mes' },
	{ id: 'cambio3', nombre: 'por lo que cambian en tres meses' },
	{ id: 'horizonte', nombre: 'por probabilidad de crítico a seis meses' },
	{ id: 'avisos', nombre: 'por avisos del mes' },
	{ id: 'tamano', nombre: 'por tamaño' },
];

export const MOVIMIENTOS_M: { id: MovM; nombre: string; frase: string }[] = [
	{ id: 'entra_critico', nombre: 'Entran en crítico', frase: 'que entran en crítico este mes' },
	{ id: 'baja_banda', nombre: 'Bajan de banda', frase: 'que bajan de banda este mes' },
	{ id: 'sube_banda', nombre: 'Suben de banda', frase: 'que suben de banda este mes' },
	{ id: 'cae', nombre: 'Caen tres puntos o más', frase: 'que caen tres puntos o más este mes' },
	{ id: 'crece', nombre: 'Suben tres puntos o más', frase: 'que suben tres puntos o más este mes' },
	{ id: 'deterioro', nombre: 'Deterioro confirmado', frase: 'con un deterioro confirmado este mes' },
	{ id: 'mejora', nombre: 'Mejora confirmada', frase: 'con una mejora confirmada este mes' },
	{ id: 'hacia_critico', nombre: 'Van hacia crítico', frase: 'que van hacia crítico (50 % o más a seis meses)' },
	{ id: 'por_confirmar', nombre: 'Golpe por confirmar', frase: 'con un golpe por confirmar' },
	{ id: 'avisos', nombre: 'Con avisos del mes', frase: 'con algún aviso este mes' },
	{ id: 'sin_datos', nombre: 'Datos sin actualizar', frase: 'con los datos del banco sin actualizar' },
];

/** Los tipos de aviso del motor, en el orden del calendario (lo grave arriba). */
export const TIPOS_AVISO: { id: TipoAlerta; nombre: string; tono: 'baja' | 'sube' | 'neutro' }[] = [
	{ id: 'level_critical', nombre: 'Nivel crítico', tono: 'baja' },
	{ id: 'deterioration_structural', nombre: 'Deterioro', tono: 'baja' },
	{ id: 'deterioration_drift', nombre: 'Deriva a la baja', tono: 'baja' },
	{ id: 'improvement_structural', nombre: 'Mejora', tono: 'sube' },
	{ id: 'improvement_drift', nombre: 'Deriva al alza', tono: 'sube' },
	{ id: 'stale_feed', nombre: 'Datos sin actualizar', tono: 'neutro' },
	{ id: 'cap_fired', nombre: 'Tope aplicado', tono: 'neutro' },
];

export interface Entidad {
	id: string;
	kind: 'group' | 'company';
	/** Grupo al que pertenece (el propio id en una organización). */
	grupo: string;
	nombre: string;
	sector: string | null;
	pais: string | null;
	tamano: string | null;
	/** Para ordenar por tamaño: empresas del grupo o tramo de la empresa. */
	peso: number;
	/** Score en décimas, mes a mes (alineado con cartera.months). */
	serie: (number | null)[];
	bandas: (Banda | null)[];
	shown: number | null;
	band: Banda | null;
	prevShown: number | null;
	prevBand: Banda | null;
	delta1: number | null;
	delta3: number | null;
	ritmo: number | null;
	zona: Zona | null;
	direction: Direccion | null;
	nature: Naturaleza | null;
	/** Avisos del corte (disparados o silenciados). */
	avisos: Alerta[];
	/** Todos los avisos de la entidad hasta el corte. */
	historia: Alerta[];
	hz: { p50: number | null; pCritico: number | null; cruce: { to: Banda; month: string; prob: number | null } | null } | null;
	/** 0 entra en crítico · 1 deterioro · 2 crítico y baja · 3 hacia crítico · 4 golpe por confirmar · 5 resto de críticas · 6 el resto. */
	nivel: number;
	motivo: string;
	/** Si sube este mes, por qué (para la lista de las que suben). */
	sube: string | null;
	/** Solo organizaciones (para el filtro de producto). */
	gi?: number;
}

const rangoBanda = (b: Banda | null) => (b ? BANDAS.indexOf(b) : -1);
export const nombreBandaM = (c: Cartera, b: Banda) => c.manifiesto?.bands.find((x) => x.key === b)?.label ?? b;

/** Ritmo (puntos al mes) con Theil–Sen sobre los últimos 12 meses: el mismo cálculo que el mapa. */
export function ritmoSerie(serie: (number | null)[], t: number, desde = 0, ventana = 12): number | null {
	const xs: number[] = [], ys: number[] = [];
	for (let k = Math.max(desde, t - ventana + 1); k <= t; k++) { const s = serie[k]; if (s !== null && s !== undefined) { xs.push(k); ys.push(s / 10); } }
	if (xs.length < 4) return null;
	const pend: number[] = [];
	for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) pend.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
	pend.sort((a, b) => a - b);
	const m = pend.length >> 1;
	return pend.length % 2 ? pend[m] : (pend[m - 1] + pend[m]) / 2;
}

const zonaDe = (shown: number | null, ritmo: number | null): Zona | null => {
	if (shown === null) return null;
	const r = ritmo ?? 0;
	if (shown / 10 >= CORTE_SCORE) return r >= 0 ? 'solida' : 'tuerce';
	return r >= 0 ? 'mejora' : 'hunde';
};

const DETERIORO: TipoAlerta[] = ['deterioration_structural', 'deterioration_drift'];
const MEJORA: TipoAlerta[] = ['improvement_structural', 'improvement_drift'];

/** Nivel de gravedad y su motivo, con la regla a la vista (propuesta 08, §2.3). */
function gravedad(c: Cartera, e: Omit<Entidad, 'nivel' | 'motivo' | 'sube'>): { nivel: number; motivo: string; sube: string | null } {
	const disparados = e.avisos.filter((a) => a.state === 'fired');
	const baja = (b: Banda) => nombreBandaM(c, b).toLowerCase();
	let nivel = 6, motivo = '';
	if (e.band === 'critical' && e.prevBand && e.prevBand !== 'critical') { nivel = 0; motivo = `entra en crítico${e.delta1 !== null ? ` (${f.deltaEntero(e.delta1)} puntos)` : ''}`; }
	else if (disparados.some((a) => DETERIORO.includes(a.kind))) { nivel = 1; motivo = 'deterioro confirmado por el motor'; }
	else if (e.band === 'critical' && e.delta1 !== null && e.delta1 < 0) { nivel = 2; motivo = `sigue en crítico y baja ${f.deltaEntero(e.delta1)}`; }
	else if (e.band && e.band !== 'critical' && (e.hz?.pCritico ?? 0) >= 0.5) { nivel = 3; motivo = `${f.porcentaje(e.hz!.pCritico!, 0)} de estar en crítico dentro de seis meses`; }
	else if (e.nature === 'shock_pending') { nivel = 4; motivo = 'se ha movido de golpe; falta confirmar si dura'; }
	else if (e.band === 'critical') { nivel = 5; motivo = 'en crítico'; }
	else if (e.band) motivo = baja(e.band);
	if (disparados.some((a) => a.kind === 'stale_feed')) motivo += motivo ? ' · datos del banco sin actualizar' : 'datos del banco sin actualizar';
	let sube: string | null = null;
	if (e.band && e.prevBand && rangoBanda(e.band) > rangoBanda(e.prevBand)) sube = `sube a ${baja(e.band)}${e.delta1 !== null ? ` (${f.deltaEntero(e.delta1)} puntos)` : ''}`;
	else if (disparados.some((a) => MEJORA.includes(a.kind))) sube = 'mejora confirmada por el motor';
	else if (e.delta1 !== null && e.delta1 >= 30) sube = `sube ${f.deltaEntero(e.delta1)} puntos`;
	return { nivel, motivo, sube };
}

const ORDEN_TAMANO: Record<string, number> = { Micro: 1, Pequeña: 2, Mediana: 3, Grande: 4 };

/** Todas las entidades de la unidad en el mes t. */
export function entidades(c: Cartera, unidad: Unidad, t: number, indice: IndiceEmpresasM | null): Entidad[] {
	const hzIx = c.horizontes && c.horizontes.cut === c.months[t] ? c.horizontes.entities : null;
	const hzDe = (id: string) => { const h = hzIx?.[id]; return h ? { p50: h.p50_h6, pCritico: h.p_critical_h6, cruce: h.cross } : null; };
	const salida: Entidad[] = [];
	if (unidad === 'organizaciones') {
		c.groups.forEach((g, gi) => {
			const m = g.meses[t], a = g.meses[t - 1], m3 = g.meses[t - 3];
			const serie = g.meses.map((x) => x.shown);
			const ritmo = tendencia(g, t);
			const base = {
				id: g.id, kind: 'group' as const, grupo: g.id, nombre: f.grupo(g.id), sector: g.industry, pais: g.country, tamano: g.size_band, peso: g.n_companies,
				serie, bandas: g.meses.map((x) => x.band), shown: m?.shown ?? null, band: m?.band ?? null, prevShown: a?.shown ?? null, prevBand: a?.band ?? null,
				delta1: m?.shown != null && a?.shown != null ? m.shown - a.shown : null, delta3: m?.shown != null && m3?.shown != null ? m.shown - m3.shown : null,
				ritmo, zona: zonaDe(m?.shown ?? null, ritmo), direction: m?.direction ?? null, nature: m?.nature ?? null,
				avisos: g.alerts.filter((x) => x.month === t), historia: g.alerts.filter((x) => x.month <= t), hz: hzDe(g.id), gi,
			};
			salida.push({ ...base, ...gravedad(c, base) });
		});
		return salida;
	}
	const porEmpresa = new Map<string, Alerta[]>();
	for (const a of c.alertasEmpresas ?? []) { if (a.month > t) continue; const l = porEmpresa.get(a.entity_id) ?? []; l.push(a); porEmpresa.set(a.entity_id, l); }
	for (const g of c.groups) for (const em of g.companies) {
		const s = em.shown[t] ?? null, a = em.shown[t - 1] ?? null, s3 = em.shown[t - 3] ?? null;
		if (s === null && a === null) continue; // sin datos en el corte ni el mes anterior: fuera del monitor
		const ritmo = ritmoSerie(em.shown, t, em.first_month);
		const tam = indice?.companies[em.id]?.size?.split(' ')[0] ?? null;
		const historia = porEmpresa.get(em.id) ?? [];
		const base = {
			id: em.id, kind: 'company' as const, grupo: g.id, nombre: f.empresa(em.id), sector: g.industry, pais: g.country, tamano: tam, peso: ORDEN_TAMANO[tam ?? ''] ?? 0,
			serie: em.shown, bandas: em.band, shown: s, band: em.band[t] ?? null, prevShown: a, prevBand: em.band[t - 1] ?? null,
			delta1: s !== null && a !== null ? s - a : null, delta3: s !== null && s3 !== null ? s - s3 : null,
			ritmo, zona: zonaDe(s, ritmo), direction: null, nature: null,
			avisos: historia.filter((x) => x.month === t), historia, hz: hzDe(em.id),
		};
		salida.push({ ...base, ...gravedad(c, base) });
	}
	return salida;
}

// ─── Filtros y orden ─────────────────────────────────────────

export function pasa(c: Cartera, e: Entidad, fl: FiltrosM, t: number): boolean {
	if (fl.banda && e.band !== fl.banda) return false;
	if (fl.zona && e.zona !== fl.zona) return false;
	if (fl.sector && e.sector !== fl.sector) return false;
	if (fl.pais && e.pais !== fl.pais) return false;
	if (fl.tamano && e.tamano !== fl.tamano) return false;
	if (fl.grupo && e.grupo !== fl.grupo) return false;
	if (fl.producto) {
		if (e.gi === undefined) return false; // el filtro de producto es de organizaciones
		const g = c.groups[e.gi];
		const ok = fl.producto.modo === 'tiene' ? (g.tenencia?.[fl.producto.id] ?? 0) > 0 : encajaAGrupo(g.meses[t]?.acciones, g.tenencia, fl.producto.id);
		if (!ok) return false;
	}
	if (fl.mov) {
		const disparados = e.avisos.filter((a) => a.state === 'fired');
		switch (fl.mov) {
			case 'entra_critico': return e.nivel === 0;
			case 'baja_banda': return !!e.band && !!e.prevBand && rangoBanda(e.band) < rangoBanda(e.prevBand);
			case 'sube_banda': return !!e.band && !!e.prevBand && rangoBanda(e.band) > rangoBanda(e.prevBand);
			case 'cae': return e.delta1 !== null && e.delta1 <= -30;
			case 'crece': return e.delta1 !== null && e.delta1 >= 30;
			case 'deterioro': return disparados.some((a) => DETERIORO.includes(a.kind));
			case 'mejora': return disparados.some((a) => MEJORA.includes(a.kind));
			case 'hacia_critico': return e.band !== 'critical' && (e.hz?.pCritico ?? 0) >= 0.5;
			case 'por_confirmar': return e.nature === 'shock_pending';
			case 'avisos': return disparados.length > 0;
			case 'sin_datos': return disparados.some((a) => a.kind === 'stale_feed');
		}
	}
	return true;
}

const nulos = (v: number | null, x: number) => (v === null ? x : v);

export function ordenar(lista: Entidad[], orden: OrdenM): Entidad[] {
	const l = [...lista];
	const porId = (a: Entidad, b: Entidad) => (a.id < b.id ? -1 : 1);
	switch (orden) {
		case 'gravedad':
			return l.sort((a, b) => a.nivel - b.nivel || (a.nivel === 3 ? nulos(b.hz?.pCritico ?? null, 0) - nulos(a.hz?.pCritico ?? null, 0) : 0)
				|| ([0, 2, 4].includes(a.nivel) ? nulos(a.delta1, 0) - nulos(b.delta1, 0) : 0) || nulos(a.shown, 1e4) - nulos(b.shown, 1e4) || porId(a, b));
		case 'score': return l.sort((a, b) => nulos(a.shown, 1e4) - nulos(b.shown, 1e4) || porId(a, b));
		case 'cambio': return l.sort((a, b) => nulos(a.delta1, 1e4) - nulos(b.delta1, 1e4) || porId(a, b));
		case 'cambio3': return l.sort((a, b) => nulos(a.delta3, 1e4) - nulos(b.delta3, 1e4) || porId(a, b));
		case 'horizonte': return l.sort((a, b) => nulos(b.hz?.pCritico ?? null, -1) - nulos(a.hz?.pCritico ?? null, -1) || porId(a, b));
		case 'avisos': return l.sort((a, b) => b.avisos.filter((x) => x.state === 'fired').length - a.avisos.filter((x) => x.state === 'fired').length || a.nivel - b.nivel || porId(a, b));
		case 'tamano': return l.sort((a, b) => b.peso - a.peso || porId(a, b));
	}
}

/** Las que piden atención (niveles 0–4) y las que suben, en el orden de la portada. */
export function atencion(lista: Entidad[]) {
	const piden = ordenar(lista.filter((e) => e.nivel <= 4), 'gravedad');
	const suben = lista.filter((e) => e.sube && e.nivel > 4).sort((a, b) => nulos(b.delta1, -1e4) - nulos(a.delta1, -1e4));
	return { piden, suben };
}

// ─── Resumen del mes ─────────────────────────────────────────

export interface Resumen {
	total: number;
	conScore: number;
	bandas: Record<Banda, { n: number; entran: number; salen: number }>;
	cambian: number; suben: number; bajan: number;
	caen3: number; crecen3: number;
	zonas: Record<Zona, number>;
	avisos: number;
	avisosPorTipo: Partial<Record<TipoAlerta, number>>;
	haciaCritico: number;
	porConfirmar: number;
	sinScore: number;
	/** Media del score (puntos) y del ritmo: para orientar la aguja de la rosa. */
	media: number | null;
	ritmoMedio: number | null;
}

export function resumen(lista: Entidad[]): Resumen {
	const bandas = Object.fromEntries(BANDAS.map((b) => [b, { n: 0, entran: 0, salen: 0 }])) as Resumen['bandas'];
	const zonas: Record<Zona, number> = { solida: 0, mejora: 0, tuerce: 0, hunde: 0 };
	const r: Resumen = { total: lista.length, conScore: 0, bandas, cambian: 0, suben: 0, bajan: 0, caen3: 0, crecen3: 0, zonas, avisos: 0, avisosPorTipo: {}, haciaCritico: 0, porConfirmar: 0, sinScore: 0, media: null, ritmoMedio: null };
	let sm = 0, sr = 0, nr = 0;
	for (const e of lista) {
		if (e.shown === null) { r.sinScore++; continue; }
		r.conScore++; sm += e.shown / 10;
		if (e.ritmo !== null) { sr += e.ritmo; nr++; }
		if (e.band) bandas[e.band].n++;
		if (e.band && e.prevBand && e.band !== e.prevBand) {
			r.cambian++; bandas[e.band].entran++; bandas[e.prevBand].salen++;
			if (rangoBanda(e.band) > rangoBanda(e.prevBand)) r.suben++; else r.bajan++;
		}
		if (e.delta1 !== null && e.delta1 <= -30) r.caen3++;
		if (e.delta1 !== null && e.delta1 >= 30) r.crecen3++;
		if (e.zona) zonas[e.zona]++;
		if (e.band !== 'critical' && (e.hz?.pCritico ?? 0) >= 0.5) r.haciaCritico++;
		if (e.nature === 'shock_pending') r.porConfirmar++;
		for (const a of e.avisos) if (a.state === 'fired') { r.avisos++; r.avisosPorTipo[a.kind] = (r.avisosPorTipo[a.kind] ?? 0) + 1; }
	}
	r.media = r.conScore ? sm / r.conScore : null;
	r.ritmoMedio = nr ? sr / nr : null;
	return r;
}

/** Matriz del flujo entre bandas: [banda del mes pasado][banda de este mes] → entidades. */
export function flujo(lista: Entidad[]): Record<Banda, Record<Banda, Entidad[]>> {
	const m = Object.fromEntries(BANDAS.map((a) => [a, Object.fromEntries(BANDAS.map((b) => [b, [] as Entidad[]]))])) as Record<Banda, Record<Banda, Entidad[]>>;
	for (const e of lista) if (e.band && e.prevBand) m[e.prevBand][e.band].push(e);
	return m;
}

// ─── Estado en la URL ────────────────────────────────────────
// Claves propias («m…») que no chocan con las del mapa, que el almacén borra y reescribe.

const CLAVES = { forma: 'mf', modo: 'mm', unidad: 'mu', orden: 'mo', banda: 'mb', zona: 'mz', mov: 'mmov', sector: 'msec', pais: 'mpais', tamano: 'mtam', producto: 'mprod', grupo: 'mgr' } as const;

export function leerEstadoURL(): EstadoMonitor {
	const q = new URLSearchParams(location.search);
	const val = <T extends string>(k: string, ok: readonly T[], def: T): T => (ok.includes(q.get(k) as T) ? (q.get(k) as T) : def);
	const fl: FiltrosM = {};
	const b = q.get(CLAVES.banda); if (b && (BANDAS as string[]).includes(b)) fl.banda = b as Banda;
	const z = q.get(CLAVES.zona); if (z && ['solida', 'mejora', 'tuerce', 'hunde'].includes(z)) fl.zona = z as Zona;
	const mv = q.get(CLAVES.mov); if (mv && MOVIMIENTOS_M.some((x) => x.id === mv)) fl.mov = mv as MovM;
	for (const k of ['sector', 'pais', 'tamano', 'grupo'] as const) { const v = q.get(CLAVES[k]); if (v) fl[k] = v; }
	const pr = q.get(CLAVES.producto); if (pr) { const [id, modo] = pr.split(':'); fl.producto = { id: id as ProductoId, modo: modo === 'tiene' ? 'tiene' : 'encaja' }; }
	return {
		forma: val(CLAVES.forma, FORMAS.map((x) => x.id), ESTADO_INICIAL.forma),
		modo: val(CLAVES.modo, ['arena', 'tabla'] as const, ESTADO_INICIAL.modo),
		unidad: val(CLAVES.unidad, ['organizaciones', 'empresas'] as const, ESTADO_INICIAL.unidad),
		orden: val(CLAVES.orden, ORDENES.map((x) => x.id), ESTADO_INICIAL.orden),
		filtros: fl,
	};
}

export function escribirEstadoURL(e: EstadoMonitor) {
	const q = new URLSearchParams(location.search);
	for (const k of Object.values(CLAVES)) q.delete(k);
	if (e.forma !== ESTADO_INICIAL.forma) q.set(CLAVES.forma, e.forma);
	if (e.modo !== ESTADO_INICIAL.modo) q.set(CLAVES.modo, e.modo);
	if (e.unidad !== ESTADO_INICIAL.unidad) q.set(CLAVES.unidad, e.unidad);
	if (e.orden !== ESTADO_INICIAL.orden) q.set(CLAVES.orden, e.orden);
	const fl = e.filtros;
	if (fl.banda) q.set(CLAVES.banda, fl.banda);
	if (fl.zona) q.set(CLAVES.zona, fl.zona);
	if (fl.mov) q.set(CLAVES.mov, fl.mov);
	for (const k of ['sector', 'pais', 'tamano', 'grupo'] as const) if (fl[k]) q.set(CLAVES[k], fl[k]!);
	if (fl.producto) q.set(CLAVES.producto, `${fl.producto.id}:${fl.producto.modo}`);
	const s = q.toString();
	history.replaceState(history.state, '', `${location.pathname}${s ? `?${s}` : ''}`);
}

// ─── Lo que se ve, en una frase ──────────────────────────────

const NOMBRE_ZONA_PL: Record<Zona, string> = { solida: 'sólidas', mejora: 'que mejoran', tuerce: 'que se tuercen', hunde: 'que se hunden' };

/** Las piezas de la frase: cada filtro es una ficha que se puede quitar. */
export function piezasFiltro(c: Cartera, fl: FiltrosM, nombreProducto: (id: ProductoId) => string): { clave: keyof FiltrosM; texto: string }[] {
	const p: { clave: keyof FiltrosM; texto: string }[] = [];
	if (fl.banda) p.push({ clave: 'banda', texto: `en ${nombreBandaM(c, fl.banda).toLowerCase()}` });
	if (fl.zona) p.push({ clave: 'zona', texto: NOMBRE_ZONA_PL[fl.zona] });
	if (fl.mov) p.push({ clave: 'mov', texto: MOVIMIENTOS_M.find((x) => x.id === fl.mov)!.frase });
	if (fl.sector) p.push({ clave: 'sector', texto: `de ${fl.sector.toLowerCase()}` });
	if (fl.pais) p.push({ clave: 'pais', texto: `de ${PAISES[fl.pais] ?? fl.pais}` });
	if (fl.tamano) p.push({ clave: 'tamano', texto: `de tamaño ${fl.tamano.toLowerCase()}` });
	if (fl.producto) p.push({ clave: 'producto', texto: fl.producto.modo === 'tiene' ? `que tienen ${nombreProducto(fl.producto.id).toLowerCase()}` : `a las que les encaja ${nombreProducto(fl.producto.id).toLowerCase()}` });
	if (fl.grupo) p.push({ clave: 'grupo', texto: `del ${f.grupo(fl.grupo)}` });
	return p;
}

/** Sectores, países y tamaños presentes en la cartera (para los filtros y para Jev). */
export function vocabulario(c: Cartera) {
	const sectores = [...new Set(c.groups.map((g) => g.industry).filter((x): x is string => !!x))].sort((a, b) => a.localeCompare(b, 'es'));
	const paises = [...new Set(c.groups.map((g) => g.country).filter((x): x is string => !!x))].sort((a, b) => (PAISES[a] ?? a).localeCompare(PAISES[b] ?? b, 'es'));
	return { sectores, paises, tamanos: TAMANOS };
}
