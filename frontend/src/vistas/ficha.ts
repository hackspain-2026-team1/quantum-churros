// La ficha de una entidad (empresa u organización). Jerarquía, de más a menos:
//   1. El protagonista, fijo arriba y siempre a la vista: el número en su círculo (dónde está) y el
//      horizonte (hacia dónde va). Es lo único de arena de la página.
//   2. Las secciones, que explican y actúan sobre el protagonista: Scoring (qué lo compone), Productos
//      (con qué cuenta y qué le falta), Acciones (qué puede cambiar su rumbo).
//   3. Técnico: el reverso, la trazabilidad (ver tecnico.ts).
// Todo sale de los ficheros: el bundle del motor, products/, horizons/ (la previsión del motor) y params.json.

import { TONO, type Hilo } from '../arena/arena';
import type { Futuro, LineaSerie, PlacaSerie } from '../arena/placas';
import { carga } from '../datos/carga';
import type {
	AccionM, AlertaM, EmpresaM, EmpresaResumenM, EscenarioM, EvidenciaM, GrupoM, HorizonteM, HorizontesPasadosM, Manifiesto, MesM,
	ParametrosM, ProductosEmpresaM, ProductosGrupoM, TenenciaM,
} from '../datos/contrato';
import { estadosProductos, recomendaciones, type EstadoProducto } from '../datos/encaje';
import { f, primeraMayuscula } from '../datos/formato';
import { FAMILIAS, PRODUCTOS, producto } from '../datos/productos';
import { ESFUERZO, ESTADO_AVISO, explicacionAccion, lineaAvisoM, nombreBanda, nombrePilar, tituloAccion } from '../datos/redaccion';
import type { Seccion } from '../estado';
import { h, vaciar } from './dom';
import { iconoProducto } from './iconos';
import { hilo, lineaEstado, llamadas, seccion, sello, type Nudo } from './primitivos';
import { placa } from './registro';
import { seccionTecnica } from './tecnico';
import { triaje } from './triaje';

/** Filtro con el que se abre la evidencia desde un nudo del hilo. */
export interface FiltroEvidencia {
  pilar?: string | null;
  fichero?: string;
  texto?: string;
}

export interface EmpresaDeGrupo {
  res: EmpresaResumenM;
  ent: EmpresaM | null;
  prod: ProductosEmpresaM | null;
}

export interface DatosFicha {
	kind: 'company' | 'group';
	id: string;
	grupoId: string;
	ent: EmpresaM | GrupoM;
	corte: string;
	mes: MesM | null;
	man: Manifiesto;
	params: ParametrosM | null;
	evid: EvidenciaM | null;
	prodE: ProductosEmpresaM | null;
	prodG: ProductosGrupoM | null;
	hor: HorizonteM | null;
	/** El futuro visto desde cortes pasados (para cuando la regla está en un mes pasado). */
	pasados: HorizontesPasadosM | null;
	/** Hasta qué horizonte está validada la previsión (meses). */
	validado: number;
	/** Score del grupo en el corte (para situar a la empresa). */
	grupoMes: MesM | null;
	empresas: EmpresaDeGrupo[];
	/** Entidades del mismo tamaño en el corte: mediana y cuántas. */
	pares?: { mediana: number; n: number; tamano: string } | null;
}

export async function cargarFicha(kind: 'company' | 'group', id: string, grupoId: string, corte: string, man: Manifiesto): Promise<DatosFicha | null> {
	const ent = kind === 'company' ? await carga.empresa(id) : await carga.grupo(id);
	if (!ent) return null;
	const [params, evid, hor, grupo, ix] = await Promise.all([carga.parametros(), carga.evidencia(id), carga.horizonte(id), kind === 'company' ? carga.grupo(grupoId) : Promise.resolve(ent as GrupoM), carga.horizontesIndice()]);
	const pasados = hor && hor.cut !== corte ? await carga.horizontePasado(id) : null;
	const prodE = kind === 'company' ? await carga.productosEmpresa(id) : null;
	const prodG = await carga.productosGrupo(grupoId);
	let empresas: EmpresaDeGrupo[] = [];
	if (kind === 'group') {
		const g = ent as GrupoM;
		empresas = await Promise.all(g.companies.map(async (res) => ({ res, ent: await carga.empresa(res.id), prod: await carga.productosEmpresa(res.id) })));
	}
	return {
		kind, id, grupoId, ent, corte, man, params, evid, hor, pasados, prodE, prodG, empresas,
		validado: ix?.validation?.validado_hasta ?? 0,
		mes: ent.months.find((m) => m.month === corte) ?? null,
		grupoMes: (grupo as GrupoM).months.find((m) => m.month === corte) ?? null,
	};
}

// ─── Nombres ─────────────────────────────────────────────────
export const nombreEntidad = (kind: 'company' | 'group', id: string) => (kind === 'company' ? f.empresa(id) : f.grupo(id));
const atributo = (d: DatosFicha, k: string) => d.ent.profile.find((a) => a.key === k)?.value ?? null;
const tenenciaDe = (d: DatosFicha): TenenciaM[] => d.prodE?.held ?? [];
const hayFuturo = (d: DatosFicha) => !!d.hor?.scenarios && d.hor.cut === d.corte;

function estados(d: DatosFicha): EstadoProducto[] {
  if (!d.mes) return [];
  const papel = d.kind === "company" ? (d.ent as EmpresaM).role : null;
  const tenencia: TenenciaM[] =
    d.kind === "company"
      ? tenenciaDe(d)
      : PRODUCTOS.filter((p) => (d.prodG?.counts[p.id] ?? 0) > 0).map(
          (p) =>
            ({
              product: p.id,
              source: "declarado",
              items: [],
              evidence: [],
            }) as TenenciaM,
        );
  return estadosProductos({
    mes: d.mes,
    man: d.man,
    tenencia,
    perfil: d.ent.profile,
    papel,
    heredaLiquidez:
      d.kind === "company" ? (d.ent as EmpresaM).inherits_liquidity : false,
  });
}

// ─── Lo que las secciones pueden pedirle al protagonista ─────

export interface Acciones {
	abrirEmpresa(id: string): void;
	abrirGrupo(id: string): void;
	irSeccion(s: Seccion, accion?: string, filtro?: FiltroEvidencia): void;
	irBandeja(): void;
	repintarArena(): void;
	/** El horizonte, siempre a la vista: las secciones lo previsualizan y lo fijan. */
	horizonte: {
		elegidas(): Set<string>;
		alternar(id: string, si: boolean): void;
		previa(ids: string[] | null): void;
		pilar(k: string | null): void;
	};
	/** El hilo de arena para leer una gráfica (coordenadas de pantalla); [] lo apaga. */
	hilo(hs: Hilo[]): void;
}

