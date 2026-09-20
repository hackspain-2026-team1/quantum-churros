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
	AccionM, AlertaM, EmpresaM, EmpresaResumenM, EscenarioM, EvidenciaM, GrupoM, HorizonteM, HorizontesPasadosM, Manifiesto, MesM, PilarMesM,
	ParametrosM, ProductosEmpresaM, ProductosGrupoM, TenenciaM,
} from '../datos/contrato';
import { estadosProductos, recomendaciones, type EstadoProducto } from '../datos/encaje';
import { TIPOS_AVISO } from '../datos/monitorCartera';
import { f, primeraMayuscula } from '../datos/formato';
import { pendienteTheilSen } from '../datos/derivados';
import { FAMILIAS, PRODUCTOS, producto } from '../datos/productos';
import { ESFUERZO, ESTADO_AVISO, accionCorta, explicacionAccion, lineaAvisoM, movimiento, nombreBanda, nombrePilar, palancaDeAccion, tituloAccion, voz } from '../datos/redaccion';
import type { Seccion } from '../estado';
import { h, vaciar } from './dom';
import { conCifras, type Origen } from './cifras';
import { seguimientoAcciones } from './ejecuciones';
import { iconoProducto } from './iconos';
import { hilo, lineaEstado, llamadas, marcaBanco, seccion, sello, type Nudo } from './primitivos';
import { placa } from './registro';
import { seccionConciliacion, seccionTecnica } from './tecnico';
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
	/** Avisos de la organización, vistos desde una de sus empresas (vacío en la ficha del grupo). */
	avisosGrupo: AlertaM[];
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
		avisosGrupo: kind === 'company' ? (grupo as GrupoM).alerts : [],
	};
}

/** Cada banda con su color, también en la arena: crítico rojo, vigilancia ámbar, estable azul, sólido verde. */
export const TONO_BANDA: Record<string, number> = { critical: TONO.peligro, watch: TONO.aviso, stable: TONO.info, solid: TONO.exito };

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

/** De dónde sale lo que se dice de un pilar: fichero y filas de la evidencia de ese mes. */
function origenPilar(d: DatosFicha, acc: Acciones, pilar: string | null, que?: string): Origen {
	const filas = (d.evid?.months.find((x) => x.month === d.corte)?.rows ?? []).filter((r) => (pilar ? r.pillar === pilar : true));
	const fichero = [...new Set(filas.map((r) => r.source_file))][0];
	return {
		que, mes: d.corte, pilar: pilar ? nombrePilar(d.man, pilar) : null, fichero,
		filas: fichero ? filas.filter((r) => r.source_file === fichero).reduce((n, r) => n + (r.n_rows ?? 0), 0) || undefined : undefined,
		ir: d.evid ? () => acc.irSeccion('conciliacion', undefined, { pilar }) : undefined,
	};
}

// ─── 1. La cabecera: el número en su círculo ─────────────────

/** Desde una empresa, volver a su organización: un paso atrás, siempre a la vista. */
function botonVolver(nombre: string, ir: () => void): HTMLElement {
	const b = h('button', { type: 'button', class: 'volver-grupo', title: `Volver a ${nombre} (Esc)` }, nombre);
	b.addEventListener('click', ir);
	return b;
}

export function cabecera(d: DatosFicha, movil: boolean, acc: Acciones): HTMLElement {
	const nombre = nombreEntidad(d.kind, d.id);
	const m = d.mes;
	const grupo = d.kind === 'company' ? d.grupoMes : null;
	const circulo = h('div', { class: 'cab-circulo', role: 'img', 'aria-label': m ? `Score ${f.score(m.shown)} de 100, ${nombreBanda(d.man, m.band).toLowerCase()}${grupo ? `, su grupo ${f.score(grupo.shown)}` : ''}` : 'Sin score' });
	const numero = h('div', { class: 'cab-numeral', 'aria-label': m ? `Score ${f.score(m.shown)}` : 'Sin score' });
	circulo.append(numero);
	if (m) {
		const marcas: { v: number; tipo: 'pares' | 'grupo' }[] = [];
		if (d.pares) marcas.push({ v: d.pares.mediana / 10, tipo: 'pares' });
		if (grupo) marcas.push({ v: grupo.shown / 10, tipo: 'grupo' });
		placa(circulo, (c) => ({
			tipo: 'numeral', x: c.x, y: c.y, h: c.h, texto: f.score(m.shown),
			anillo: { cx: c.x + c.w / 2, cy: c.y + c.h / 2, r: Math.min(c.w, c.h) / 2 - 14, valor: m.shown / 10, bandas: d.man.bands.filter((b) => b.min > 0).map((b) => b.min / 10), tono: TONO_BANDA[m.band] ?? TONO.tinta, marcas },
		}));
		circulo.append(h('span', { class: `cab-banda banda-${m.band}` }, nombreBanda(d.man, m.band).toLowerCase()));
		if (grupo) circulo.append(h('span', { class: 'cab-grupo' }, ...conCifras(`Grupo ${f.score(grupo.shown)}`, { que: 'Score del grupo en este mes', mes: d.corte, ir: () => acc.abrirGrupo(d.grupoId) })));
		circulo.title = d.man.bands.map((b) => `${b.label} desde ${f.score(b.min)}`).join(' · ');
	}
	const sub: (Node | string)[] = [];
	if (d.kind === 'company') {
		sub.push((d.ent as EmpresaM).role);
		// El nombre de la organización es el camino de vuelta: desde una empresa se sube de un clic.
		sub.push(d.kind === 'company' ? botonVolver(f.grupo(d.grupoId), () => acc.abrirGrupo(d.grupoId)) : f.grupo(d.grupoId));
	} else sub.push(f.plural((d.ent as GrupoM).companies.length, 'empresa', 'empresas'));
	const pais = atributo(d, 'country'); if (pais) sub.push(pais.replace(/\s*\([A-Z]{2}\)/, ''));
	const sector = d.ent.context.industry?.label; if (sector) sub.push(sector);
	const lineaSub = h('p', { class: 'cab-sub' });
	sub.forEach((x, i) => { if (i) lineaSub.append(' · '); lineaSub.append(x); });
	const cab = h('header', { class: 'ficha-cab' }, circulo,
		h('div', { class: 'cab-texto' },
			h('h1', {}, nombre),
			lineaSub,
			m ? lineaEstado(d.man, m, null, true) : h('p', { class: 'cab-vacio' }, `Sin datos en ${f.mes(d.corte)}.`),
			m ? explicacion(d, acc) : null),
		avisosDelMes(d, acc));
	void movil;
	return cab;
}

/** Lo que el número no dice solo: qué pesa más y con quién se compara (las marcas del círculo). */
function explicacion(d: DatosFicha, acc: Acciones): HTMLElement {
	const m = d.mes!;
	const p = h('p', { class: 'cab-explica' });
	const peor = [...m.pillars].filter((x) => x.score !== null).sort((a, b) => a.contrib - b.contrib)[0];
	if (m.abstain) p.append(h('span', {}, `El motor se abstiene: ${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason}`));
	else if (peor && peor.contrib < 0) p.append(h('span', {}, ...conCifras(`Lo que más resta: ${nombrePilar(d.man, peor.key).toLowerCase()}, ${f.numero(Math.abs(peor.contrib) / 10, 1)} puntos.`, origenPilar(d, acc, peor.key, `Lo que resta el pilar de ${nombrePilar(d.man, peor.key).toLowerCase()} al score`))));
	if (d.pares) p.append(h('span', { class: 'cab-marca pares' }, h('i', { 'aria-hidden': 'true' }), ...conCifras(`las ${f.numero(d.pares.n)} de su tamaño: mediana ${f.score(d.pares.mediana)}`, { que: `Mediana de las entidades del mismo tramo de tamaño (${d.pares.tamano})`, mes: d.corte })));
	return p;
}

// ─── Los avisos, debajo del número ────────────────────────────
// Lo que el motor ha levantado este mes sobre la entidad abierta y, en una organización, sobre cada
// una de sus empresas. Van junto al número porque son lo único de la ficha que pide una decisión
// hoy; el detalle, los descartados y la historia entera siguen en la bandeja del Desglose.

interface AvisoFicha { a: AlertaM; empresa: string | null }

/** El color de cada aviso: lo grave en rojo, lo que se tuerce en ámbar, lo que sube en verde. */
const TONO_AVISO: Record<string, 'grave' | 'baja' | 'sube' | 'neutro'> = {
	level_critical: 'grave', deterioration_structural: 'grave', deterioration_drift: 'baja', cap_fired: 'baja',
	improvement_structural: 'sube', improvement_drift: 'sube', stale_feed: 'neutro',
};
/** El orden con el que se leen: primero lo que más pesa (el mismo del monitor de la cartera). */
const gravedad = (a: AlertaM) => { const i = TIPOS_AVISO.findIndex((x) => x.id === a.kind); return i < 0 ? TIPOS_AVISO.length : i; };

function avisosDeLaFicha(d: DatosFicha): AvisoFicha[] {
	const propios: AvisoFicha[] = d.ent.alerts.map((a) => ({ a, empresa: null }));
	if (d.kind !== 'group') return propios;
	return [...propios, ...d.empresas.flatMap((em) => (em.ent?.alerts ?? []).map((a) => ({ a, empresa: em.res.id })))];
}

