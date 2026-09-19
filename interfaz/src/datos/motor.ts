// Adaptador del bundle real del motor v2 (contracts/xray-export-v1.schema.json) al modelo de la
// interfaz. Lee manifest, portfolio, alerts y los ficheros de grupo; la evidencia de cada grupo se
// pide solo al abrir su expediente. Si no hay bundle, la interfaz usa la cartera sintética.

import {
	NOMBRE_BANDA, NOMBRE_PILAR, PILARES, type Alerta, type Atributo, type Banda, type Cartera, type Confianza, type Direccion, type Empresa,
	type Grupo, type Huella, type MesEntidad, type Naturaleza, type Pilar, type PilarMes, type TipoAlerta,
} from './modelo';
import type { AccionM, Manifiesto } from './contrato';
import { carga, RAIZ_BUNDLE as RAIZ } from './carga';


interface MesMotor {
	actions?: AccionM[];
	month: string; shown: number; band: Banda; base: number; penalty: number; cap: { amount: number };
	conf: { label: Confianza }; flags: string[]; abstain: { reason: string } | null; perimeter_changed: boolean;
	pillars: { key: Pilar; score: number | null; contrib: number; gates: string[]; note: string | null }[];
	verdict: { delta3: number | null; detected_since: string | null; compared_to: string | null; persistence_months: number | null; pillars_moved: string[]; direction?: Direccion; nature?: Naturaleza | null } | null;
}
interface GrupoMotor {
	id: string; first_month: string; months: MesMotor[];
	companies: { id: string; role: string; treasury_class: string | null; inherits_liquidity: boolean; first_month: string; shown: (number | null)[]; band: (Banda | null)[] }[];
	profile: Atributo[]; context: { industry: { label: string } | null };
	alerts: AlertaMotor[];
}
interface AlertaMotor { id: string; entity_id: string; entity_kind: 'group' | 'company'; group_id: string; month: string; kind: TipoAlerta; state: Alerta['state']; shown: number }
interface PortfolioMotor {
	months: string[];
	groups: { id: string; n_companies: number; first_month: string; country: string | null; size_band: string | null; industry: string | null;
		shown: (number | null)[]; band: (Banda | null)[]; direction: (Direccion | null)[]; nature: (Naturaleza | null)[]; conf: (Confianza | null)[];
		abstained: (boolean | null)[]; perimeter_changed: (boolean | null)[] }[];
}

async function json<T>(ruta: string): Promise<T> {
	const r = await fetch(RAIZ + ruta);
	if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
	return r.json() as Promise<T>;
}

/** Pide muchas rutas con concurrencia limitada, informando del progreso. */
async function muchos<T>(rutas: string[], n: number, progreso: (hechos: number) => void): Promise<T[]> {
	const salida: T[] = new Array(rutas.length);
	let i = 0, hechos = 0;
	await Promise.all(Array.from({ length: n }, async () => {
		while (i < rutas.length) {
			const k = i++;
			salida[k] = await json<T>(rutas[k]);
			progreso(++hechos);
		}
	}));
	return salida;
}

/** ¿Hay un bundle real servido junto a la interfaz? */
export async function hayBundle(): Promise<boolean> {
	try {
		const r = await fetch(RAIZ + 'manifest.json', { method: 'GET' });
		if (!r.ok) return false;
		const m = await r.json();
		return m?.schema === 'xray-export-v1';
	} catch {
		return false;
	}
}