// ─── 1. La cabecera: el número en su círculo ─────────────────

export function cabecera(d: DatosFicha, movil: boolean): HTMLElement {
	const nombre = nombreEntidad(d.kind, d.id);
	const m = d.mes;
	const circulo = h('div', { class: 'cab-circulo', role: 'img', 'aria-label': m ? `Score ${f.score(m.shown)} de 100, ${nombreBanda(d.man, m.band).toLowerCase()}` : 'Sin score' });
	const numero = h('div', { class: 'cab-numeral', 'aria-label': m ? `Score ${f.score(m.shown)}` : 'Sin score' });
	circulo.append(numero);
	if (m) {
		const marcas: { v: number; tipo: 'pares' | 'grupo' }[] = [];
		if (d.pares) marcas.push({ v: d.pares.mediana / 10, tipo: 'pares' });
		if (d.kind === 'company' && d.grupoMes) marcas.push({ v: d.grupoMes.shown / 10, tipo: 'grupo' });
		placa(circulo, (c) => ({
			tipo: 'numeral', x: c.x, y: c.y, h: c.h, texto: f.score(m.shown),
			anillo: { cx: c.x + c.w / 2, cy: c.y + c.h / 2, r: Math.min(c.w, c.h) / 2 - 14, valor: m.shown / 10, bandas: d.man.bands.filter((b) => b.min > 0).map((b) => b.min / 10), tono: m.band === 'critical' ? TONO.peligro : TONO.tinta, marcas },
		}));
		circulo.append(h('span', { class: `cab-banda banda-${m.band}` }, nombreBanda(d.man, m.band).toLowerCase()));
		circulo.title = d.man.bands.map((b) => `${b.label} desde ${f.score(b.min)}`).join(' · ');
	}
	const sub: string[] = [];
	if (d.kind === 'company') sub.push(`${(d.ent as EmpresaM).role} · ${f.grupo(d.grupoId)}`);
	else sub.push(f.plural((d.ent as GrupoM).companies.length, 'empresa', 'empresas'));
	const pais = atributo(d, 'country'); if (pais) sub.push(pais.replace(/\s*\([A-Z]{2}\)/, ''));
	const sector = d.ent.context.industry?.label; if (sector) sub.push(sector);
	const cab = h('header', { class: 'ficha-cab' }, circulo,
		h('div', { class: 'cab-texto' },
			h('h1', {}, nombre),
			h('p', { class: 'cab-sub' }, sub.join(' · ')),
			m ? lineaEstado(d.man, m, null, true) : h('p', { class: 'cab-vacio' }, `Sin datos en ${f.mes(d.corte)}.`),
			m ? explicacion(d) : null));
	void movil;
	return cab;
}

/** Lo que el número no dice solo: qué pesa más y con quién se compara (las marcas del círculo). */
function explicacion(d: DatosFicha): HTMLElement {
	const m = d.mes!;
	const p = h('p', { class: 'cab-explica' });
	const peor = [...m.pillars].filter((x) => x.score !== null).sort((a, b) => a.contrib - b.contrib)[0];
	if (m.abstain) p.append(h('span', {}, `El motor se abstiene: ${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason}`));
	else if (peor && peor.contrib < 0) p.append(h('span', {}, `Lo que más resta: ${nombrePilar(d.man, peor.key).toLowerCase()}, ${f.delta(peor.contrib)}.`));
	if (d.pares) p.append(h('span', { class: 'cab-marca pares' }, h('i', { 'aria-hidden': 'true' }), `las ${f.numero(d.pares.n)} de su tamaño: mediana ${f.score(d.pares.mediana)}`));
	if (d.kind === 'company' && d.grupoMes) p.append(h('span', { class: 'cab-marca grupo' }, h('i', { 'aria-hidden': 'true' }), `su grupo: ${f.score(d.grupoMes.shown)}`));
	return p;
}

// ─── 2. El horizonte ──────────────────────────────────────────

export interface OpcionesGrafico {
	metrica: string; // 'score' o la clave de una serie
	/** Acciones fijadas y en vista previa. */
	acciones: Set<string>;
	previa: string[] | null;
	/** Un pilar señalado desde la sección de scoring. */
	pilar: string | null;
	alto: number;
	alHilo?: (hs: Hilo[]) => void;
}

const NOMBRE_SUPUESTO = { drift: 'si sigue la deriva', stress: 'si se repite su peor trimestre' } as const;
const marcasEje = (lo: number, hi: number) => {
	const paso = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1e6].find((p) => (hi - lo) / p <= 5) ?? 1e7;
	const out: number[] = [];
	for (let v = Math.ceil(lo / paso) * paso; v <= hi + 1e-9; v += paso) out.push(v);
	return out;
};