export function avisosDelMes(d: DatosFicha, acc: Acciones): HTMLElement {
	const caja = h('section', { class: 'cab-avisos', 'aria-label': `Avisos de ${f.mes(d.corte)}` });
	const umbral = d.params?.alerts.critical_score ?? null;
	const hasta = avisosDeLaFicha(d).filter((x) => x.a.month <= d.corte);
	const delMes = hasta.filter((x) => x.a.month === d.corte);
	const disparados = delMes.filter((x) => x.a.state === 'fired')
		.sort((x, y) => gravedad(x.a) - gravedad(y.a) || Number(!!x.empresa) - Number(!!y.empresa) || x.a.shown - y.a.shown);
	const retenidos = delMes.filter((x) => x.a.state !== 'fired').length;
	const antes = hasta.filter((x) => x.a.month < d.corte && x.a.state === 'fired');
	const ultimoAntes = [...antes].sort((x, y) => y.a.month.localeCompare(x.a.month) || gravedad(x.a) - gravedad(y.a))[0] ?? null;
	// Desde una empresa, lo que se ha levantado sobre su organización: no es suyo, pero le toca.
	const enElGrupo = d.avisosGrupo.filter((a) => a.month === d.corte && a.state === 'fired').length;
	const MAX = 4;

	function fila(x: AvisoFicha, pasado = false): HTMLElement {
		const t = triaje.de(x.a.id);
		const cuerpo = h('span', { class: 'cav-cuerpo' });
		if (pasado) cuerpo.append(h('span', { class: 'av-mes' }, f.mesCorto(x.a.month)), ' · ');
		// En una organización cada aviso dice de quién es: de una empresa suya o del grupo entero.
		if (d.kind === 'group') {
			if (x.empresa) {
				const b = h('button', { type: 'button', class: 'av-ent', title: `Abrir ${f.empresa(x.empresa)}` }, f.empresa(x.empresa));
				b.addEventListener('click', (ev) => { ev.stopPropagation(); acc.abrirEmpresa(x.empresa!); });
				cuerpo.append(b, ' · ');
			} else cuerpo.append(h('span', { class: 'av-ent propio' }, 'el grupo'), ' · ');
		}
		cuerpo.append(h('span', { class: 'av-texto' }, lineaAvisoM(x.a, d.man, umbral)));
		const li = h('li', {
			class: `cav-aviso tono-${TONO_AVISO[x.a.kind] ?? 'neutro'}${pasado ? ' pasado' : ''}${t ? ` triaje-${t}` : ''}`, tabindex: '0',
			title: `${x.a.detail || x.a.title} · ${ESTADO_AVISO[x.a.state]}. Clic para la bandeja de avisos.`,
		}, h('span', { class: 'av-grano' }), cuerpo);
		const marca = h('span', { class: 'av-triaje' });
		const boton = (texto: string, valor: 'visto' | null) => {
			const b = h('button', { type: 'button', class: 'av-boton' }, texto);
			b.addEventListener('click', (ev) => { ev.stopPropagation(); triaje.fijar(x.a.id, valor); });
			marca.append(b);
		};
		if (t === 'visto') boton('Restaurar', null); else boton('Visto', 'visto');
		li.append(marca);
		const ir = () => acc.irBandeja();
		li.addEventListener('click', ir);
		li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
		return li;
	}

	function pintar() {
		vaciar(caja);
		// Lo descartado no vuelve a aparecer aquí: se queda en la bandeja, que es donde se restaura.
		const ver = disparados.filter((x) => triaje.de(x.a.id) !== 'descartado');
		const descartados = disparados.length - ver.length;
		const verTodos = h('button', { type: 'button', class: 'as-enlace' }, 'Ver todos');
		verTodos.addEventListener('click', () => acc.irBandeja());
		// Ni el mes ni la cuenta: el mes ya lo dicen la regla y la ficha, y lo que está aquí es
		// justo lo que queda por revisar.
		caja.append(h('header', { class: 'cav-cab' }, h('h2', {}, 'Avisos'), h('span', { class: 'hueco' }), verTodos));
		if (ver.length) {
			const lista = h('ul', { class: 'cav-lista' });
			for (const x of ver.slice(0, MAX)) lista.append(fila(x));
			caja.append(lista);
		} else {
			caja.append(h('p', { class: 'cav-nada' }, 'Ningún aviso este mes.'));
			// Sin avisos este mes se enseña el último que hubo: el bloque nunca se queda en blanco.
			if (ultimoAntes) caja.append(h('ul', { class: 'cav-lista' }, fila(ultimoAntes, true)));
		}
		// La cola: lo que no cabe, lo que el motor retuvo y lo que ya pasó. Todo lleva a la bandeja.
		const resto: string[] = [];
		if (ver.length > MAX) resto.push(`${f.numero(ver.length - MAX)} más`);
		if (retenidos) resto.push(`${f.numero(retenidos)} sin disparar`);
		if (descartados) resto.push(`${f.numero(descartados)} ${descartados === 1 ? 'descartado' : 'descartados'}`);
		if (antes.length) resto.push(ver.length
			? `${f.numero(antes.length)} antes, el último en ${f.mes(ultimoAntes!.a.month)}`
			: `${f.numero(antes.length)} en los meses anteriores`);
		if (resto.length) {
			const mas = h('button', { type: 'button', class: 'cav-mas' }, resto.join(' · '));
			mas.addEventListener('click', () => acc.irBandeja());
			caja.append(mas);
		}
		// El aviso de la organización no es de la empresa: se dice aparte y lleva a su ficha.
		if (enElGrupo) {
			const ir = h('button', { type: 'button', class: 'cav-mas grupo' }, `${f.grupo(d.grupoId)}, ${f.plural(enElGrupo, 'aviso', 'avisos')}`);
			ir.addEventListener('click', () => acc.abrirGrupo(d.grupoId));
			caja.append(ir);
		}
	}

	triaje.oir(() => { if (caja.isConnected) pintar(); });
	pintar();
	return caja;
}

// ─── 2. El horizonte ──────────────────────────────────────────

export interface OpcionesGrafico {
	metrica: string; // 'score' o la clave de una serie
	/** Acciones fijadas y en vista previa. */
	acciones: Set<string>;
	previa: string[] | null;
	/** Escenario definido; los otros se ven sueltos y en su color. */
	escenario: 'base' | 'drift' | 'stress';
	/** Un pilar señalado desde la sección de scoring. */
	pilar: string | null;
	/** Dibujar la tendencia Theil–Sen del score sobre la zona pasada (solo metrica 'score'). */
	tendencia: boolean;
	alto: number;
	/** Primer mes del intervalo de la regla; vacío si la regla está en un mes suelto. */
	desde?: string;
	alHilo?: (hs: Hilo[]) => void;
	/** Tocar la arena del futuro o una etiqueta elige el escenario más cercano. */
	alElegir?: (e: OpcionesGrafico['escenario']) => void;
}

type Escenario = OpcionesGrafico['escenario'];
const ESCENARIOS: Escenario[] = ['base', 'drift', 'stress'];
const NOMBRE_ESCENARIO = { base: 'Si todo sigue igual', drift: 'Si sigue al mismo ritmo', stress: 'Si se repite su peor trimestre' } as const;
const CORTO_ESCENARIO = { base: 'todo igual', drift: 'mismo ritmo', stress: 'peor trimestre' } as const;
const TONO_ESCENARIO = { base: TONO.tinta, drift: TONO.tellme, stress: TONO.ocre } as const;
/** Cuánto tarda en notarse una acción, dicho como se dice. */
const PLAZO = (m: number) => (m === 1 ? 'a un mes' : m === 12 ? 'a un año' : `a ${f.numero(m)} meses`);

/**
 * Percentil de un escenario en el mes m (0 = el primero previsto). Los supuestos solo
 * traen la mediana: la franja sale entonces de sus propios granos de ese mes, o de la mediana.
 */
function cuantil(e: { q: { p50: number[] } & Partial<Record<'p10' | 'p90', number[]>>; grains?: [number, number][] }, k: 'p10' | 'p50' | 'p90', m: number): number {
	const q = e.q[k];
	if (q) return q[m];
	const v = (e.grains ?? []).filter((g) => g[0] === m + 1).map((g) => g[1]).sort((a, b) => a - b);
	if (!v.length) return e.q.p50[m];
	return v[Math.min(v.length - 1, Math.max(0, Math.round((k === 'p10' ? 0.1 : k === 'p90' ? 0.9 : 0.5) * (v.length - 1))))];
}
const marcasEje = (lo: number, hi: number) => {
	const paso = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1e6].find((p) => (hi - lo) / p <= 5) ?? 1e7;
	const out: number[] = [];
	for (let v = Math.ceil(lo / paso) * paso; v <= hi + 1e-9; v += paso) out.push(v);
	return out;
};