export async function carteraMotor(progreso: (fraccion: number) => void): Promise<Cartera> {
	const manifest = (await carga.manifiesto()) as Manifiesto;
	// Los nombres de pilares y bandas salen del manifiesto, nunca del código.
	for (const p of manifest.pillars) NOMBRE_PILAR[p.key] = p.label;
	for (const b of manifest.bands) NOMBRE_BANDA[b.key] = b.label;
	const [portfolio, alertas, productos, horizontes] = await Promise.all([json<PortfolioMotor>('portfolio.json'), json<{ alerts: AlertaMotor[] }>('alerts.json'), carga.productosIndice(), carga.horizontesIndice()]);
	progreso(0.08);
	const months = manifest.months;
	const idx = new Map(months.map((m, i) => [m, i]));
	const ficheros = await muchos<GrupoMotor>(portfolio.groups.map((g) => `groups/${g.id}.json`), 12, (n) => progreso(0.08 + (0.9 * n) / portfolio.groups.length));
	const porId = new Map(ficheros.map((g) => [g.id, g]));

	const alertasPorGrupo = new Map<string, Alerta[]>();
	// Los avisos de empresa se guardan aparte: los usa el monitor de la portada.
	const alertasEmpresas: Alerta[] = [];
	for (const a of alertas.alerts) {
		const al: Alerta = { id: a.id, entity_id: a.entity_id, group_id: a.group_id, month: idx.get(a.month) ?? 0, kind: a.kind, state: a.state, shown: a.shown };
		if (a.entity_kind !== 'group') { alertasEmpresas.push(al); continue; }
		const lista = alertasPorGrupo.get(a.group_id) ?? [];
		lista.push(al);
		alertasPorGrupo.set(a.group_id, lista);
	}

	const groups: Grupo[] = portfolio.groups.map((pg) => {
		const gm = porId.get(pg.id)!;
		const porMes = new Map(gm.months.map((m) => [m.month, m]));
		const meses: MesEntidad[] = months.map((iso, t) => {
			const m = porMes.get(iso);
			const vacio: PilarMes[] = PILARES.map((key) => ({ key, score: null, contrib: 0 }));
			if (!m || pg.shown[t] === null) {
				return { shown: null, band: null, direction: null, nature: null, conf: null, abstained: null, perimeter_changed: null, base: 0, pillars: vacio, penalty: 0, cap: 0 };
			}
			const pillars: PilarMes[] = PILARES.map((key) => {
				const p = m.pillars.find((x) => x.key === key);
				return { key, score: p?.score ?? null, contrib: p?.contrib ?? 0, note: p?.note ?? null, gates: p?.gates ?? [] };
			});
			return {
				shown: m.shown, band: m.band, direction: pg.direction[t], nature: pg.nature[t], conf: pg.conf[t] ?? m.conf.label,
				abstained: pg.abstained[t], perimeter_changed: pg.perimeter_changed[t], base: m.base, pillars, penalty: m.penalty, cap: m.cap.amount,
				flags: m.flags, abstain_reason: m.abstain?.reason ?? null, acciones: m.actions ?? [],
				verdict: m.verdict ? { delta3: m.verdict.delta3, detected_since: m.verdict.detected_since, compared_to: m.verdict.compared_to, persistence_months: m.verdict.persistence_months, pillars_moved: m.verdict.pillars_moved ?? [] } : null,
			};
		});
		// Las empresas vienen alineadas con los meses del fichero de grupo: se llevan a la ventana entera.
		const mesesGrupo = gm.months.map((m) => idx.get(m.month) ?? 0);
		const companies: Empresa[] = gm.companies.map((c) => {
			const shown: (number | null)[] = months.map(() => null);
			const band: (Banda | null)[] = months.map(() => null);
			c.shown.forEach((v, k) => { shown[mesesGrupo[k]] = v; band[mesesGrupo[k]] = c.band[k]; });
			return { id: c.id, role: c.role, treasury_class: c.treasury_class, inherits_liquidity: c.inherits_liquidity, first_month: idx.get(c.first_month) ?? 0, shown, band };
		});
		const perfil: Record<string, Atributo> = {};
		for (const a of gm.profile) perfil[a.key] = a;
		return {
			id: pg.id,
			n_companies: pg.n_companies,
			first_month: idx.get(pg.first_month) ?? 0,
			// «España (ES) · multinacional» → «ES»; «Mediana (10-50 M€)» → «Mediana»: los mismos códigos que usan los filtros.
			country: pg.country?.match(/\(([A-Z]{2})\)/)?.[1] ?? pg.country,
			size_band: pg.size_band?.split(' ')[0] ?? null,
			industry: pg.industry ?? gm.context.industry?.label ?? null,
			meses,
			companies,
			alerts: (alertasPorGrupo.get(pg.id) ?? []).sort((a, b) => a.month - b.month),
			perfil,
			tenencia: productos?.groups[pg.id] ?? {},
		};
	});
	progreso(1);

	return {
		origen: 'motor',
		manifiesto: manifest,
		productos,
		horizontes,
		meta: { bundle_id: manifest.bundle_id, engine_version: manifest.engine_version, dataset_hash: manifest.dataset_hash, generated_at: manifest.generated_at },
		glosario: manifest.glossary,
		months,
		pillars: manifest.pillars.map((p) => ({ key: p.key, label: p.label, weight: p.weight })),
		groups,
		alertasEmpresas,
	};
}

// ─── Evidencia: se pide al abrir un grupo ──────────────────────
interface EvidenciaMotor { months: { month: string; rows: { label: string; n_rows: number | null; period: string; pillar: Pilar; source_file: string; unit: string; value: number | null }[] }[] }
const cacheEvidencia = new Map<string, Promise<EvidenciaMotor | null>>();

export function evidencia(id: string): Promise<EvidenciaMotor | null> {
	if (!cacheEvidencia.has(id)) cacheEvidencia.set(id, json<EvidenciaMotor>(`evidence/${id}.json`).catch(() => null));
	return cacheEvidencia.get(id)!;
}

/** Huella de cada pilar en un mes: los ficheros de origen y las filas que la sostienen. */
export function huellaDeMes(ev: EvidenciaMotor, mes: string): Partial<Record<Pilar, Huella & { filasDetalle: { label: string; valor: string }[] }>> {
	const m = ev.months.find((x) => x.month === mes) ?? ev.months[ev.months.length - 1];
	const salida: Partial<Record<Pilar, Huella & { filasDetalle: { label: string; valor: string }[] }>> = {};
	if (!m) return salida;
	for (const p of PILARES) {
		const filas = m.rows.filter((r) => r.pillar === p);
		if (!filas.length) continue;
		const ficheros = [...new Set(filas.map((r) => r.source_file))];
		const n = filas.reduce((s, r) => s + (r.n_rows ?? 0), 0);
		salida[p] = {
			fichero: ficheros.join(' + '),
			filas: n,
			detalle: n ? 'filas' : `${filas.length} medidas`,
			filasDetalle: filas.slice(0, 4).map((r) => ({ label: r.label, valor: formatoValor(r.value, r.unit) })),
		};
	}
	return salida;
}

function formatoValor(v: number | null, unidad: string) {
	if (v === null || Number.isNaN(v)) return '—';
	if (unidad === 'EUR') {
		const a = Math.abs(v);
		const f = new Intl.NumberFormat('es-ES', { maximumFractionDigits: a >= 1e6 ? 1 : 0 });
		return a >= 1e6 ? `${f.format(v / 1e6)} M€` : a >= 1e3 ? `${f.format(v / 1e3)} k€` : `${f.format(v)} €`;
	}
	const f = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 1 });
	return unidad === 'días' ? `${f.format(v)} días` : unidad === 'ratio' ? `${f.format(v)} ×` : `${f.format(v)} ${unidad}`;
}