/** El horizonte: un calendario fijo (todos los meses del bundle más doce) que cruza el mes de la regla. */
export function graficoHorizonte(d: DatosFicha, o: OpcionesGrafico, empresasHilo = false): HTMLElement {
	const caja = h('div', { class: 'grafico', style: { height: `${o.alto}px` } });
	const cal = [...d.man.months];
	const ultimoBundle = cal[cal.length - 1];
	for (let k = 1; k <= 12; k++) { const [y, mm] = ultimoBundle.split('-').map(Number); const t = y * 12 + mm - 1 + k; cal.push(`${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`); }
	const col = (iso: string) => cal.indexOf(iso);
	const hoy = col(d.corte);
	const columnas = cal.length;
	const esScore = o.metrica === 'score';

	// Pasado (hasta el corte) y lo que pasó después (si la regla está en un mes pasado).
	let unidad = 'puntos';
	let pasado: [number, number | null, number?][] = [];
	let despues: [number, number | null][] = [];
	if (esScore) {
		for (const m of d.ent.months) {
			const c = col(m.month);
			if (c < 0) continue;
			if (m.month <= d.corte) pasado.push([c, m.shown / 10, m.band === 'critical' ? TONO.peligro : TONO.tinta]);
			else despues.push([c, m.shown / 10]);
		}
	} else {
		const s = d.ent.series.find((x) => x.key === o.metrica);
		unidad = s?.unit ?? '';
		// Las series traen los últimos meses de la entidad: se alinean por el final.
		const vals = s?.values ?? [];
		const ult = d.ent.months.length;
		d.ent.months.forEach((m, i) => {
			const k = vals.length - (ult - i);
			const v = k >= 0 ? (vals[k] ?? null) : null;
			const c = col(m.month);
			if (m.month <= d.corte) pasado.push([c, v]); else despues.push([c, v]);
		});
	}
	pasado = pasado.filter((q) => q[0] >= 0);

	const futuros: Futuro[] = [];
	const lineas: LineaSerie[] = [];
	const marcas: [number, number][] = [];
	const etFuturo: { t: string; clase: string } = { t: '', clase: '' };
	const boyas: { h: number; texto: string; titulo?: string }[] = [];
	const HITOS = [3, 6, 12];
	const alternativas: { texto: string; clase: string; v: number }[] = [];
	const validado = d.validado || 12;
	const base = d.hor?.scenarios?.base;
	const q6 = (e: { q: { p10: number[]; p90: number[] } }, k: number) => `${f.score(e.q.p10[k])}–${f.score(e.q.p90[k])}`;
	if (esScore && hayFuturo(d) && base) {
		const vivas = new Set([...o.acciones, ...(o.previa ?? [])]);
		const accs = (d.hor!.actions ?? []).filter((a) => vivas.has(a.id));
		// La franja de la previsión y su mediana; más allá de lo validado, se aclara.
		const abanico = (e: EscenarioM, tono: number, alfa: number): Futuro => ({ granos: [], tono, alfa, mediana: e.q.p50, franja: e.q, validado, hitos: HITOS });
		if (accs.length) {
			// «No hacer nada» queda como contorno fantasma; las acciones, en azul, con su mediana.
			lineas.push({ puntos: base.q.p10.map((v, i) => [hoy + i + 1, v / 10]), tono: TONO.apagado, alfa: 0.7, punteada: true });
			lineas.push({ puntos: base.q.p90.map((v, i) => [hoy + i + 1, v / 10]), tono: TONO.apagado, alfa: 0.7, punteada: true });
			lineas.push({ puntos: [[hoy, d.mes!.shown / 10], ...base.q.p50.map((v, i) => [hoy + i + 1, v / 10] as [number, number])], tono: TONO.apagado, alfa: 0.8, punteada: true });
			const principal = accs.length === 1 ? accs[0] : accs.reduce((a, b) => (a.q.p50[5] > b.q.p50[5] ? a : b));
			// La principal, con su franja; las demás marcadas, solo su mediana.
			for (const a of accs) futuros.push(a === principal ? abanico(a, TONO.info, 0.72) : { granos: [], tono: TONO.info, alfa: 0.15, mediana: a.q.p50 });
			const lag = Math.max(...accs.map((a) => a.lag_months));
			const ids = accs.map((a) => a.id).sort().join();
			const cifra = accs.length === 1 ? accs[0].engine_new_score : d.hor!.combos?.find((c) => [...c.ids].sort().join() === ids)?.new_score;
			if (cifra !== undefined) marcas.push([hoy + lag, cifra / 10]);
			for (const hz of HITOS) {
				const k = hz - 1;
				const dif = Math.round((principal.q.p50[k] - base.q.p50[k]) / 10);
				boyas.push({ h: hz, texto: `${f.score(base.q.p50[k])} → ${f.score(principal.q.p50[k])} (${dif >= 0 ? '+' : '−'}${Math.abs(dif)})`, titulo: `Mediana sin hacer nada → con ${accs.length > 1 ? 'la mejor de las acciones marcadas' : 'la acción'}` });
			}
			etFuturo.t = o.previa?.length && !o.previa.every((x) => o.acciones.has(x)) ? 'vista previa · con esta acción' : accs.length > 1 ? `con ${accs.length} acciones` : 'con la acción marcada';
			etFuturo.clase = 'con-acciones';
		} else {
			futuros.push(abanico(base, TONO.tinta, 0.55));
			for (const hz of HITOS) {
				const k = hz - 1;
				const b = base.bands[`h${hz}` as 'h3' | 'h6' | 'h12'];
				boyas.push({ h: hz, texto: `${f.score(base.q.p50[k])} · ${q6(base, k)}`, titulo: b ? d.man.bands.map((x) => `${x.label} ${f.porcentaje(b[x.key] ?? 0, 0)}`).join(' · ') : undefined });
			}
			etFuturo.t = 'lo que puede pasar';
		}
		for (const k of ['drift', 'stress'] as const) {
			const e = d.hor!.scenarios![k];
			if (!e) continue;
			lineas.push({ puntos: [[hoy, d.mes!.shown / 10], ...e.q.p50.map((v, i) => [hoy + i + 1, v / 10] as [number, number])], tono: k === 'drift' ? TONO.tellme : TONO.ocre, alfa: 0.9, punteada: true });
			alternativas.push({ texto: `${NOMBRE_SUPUESTO[k]} · ${f.score(e.q.p50[11])}`, clase: `esc-${k}`, v: e.q.p50[11] / 10 });
		}
	} else if (esScore && d.pasados?.cuts[d.corte]) {
		// La regla está en un mes pasado: lo que el modelo preveía entonces (sin ver lo que vino después).
		const pc = d.pasados.cuts[d.corte];
		futuros.push({ granos: [], tono: TONO.tinta, alfa: 0.5, mediana: pc.q.p50, franja: pc.q, hitos: HITOS });
		etFuturo.t = `lo que se preveía en ${f.mesCorto(d.corte)}`;
		for (const hz of HITOS) if (hz <= pc.months.length) boyas.push({ h: hz, texto: `${f.score(pc.q.p50[hz - 1])} · ${q6(pc, hz - 1)}` });
	}

	// Dominio: el score siempre de 0 a 100 (las formas se comparan entre páginas).
	let lo = 0, hi = 100;
	if (!esScore) {
		const vs = [...pasado, ...despues].map((q) => q[1]).filter((v): v is number => v !== null);
		lo = vs.length ? Math.min(...vs) : 0; hi = vs.length ? Math.max(...vs) : 1;
		const mg = Math.max((hi - lo) * 0.1, Math.abs(hi) * 0.02, 1e-6);
		lo -= mg; hi += mg;
		if (lo > 0 && lo < (hi - lo) * 0.5) lo = 0;
	}
	const rejilla = esScore ? [0, 20, 40, 60, 80, 100] : marcasEje(lo, hi);
	const bandas = esScore ? d.man.bands.filter((b) => b.min > 0).map((b) => b.min / 10) : [];

	// En el grupo, las estelas finas de sus empresas; con un pilar señalado, el pilar.
	const hilos: [number, number | null][][] = [];
	if (empresasHilo && d.kind === 'group' && esScore && !o.pilar) {
		const g = d.ent as GrupoM;
		for (const em of g.companies) hilos.push(g.months.map((m, i) => [col(m.month), m.month <= d.corte && em.shown[i] != null ? em.shown[i]! / 10 : null] as [number, number | null]).filter((q) => q[0] >= 0));
	}
	const pilar = o.pilar && esScore ? d.ent.months.filter((m) => m.month <= d.corte).map((m) => [col(m.month), m.pillars.find((p) => p.key === o.pilar)?.score ?? null] as [number, number | null]).map(([c, v]) => [c, v === null ? null : v / 10] as [number, number | null]) : undefined;
	const avisos = esScore ? d.ent.alerts.filter((a) => a.state === 'fired' && a.month <= d.corte && /structural|drift/.test(a.kind)).map((a) => {
		const v = d.ent.months.find((m) => m.month === a.month)?.shown;
		return v === undefined ? null : { col: col(a.month), v: v / 10, mejora: a.kind.startsWith('improvement') };
	}).filter((x): x is { col: number; v: number; mejora: boolean } => !!x && x.col >= 0) : [];

	const hueco = h('div', { class: 'grafico-arena' });
	placa(hueco, (c): PlacaSerie => ({ tipo: 'serie', x: c.x, y: c.y, w: c.w, h: c.h, lo, hi, columnas, hoy, pasado, despues, hilos, futuros, lineas, bandas, rejilla, marcas, avisos, pilar }));
	caja.append(hueco);

	// La capa HTML con el mismo mapeo (porcentajes de la caja).
	const X = (c: number) => `${((c + 0.5) / columnas) * 100}%`;
	const Y = (v: number) => `${(1 - (v - lo) / (hi - lo)) * 100}%`;
	const eti = (clase: string, texto: string, x: string, y: string) => { const e = h('span', { class: `g-etq ${clase}` }, texto); e.style.left = x; e.style.top = y; caja.append(e); return e; };
	const fmtV = (v: number) => (esScore ? f.numero(v) : unidad === 'EUR' ? f.eurosCorto(v) : unidad === 'ratio' ? f.ratio(v) : `${f.numero(v, Math.abs(v) < 10 ? 1 : 0)}`);
	for (const v of rejilla) eti('eje-v', fmtV(v), '0', Y(v));
	for (const b of d.man.bands) if (esScore && b.min > 0) eti('eje-banda', b.label.toLowerCase(), '100%', Y((b.min + (d.man.bands[d.man.bands.indexOf(b) + 1]?.min ?? 1000)) / 20));
	if (esScore) eti('eje-banda', d.man.bands[0].label.toLowerCase(), '100%', Y(d.man.bands[1].min / 20));
	eti('eje-titulo-v', esScore ? 'score' : unidad === 'EUR' ? 'euros' : unidad || 'valor', '0', '0');
	// Con horizontes, el futuro se rotula con ellos y no con los meses: así no se pisan.
	cal.forEach((m, i) => { if (Math.abs(i - hoy) > 3 && (i - hoy) % 3 === 0 && !(i > hoy && boyas.length)) eti(`eje-m ${i > hoy ? 'fut' : ''}`, f.mesCorto(m), X(i), '100%'); });
	const etHoy = h('span', { class: 'g-etq eje-hoy' }, h('i', { class: 'asa-mini', 'aria-hidden': 'true' }, h('b'), h('b'), h('b')), `hoy · ${f.mesCorto(d.corte)}`);
	etHoy.style.left = X(hoy); caja.append(etHoy);
	// Las dos zonas, rotuladas: lo que ha pasado y lo que puede pasar.
	const zp = eti('zona-t pasado', 'lo que ha pasado', '0', '0'); void zp;
	const zfFondo = h('div', { class: 'zona-futuro' }); zfFondo.style.left = `${((hoy + 1) / columnas) * 100}%`; caja.prepend(zfFondo);
	if (etFuturo.t) { const zf = eti(`zona-t futuro ${etFuturo.clase}`, etFuturo.t, `${((hoy + 1) / columnas) * 100}%`, '0'); void zf; }
	if (despues.length && esScore) eti('zona-t despues', 'lo que pasó después', X(Math.min(columnas - 1, hoy + 1)), '14px');
	if (esScore && hayFuturo(d) && validado < 12) { const ev = eti('sin-validar', 'sin validar', X(hoy + validado + 1), '0'); ev.title = `La previsión está validada fuera de muestra hasta ${validado} meses. Más allá, el modelo no se ha podido comprobar con lo que pasó.`; }
	// Los horizontes, todos a la vista y en una fila: cuándo y qué se espera (mediana · franja del 80 %).
	for (const b of boyas) {
		const el = eti(`boya h${b.h} ${b.h === 12 ? 'fin' : ''}`, '', X(hoy + b.h), '100%');
		el.append(h('b', {}, b.h === 12 ? 'un año' : `${b.h} meses`), h('span', {}, b.texto));
		el.title = [cal[hoy + b.h] ? f.mes(cal[hoy + b.h]) : '', b.titulo].filter(Boolean).join(' · ');
	}
	let ultimoY = -Infinity;
	for (const a of alternativas.sort((x, y) => y.v - x.v)) {
		const yPx = Math.max((1 - (a.v - lo) / (hi - lo)) * o.alto, ultimoY + 14);
		ultimoY = yPx;
		eti(`alternativa ${a.clase}`, a.texto, X(hoy + 12), `${yPx}px`);
	}

	// El hilo de arena: cae por el mes que se señala y se lee el valor exacto.
	const lectura = h('span', { class: 'g-lectura' });
	const punto = h('span', { class: 'g-punto' });
	caja.append(lectura, punto);
	const leer = (ev: PointerEvent) => {
		const r = hueco.getBoundingClientRect();
		const c = Math.max(0, Math.min(columnas - 1, Math.floor(((ev.clientX - r.left) / r.width) * columnas)));
		const x = r.left + ((c + 0.5) / columnas) * r.width;
		const vPas = pasado.find((q) => q[0] === c)?.[1] ?? despues.find((q) => q[0] === c)?.[1] ?? null;
		let texto = f.mesCorto(cal[c]);
		let v: number | null = vPas;
		if (c > hoy) {
			const k = c - hoy - 1;
			const vivas = new Set([...o.acciones, ...(o.previa ?? [])]);
			const acc = (d.hor?.actions ?? []).find((a) => vivas.has(a.id));
			const e = hayFuturo(d) ? (acc ?? base) : d.pasados?.cuts[d.corte] ?? null;
			if (e && k < e.q.p50.length) {
				v = e.q.p50[k] / 10;
				texto += ` · previsto ${f.score(e.q.p50[k])} (entre ${f.score(e.q.p10[k])} y ${f.score(e.q.p90[k])})`;
				if (vPas !== null) texto += ` · pasó ${fmtV(vPas)}`;
			} else if (vPas !== null) texto += ` · ${fmtV(vPas)}`;
			else texto += ' · sin previsión';
		} else texto += v !== null ? ` · ${fmtV(v)}` : ' · sin dato';
		lectura.textContent = texto;
		lectura.style.left = `${((c + 0.5) / columnas) * 100}%`;
		lectura.classList.toggle('izq', c > columnas * 0.6);
		caja.classList.add('leyendo');
		if (v !== null) { punto.style.left = `${((c + 0.5) / columnas) * 100}%`; punto.style.top = `${(1 - (v - lo) / (hi - lo)) * 100}%`; punto.hidden = false; } else punto.hidden = true;
		o.alHilo?.([{ x0: x, y0: r.top - 2, x1: x, y1: r.bottom, tono: TONO.info }]);
	};
	hueco.addEventListener('pointermove', leer);
	hueco.addEventListener('pointerleave', () => { caja.classList.remove('leyendo'); o.alHilo?.([]); });
	return caja;
}