/** El horizonte: un calendario fijo (todos los meses del bundle más doce) que cruza el mes de la regla. */
export function graficoHorizonte(d: DatosFicha, o: OpcionesGrafico, empresasHilo = false): HTMLElement {
	const caja = h('div', { class: 'grafico', style: { height: `${o.alto}px` } });
	// El calendario empieza en el mes que dice la regla, así que elegir un intervalo acerca el gráfico.
	const inicio = o.desde ? Math.max(0, d.man.months.indexOf(o.desde)) : 0;
	const cal = d.man.months.slice(inicio);
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
	despues = despues.filter((q) => q[0] >= 0);

	const futuros: Futuro[] = [];
	const lineas: LineaSerie[] = [];
	const marcas: [number, number][] = [];
	const etFuturo: { t: string; clase: string } = { t: '', clase: '' };
	const boyas: { h: number; texto: string; titulo?: string }[] = [];
	const HITOS = [3, 6, 12];
	/** El punto de cada acción en el calendario: cuándo se nota y con qué score. */
	const hitos: { col: number; v: number; texto: string; titulo: string }[] = [];
	const alternativas: { texto: string; clase: string; v: number; k: Escenario }[] = [];
	const validado = d.validado || 12;
	const base = d.hor?.scenarios?.base;
	// La franja del 80 %. Los supuestos que solo traen la mediana no la tienen: entonces se calla,
	// porque «76–76» se lee como una franja que no existe.
	const q6 = (e: { q: { p50: number[] } & Partial<Record<'p10' | 'p90', number[]>>; grains?: [number, number][] }, k: number) => {
		const p10 = cuantil(e, 'p10', k), p90 = cuantil(e, 'p90', k);
		return p10 === p90 ? '' : `${f.score(p10)}–${f.score(p90)}`;
	};
	const elegido: Escenario = hayFuturo(d) && d.hor!.scenarios?.[o.escenario] ? o.escenario : 'base';

	// La tendencia Theil–Sen: la misma pendiente robusta que nombra la deriva lenta en «Qué está
	// pasando», anclada en el corte y dibujada hacia atrás sobre los meses que la sostienen.
	// Descriptiva y pasada: nunca entra en el score ni en la previsión (ENGINE.md, «Slow drift»).
	if (esScore && o.tendencia && !o.pilar) {
		const idx = d.ent.months.findIndex((m) => m.month === d.corte);
		const serie = d.ent.months.map((m) => (m.month <= d.corte ? m.shown : null));
		const pend = idx >= 0 ? pendienteTheilSen(serie, idx) : null;
		if (pend !== null && serie[idx] != null) {
			let primero = Math.max(0, idx - 11);
			while (primero < idx && serie[primero] == null) primero++;
			const cDesde = col(d.ent.months[primero].month);
			// La regla puede enseñar solo un intervalo corto. El cálculo sigue usando doce meses,
			// pero la recta se recorta al primer mes visible en vez de desaparecer entera.
			const cVisible = Math.max(cDesde, 0);
			const idxVisible = d.ent.months.findIndex((m) => m.month === cal[cVisible]);
			if (idxVisible >= 0 && cVisible < hoy) {
				const valor = (k: number) => serie[idx]! / 10 + pend * (k - idx);
				lineas.push({ puntos: [[cVisible, valor(idxVisible)], [hoy, valor(idx)]], tono: TONO.tellme, alfa: 1, punteada: false, grosor: 1.5 });
			}
		}
	}
	if (esScore && hayFuturo(d) && base) {
		const vivas = new Set([...o.acciones, ...(o.previa ?? [])]);
		const accs = (d.hor!.actions ?? []).filter((a) => vivas.has(a.id));
		// La franja de la previsión y su mediana: una retícula regular en vez de la nube de trayectorias.
		const abanico = (e: EscenarioM, tono: number, alfa: number): Futuro => ({ granos: [], tono, alfa, mediana: e.q.p50, franja: e.q, validado, hitos: HITOS });
		if (accs.length) {
			// La referencia es el caso que se está mirando, no siempre «si sigue al mismo ritmo»:
			// comparar contra otro caso hacía leer como caída lo que solo era cambiar de supuesto.
			const tendencia = d.hor!.scenarios![elegido] ?? base;
			const tonoTendencia = TONO_ESCENARIO[elegido];
			const p10 = 'p10' in tendencia.q ? tendencia.q.p10 : [];
			const p90 = 'p90' in tendencia.q ? tendencia.q.p90 : [];
			if (p10.length) lineas.push({ puntos: p10.map((v, i) => [hoy + i + 1, v / 10]), tono: tonoTendencia, alfa: 0.4, punteada: true });
			if (p90.length) lineas.push({ puntos: p90.map((v, i) => [hoy + i + 1, v / 10]), tono: tonoTendencia, alfa: 0.4, punteada: true });
			lineas.push({ puntos: [[hoy, d.mes!.shown / 10], ...tendencia.q.p50.map((v, i) => [hoy + i + 1, v / 10] as [number, number])], tono: tonoTendencia, alfa: 0.9, punteada: true });
			// Los otros casos no desaparecen al marcar una acción: siguen dibujados, tenues, y los
			// tres llevan su score a un año al borde derecho. Así se ve la acción contra todos.
			for (const k of ESCENARIOS) {
				const raw = d.hor!.scenarios![k];
				if (!raw) continue;
				if (k !== elegido) lineas.push({ puntos: [[hoy, d.mes!.shown / 10], ...raw.q.p50.map((v, i) => [hoy + i + 1, v / 10] as [number, number])], tono: TONO_ESCENARIO[k], alfa: 0.38, punteada: true, grosor: 0.7 });
				if (raw.q.p50[11] != null) alternativas.push({ texto: `${CORTO_ESCENARIO[k]} · ${f.score(raw.q.p50[11])}`, clase: `esc-${k} ${k === elegido ? 'actual' : ''}`, v: raw.q.p50[11] / 10, k });
			}
			const principal = accs.length === 1 ? accs[0] : accs.reduce((a, b) => (a.q.p50[5] > b.q.p50[5] ? a : b));
			// La principal, con su franja; las demás marcadas, solo su mediana.
			for (const a of accs) futuros.push(a === principal ? abanico(a, TONO.info, 0.72) : { granos: [], tono: TONO.info, alfa: 0.15, mediana: a.q.p50 });
			// Cada acción tarda lo suyo en notarse: se marca el punto a esa distancia, con su score.
			for (const a of accs) {
				const lag = Math.min(Math.max(1, a.lag_months), a.q.p50.length);
				const v = a.q.p50[lag - 1] / 10;
				marcas.push([hoy + lag, v]);
				const ficha = d.mes!.actions?.find((x) => x.id === a.id);
				hitos.push({ col: hoy + lag, v, texto: `${PLAZO(lag)} · ${f.score(a.q.p50[lag - 1])}`, titulo: `${ficha ? tituloAccion(ficha) : a.id}: el motor la da por hecha en ${f.mes(cal[Math.min(cal.length - 1, hoy + lag)])}` });
			}
			// Varias juntas: el motor da una cifra combinada; se marca donde ya están todas hechas.
			const ids = accs.map((a) => a.id).sort().join();
			const combo = accs.length > 1 ? d.hor!.combos?.find((c) => [...c.ids].sort().join() === ids)?.new_score : undefined;
			if (combo !== undefined) {
				const lag = Math.max(...accs.map((a) => Math.max(1, a.lag_months)));
				marcas.push([hoy + lag, combo / 10]);
				hitos.push({ col: hoy + lag, v: combo / 10, texto: `las ${accs.length} juntas · ${f.score(combo)}`, titulo: `Las ${accs.length} acciones marcadas, según el motor` });
			}
			for (const hz of HITOS) {
				const k = hz - 1;
				const dif = Math.round((principal.q.p50[k] - tendencia.q.p50[k]) / 10);
				boyas.push({ h: hz, texto: `${f.score(tendencia.q.p50[k])} → ${f.score(principal.q.p50[k])}${dif === 0 ? '' : ` (${dif > 0 ? '+' : '−'}${Math.abs(dif)})`}`, titulo: `Sin hacer nada (${NOMBRE_ESCENARIO[elegido].toLowerCase()}) → con ${accs.length > 1 ? 'la mejor de las acciones marcadas' : 'la acción'}` });
			}
			etFuturo.t = o.previa?.length && !o.previa.every((x) => o.acciones.has(x)) ? 'vista previa · con esta acción' : accs.length > 1 ? `con ${accs.length} acciones` : 'con la acción marcada';
			etFuturo.clase = 'con-acciones';
		} else {
			// Los tres a la vez: el elegido, definido y con su mediana; los otros, sueltos y en su color.
			for (const k of ESCENARIOS) {
				const raw = d.hor!.scenarios![k];
				if (!raw) continue;
				const es = k === elegido;
				const granos = 'grains' in raw && raw.grains?.length ? raw.grains : [];
				if (granos.length) {
					// El que se mira, en abanico; los otros, solo su mediana, para que no ensucien la gráfica.
					futuros.push(es ? abanico(raw as EscenarioM, TONO_ESCENARIO[k], 0.55) : { granos: [], tono: TONO_ESCENARIO[k], alfa: 0.22, mediana: raw.q.p50 });
				} else {
					lineas.push({ puntos: [[hoy, d.mes!.shown / 10], ...raw.q.p50.map((v, i) => [hoy + i + 1, v / 10] as [number, number])], tono: TONO_ESCENARIO[k], alfa: es ? 0.95 : 0.72, punteada: !es, grosor: es ? 1.1 : 0.8 });
				}
				if (raw.q.p50[11] != null) alternativas.push({ texto: `${CORTO_ESCENARIO[k]} · ${f.score(raw.q.p50[11])}`, clase: `esc-${k} ${es ? 'actual' : ''}`, v: raw.q.p50[11] / 10, k });
			}
			const esc = d.hor!.scenarios![elegido] ?? base;
			for (const hz of [3, 6, 12]) {
				const k = hz - 1;
				if (k >= esc.q.p50.length) continue;
				const b = 'bands' in esc ? esc.bands[`h${hz}` as 'h3' | 'h6' | 'h12'] : undefined;
				const franja = q6(esc, k);
				boyas.push({ h: hz, texto: `${f.score(esc.q.p50[k])}${franja ? ` · ${franja}` : ''}`, titulo: b ? d.man.bands.map((x) => `${x.label} ${f.porcentaje(b[x.key] ?? 0, 0)}`).join(' · ') : undefined });
			}
			etFuturo.t = `previsto · ${NOMBRE_ESCENARIO[elegido].toLowerCase()}`;
		}
	} else if (esScore && d.pasados?.cuts[d.corte]) {
		// La regla está en un mes pasado: lo que el modelo preveía entonces (sin ver lo que vino después).
		const pc = d.pasados.cuts[d.corte];
		futuros.push({ granos: [], tono: TONO.tinta, alfa: 0.5, mediana: pc.q.p50, franja: pc.q, hitos: HITOS });
		etFuturo.t = `lo que se preveía en ${f.mesCorto(d.corte)}`;
		for (const hz of HITOS) if (hz <= pc.months.length) { const fr = q6(pc, hz - 1); boyas.push({ h: hz, texto: `${f.score(pc.q.p50[hz - 1])}${fr ? ` · ${fr}` : ''}` }); }
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
	// Los tres horizontes se eligen en la gráfica misma. La arena va en lienzo y no se deja señalar
	// grano a grano, así que encima va esta capa de trazos: no recibe el ratón —lo recibe la
	// gráfica entera, que ya lee el hilo de arena— y solo enciende el horizonte señalado.
	const NS = 'http://www.w3.org/2000/svg';
	const capaHz = document.createElementNS(NS, 'svg');
	capaHz.setAttribute('class', 'g-horizontes');
	capaHz.setAttribute('viewBox', `0 0 ${columnas} 1000`);
	capaHz.setAttribute('preserveAspectRatio', 'none');
	capaHz.setAttribute('aria-hidden', 'true');
	caja.append(capaHz);
	const trazos = {} as Partial<Record<Escenario, SVGPathElement>>;
	if (esScore && hayFuturo(d) && d.mes) {
		const uX = (c: number) => c + 0.5;
		const uY = (v: number) => (1 - (v - lo) / (hi - lo)) * 1000;
		for (const k of ESCENARIOS) {
			const raw = d.hor!.scenarios![k];
			if (!raw) continue;
			const puntos = [[hoy, d.mes.shown / 10] as [number, number], ...raw.q.p50.map((v, i) => [hoy + i + 1, v / 10] as [number, number])];
			const t = document.createElementNS(NS, 'path');
			t.setAttribute('class', `hz hz-${k}`);
			t.setAttribute('d', puntos.map(([c, v], i) => `${i ? 'L' : 'M'}${uX(c).toFixed(3)} ${uY(v).toFixed(2)}`).join(' '));
			t.setAttribute('vector-effect', 'non-scaling-stroke');
			capaHz.append(t);
			trazos[k] = t;
		}
	}
	for (const v of rejilla) eti('eje-v', fmtV(v), '0', Y(v));
	for (const b of d.man.bands) if (esScore && b.min > 0) eti(`eje-banda banda-${b.key}`, b.label.toLowerCase(), '100%', Y((b.min + (d.man.bands[d.man.bands.indexOf(b) + 1]?.min ?? 1000)) / 20));
	if (esScore) eti(`eje-banda banda-${d.man.bands[0].key}`, d.man.bands[0].label.toLowerCase(), '100%', Y(d.man.bands[1].min / 20));
	eti('eje-titulo-v', esScore ? 'score' : unidad === 'EUR' ? 'euros' : unidad || 'valor', '0', '0');
	// Con horizontes, el futuro se rotula con ellos y no con los meses: así no se pisan.
	cal.forEach((m, i) => { if (Math.abs(i - hoy) > 3 && (i - hoy) % 3 === 0 && !(i > hoy && boyas.length)) eti(`eje-m ${i > hoy ? 'fut' : ''}`, f.mesCorto(m), X(i), '100%'); });
	const etHoy = h('span', { class: 'g-etq eje-hoy' }, h('i', { class: 'asa-mini', 'aria-hidden': 'true' }, h('b'), h('b'), h('b')), `hoy · ${f.mesCorto(d.corte)}`);
	etHoy.style.left = X(hoy); caja.append(etHoy);
	// Las dos zonas, rotuladas: lo que ha pasado y lo que puede pasar.
	const zp = eti('zona-t pasado', 'lo que ha pasado', '0', '0'); void zp;
	const zfFondo = h('div', { class: 'zona-futuro' }); zfFondo.style.left = `${((hoy + 1) / columnas) * 100}%`; caja.prepend(zfFondo);
	if (etFuturo.t) {
		const zf = eti(`zona-t futuro ${etFuturo.clase}`, etFuturo.t, `${((hoy + 1) / columnas) * 100}%`, '0');
		// Ya no hay botones de supuesto: se dice aquí que los tres casos están dibujados y se tocan.
		if (o.alElegir) zf.title = 'Los tres casos están dibujados. Pasa el ratón por el futuro y se enciende el que tienes más cerca; tócalo, o toca su rótulo, para mirarlo definido.';
	}
	if (despues.length && esScore) eti('zona-t despues', 'lo que pasó después', X(Math.min(columnas - 1, hoy + 1)), '14px');
	if (esScore && hayFuturo(d) && validado < 12) { const ev = eti('sin-validar', 'sin validar', X(hoy + validado + 1), '0'); ev.title = `La previsión está validada fuera de muestra hasta ${validado} meses. Más allá, el modelo no se ha podido comprobar con lo que pasó.`; }
	// Los horizontes, todos a la vista y en una fila: cuándo y qué se espera (mediana · franja del 80 %).
	for (const b of boyas) {
		const el = eti(`boya h${b.h} ${b.h === 12 ? 'fin' : ''}`, '', X(hoy + b.h), '100%');
		el.append(h('b', {}, b.h === 12 ? 'un año' : `${b.h} meses`), h('span', {}, b.texto));
		el.title = [cal[hoy + b.h] ? f.mes(cal[hoy + b.h]) : '', b.titulo].filter(Boolean).join(' · ');
	}
	// El nombre del caso elegido y «sin validar» comparten renglón: con los nombres largos se
	// pisan, y entonces «sin validar» baja una fila.
	if (caja.querySelector('.sin-validar')) requestAnimationFrame(() => {
		const a = caja.querySelector('.zona-t.futuro')?.getBoundingClientRect();
		const b = caja.querySelector('.sin-validar')?.getBoundingClientRect();
		caja.classList.toggle('sin-validar-baja', !!a && !!b && b.left < a.right + 8);
	});
	// Con una acción marcada los rótulos crecen («75 → 67 (−8)») y se pisan: entonces, y solo
	// entonces, el de seis meses baja una fila.
	if (boyas.length > 1) requestAnimationFrame(() => {
		const els = [...caja.querySelectorAll<HTMLElement>('.g-etq.boya')].map((x) => x.getBoundingClientRect());
		const chocan = els.some((r, i) => i > 0 && r.left < els[i - 1].right + 6);
		caja.classList.toggle('boyas-escalonadas', chocan);
	});
	// El punto de cada acción: a qué distancia se nota y con qué score. Dos rótulos solo se apilan
	// si además caen a la misma altura; si no, cada uno se queda sobre su punto.
	const puestos: { col: number; v: number }[] = [];
	for (const q of hitos) {
		const n = puestos.filter((x) => x.col === q.col && Math.abs(x.v - q.v) < 9).length;
		puestos.push({ col: q.col, v: q.v });
		const x = X(Math.min(columnas - 1, q.col)), y = Y(q.v);
		const pto = h('span', { class: 'g-hito-pto', 'aria-hidden': 'true' });
		pto.style.left = x; pto.style.top = y;
		caja.append(pto);
		const et = eti(`hito-accion ${q.col > columnas - 4 ? 'izq' : ''}`, q.texto, x, y);
		et.style.marginTop = `${-n * 18}px`;
		et.title = q.titulo;
	}
	// El rótulo de cada horizonte, al borde derecho: dice cuál es y en cuánto acaba el año. Con el
	// ratón encendido son los tres botones del supuesto, que antes vivían fuera de la gráfica.
	const etqs = {} as Partial<Record<Escenario, HTMLElement>>;
	const rotulos = h('div', { class: 'g-horizontes-etq', role: o.alElegir ? 'group' : undefined, 'aria-label': o.alElegir ? 'Qué pasaría si: el horizonte que se mira' : undefined });
	caja.append(rotulos);
	let ultimoY = -Infinity;
	for (const a of alternativas.sort((x, y) => y.v - x.v)) {
		const yPx = Math.max((1 - (a.v - lo) / (hi - lo)) * o.alto, ultimoY + 14);
		ultimoY = yPx;
		const actual = a.clase.includes('actual');
		const et = o.alElegir
			? h('button', { type: 'button', class: `g-etq alternativa ${a.clase}`, 'aria-pressed': String(actual) }, a.texto)
			: h('span', { class: `g-etq alternativa ${a.clase}` }, a.texto);
		et.style.left = X(hoy + 12); et.style.top = `${yPx}px`;
		et.title = `${NOMBRE_ESCENARIO[a.k]}${actual ? ', el caso que estás mirando' : ''}: a un año, sin hacer nada, entre ${f.score(cuantil(d.hor!.scenarios![a.k]!, 'p10', 11))} y ${f.score(cuantil(d.hor!.scenarios![a.k]!, 'p90', 11))}.${actual ? '' : ' Toca para verlo definido.'}`;
		rotulos.append(et);
		etqs[a.k] = et;
	}
	/** Cuál de los tres pasa más cerca del punto señalado: el que se enciende y el que se elige. */
	const cercano = (c: number, v: number): Escenario | null => {
		const m = c - hoy - 1;
		if (m < 0 || !d.hor?.scenarios) return null;
		let mejor: Escenario | null = null, dm = Infinity;
		for (const k of ESCENARIOS) {
			const e = d.hor.scenarios[k];
			if (!e || e.q.p50[m] == null) continue;
			const dd = Math.abs(e.q.p50[m] / 10 - v);
			if (dd < dm) { dm = dd; mejor = k; }
		}
		return mejor;
	};
	let senalado: Escenario | null = null;
	const senalar = (k: Escenario | null) => {
		if (k === senalado) return;
		senalado = k;
		for (const j of ESCENARIOS) {
			trazos[j]?.classList.toggle('senalado', j === k);
			etqs[j]?.classList.toggle('senalada', j === k);
		}
	};
	if (o.alElegir && alternativas.length) {
		caja.classList.add('elegible');
		for (const k of ESCENARIOS) {
			const et = etqs[k];
			if (!et) continue;
			et.addEventListener('pointerenter', () => senalar(k));
			et.addEventListener('focus', () => senalar(k));
			et.addEventListener('blur', () => senalar(null));
			et.addEventListener('click', (ev) => { ev.stopPropagation(); if (k !== elegido) o.alElegir!(k); });
		}
		caja.addEventListener('click', (ev) => {
			const r = caja.getBoundingClientRect();
			const c = Math.floor(((ev.clientX - r.left) / r.width) * columnas);
			const v = hi - ((ev.clientY - r.top) / r.height) * (hi - lo);
			const mejor = cercano(c, v);
			if (mejor && mejor !== elegido) o.alElegir!(mejor);
		});
	}

	// El hilo de arena: cae por el mes que se señala y se lee el valor exacto.
	const lectura = h('span', { class: 'g-lectura' });
	const punto = h('span', { class: 'g-punto' });
	caja.append(lectura, punto);
	const leer = (ev: PointerEvent) => {
		const r = hueco.getBoundingClientRect();
		const c = Math.max(0, Math.min(columnas - 1, Math.floor(((ev.clientX - r.left) / r.width) * columnas)));
		const x = r.left + ((c + 0.5) / columnas) * r.width;
		// En el futuro, el horizonte que pasa más cerca del ratón se enciende: es el que se elige.
		// Sobre un rótulo manda el rótulo, que ya ha encendido el suyo.
		const vRaton = hi - ((ev.clientY - r.top) / r.height) * (hi - lo);
		if (!(ev.target as Element | null)?.closest?.('.g-etq.alternativa')) senalar(c > hoy ? cercano(c, vRaton) : null);
		caja.classList.toggle('en-futuro', !!senalado);
		const vPas = pasado.find((q) => q[0] === c)?.[1] ?? despues.find((q) => q[0] === c)?.[1] ?? null;
		let texto = f.mesCorto(cal[c]);
		let v: number | null = vPas;
		if (c > hoy) {
			const k = c - hoy - 1;
			const vivas = new Set([...o.acciones, ...(o.previa ?? [])]);
			const acc = (d.hor?.actions ?? []).find((a) => vivas.has(a.id));
			// Sin acción marcada, el globo lee el horizonte señalado y lo nombra: leer «previsto 76»
			// sin decir de cuál de los tres era la cifra no significaba nada.
			const sup = senalado ?? elegido;
			const e = hayFuturo(d) ? (acc ?? d.hor!.scenarios![sup] ?? base) : d.pasados?.cuts[d.corte] ?? null;
			if (e && k < e.q.p50.length) {
				v = e.q.p50[k] / 10;
				if (!acc && hayFuturo(d)) texto += ` · ${NOMBRE_ESCENARIO[sup].toLowerCase()}`;
				// Los supuestos solo traen la mediana: cuando no hay franja, «entre 68 y 68» no dice nada.
				const p10 = cuantil(e, 'p10', k), p90 = cuantil(e, 'p90', k);
				texto += ` · previsto ${f.score(e.q.p50[k])}${p10 === p90 ? '' : ` (entre ${f.score(p10)} y ${f.score(p90)})`}`;
				if (vPas !== null) texto += ` · pasó ${fmtV(vPas)}`;
			} else if (vPas !== null) texto += ` · ${fmtV(vPas)}`;
			else texto += ' · sin previsión';
		} else texto += v !== null ? ` · ${fmtV(v)}` : ' · sin dato';
		lectura.textContent = texto;
		// El globo va debajo y a la derecha del ratón, donde no tapa lo que se está mirando.
		// Solo se aparta cuando no cabe: arriba si el ratón está muy abajo, a la izquierda si
		// se sale por el borde derecho.
		caja.classList.add('leyendo');
		const px = ev.clientX - r.left, py = ev.clientY - r.top;
		const anchoG = lectura.offsetWidth, altoG = lectura.offsetHeight;
		const cabeDebajo = py + 18 + altoG <= r.height;
		lectura.style.top = `${cabeDebajo ? py + 18 : Math.max(-altoG - 4, py - 12 - altoG)}px`;
		lectura.style.left = `${Math.max(0, px + 14 + anchoG <= r.width ? px + 14 : px - 14 - anchoG)}px`;
		if (v !== null) { punto.style.left = `${((c + 0.5) / columnas) * 100}%`; punto.style.top = `${(1 - (v - lo) / (hi - lo)) * 100}%`; punto.hidden = false; } else punto.hidden = true;
		o.alHilo?.([{ x0: x, y0: r.top - 2, x1: x, y1: r.bottom, tono: TONO.info }]);
	};
	// Se escucha en la caja entera, no solo en la arena: los rótulos de los horizontes están dentro
	// de la gráfica y, si se escuchara en el hueco, pasar por uno cortaría el hilo y el globo.
	caja.addEventListener('pointermove', leer);
	caja.addEventListener('pointerleave', () => { caja.classList.remove('leyendo', 'en-futuro'); senalar(null); o.alHilo?.([]); });
	return caja;
}

// ─── Sección · Scoring ────────────────────────────────────────

export function seccionScoring(d: DatosFicha, acc: Acciones, flota: HTMLElement | null): HTMLElement {
	const raiz = h('div', { class: 'sec-scoring' });
	if (!d.mes) { raiz.append(h('p', { class: 'vacio' }, `${nombreEntidad(d.kind, d.id)} no tiene datos en ${f.mes(d.corte)}. Su primer mes es ${f.mes(d.ent.first_month)}.`)); return raiz; }
	// En una organización esta pestaña se llama «Empresas»: la lista manda y la explicación del
	// score viene después. En una empresa, la explicación es la pestaña entera.
	if (flota) raiz.append(flota);
	raiz.append(queEsElNumero(d, acc), balancePilares(d, acc));
	const pasa = queEstaPasando(d);
	if (pasa) raiz.append(pasa);
	const limita = queLoLimita(d);
	if (limita) raiz.append(limita);
	const cambia = queLoCambiaria(d, acc);
	if (cambia) raiz.append(cambia);
	raiz.append(seccion('De dónde sale', hilo(nudosScore(d, acc).slice(0, 3), true), (() => { const b = h('button', { type: 'button', class: 'as-enlace' }, 'Ver hilo entero en Desglose'); b.addEventListener('click', () => acc.irSeccion('tecnico')); return b; })()));
	return raiz;
}

// ─── Scoring · qué está pasando y por qué ────────────────────
/** Los textos del glosario del motor ya traen su punto final: encadenarlos deja dos seguidos. */
const sinPunto = (s: string) => s.trim().replace(/\.+$/, '');

// La pestaña que se abre primero tiene que contestar tres preguntas en el orden en que se hacen:
// qué es este número, qué lo empuja y qué lo frena, y qué ha cambiado. El Desglose sigue siendo el
// reverso auditable (la partitura, la cascada y las curvas); aquí se cuenta, no se audita.

/** Qué significa el número: su banda, cuánto falta para la siguiente, la cuenta y la confianza. */
function queEsElNumero(d: DatosFicha, acc: Acciones): HTMLElement {
	const m = d.mes!;
	const banda = d.man.bands.find((b) => b.key === m.band);
	const arriba = d.man.bands.filter((b) => b.min > m.shown).sort((a, b) => a.min - b.min)[0];
	const abajo = [...d.man.bands].filter((b) => b.min <= m.shown && b.key !== m.band).sort((a, b) => b.min - a.min)[0];
	const quien = nombreEntidad(d.kind, d.id);

	const primera = h('p', { class: 'sc-lead' },
		...conCifras(`${quien} saca ${f.score(m.shown)} sobre 100 en ${f.mes(d.corte)}.`, { que: 'Score del mes', mes: d.corte }),
		' ',
		...conCifras(banda ? `Eso es ${banda.label.toLowerCase()}, la banda que empieza en ${f.score(banda.min)}.` : 'Sin banda.', { que: 'Banda del motor', mes: d.corte }),
		' ',
		...(arriba
			? conCifras(`Le faltan ${f.scoreDec(arriba.min - m.shown)} puntos para ${arriba.label.toLowerCase()}.`, { que: `Distancia hasta la banda ${arriba.label.toLowerCase()}` })
			: [h('span', {}, 'Es la banda más alta del motor.')]),
		abajo && banda ? ' ' : null,
		...(abajo && banda ? conCifras(`Le quedan ${f.scoreDec(m.shown - banda.min)} puntos de margen antes de caer a ${abajo.label.toLowerCase()}.`, { que: `Margen hasta caer a la banda ${abajo.label.toLowerCase()}` }) : []));

	const segunda = h('p', { class: 'sc-que-es' },
		`El score resume ${f.plural(m.pillars.length, 'pilar de tesorería', 'pilares de tesorería')} medidos sobre los extractos del banco y las facturas del ERP: `,
		m.pillars.map((p) => nombrePilar(d.man, p.key).toLowerCase()).join(', '),
		'. No es un rating de crédito ni una probabilidad de impago: dice cómo se gobierna la caja este mes.');

	// La cuenta entera en una línea: de dónde parte, qué suman los pilares y qué le quitan.
	const suma = m.pillars.reduce((s, p) => s + p.contrib, 0);
	const termino = (valor: string, que: string, clase = '') => h('span', { class: `sc-term ${clase}` }, h('b', {}, valor), h('span', {}, que));
	const operador = (s: string) => h('span', { class: 'sc-op', 'aria-hidden': 'true' }, s);
	const cuenta = h('div', { class: 'sc-cuenta', 'aria-label': `Cuenta del score: punto de partida ${f.scoreDec(m.base)}, pilares ${f.delta(suma)}, penalización ${f.delta(-m.penalty)}, tope ${f.delta(-m.cap.amount)}, score ${f.scoreDec(m.shown)}` },
		termino(f.scoreDec(m.base), 'punto de partida'),
		operador(suma >= 0 ? '+' : '−'), termino(f.scoreDec(Math.abs(suma)), suma >= 0 ? voz('lo que aportan sus pilares', 'lo que aportan tus pilares') : voz('lo que restan sus pilares', 'lo que restan tus pilares'), suma >= 0 ? 'pos' : 'neg'),
		operador('−'), termino(f.scoreDec(m.penalty), 'penalización', m.penalty > 0 ? 'neg' : 'cero'),
		operador('−'), termino(f.scoreDec(m.cap.amount), 'tope', m.cap.amount > 0 ? 'neg' : 'cero'),
		operador('='), termino(f.scoreDec(m.shown), 'score', 'total'));

	const CONF: Record<string, string> = { high: 'alta', medium: 'media', low: 'baja' };
	const conf = h('p', { class: 'nota' }, ...conCifras(
		`La confianza es ${CONF[m.conf.label] ?? m.conf.label} (${f.porcentaje(m.conf.value, 0)}): ${f.plural(m.months_observed, 'mes observado', 'meses observados')}, ${f.porcentaje(m.conf.coverage, 0)} de cobertura y ${f.porcentaje(m.conf.quality, 0)} de calidad. No entra en la cuenta: dice cuánto fiarse del número.`,
		{ que: 'Confianza del mes', mes: d.corte, ir: () => acc.irSeccion('conciliacion') }));

	return seccion(voz('Qué dice este número', 'Qué dice tu número'), primera, segunda, cuenta, conf);
}

/** El porqué: qué pilar empuja, cuál frena y cuánto, sobre un eje que parte de cero. */
function balancePilares(d: DatosFicha, acc: Acciones): HTMLElement {
	const m = d.mes!;
	const conDato = m.pillars.filter((p) => p.score !== null);
	const empujan = conDato.filter((p) => p.contrib > 0);
	const frenan = conDato.filter((p) => p.contrib < 0);
	const sinDato = m.pillars.length - conDato.length;
	const mejor = [...empujan].sort((a, b) => b.contrib - a.contrib)[0];
	const peor = [...frenan].sort((a, b) => a.contrib - b.contrib)[0];

	const cuantos = (n: number, uno: string, varios: string) => (n === 0 ? `ninguno ${uno}` : f.plural(n, uno, varios));
	const partes = [`De ${f.plural(m.pillars.length, 'pilar', 'pilares')}, ${cuantos(empujan.length, 'empuja', 'empujan')} y ${cuantos(frenan.length, 'frena', 'frenan')}`];
	if (sinDato) partes.push(`${f.plural(sinDato, 'se queda sin dato', 'se quedan sin dato')}`);
	let frase = `${partes.join('; ')}.`;
	if (mejor) frase += ` El que más aporta es ${nombrePilar(d.man, mejor.key).toLowerCase()}, ${f.delta(mejor.contrib)}.`;
	if (peor) frase += ` El que más resta es ${nombrePilar(d.man, peor.key).toLowerCase()}, ${f.delta(peor.contrib)}.`;
	const resumen = h('p', { class: 'sc-lead' }, ...conCifras(frase, { que: 'Aportación de cada pilar al score', mes: d.corte }));

	const tope = Math.max(1, ...m.pillars.map((p) => Math.abs(p.contrib)));
	const lista = h('div', { class: 'sc-bal' });
	lista.append(h('div', { class: 'sc-bal-eje', 'aria-hidden': 'true' }, h('span', {}), h('span', { class: 'sc-bal-eje-c' }, h('i', {}, 'resta'), h('i', {}, 'aporta')), h('span', {})));
	// De lo que más empuja a lo que más frena; los pilares sin dato, siempre al final.
	const rango = (p: PilarMesM) => (p.score === null ? -Infinity : p.contrib);
	for (const p of [...m.pillars].sort((a, b) => rango(b) - rango(a))) {
		const nulo = p.score === null;
		const ancho = (Math.abs(p.contrib) / tope) * 50;
		const barra = h('div', { class: 'sc-bal-barra' }, h('i', { class: 'sc-bal-cero', 'aria-hidden': 'true' }),
			nulo ? null : h('i', { class: `sc-bal-tramo ${p.contrib < 0 ? 'neg' : 'pos'}`, style: p.contrib < 0 ? { right: '50%', width: `${ancho}%` } : { left: '50%', width: `${ancho}%` } }));
		const fila = h('div', { class: `sc-bal-fila tocable ${nulo ? 'nulo' : ''}`, tabindex: '0', title: 'Pasa por encima para verlo en el horizonte; clic para su evidencia' },
			h('div', { class: 'sc-bal-nombre' }, nombrePilar(d.man, p.key), h('span', { class: 'sc-bal-peso' }, `${f.porcentaje(p.w_eff, 0)} del peso`)),
			barra,
			h('div', { class: `sc-bal-cifra ${nulo ? 'nulo' : p.contrib < 0 ? 'neg' : p.contrib > 0 ? 'pos' : ''}` }, nulo ? 'sin dato' : f.delta(p.contrib)),
			h('p', { class: 'sc-bal-nota' }, ...conCifras(p.note ?? '', origenPilar(d, acc, p.key, `Lo que mide el pilar de ${nombrePilar(d.man, p.key).toLowerCase()}`))));
		const ir = () => acc.irSeccion('conciliacion', undefined, { pilar: p.key });
		fila.addEventListener('click', ir);
		fila.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
		if (!nulo) {
			fila.addEventListener('pointerenter', () => acc.horizonte.pilar(p.key));
			fila.addEventListener('pointerleave', () => acc.horizonte.pilar(null));
			fila.addEventListener('focus', () => acc.horizonte.pilar(p.key));
			fila.addEventListener('blur', () => acc.horizonte.pilar(null));
		}
		lista.append(fila);
	}
	const pie = h('p', { class: 'nota' }, 'Cada pilar puntúa de 0 a 100 y aporta según su peso, contado desde el punto de partida del motor. Las barras y las curvas de cada pilar están en Desglose.');
	return seccion('Qué lo empuja y qué lo frena', resumen, lista, pie);
}

/** Qué ha cambiado: el veredicto del motor dicho en palabras, con su tamaño y su persistencia. */
function queEstaPasando(d: DatosFicha): HTMLElement | null {
	const m = d.mes!;
	const v = m.verdict;
	if (!v.available) {
		return seccion('Qué está pasando', h('p', { class: 'sc-lead' }, `Este mes no hay veredicto de movimiento${v.reason ? `: ${sinPunto(d.man.glossary.reasons[v.reason] ?? v.reason)}.` : '.'}`),
			h('p', { class: 'nota' }, 'El motor compara con el mes de hace tres y necesita historia suficiente; sin ella prefiere callarse a inventar una tendencia.'));
	}
	const sube = v.direction === 'improving';
	const partes: string[] = [];
	if (v.direction === 'perimeter_shift') partes.push('El perímetro ha cambiado: entran o salen empresas, así que el score de este mes no se compara con el de hace tres.');
	else if (v.direction === 'stable') partes.push(v.delta3 === null || Math.abs(v.delta3) < 5
		? `Se mantiene: el score es el de hace tres meses${v.compared_to ? `, ${f.mes(v.compared_to)}` : ''}.`
		: `Se mantiene: ${f.delta(v.delta3)} puntos en tres meses${v.compared_to ? `, frente a ${f.mes(v.compared_to)}` : ''}.`);
	else partes.push(`${sube ? 'Sube' : 'Baja'} ${f.scoreDec(Math.abs(v.delta3 ?? 0))} puntos en tres meses${v.compared_to ? `, frente a ${f.mes(v.compared_to)}` : ''}.`);
	// La comparación con el vaivén normal solo dice algo si el movimiento existe: «0 veces lo
	// habitual» es ruido delante de un mes que no se ha movido.
	if (v.sigma !== null && v.delta3_sigma !== null && Math.abs(v.delta3_sigma) >= 0.1) partes.push(`Su vaivén normal es de ${f.scoreDec(v.sigma)} puntos, así que el movimiento es ${f.numero(Math.abs(v.delta3_sigma), 1)} veces lo habitual.`);
	if (v.nature === 'structural') partes.push(`Es un movimiento confirmado, no un bache${v.detected_since ? `: se ve desde ${f.mes(v.detected_since)}` : ''}.`);
	else if (v.nature === 'bump') partes.push('Es un bache, no un cambio de fondo.');
	else if (v.nature === 'shock_pending') partes.push(`Es un golpe todavía por confirmar${v.shock_month ? `, de ${f.mes(v.shock_month)}` : ''}: hacen falta más meses para saber si se queda.`);
	if (v.persistence_months > 1) partes.push(`Lleva ${f.plural(v.persistence_months, 'mes', 'meses')} en la misma dirección.`);
	const indiceCorte = d.ent.months.findIndex((x) => x.month === d.corte);
	const pendiente = indiceCorte >= 0 ? pendienteTheilSen(d.ent.months.map((x) => x.shown), indiceCorte) : null;
	if (pendiente !== null) partes.push(`La deriva lenta de los últimos doce meses es ${pendiente >= 0 ? '+' : '−'}${f.numero(Math.abs(pendiente), 1)} puntos por mes; es descriptiva y no cambia el score.`);
	if (v.pillars_moved.length) {
		const ps = v.pillars_moved.map((k) => nombrePilar(d.man, k).toLowerCase());
		partes.push(`Lo ${ps.length > 1 ? 'mueven' : 'mueve'} ${ps.length > 1 ? `${ps.slice(0, -1).join(', ')} y ${ps[ps.length - 1]}` : ps[0]}.`);
	}

	const p = h('p', { class: 'sc-lead' }, ...conCifras(partes.join(' '), { que: 'Veredicto del mes', mes: d.corte }));
	// Los avisos del mes no se repiten aquí: viven junto al número, en la cabecera.
	return seccion('Qué está pasando', h('div', { class: 'sc-mov' }, h('span', { class: `sc-mov-sello ${v.direction}` }, movimiento(m)), p));
}

/** Lo que recorta el número aunque los pilares digan otra cosa: topes, penalización, compuertas. */
function queLoLimita(d: DatosFicha): HTMLElement | null {
	const m = d.mes!;
	const puntos: string[] = [];
	if (m.abstain) puntos.push(`El motor se abstiene: ${sinPunto(d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason)}. Para volver a puntuar, ${sinPunto(m.abstain.unlock).charAt(0).toLowerCase()}${sinPunto(m.abstain.unlock).slice(1)}.`);
	if (m.cap.amount > 0) puntos.push(`Un tope recorta ${f.scoreDec(m.cap.amount)} puntos${m.cap.rule ? `: ${sinPunto(d.man.glossary.caps[m.cap.rule] ?? m.cap.rule)}.` : '.'}`);
	for (const regla of m.cap.fired.filter((x) => x !== m.cap.rule)) puntos.push(`${sinPunto(d.man.glossary.caps[regla] ?? regla)}.`);
	if (m.penalty > 0) puntos.push(`El pilar más débil penaliza ${f.scoreDec(m.penalty)} puntos: el motor no deja que una media buena tape un pilar hundido.`);
	// Las compuertas que ya se leen como frase de un pilar no se repiten: ahí están en su sitio.
	const notas = new Set(m.pillars.map((p) => sinPunto(p.note ?? '')).filter(Boolean));
	for (const g of [...new Set(m.pillars.flatMap((p) => p.gates))]) {
		const t = sinPunto(d.man.glossary.gates[g] ?? g);
		if (!notas.has(t)) puntos.push(`${t}.`);
	}
	// Si el motor ya se abstiene por el feed, no hace falta repetirlo con otras palabras.
	if (!m.feed_live && !m.abstain) puntos.push('Los datos del banco no están al día: lo que se ve puede haber envejecido.');
	if (m.perimeter_changed) puntos.push('El perímetro ha cambiado este mes: entran o salen empresas.');
	for (const fl of m.flags) puntos.push(`${sinPunto(d.man.glossary.flags[fl] ?? fl)}.`);
	const unicos = [...new Set(puntos)];
	if (!unicos.length) return null;
	return seccion('Qué lo está limitando', h('ul', { class: 'sc-limites' }, ...unicos.map((x) => h('li', {}, ...conCifras(x, { que: 'Límite del motor', mes: d.corte })))));
}

/** El puente a Acciones: cuánto hay en juego, sin repetir la pestaña entera. */
function queLoCambiaria(d: DatosFicha, acc: Acciones): HTMLElement | null {
	const m = d.mes!;
	const accs = m.actions ?? [];
	if (!accs.length) return null;
	const mejor = accs.reduce((a, b) => (b.uplift_tenths > a.uplift_tenths ? b : a));
	const juntas = m.actions_combined;
	const frase = `El motor mide ${f.plural(accs.length, 'acción', 'acciones')} sobre este mes. La que más mueve es «${tituloAccion(mejor)}»: ${f.delta(mejor.uplift_tenths)} puntos, ${ESFUERZO[mejor.effort]}.`
		+ (juntas && accs.length > 1 ? ` Todas juntas dejarían el score en ${f.score(juntas.new_score)}.` : '');
	const b = h('button', { type: 'button', class: 'as-enlace' }, 'Ver las acciones');
	b.addEventListener('click', () => acc.irSeccion('acciones'));
	return seccion('Qué lo cambiaría', h('p', { class: 'sc-lead' }, ...conCifras(frase, { que: 'Efecto que el motor mide para las acciones del mes', mes: d.corte })), b);
}

/** La partitura de pilares: qué puntúa cada uno y qué aporta al score. Vive en el tab Desglose. */
export function partitura(d: DatosFicha, acc: Acciones): HTMLElement {
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
			h('p', { class: 'pt-nota' }, ...conCifras(p.note ?? '', origenPilar(d, acc, p.key, `Lo que mide el pilar de ${nombrePilar(d.man, p.key).toLowerCase()}`))));
		const ir = () => acc.irSeccion('conciliacion', undefined, { pilar: p.key });
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
    accion: () => acc.irSeccion("conciliacion", undefined, { pilar: peor.key }),
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
        acc.irSeccion("conciliacion", undefined, {
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
        acc.irSeccion("conciliacion", undefined, {
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
	// Lo que esta empresa necesita va primero, delante de las familias: quien abre Productos viene
	// a saber qué ofrecerle, no a repasar el catálogo. Lo recomendado es lo que encaja hoy y lo que
	// ya tiene pero el motor pide ampliar o usar más; manda la subida de score que promete.
	const recomendado = (e: EstadoProducto) => e.estado === 'encaja' || (e.estado === 'tiene' && !!e.forma);
	const orden = (e: EstadoProducto) => PRODUCTOS.findIndex((p) => p.id === e.id);
	const primeros = es.filter(recomendado).sort((a, b) => (b.accion?.uplift_tenths ?? -1) - (a.accion?.uplift_tenths ?? -1) || orden(a) - orden(b));
	const resto = es.filter((e) => !recomendado(e));
	let familia = '';
	for (const e of primeros.length ? [...primeros, ...resto] : es) {
		const p = producto(e.id);
		const enCabeza = primeros.includes(e);
		if (enCabeza && !familia) { familia = 'recomendado'; estante.append(h('h3', { class: 'est-familia recomendado' }, voz('Lo que le encajaría ahora', 'Lo que te conviene ahora'))); }
		if (!enCabeza && primeros.length && familia === 'recomendado') { familia = ''; estante.append(h('h3', { class: 'est-familia estante' }, 'El resto de la estantería')); }
		if (!enCabeza && p.familia !== familia) { familia = p.familia; estante.append(h('h3', { class: 'est-familia' }, FAMILIAS[p.familia].nombre)); }
		const t = tenenciaDe(d).find((x) => x.product === e.id);
		const fila = h('div', { class: `est-fila inv-item estado-${e.estado} ${enCabeza ? 'destacada' : ''}` });
		const estadoT = e.estado === 'tiene' ? (t?.source === 'movimientos' ? voz('deducido de sus movimientos', 'deducido de tus movimientos') : 'contratado') : e.estado === 'encaja' ? voz('le encajaría', 'te conviene') : e.estado === 'bloqueado' ? 'hoy no' : 'no consta';
		const cuerpo = h('div', { class: 'est-cuerpo' }, h('div', { class: 'est-cab' }, h('span', { class: 'inv-nombre' }, p.nombre), h('span', { class: 'est-estado' }, estadoT)));
		if (t) cuerpo.append(contratos(t));
		if (e.estado === 'encaja' || e.estado === 'bloqueado' || e.forma) cuerpo.append(h('p', { class: 'est-motivo' }, ...conCifras(e.bloqueo ?? e.motivo, origenPilar(d, acc, e.accion?.pillar ?? null, 'Por qué el motor lo pide'))));
		const efecto = h('div', { class: 'est-efecto' });
		if (e.accion && e.estado !== 'bloqueado') {
			const ha = d.hor?.actions?.find((a) => a.id === e.accion!.id);
			efecto.append(h('b', {}, `${f.delta(e.accion.uplift_tenths)}`), h('span', {}, ha && hayFuturo(d) ? `a 6 meses, ${f.score(ha.q.p50[5])}` : 'puntos'));
			fila.classList.add('tocable');
			fila.title = voz('Pasa por encima para verlo en el horizonte; clic para marcar su acción', 'Pasa por encima para verlo en tu horizonte; clic para marcar la acción');
			fila.addEventListener('pointerenter', () => acc.horizonte.previa([e.accion!.id]));
			fila.addEventListener('pointerleave', () => acc.horizonte.previa(null));
			fila.addEventListener('click', () => acc.irSeccion('acciones', e.accion!.id));
		}
		fila.append(h('div', { class: 'est-icono' }, iconoProducto(e.id, { tam: 44, estado: e.estado === 'tiene' && e.forma ? 'tiene' : e.estado, titulo: false })), cuerpo, efecto);
		estante.append(fila);
	}
	raiz.append(estante);
	const otras = d.prodE?.other_debt.filter((x) => !x.closed) ?? [];
	// La unidad que se repite entre las filas sube a la cabecera y las celdas quedan limpias; el
	// cero no lastra la unidad (0 € = 0 k€). Si se mezclan, cada fila lleva la suya (docs/DESIGN_UX.mdx).
	const unidadDe = (v: number | null) => (v === null || v === 0 ? null : Math.abs(v) >= 1e6 ? 'M€' : Math.abs(v) >= 1e3 ? 'k€' : '€');
	const unidadComun = (vs: (number | null)[]) => {
		const us = new Set(vs.filter((v) => v !== null && v !== 0).map(unidadDe));
		return us.size === 1 ? [...us][0]! : null;
	};
	const importe = (v: number | null, u: '€' | 'k€' | 'M€' | null) => (v === null ? '—' : u ? f.eurosEn(v, u) : f.eurosCorto(v));
	// El símbolo que se repite en todas las filas de la columna sube a su cabecera y las celdas se
	// quedan con el nombre; si las entidades difieren, cada celda abre con su marca (docs/DESIGN_UX.mdx).
	const bancoComun = (vs: typeof otras) => {
		const bancos = vs.map((x) => x.bank).filter((b): b is string => !!b);
		return bancos.length && bancos.every((b) => b === bancos[0]) ? bancos[0] : null;
	};
	// La tabla se reconstruye por filtro y las unidades se vuelven a medir sobre las filas visibles:
	// filtrar a un solo tipo puede cambiar la unidad común de la columna (docs/DESIGN_UX.mdx).
	const tablaOtras = (visibles: typeof otras) => {
		const uc = unidadComun(visibles.map((x) => x.granted));
		const up = unidadComun(visibles.map((x) => x.outstanding));
		const bc = bancoComun(visibles);
		return h('table', { class: 'tabla-sutil' },
			h('thead', {}, h('tr', {}, h('th', {}, 'Tipo'), h('th', {}, bc ? h('span', { class: 'banco' }, marcaBanco(bc), 'Entidad') : 'Entidad'), h('th', { class: 'num' }, uc ? `Concedido (${uc})` : 'Concedido'), h('th', { class: 'num' }, up ? `Pendiente (${up})` : 'Pendiente'), h('th', { class: 'num' }, 'Interés (%)'), h('th', {}, 'Próxima cuota'))),
			h('tbody', {}, ...visibles.map((x) => h('tr', {}, h('td', {}, x.type_label), h('td', {}, !x.bank ? '—' : bc ? x.bank : h('span', { class: 'banco' }, marcaBanco(x.bank), x.bank)), h('td', { class: 'num' }, importe(x.granted, uc)), h('td', { class: 'num' }, importe(x.outstanding, up)), h('td', { class: 'num' }, x.rate === null ? '—' : f.numero(x.rate, 2)), h('td', {}, x.next_payment ? f.mes(x.next_payment.slice(0, 7)) : '—')))));
	};
	const tipos = [...new Set(otras.map((x) => x.type_label))];
	let filtro: string | null = null;
	const tabla = h('div');
	const pinta = () => { vaciar(tabla); tabla.append(tablaOtras(filtro === null ? otras : otras.filter((x) => x.type_label === filtro))); };
	const botonesFiltro = tipos.length > 1
		? [null, ...tipos].map((t) => h('button', { type: 'button', class: 'filtro-opcion', 'aria-pressed': String(filtro === t), 'data-tipo': String(t) }, t === null ? 'Todos' : t))
		: null;
	if (botonesFiltro) for (const b of botonesFiltro) b.addEventListener('click', () => { filtro = b.dataset.tipo === 'null' || b.dataset.tipo === undefined ? null : b.dataset.tipo; for (const x of botonesFiltro) x.setAttribute('aria-pressed', String(x === b)); pinta(); });
	pinta();
	if (otras.length) raiz.append(seccion('Otras deudas',
		...(botonesFiltro ? [h('div', { class: 'filtro-tipo', role: 'group', 'aria-label': 'Filtrar otras deudas por tipo' }, ...botonesFiltro)] : []),
		h('div', { class: 'tabla-caja' }, tabla),
		h('p', { class: 'nota' }, 'No son de los siete productos, pero pesan en el pilar de deuda.')));
	return raiz;
}

/** Los contratos de un producto: entidad, uso sobre el límite (con su escala) y tipo. */
function contratos(t: TenenciaM): HTMLElement {
	const lista = h('ul', { class: 'contratos' });
	for (const it of t.items.slice(0, 4)) {
		const uso = !it.inconsistent && it.usage !== null ? Math.max(0, Math.min(1, it.usage)) : null;
		lista.append(h('li', {},
			h('span', { class: 'ct-banco' }, marcaBanco(it.bank), it.bank ?? 'Entidad sin nombre'),
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
	const leyenda = h('div', { class: 'mz-leyenda' }, ...(['tiene', 'encaja', 'bloqueado', 'no_consta'] as const).map((s) => h('span', {}, iconoProducto('linea_credito' as never, { tam: 22, estado: s, titulo: false, sinFilete: true }), { tiene: voz('lo tiene', 'lo tiene'), encaja: voz('le encajaría', 'le conviene'), bloqueado: 'hoy no', no_consta: 'no consta' }[s])));
	raiz.append(seccion(voz('Qué tiene cada empresa y qué le encajaría', 'Qué tiene cada una de tus empresas y qué le conviene'), leyenda, h('div', { class: 'matriz-caja' }, tabla)));
	return raiz;
}

// ─── Sección · Acciones ───────────────────────────────────────

/** Cuánto tarda en notarse una acción, en meses. La cifra y la curva están en el horizonte. */
function mesesAccion(d: DatosFicha, a?: AccionM): number | null {
	const ha = a && d.hor?.actions?.find((x) => x.id === a.id);
	if (!ha || !hayFuturo(d)) return null;
	return Math.max(1, ha.lag_months);
}

export function seccionAcciones(d: DatosFicha, acc: Acciones): HTMLElement {
	const raiz = h('div', { class: 'sec-acciones' });
	const m = d.mes;
	if (!m) { raiz.append(h('p', { class: 'vacio' }, `Sin datos en ${f.mes(d.corte)}.`)); return raiz; }
	const recs = recomendaciones({ mes: m, man: d.man, tenencia: tenenciaDe(d), perfil: d.ent.profile, papel: d.kind === 'company' ? (d.ent as EmpresaM).role : null, heredaLiquidez: d.kind === 'company' ? (d.ent as EmpresaM).inherits_liquidity : false });
	const sel = acc.horizonte.elegidas();
	const lista = h('ol', { class: 'recomendaciones' });
	// Una columna por pregunta: qué hacer, de cuánto a cuánto, cuánto cuesta, cómo queda y cuánto sube.
	const cabezaLista = h('div', { class: 'rec-cab', 'aria-hidden': 'true' },
		h('span', {}, 'Ver'), h('span', {}, 'Qué hacer'), h('span', { class: 'centro' }, 'Esfuerzo'), h('span', { class: 'centro' }, 'Se nota'), h('span', { class: 'der' }, 'Sube'), h('span', {}, 'Seguimiento'));
	const filas = new Map<string, () => void>();
	const seguimiento = seguimientoAcciones(d, () => acc.horizonte.elegidas(), {
		alCambiar: () => ordenarFilas(),
		soltar: (ids) => { for (const id of ids) if (sel.has(id)) acc.horizonte.alternar(id, false); },
		enLista: (id) => filas.has(id),
	});
	recs.forEach((r) => {
		const a = r.accion;
		// La casilla es lo primero de la fila y es lo que la lleva al horizonte. Es una casilla de verdad
		// (teclado, lectores de pantalla), pero dibujada por nosotros, no la del sistema operativo.
		const marca = h('input', { type: 'checkbox', class: 'rec-tick', checked: sel.has(a.id), 'aria-label': `Ver en el horizonte: ${tituloAccion(a)}` }) as HTMLInputElement;
		const fijarMarca = (v: boolean) => {
			marca.checked = v;
			acc.horizonte.alternar(a.id, v);
			li.classList.toggle('elegida', v);
			seguimiento.actualizarBoton();
		};
		marca.addEventListener('change', () => fijarMarca(marca.checked));
		marca.addEventListener('click', (ev) => ev.stopPropagation());
		// Decidida ya, la casilla deja su sitio a una señal del estado: no se puede volver a ejecutar.
		const senal = h('span', { class: 'rec-senal', 'aria-hidden': 'true' });
		const orden = h('span', { class: 'rec-orden', 'aria-hidden': 'true' });
		// Decidida, la fila es su seguimiento: la medida ocupa el sitio de la palanca y los mandos, la última columna.
		const medida = h('div', { class: 'rec-medida' });
		const estado = h('div', { class: 'rec-estado' });
		const panel = h('div', { class: 'rec-panel' });
		const prods = r.productos.map((p) => iconoProducto(p, { tam: 26, titulo: true, sinFilete: true, estado: tenenciaDe(d).some((t) => t.product === p) ? 'tiene' : 'encaja' }));
		const pal = palancaDeAccion(a);
		const meses = mesesAccion(d, a);
		const li = h('li', { class: 'rec', 'data-accion': a.id },
			h('span', { class: 'rec-marca' }, marca, senal, orden),
			h('div', { class: 'rec-cuerpo' },
				h('div', { class: 'rec-titulo' }, accionCorta(a)),
				// La palanca, en cifras y grande: de dónde sale y adónde tiene que llegar.
				h('div', { class: 'rec-palanca', title: tituloAccion(a) },
					h('b', {}, ...conCifras(pal.de, origenPilar(d, acc, a.pillar, 'Dónde está hoy la palanca'))),
					h('i', { 'aria-hidden': 'true' }, '→'),
					h('b', { class: 'meta' }, ...conCifras(pal.hasta, origenPilar(d, acc, a.pillar, 'Adónde tiene que llegar')))),
				medida,
				h('p', { class: 'rec-texto' }, ...conCifras(r.delGrupo ? `${explicacionAccion(a)} En una filial que financia el grupo, esto se decide en el grupo.` : explicacionAccion(a), origenPilar(d, acc, a.pillar, 'Lo que hace falta para llegar al objetivo'))),
				h('p', { class: 'rec-productos' },
					...prods,
					prods.length ? h('span', {}, r.productos.map((p) => producto(p).nombre.toLowerCase()).join(' o ')) : null,
					r.propia && !prods.length ? h('span', { class: 'propia' }, r.propia) : null,
					h('span', { class: 'rec-pilar' }, nombrePilar(d.man, a.pillar).toLowerCase()))),
			h('div', { class: 'rec-esfuerzo' }, h('b', {}, a.effort)),
			h('div', { class: 'rec-plazo' }, meses === null ? h('b', { class: 'vacia' }, '—') : h('b', {}, f.numero(meses)),
				h('span', {}, meses === null ? 'sin previsión' : meses === 1 ? 'mes' : 'meses')),
			h('div', { class: 'rec-efecto' }, h('b', {}, f.delta(a.uplift_tenths)), h('span', {}, 'puntos')),
			estado, panel);
		// Tantear: pasar por encima ya lo enseña en el horizonte; marcar lo fija — también al pulsar la fila.
		li.addEventListener('pointerenter', () => acc.horizonte.previa([a.id]));
		li.addEventListener('pointerleave', () => acc.horizonte.previa(null));
		li.addEventListener('click', (e) => {
			if ((e.target as Element).closest('.rec-estado, .rec-panel')) return;
			const r = seguimiento.situacion(a.id).registro;
			if (r) { seguimiento.alternarPanel(r.id); return; }
			fijarMarca(!marca.checked);
		});
		filas.set(a.id, () => {
			const piezas = seguimiento.enFila(a.id);
			const libre = !piezas;
			li.dataset.estado = piezas?.registro.status ?? 'disponible';
			if (piezas) li.dataset.ejecucion = piezas.registro.id; else delete li.dataset.ejecucion;
			li.tabIndex = -1;
			marca.hidden = !libre; marca.disabled = !libre; senal.hidden = libre;
			if (!libre) marca.checked = false;
			li.classList.toggle('elegida', libre && marca.checked);
			li.classList.toggle('reciente', !!piezas?.reciente);
			medida.replaceChildren(...(piezas ? [piezas.medida] : []));
			estado.replaceChildren(...(piezas ? [piezas.mandos] : []));
			panel.replaceChildren(...(piezas ? [piezas.panel] : []));
			panel.hidden = !piezas || piezas.panel.hidden;
		});
		lista.append(li);
	});
	/** Lo que queda por decidir va primero y numerado; lo ya decidido baja, con su estado a la vista. */
	function ordenarFilas() {
		for (const pintarFila of filas.values()) pintarFila();
		const todas = recs.map((r) => lista.querySelector<HTMLElement>(`[data-accion="${CSS.escape(r.accion.id)}"]`)!);
		const libres = todas.filter((li) => li.dataset.estado === 'disponible');
		const decididas = todas.filter((li) => li.dataset.estado !== 'disponible');
		libres.forEach((li, i) => { li.querySelector('.rec-orden')!.textContent = String(i + 1); });
		for (const li of decididas) li.querySelector('.rec-orden')!.textContent = '';
		const ancla = lista.querySelector('.rec.nada');
		for (const li of libres) lista.insertBefore(li, ancla);
		// «No hacer nada» es una opción más entre las que quedan: lo decidido va después.
		// En marcha antes que finalizada: lo que pide atención, arriba.
		const peso = (li: HTMLElement) => ['en_curso', 'pausada', 'completada'].indexOf(li.dataset.estado!);
		decididas.sort((x, y) => peso(x) - peso(y));
		decididas.forEach((li, i) => li.classList.toggle('primera-decidida', i === 0));
		for (const li of libres) li.classList.remove('primera-decidida');
		lista.append(...decididas);
		seguimiento.tras();
		seguimiento.actualizarBoton();
	}
	const base = d.hor?.scenarios?.base;
	if (base && hayFuturo(d)) {
		const peor = base.cross && base.cross.dir === 'down';
		const nada = h('li', { class: 'rec nada' }, h('span', { class: 'rec-marca' }, h('span', { class: 'rec-orden', 'aria-hidden': 'true' }, '—')),
			h('div', { class: 'rec-cuerpo' }, h('div', { class: 'rec-titulo' }, 'No hacer nada'),
				peor && base.cross!.prob !== null ? h('p', { class: 'rec-texto' }, `${f.porcentaje(base.cross!.prob, 0)} de pasar a ${nombreBanda(d.man, base.cross!.to).toLowerCase()} hacia ${f.mes(base.cross!.month)}.`) : null),
			h('div', { class: 'rec-esfuerzo' }, h('b', { class: 'vacia' }, '—')),
			h('div', { class: 'rec-plazo seis' }, h('b', {}, f.score(base.q.p50[5])), h('span', {}, `a seis meses · entre ${f.score(base.q.p10[5])} y ${f.score(base.q.p90[5])}`)),
			h('div', { class: 'rec-efecto' }, h('b', { class: 'vacia' }, '—'), h('span', {}, 'puntos')),
			h('div', { class: 'rec-estado' }));
		nada.addEventListener('pointerenter', () => acc.horizonte.previa([]));
		nada.addEventListener('pointerleave', () => acc.horizonte.previa(null));
		lista.append(nada);
	}
	if (!recs.length) {
		const razon = m.abstain
			? `El motor se abstiene este mes y no propone acciones: ${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason}. Qué la levantaría: ${m.abstain.unlock}`
			: !m.feed_live
				? 'Sin datos del banco al día, el motor no propone acciones. Las palancas salen de los movimientos recientes de cobros y pagos; cuando el feed vuelva a estar al día, la lista se recupera sola.'
				: 'El motor no encuentra este mes ninguna palanca que suba el score al menos medio punto. Evalúa los movimientos del mes y los productos en cartera, y con lo que hay hoy ninguno mueve el número lo suficiente. No es un error ni una falta de datos: el score ya recoge el estado del mes y el horizonte sigue leyéndose en «si todo sigue igual».';
		lista.prepend(h('li', { class: 'rec vacia' }, h('p', {}, razon)));
	}
	ordenarFilas();
	const cabeceraAcciones = h(
		'div',
		{ class: 'sec-acciones-cabecera' },
		seguimiento.boton,
		seguimiento.mensaje,
	);
	raiz.append(seccion(d.kind === 'group' ? voz('Qué puede hacer el grupo', 'Qué puedes hacer en el grupo') : voz('Qué puede cambiar su rumbo', 'Qué puede cambiar tu rumbo'), cabeceraAcciones, recs.length ? cabezaLista : null, lista));
	raiz.append(seguimiento.raiz);
	if (d.kind === 'group') raiz.append(seccion(voz('Lo que proponen sus empresas', 'Lo que puede hacer cada una de tus empresas'), accionesEmpresas(d, acc)));
	return raiz;
}

/** En la organización: las acciones de todas sus empresas, ordenadas por lo que suben según el motor. */
function accionesEmpresas(d: DatosFicha, acc: Acciones): HTMLElement {
	const filas = d.empresas.flatMap((em) => (em.ent?.months.find((m) => m.month === d.corte)?.actions ?? []).map((a) => ({ em, a })));
	filas.sort((x, y) => y.a.uplift_tenths - x.a.uplift_tenths);
	// Las mismas columnas que la tabla de arriba, para que se lean igual: qué hacer, de cuánto a
	// cuánto, qué esfuerzo y cuánto sube. «En la empresa» sobraba en cada renglón: la empresa ya va delante.
	const lista = h('ul', { class: 'acciones-empresas' });
	if (filas.length) lista.append(h('li', { class: 'ae-cab', 'aria-hidden': 'true' },
		h('span', {}, 'Empresa'), h('span', {}, 'Qué hacer'), h('span', {}, 'De cuánto a cuánto'), h('span', { class: 'centro' }, 'Esfuerzo'), h('span', { class: 'der' }, 'Sube')));
	for (const { em, a } of filas.slice(0, 12)) {
		const pal = palancaDeAccion(a);
		const li = h('li', { class: 'tocable', tabindex: '0', title: tituloAccion(a) },
			h('b', {}, f.empresa(em.res.id)),
			h('span', { class: 'ae-titulo' }, accionCorta(a)),
			h('span', { class: 'ae-palanca' }, pal.de, h('i', { 'aria-hidden': 'true' }, '→'), h('em', {}, pal.hasta)),
			h('span', { class: 'ae-esfuerzo' }, a.effort),
			h('span', { class: 'ae-efecto' }, f.delta(a.uplift_tenths)));
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
		case 'tecnico': return seccionTecnica(d, acc);
		case 'conciliacion': return seccionConciliacion(d, filtro);
	}
}

export { primeraMayuscula, vaciar };