// ─── Sección · Scoring ────────────────────────────────────────

export function seccionScoring(d: DatosFicha, acc: Acciones, flota: HTMLElement | null): HTMLElement {
	const raiz = h('div', { class: 'sec-scoring' });
	if (!d.mes) { raiz.append(h('p', { class: 'vacio' }, `${nombreEntidad(d.kind, d.id)} no tiene datos en ${f.mes(d.corte)}. Su primer mes es ${f.mes(d.ent.first_month)}.`)); return raiz; }
	raiz.append(partitura(d, acc));
	if (flota) raiz.append(flota);
	raiz.append(seccion('De dónde sale', hilo(nudosScore(d, acc).slice(0, 3), true), (() => { const b = h('button', { type: 'button', class: 'as-enlace' }, 'Ver el hilo entero en Técnico'); b.addEventListener('click', () => acc.irSeccion('tecnico')); return b; })()));
	return raiz;
}

function partitura(d: DatosFicha, acc: Acciones): HTMLElement {
	const m = d.mes!;
	const filas = h('div', { class: 'partitura' });
	// El eje de las barras: de 0 a 100, con la referencia del motor explicada una vez.
	filas.append(h('div', { class: 'pt-eje', 'aria-hidden': 'true' }, h('span', { class: 'pt-eje-t' }, 'pilar'), h('span', {}), h('span', { class: 'pt-escala' }, ...[0, 20, 40, 60, 80, 100].map((v) => { const s = h('span', {}, String(v)); s.style.left = `${v}%`; return s; })), h('span', { class: 'pt-eje-t der' }, 'aporta')));
	const textosNota: string[] = [];
	for (const p of m.pillars) {
		const ref = d.man.pillars.find((x) => x.key === p.key)?.baseline ?? null;
		const gates = p.gates.map((g) => d.man.glossary.gates[g] ?? g);
		const llam: HTMLElement[] = [];
		for (const g of gates) { textosNota.push(g); llam.push(h('sup', { class: 'llamada' }, '¹²³⁴⁵⁶⁷⁸⁹'[textosNota.length - 1] ?? String(textosNota.length))); }
		const barra = h('div', { class: 'pt-barra' },
			h('span', { class: 'pt-lleno', style: { width: `${p.score === null ? 0 : p.score / 10}%` } }),
			ref !== null ? h('span', { class: 'pt-ref', style: { left: `${ref / 10}%` }, title: `Referencia del motor: ${f.score(ref)}` }) : null);
		const fila = h('div', { class: `pt-fila tocable ${p.score === null ? 'nulo' : ''}`, tabindex: '0', title: 'Pasa por encima para verlo en el horizonte; clic para su evidencia' },
			h('div', { class: 'pt-nombre' }, nombrePilar(d.man, p.key), ...llam, h('span', { class: 'pt-peso' }, ` ${f.porcentaje(p.w_eff, 0)}`)),
			h('div', { class: 'pt-score' }, p.score === null ? 'sin dato' : f.score(p.score)),
			barra,
			h('div', { class: `pt-aporta ${p.contrib < 0 ? 'neg' : p.contrib > 0 ? 'pos' : ''}` }, p.score === null ? '' : f.delta(p.contrib)),
			h('p', { class: 'pt-nota' }, p.note ?? ''));
		const ir = () => acc.irSeccion('tecnico', undefined, { pilar: p.key });
		fila.addEventListener('click', ir);
		fila.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
		if (p.score !== null) {
			fila.addEventListener('pointerenter', () => acc.horizonte.pilar(p.key));
			fila.addEventListener('pointerleave', () => acc.horizonte.pilar(null));
			fila.addEventListener('focus', () => acc.horizonte.pilar(p.key));
			fila.addEventListener('blur', () => acc.horizonte.pilar(null));
		}
		filas.append(fila);
	}
	filas.append(h('p', { class: 'pt-leyenda' }, h('i', { class: 'pt-ref-glifo', 'aria-hidden': 'true' }), 'referencia del motor para cada pilar'));
	const { notas } = llamadas(textosNota);
	return seccion('Qué aporta cada pilar', filas, notas);
}

/** Nudos del hilo del score: score → pilar que más resta → sus medidas → ficheros. */
export function nudosScore(d: DatosFicha, acc: Acciones): Nudo[] {
  const m = d.mes!;
  const nudos: Nudo[] = [
    {
      valor: f.score(m.shown),
      texto: "score",
      detalle: `base ${f.scoreDec(m.base)} · pilares ${f.delta(m.pillars.reduce((s, p) => s + p.contrib, 0))} · penalización ${f.delta(-m.penalty)} · tope ${f.delta(-m.cap.amount)}`,
    },
  ];
  const peor = [...m.pillars]
    .filter((p) => p.score !== null)
    .sort((a, b) => a.contrib - b.contrib)[0];
  if (!peor) return nudos;
  nudos.push({
    valor: f.delta(peor.contrib),
    texto: `${nombrePilar(d.man, peor.key).toLowerCase()} ${peor.contrib < 0 ? "resta" : "aporta"}`,
    detalle: peor.note ?? undefined,
    accion: () => acc.irSeccion("tecnico", undefined, { pilar: peor.key }),
  });
  const filas =
    d.evid?.months
      .find((x) => x.month === d.corte)
      ?.rows.filter((r) => r.pillar === peor.key) ?? [];
  for (const r of filas.slice(0, 3))
    nudos.push({
      valor: f.valorUnidad(r.value, r.unit),
      texto: r.label.charAt(0).toLowerCase() + r.label.slice(1),
      detalle: f.periodo(r.period),
      accion: () =>
        acc.irSeccion("tecnico", undefined, {
          pilar: peor.key,
          texto: r.label,
        }),
    });
  const ficheros = [...new Set(filas.map((r) => r.source_file))];
  if (ficheros.length)
    nudos.push({
      valor: f.plural(ficheros.length, "fichero", "ficheros"),
      texto: ficheros.join(" · "),
      detalle: filas.some((r) => r.n_rows)
        ? `${f.numero(Math.max(...filas.map((r) => r.n_rows ?? 0)))} filas en la ventana`
        : "medidas derivadas",
      accion: () =>
        acc.irSeccion("tecnico", undefined, {
          pilar: peor.key,
          fichero: ficheros[0],
        }),
    });
  return nudos;
}

// ─── Sección · Productos: la estantería de los siete ─────────
// Acciones dice qué hacer, ordenado por lo que sube el score. Productos dice con qué cuenta y qué le
// falta: siempre los siete, en el mismo orden, con sus contratos. La misma forma en todas las empresas.

export function seccionProductos(d: DatosFicha, acc: Acciones): HTMLElement {
	const raiz = h('div', { class: 'sec-productos' });
	if (!d.mes) { raiz.append(h('p', { class: 'vacio' }, `Sin datos en ${f.mes(d.corte)}.`)); return raiz; }
	if (d.kind === 'group') return productosGrupo(d, acc);
	const es = estados(d);
	if (!d.prodE) raiz.append(h('p', { class: 'aviso-datos' }, 'Falta products/ para esta empresa.'));
	const estante = h('div', { class: 'estanteria' });
	let familia = '';
	for (const e of es) {
		const p = producto(e.id);
		if (p.familia !== familia) { familia = p.familia; estante.append(h('h3', { class: 'est-familia' }, FAMILIAS[p.familia].nombre)); }
		const t = tenenciaDe(d).find((x) => x.product === e.id);
		const fila = h('div', { class: `est-fila inv-item estado-${e.estado}` });
		const estadoT = e.estado === 'tiene' ? (t?.source === 'movimientos' ? 'deducido de sus movimientos' : 'contratado') : e.estado === 'encaja' ? 'le encajaría' : e.estado === 'bloqueado' ? 'hoy no' : 'no consta';
		const cuerpo = h('div', { class: 'est-cuerpo' }, h('div', { class: 'est-cab' }, h('span', { class: 'inv-nombre' }, p.nombre), h('span', { class: 'est-estado' }, estadoT)));
		if (t) cuerpo.append(contratos(t));
		if (e.estado === 'encaja' || e.estado === 'bloqueado' || e.forma) cuerpo.append(h('p', { class: 'est-motivo' }, e.bloqueo ?? e.motivo));
		const efecto = h('div', { class: 'est-efecto' });
		if (e.accion && e.estado !== 'bloqueado') {
			const ha = d.hor?.actions?.find((a) => a.id === e.accion!.id);
			efecto.append(h('b', {}, `${f.delta(e.accion.uplift_tenths)}`), h('span', {}, ha && hayFuturo(d) ? `a 6 meses, ${f.score(ha.q.p50[5])}` : 'puntos'));
			fila.classList.add('tocable');
			fila.title = 'Pasa por encima para verlo en el horizonte; clic para marcar su acción';
			fila.addEventListener('pointerenter', () => acc.horizonte.previa([e.accion!.id]));
			fila.addEventListener('pointerleave', () => acc.horizonte.previa(null));
			fila.addEventListener('click', () => acc.irSeccion('acciones', e.accion!.id));
		}
		fila.append(h('div', { class: 'est-icono' }, iconoProducto(e.id, { tam: 44, estado: e.estado === 'tiene' && e.forma ? 'tiene' : e.estado, titulo: false })), cuerpo, efecto);
		estante.append(fila);
	}
	raiz.append(estante);
	const otras = d.prodE?.other_debt.filter((x) => !x.closed) ?? [];
	if (otras.length) raiz.append(seccion('Otras deudas', h('div', { class: 'tabla-caja' }, h('table', { class: 'tabla-sutil' },
		h('thead', {}, h('tr', {}, h('th', {}, 'Tipo'), h('th', {}, 'Entidad'), h('th', { class: 'num' }, 'Concedido'), h('th', { class: 'num' }, 'Pendiente'), h('th', { class: 'num' }, 'Interés'), h('th', {}, 'Próxima cuota'))),
		h('tbody', {}, ...otras.map((x) => h('tr', {}, h('td', {}, x.type_label), h('td', {}, x.bank ?? '—'), h('td', { class: 'num' }, f.eurosCorto(x.granted)), h('td', { class: 'num' }, f.eurosCorto(x.outstanding)), h('td', { class: 'num' }, x.rate === null ? '—' : `${f.numero(x.rate, 2)} %`), h('td', {}, x.next_payment ? f.mes(x.next_payment.slice(0, 7)) : '—'))))))));
	return raiz;
}

/** Los contratos de un producto: entidad, uso sobre el límite (con su escala) y tipo. */
function contratos(t: TenenciaM): HTMLElement {
	const lista = h('ul', { class: 'contratos' });
	for (const it of t.items.slice(0, 4)) {
		const uso = !it.inconsistent && it.usage !== null ? Math.max(0, Math.min(1, it.usage)) : null;
		lista.append(h('li', {},
			h('span', { class: 'ct-banco' }, it.bank ?? 'Entidad sin nombre'),
			uso !== null ? h('span', { class: 'ct-uso', title: `Dispuesto ${f.eurosCorto(it.outstanding ?? 0)} de ${f.eurosCorto(it.granted ?? 0)}` }, h('span', { class: 'ct-uso-barra' }, h('i', { style: { width: `${uso * 100}%` } })), h('span', { class: 'ct-uso-t' }, `${f.porcentaje(uso, 0)} de ${f.eurosCorto(it.granted ?? 0)}`))
				: h('span', { class: 'ct-dato' }, it.inconsistent ? 'límite y dispuesto incoherentes en el origen' : it.balance ? `saldo ${f.eurosCorto(it.balance)}` : it.granted !== null ? `límite ${f.eurosCorto(it.granted)}` : ''),
			h('span', { class: 'ct-dato' }, [it.rate !== null ? `${f.numero(it.rate, 2)} % ${it.rate_type ?? ''}`.trim() : '', it.since ? `desde ${f.mesCorto(it.since)}` : ''].filter(Boolean).join(' · '))));
	}
	const ev = (Array.isArray(t.evidence) ? t.evidence : [t.evidence]).find((x) => x.file === 'transactions.csv');
	if (ev) lista.append(h('li', { class: 'ct-mov' }, `${f.plural(ev.rows ?? 0, 'movimiento', 'movimientos')} de ${ev.first ? f.mesCorto(ev.first) : '—'} a ${ev.last ? f.mesCorto(ev.last) : '—'}${ev.amount_12m ? `, ${f.eurosCorto(ev.amount_12m)} en 12 meses` : ''}`));
	if (t.items[0]?.bank || t.source) lista.append(h('li', { class: 'ct-sello' }, sello(t.items[0]?.bank ?? null, t.source)));
	return lista;
}

function productosGrupo(d: DatosFicha, acc: Acciones): HTMLElement {
	const raiz = h('div', { class: 'sec-productos grupo' });
	const tabla = h('table', { class: 'matriz' });
	tabla.append(h('thead', {}, h('tr', {}, h('th', {}, 'Empresa'), ...PRODUCTOS.map((p) => h('th', { title: p.nombre }, iconoProducto(p.id, { tam: 30, titulo: false, sinFilete: true }), h('span', { class: 'mz-nombre' }, p.nombre))))));
	const cuerpo = h('tbody');
	for (const em of d.empresas) {
		const mes = em.ent?.months.find((m) => m.month === d.corte) ?? null;
		const es = mes && em.ent ? estadosProductos({ mes, man: d.man, tenencia: em.prod?.held ?? [], perfil: em.ent.profile, papel: em.ent.role, heredaLiquidez: em.ent.inherits_liquidity }) : [];
		const fila = h('tr', {}, h('td', {}, (() => { const b = h('button', { type: 'button', class: 'enlace-empresa' }, f.empresa(em.res.id), h('span', { class: 'mz-papel' }, em.res.role)); b.addEventListener('click', () => acc.abrirEmpresa(em.res.id)); return b; })()));
		for (const p of PRODUCTOS) {
			const e = es.find((x) => x.id === p.id);
			const estado = e?.estado ?? 'no_consta';
			fila.append(h('td', { class: `mz-celda estado-${estado}`, title: e ? `${p.nombre}: ${e.bloqueo ?? e.motivo}` : 'Sin datos este mes' }, iconoProducto(p.id, { tam: 28, estado, titulo: false, sinFilete: true })));
		}
		cuerpo.append(fila);
	}
	tabla.append(cuerpo);
	// La leyenda es la propia forma: los cuatro estados de un mismo grabado.
	const leyenda = h('div', { class: 'mz-leyenda' }, ...(['tiene', 'encaja', 'bloqueado', 'no_consta'] as const).map((s) => h('span', {}, iconoProducto('linea_credito' as never, { tam: 22, estado: s, titulo: false, sinFilete: true }), { tiene: 'lo tiene', encaja: 'le encajaría', bloqueado: 'hoy no', no_consta: 'no consta' }[s])));
	raiz.append(seccion('Qué tiene cada empresa y qué le encajaría', leyenda, h('div', { class: 'matriz-caja' }, tabla)));
	return raiz;
}

// ─── Sección · Acciones ───────────────────────────────────────

const CLAVE_ESTADOS = 'rumbo.acciones.v1';
type EstadoAccion = 'propuesta' | 'en curso' | 'hecha';
function leerEstados(): Record<string, EstadoAccion> { try { return JSON.parse(localStorage.getItem(CLAVE_ESTADOS) ?? '{}'); } catch { return {}; } }
function guardarEstado(clave: string, e: EstadoAccion) { const t = leerEstados(); t[clave] = e; try { localStorage.setItem(CLAVE_ESTADOS, JSON.stringify(t)); } catch { /* Sin almacenamiento, el estado dura solo esta sesión. */ } }

/** El efecto de una acción: la cifra del motor y la mediana prevista a seis meses con y sin ella. */
function efectoAccion(d: DatosFicha, a?: AccionM): string | null {
	if (!a) return null;
	const partes = [`${f.delta(a.uplift_tenths)} puntos según el motor`];
	const ha = d.hor?.actions?.find((x) => x.id === a.id);
	const hb = d.hor?.scenarios?.base;
	if (ha && hb && hayFuturo(d)) partes.push(`a seis meses, ${f.score(ha.q.p50[5])} en vez de ${f.score(hb.q.p50[5])}`);
	return partes.join(' · ');
}

export function seccionAcciones(d: DatosFicha, acc: Acciones): HTMLElement {
	const raiz = h('div', { class: 'sec-acciones' });
	const m = d.mes;
	if (!m) { raiz.append(h('p', { class: 'vacio' }, `Sin datos en ${f.mes(d.corte)}.`)); return raiz; }
	const recs = recomendaciones({ mes: m, man: d.man, tenencia: tenenciaDe(d), perfil: d.ent.profile, papel: d.kind === 'company' ? (d.ent as EmpresaM).role : null, heredaLiquidez: d.kind === 'company' ? (d.ent as EmpresaM).inherits_liquidity : false });
	const sel = acc.horizonte.elegidas();
	const lista = h('ol', { class: 'recomendaciones' });
	const estadosG = leerEstados();
	recs.forEach((r, i) => {
		const a = r.accion;
		const clave = `${d.id}:${d.corte}:${a.id}`;
		const marca = h('input', { type: 'checkbox', checked: sel.has(a.id), 'aria-label': `Ver en el horizonte: ${tituloAccion(a)}` }) as HTMLInputElement;
		marca.addEventListener('change', () => { acc.horizonte.alternar(a.id, marca.checked); li.classList.toggle('elegida', marca.checked); });
		const estadoSel = h('select', { class: 'sel-sutil', 'aria-label': 'Estado de la acción' }, ...(['propuesta', 'en curso', 'hecha'] as EstadoAccion[]).map((x) => h('option', { value: x, selected: (estadosG[clave] ?? 'propuesta') === x }, x)));
		estadoSel.addEventListener('change', () => { guardarEstado(clave, estadoSel.value as EstadoAccion); li.dataset.estado = estadoSel.value; });
		estadoSel.addEventListener('click', (ev) => ev.stopPropagation());
		const prods = r.productos.map((p) => iconoProducto(p, { tam: 24, titulo: true, sinFilete: true, estado: tenenciaDe(d).some((t) => t.product === p) ? 'tiene' : 'encaja' }));
		const li = h('li', { class: `rec ${sel.has(a.id) ? 'elegida' : ''}`, 'data-estado': estadosG[clave] ?? 'propuesta', 'data-accion': a.id },
			h('label', { class: 'rec-marca' }, marca, h('span', { class: 'rec-n' }, String(i + 1))),
			h('div', { class: 'rec-cuerpo' },
				h('div', { class: 'rec-titulo' }, tituloAccion(a)),
				h('p', { class: 'rec-texto' }, r.delGrupo ? `${explicacionAccion(a)} En una filial que financia el grupo, esto se decide en el grupo.` : explicacionAccion(a)),
				h('p', { class: 'rec-hechos' }, efectoAccion(d, a) ?? '', ' · ', ESFUERZO[a.effort], ' · ', `pilar de ${nombrePilar(d.man, a.pillar).toLowerCase()}`),
				prods.length ? h('p', { class: 'rec-productos' }, ...prods, ' ', r.productos.map((p) => producto(p).nombre.toLowerCase()).join(' o ')) : r.propia ? h('p', { class: 'rec-productos propia' }, r.propia) : null),
			h('div', { class: 'rec-efecto' }, h('b', {}, f.delta(a.uplift_tenths)), h('span', {}, 'puntos')),
			h('div', { class: 'rec-estado' }, estadoSel));
		// Tantear: pasar por encima ya lo enseña en el horizonte; marcar lo fija.
		li.addEventListener('pointerenter', () => acc.horizonte.previa([a.id]));
		li.addEventListener('pointerleave', () => acc.horizonte.previa(null));
		lista.append(li);
	});
	const base = d.hor?.scenarios?.base;
	if (base && hayFuturo(d)) {
		const peor = base.cross && base.cross.dir === 'down';
		const nada = h('li', { class: 'rec nada' }, h('span', { class: 'rec-marca' }, h('span', { class: 'rec-n' }, '—')),
			h('div', { class: 'rec-cuerpo' }, h('div', { class: 'rec-titulo' }, 'No hacer nada'),
				h('p', { class: 'rec-hechos' }, `a seis meses, entre ${f.score(base.q.p10[5])} y ${f.score(base.q.p90[5])}; lo más probable, ${f.score(base.q.p50[5])}`, peor && base.cross!.prob !== null ? ` · ${f.porcentaje(base.cross!.prob, 0)} de pasar a ${nombreBanda(d.man, base.cross!.to).toLowerCase()} hacia ${f.mes(base.cross!.month)}` : '')));
		nada.addEventListener('pointerenter', () => acc.horizonte.previa([]));
		nada.addEventListener('pointerleave', () => acc.horizonte.previa(null));
		lista.append(nada);
	}
	if (!recs.length) lista.prepend(h('li', { class: 'rec vacia' }, h('p', {}, m.abstain ? `El motor se abstiene este mes y no propone acciones: ${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason}` : !m.feed_live ? 'Sin datos del banco al día, el motor no propone acciones.' : 'El motor no encuentra este mes ninguna palanca que suba el score al menos medio punto.')));
	raiz.append(seccion(d.kind === 'group' ? 'Qué puede hacer el grupo' : 'Qué puede cambiar su rumbo', lista));
	if (d.kind === 'group') raiz.append(seccion('Lo que proponen sus empresas', accionesEmpresas(d, acc)));
	return raiz;
}

/** En la organización: las acciones de todas sus empresas, ordenadas por lo que suben según el motor. */
function accionesEmpresas(d: DatosFicha, acc: Acciones): HTMLElement {
	const filas = d.empresas.flatMap((em) => (em.ent?.months.find((m) => m.month === d.corte)?.actions ?? []).map((a) => ({ em, a })));
	filas.sort((x, y) => y.a.uplift_tenths - x.a.uplift_tenths);
	const lista = h('ul', { class: 'acciones-empresas' });
	for (const { em, a } of filas.slice(0, 12)) {
		const li = h('li', { class: 'tocable', tabindex: '0' }, h('b', {}, f.empresa(em.res.id)), h('span', { class: 'ae-titulo' }, tituloAccion(a)), h('span', { class: 'ae-efecto' }, `${f.delta(a.uplift_tenths)} en la empresa · ${ESFUERZO[a.effort]}`));
		const ir = () => acc.abrirEmpresa(em.res.id);
		li.addEventListener('click', ir);
		li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
		lista.append(li);
	}
	if (!filas.length) lista.append(h('li', { class: 'nota' }, 'Ninguna de sus empresas tiene acciones este mes.'));
	return lista;
}

export function lineaAviso(a: AlertaM, man: Manifiesto, umbral: number | null, conTriaje = false): HTMLElement {
	const mejora = a.kind === 'improvement_structural' || a.kind === 'improvement_drift';
	const t = triaje.de(a.id);
	const li = h('li', { class: `aviso ${mejora ? 'sube' : 'baja'} ${a.state} ${t ? `triaje-${t}` : ''}` }, h('span', { class: 'av-grano' }), h('span', { class: 'av-mes' }, f.mesCorto(a.month)),
		h('span', { class: 'av-texto', title: a.detail }, lineaAvisoM(a, man, umbral)),
		h('span', { class: 'av-estado', title: a.suppressed_by ? man.glossary.reasons[a.suppressed_by.reason] ?? a.suppressed_by.reason : undefined }, t === 'visto' ? `${ESTADO_AVISO[a.state]} · visto` : ESTADO_AVISO[a.state]));
	if (conTriaje) {
		const acciones = h('span', { class: 'av-triaje' });
		const boton = (texto: string, valor: 'visto' | 'descartado' | null) => { const b = h('button', { type: 'button', class: 'av-boton' }, texto); b.addEventListener('click', (ev) => { ev.stopPropagation(); triaje.fijar(a.id, valor); }); acciones.append(b); };
		if (t) boton('Restaurar', null);
		else { boton('Visto', 'visto'); boton('Descartar', 'descartado'); }
		li.append(acciones);
	}
	return li;
}

// ─── Todo junto ───────────────────────────────────────────────

export function contenidoSeccion(d: DatosFicha, sec: Seccion, acc: Acciones, filtro: FiltroEvidencia | null, flota: HTMLElement | null): HTMLElement {
	switch (sec) {
		case 'scoring': return seccionScoring(d, acc, flota);
		case 'productos': return seccionProductos(d, acc);
		case 'acciones': return seccionAcciones(d, acc);
		case 'tecnico': return seccionTecnica(d, acc, filtro);
	}
}

export { primeraMayuscula, vaciar };
