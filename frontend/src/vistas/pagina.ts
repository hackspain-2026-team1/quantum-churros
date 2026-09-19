// El controlador de las páginas de Rumbo: la entrada (elegir organización), la organización, la
// empresa y la metodología. Cada página es un documento que se desplaza; la arena la acompaña con
// las placas (registro.ts). La miga de pan hace de frase: Rumbo › Grupo › Empresa › Sección.

import { TONO } from '../arena/arena';
import type { Placa } from '../arena/placas';
import { carga } from '../datos/carga';
import type { AlertaM, EmpresaM, GrupoM, Manifiesto } from '../datos/contrato';
import { f } from '../datos/formato';
import type { Cartera } from '../datos/modelo';
import { nombreBanda, movimiento } from '../datos/redaccion';
import { SECCIONES, type Almacen, type Estado, type Seccion } from '../estado';
import { cola, h, vaciar } from './dom';
import { cabecera, cargarFicha, contenidoSeccion, nombreEntidad, type Acciones, type DatosFicha, type FiltroEvidencia, type OpcionesGrafico } from './ficha';
import { iconoProducto } from './iconos';
import { cabecerasOrdenables, granos3, seccion } from './primitivos';
import { medirPlacas, placa } from './registro';

export interface Paginas {
	raiz: HTMLElement;
	miga: HTMLElement;
	pintar(e: Estado): void;
	placas(): Placa[];
	/** Franja de pantalla que ocupa la página [arriba, abajo]. */
	franja(): [number, number];
	desplazamiento(): number;
	ocultar(): void;
}

const NOMBRE_SECCION: Record<Seccion, string> = { scoring: 'Scoring', productos: 'Productos', acciones: 'Acciones', tecnico: 'Técnico' };
const ROMANO: Record<Seccion, string> = { scoring: 'I', productos: 'II', acciones: 'III', tecnico: 'IV' };

export function crearPaginas(app: HTMLElement, S: Almacen, c: Cartera, man: Manifiesto, cb: { alCambiarArena(): void; alDesplazar(): void; irCartera(v?: 'plano' | 'tapiz'): void; esMovil(): boolean; corte(): string }): Paginas {
	const raiz = h('main', { class: 'pagina', tabindex: '-1' });
	const miga = h('nav', { class: 'miga', 'aria-label': 'Dónde estás' });
	app.append(raiz, miga);
	raiz.addEventListener('scroll', () => cb.alDesplazar(), { passive: true });

	let clave = '';
	let datos: DatosFicha | null = null;
	const estadoUI = { escenario: 'base' as OpcionesGrafico['escenario'], metrica: 'score', acciones: new Set<string>(), filtro: null as FiltroEvidencia | null, ancla: null as string | null };
	let accionPendiente: string | null = null;

	const acc: Acciones = {
		abrirEmpresa: (id) => { raiz.scrollTop = 0; S.fijar({ vista: 'empresa', emp: id, sec: S.e.sec }, true); },
		abrirGrupo: (id) => { raiz.scrollTop = 0; S.fijar({ vista: 'organizacion', sel: id, emp: null }, true); },
		irSeccion: (s, accion, filtro) => {
			if (accion) { estadoUI.acciones = new Set([accion]); accionPendiente = accion; }
			estadoUI.filtro = filtro ?? null;
			if (S.e.sec === s) pintarFicha(S.e); else S.fijar({ sec: s }, true);
		},
		irBandeja: () => {
			estadoUI.ancla = 'bandeja-avisos';
			if (S.e.sec === 'tecnico') pintarFicha(S.e); else S.fijar({ sec: 'tecnico' }, true);
		},
		repintarArena: () => requestAnimationFrame(() => cb.alCambiarArena()),
	};

	function ocultar() { raiz.hidden = true; miga.hidden = true; clave = ''; }

	// ─── Miga de pan ───────────────────────────────────────
	function pintarMiga(e: Estado) {
		vaciar(miga);
		const paso = (texto: string, accion: (() => void) | null, actual = false) => {
			const b = h(accion ? 'button' : 'span', { class: `miga-paso ${actual ? 'actual' : ''}`, type: accion ? 'button' : undefined, 'aria-current': actual ? 'page' : undefined }, texto);
			if (accion) b.addEventListener('click', accion);
			miga.append(b);
		};
		const sep = () => miga.append(h('span', { class: 'miga-sep', 'aria-hidden': 'true' }, '›'));
		paso('Rumbo', e.vista === 'entrada' ? null : () => S.fijar({ vista: 'entrada', sel: null, emp: null }, true), e.vista === 'entrada');
		if (e.vista === 'metodologia') { sep(); paso('Metodología', null, true); }
		if ((e.vista === 'organizacion' || e.vista === 'empresa') && e.sel) {
			sep();
			paso(f.grupo(e.sel), e.vista === 'empresa' ? () => acc.abrirGrupo(e.sel!) : null, e.vista === 'organizacion');
			if (e.vista === 'empresa' && e.emp) { sep(); paso(f.empresa(e.emp), null, true); }
			miga.append(h('span', { class: 'miga-cuando' }, `· ${f.mes(cb.corte())}`));
		}
		const mapa = h('button', { type: 'button', class: 'miga-mapa' }, 'Mapa de la cartera');
		mapa.addEventListener('click', () => cb.irCartera());
		miga.append(mapa);
	}

	// ─── Marcas de sección (I–IV) ─────────────────────────
	function marcas(e: Estado): HTMLElement {
		const nav = h('nav', { class: 'sec-marcas', 'aria-label': 'Secciones' });
		for (const s of SECCIONES) {
			const b = h('button', { type: 'button', class: `sec-marca ${e.sec === s ? 'activa' : ''}`, 'aria-current': e.sec === s ? 'true' : undefined, title: `${NOMBRE_SECCION[s]} (${SECCIONES.indexOf(s) + 1})` }, h('span', { class: 'sec-marca-n' }, ROMANO[s]), h('span', { class: 'sec-marca-t' }, NOMBRE_SECCION[s]));
			b.addEventListener('click', () => { if (S.e.sec !== s) S.fijar({ sec: s }, true); });
			nav.append(b);
		}
		return nav;
	}

	// ─── Pintar ──────────────────────────────────────────────
	async function pintar(e: Estado) {
		raiz.hidden = false; miga.hidden = false;
		document.body.dataset.pagina = e.vista;
		pintarMiga(e);
		const corte = cb.corte();
		const nueva = `${e.vista}|${e.sel}|${e.emp}|${corte}`;
		const soloSeccion = nueva === clave && datos;
		const k = `${nueva}|${e.sec}`;
		if (soloSeccion) { pintarFicha(e); return; }
		clave = nueva;
		if (e.vista === 'entrada') return pintarEntrada();
		if (e.vista === 'metodologia') return pintarMetodologia();
		vaciar(raiz);
		raiz.append(h('div', { class: 'cargando' }, h('p', {}, 'Leyendo la ficha…')));
		const kind = e.vista === 'empresa' ? 'company' : 'group';
		const id = kind === 'company' ? e.emp! : e.sel!;
		const d = await cargarFicha(kind, id, e.sel!, corte, man);
		if (`${clave}|${S.e.sec}` !== k && clave !== nueva) return;
		// Las organizaciones de su tamaño, del portfolio: el mismo corte y el mismo tramo de tamaño.
		if (d && kind === 'group') {
			const g = c.groups.find((x) => x.id === id);
			const t = c.months.indexOf(corte);
			if (g?.size_band && t >= 0) {
				const vals = c.groups.filter((x) => x.size_band === g.size_band && x.meses[t]?.shown != null).map((x) => x.meses[t].shown!).sort((a, b) => a - b);
				if (vals.length >= 5) d.pares = { mediana: vals[Math.floor(vals.length / 2)], n: vals.length, tamano: g.size_band };
			}
		}
		// Las empresas de su tamaño, del índice de empresas (sale del bundle): mismo corte, mismo tramo.
		if (d && kind === 'company') {
			const ix = await carga.indiceEmpresas();
			const yo = ix?.companies[id];
			if (ix && ix.cut === corte && yo?.size) {
				const vals = Object.values(ix.companies).filter((x) => x.size === yo.size && x.shown !== null).map((x) => x.shown!).sort((a, b) => a - b);
				if (vals.length >= 5) d.pares = { mediana: vals[Math.floor(vals.length / 2)], n: vals.length, tamano: yo.size };
			}
		}
		datos = d;
		if (!d) { vaciar(raiz); raiz.append(h('p', { class: 'vacio' }, `No hay fichero de ${nombreEntidad(kind, id)} en el bundle.`)); cb.alCambiarArena(); return; }
		estadoUI.acciones = accionPendiente ? new Set([accionPendiente]) : new Set();
		accionPendiente = null;
		pintarFicha(S.e);
	}

	function pintarFicha(e: Estado) {
		const d = datos!;
		const y = raiz.scrollTop;
		vaciar(raiz);
		if (accionPendiente) { estadoUI.acciones = new Set([accionPendiente]); accionPendiente = null; }
		const movil = cb.esMovil();
		const hoja = h('article', { class: `hoja-ficha ${d.kind}` });
		hoja.append(cabecera(d, movil, acc), marcas(e));
		const cuerpo = h('div', { class: 'ficha-cuerpo' });
		if (d.kind === 'group' && e.sec === 'scoring') cuerpo.append(flota(d));
		cuerpo.append(contenidoSeccion(d, e.sec, estadoUI, acc, movil));
		hoja.append(cuerpo);
		raiz.append(hoja);
		raiz.scrollTop = e.sec === S.e.sec ? y : 0;
		// Llegada desde un nudo del hilo: la evidencia filtrada, a la vista.
		if (estadoUI.filtro && e.sec === 'tecnico') {
			const ev = raiz.querySelector('.evidencia-filtrada') as HTMLElement | null;
			if (ev) raiz.scrollTop = ev.offsetTop - 70;
			estadoUI.filtro = null;
		}
		if (estadoUI.ancla && e.sec === 'tecnico') {
			const destino = raiz.querySelector(`#${estadoUI.ancla}`) as HTMLElement | null;
			if (destino) {
				raiz.scrollTop = destino.offsetTop - 70;
				destino.focus({ preventScroll: true });
			}
			estadoUI.ancla = null;
		}
		cb.alCambiarArena();
	}

	// ─── Organización: la flota de empresas ────────────────
	function flota(d: DatosFicha): HTMLElement {
		const g = d.ent as GrupoM;
		const filas = d.empresas.map((em) => ({ em, mes: em.ent?.months.find((m) => m.month === d.corte) ?? null }));
		const conScore = filas.filter((x) => x.mes);
		const maxD = Math.max(60, ...conScore.map((x) => Math.abs(x.mes!.verdict.delta3 ?? 0)));
		const plano = h('div', { class: 'flota-plano', 'aria-label': 'Empresas del grupo: score en horizontal, cambio en tres meses en vertical' });
		placa(plano, (cj) => ({
			tipo: 'flota', x: cj.x, y: cj.y, w: cj.w, h: cj.h,
			puntos: conScore.map((x) => ({ x: x.mes!.shown / 1000, y: 0.5 - ((x.mes!.verdict.delta3 ?? 0) / maxD) * 0.45, r: 5, tono: x.mes!.band === 'critical' ? TONO.peligro : TONO.tinta, alfa: 0.9 })),
		}));
		for (const x of conScore) {
			const et = h('button', { type: 'button', class: 'flota-etq', title: `${f.empresa(x.em.res.id)} · ${x.em.res.role} · ${f.score(x.mes!.shown)}` }, f.empresa(x.em.res.id).replace('Empresa ', ''));
			et.style.left = `${(x.mes!.shown / 1000) * 100}%`;
			et.style.top = `${(0.5 - ((x.mes!.verdict.delta3 ?? 0) / maxD) * 0.45) * 100}%`;
			et.addEventListener('click', () => acc.abrirEmpresa(x.em.res.id));
			plano.append(et);
		}
		plano.append(h('span', { class: 'flota-eje x' }, 'score →'), h('span', { class: 'flota-eje y' }, 'cambio en tres meses ↑'));
		const ordenConfianza: Record<string, number> = { high: 3, medium: 2, low: 1 };
		const cuerpotabla = h('tbody', {});
		const pares = filas.map((dato) => {
			const { em, mes } = dato;
			const tr = h('tr', { class: 'tocable', tabindex: '0' },
				h('td', {}, h('b', {}, f.empresa(em.res.id))),
				h('td', {}, em.res.role, h('span', { class: 'sub' }, em.res.inherits_liquidity ? 'hereda la liquidez del grupo' : em.res.treasury_class ?? '')),
				h('td', { class: 'num' }, mes ? h('span', {}, h('b', {}, f.score(mes.shown)), ' ', h('span', { class: 'sub' }, nombreBanda(man, mes.band).toLowerCase())) : '—'),
				h('td', {}, mes ? movimiento(mes) : 'sin datos'),
				h('td', {}, mes ? granos3(mes.conf.label) : ''),
				h('td', { class: 'mini-prods' }, ...(em.prod?.held ?? []).map((t) => iconoProducto(t.product, { tam: 18, titulo: true, sinFilete: true }))),
				h('td', { class: 'num' }, mes?.actions?.length ? f.numero(mes.actions.length) : '—'),
				h('td', {}, cola(em.res.shown.map((v) => v), 88, 20)));
			tr.addEventListener('click', () => acc.abrirEmpresa(em.res.id));
			tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') acc.abrirEmpresa(em.res.id); });
			cuerpotabla.append(tr);
			return { dato, tr };
		});
		const { thead } = cabecerasOrdenables([
			{ titulo: 'Empresa', clave: (x) => f.empresa(x.em.res.id) },
			{ titulo: 'Papel y tesorería', clave: (x) => `${x.em.res.role} ${x.em.res.inherits_liquidity ? 'hereda la liquidez del grupo' : x.em.res.treasury_class ?? ''}` },
			{ titulo: 'Score', num: true, clave: (x) => x.mes?.shown ?? null },
			{ titulo: 'Movimiento', clave: (x) => (x.mes ? movimiento(x.mes) : null) },
			{ titulo: 'Confianza', clave: (x) => (x.mes ? ordenConfianza[x.mes.conf.label] ?? null : null) },
			{ titulo: 'Productos', clave: (x) => (x.em.prod?.held ?? []).length },
			{ titulo: 'Acciones', num: true, clave: (x) => x.mes?.actions?.length ?? null },
		], pares, cuerpotabla, { col: 2, dir: 1 });
		const tabla = h('table', { class: 'tabla-sutil empresas' }, thead, cuerpotabla);
		const hereda = g.companies.filter((x) => x.inherits_liquidity).length;
		return seccion(`Sus ${f.plural(g.companies.length, 'empresa', 'empresas')}`, plano, h('div', { class: 'tabla-caja' }, tabla), hereda ? h('p', { class: 'nota' }, `${f.plural(hereda, 'empresa hereda', 'empresas heredan')} la liquidez del grupo: su colchón es el del grupo.`) : null);
	}

	// ─── Entrada ───────────────────────────────────────────
	async function pintarEntrada() {
		vaciar(raiz);
		const hoja = h('article', { class: 'entrada' });
		const rosa = h('div', { class: 'entrada-rosa', 'aria-hidden': 'true' });
		placa(rosa, (cj) => ({ tipo: 'rosa', cx: cj.x + cj.w / 2, cy: cj.y + cj.h / 2, r: Math.min(cj.w, cj.h) * 0.36 }));
		const entrada = h('input', { class: 'entrada-buscar', type: 'search', placeholder: '¿qué organización?', 'aria-label': 'Buscar organización por número, sector o país', autocomplete: 'off', autofocus: true }) as HTMLInputElement;
		const resultados = h('ul', { class: 'entrada-resultados', role: 'listbox' });
		const buscar = () => {
			vaciar(resultados);
			const q = entrada.value.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
			if (!q) return;
			const num = Number(q.replace(/^grupo\s*/, ''));
			const hits = c.groups.filter((g) => (Number.isFinite(num) && num > 0 && Number(g.id.split('_')[1]) === num) || `${g.industry ?? ''} ${g.country ?? ''} ${f.grupo(g.id)}`.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(q)).slice(0, 8);
			const t = c.months.indexOf(cb.corte());
			for (const g of hits) {
				const m = g.meses[t];
				const li = h('li', { role: 'option', tabindex: '0', class: 'tocable' }, h('b', {}, f.grupo(g.id)), h('span', { class: 'sub' }, [g.industry, g.country, f.plural(g.n_companies, 'empresa', 'empresas')].filter(Boolean).join(' · ')), h('span', { class: 'res-score' }, m?.shown != null ? f.score(m.shown) : '—'));
				li.addEventListener('click', () => acc.abrirGrupo(g.id));
				li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') acc.abrirGrupo(g.id); });
				resultados.append(li);
			}
			if (!hits.length) resultados.append(h('li', { class: 'nota' }, `Ninguna organización con «${entrada.value}». Prueba con un número (42), un sector o un país.`));
		};
		entrada.addEventListener('input', buscar);
		entrada.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') (resultados.querySelector('li.tocable') as HTMLElement | null)?.click(); });
		const atencion = h('ol', { class: 'atencion' }, h('li', { class: 'nota' }, 'Buscando las que piden atención…'));
		const mapa = h('div', { class: 'entrada-mapa' });
		for (const [v, t, d] of [['plano', 'El plano', 'Nivel y ritmo de cada organización'], ['tapiz', 'El tapiz', 'Cada organización, mes a mes']] as const) {
			const b = h('button', { type: 'button', class: 'mapa-btn' }, h('b', {}, t), h('span', {}, d));
			b.addEventListener('click', () => cb.irCartera(v));
			mapa.append(b);
		}
		const met = h('button', { type: 'button', class: 'as-enlace' }, 'Cómo se calcula todo esto');
		met.addEventListener('click', () => S.fijar({ vista: 'metodologia' }, true));
		hoja.append(
			rosa,
			h('div', { class: 'entrada-frase' }, h('span', { class: 'entrada-rumbo' }, 'Rumbo de'), entrada),
			resultados,
			h('p', { class: 'entrada-lema' }, `${f.numero(man.counts.groups)} organizaciones y ${f.numero(man.counts.companies)} empresas, de ${f.mes(man.months[0])} a ${f.mes(man.months[man.months.length - 1])}. Dónde está cada una, hacia dónde va y qué puede cambiar su rumbo.`),
			seccion('Las que piden atención hoy', atencion),
			seccion('O buscarla en el mapa', mapa, met),
		);
		raiz.append(hoja);
		cb.alCambiarArena();
		requestAnimationFrame(() => entrada.focus({ preventScroll: true }));
		// Las que piden atención: datos del motor y de los horizontes, nada más.
		const [alertas, horizontes] = await Promise.all([carga.alertas(), carga.horizontesIndice()]);
		vaciar(atencion);
		for (const it of piden(c, cb.corte(), alertas.alerts, horizontes?.entities ?? {}, man).slice(0, 8)) {
			const g = c.groups.find((x) => x.id === it.id)!;
			const li = h('li', { class: 'tocable', tabindex: '0' }, h('b', {}, f.grupo(it.id)), h('span', { class: 'at-texto' }, it.texto), cola(g.meses.map((m) => m.shown), 96, 22));
			li.addEventListener('click', () => acc.abrirGrupo(it.id));
			li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') acc.abrirGrupo(it.id); });
			atencion.append(li);
		}
		if (!atencion.children.length) atencion.append(h('li', { class: 'nota' }, 'Ninguna organización cambia este mes.'));
		cb.alCambiarArena();
	}

	// ─── Metodología ───────────────────────────────────────
	async function pintarMetodologia() {
		vaciar(raiz);
		const hoja = h('article', { class: 'metodologia' }, h('h1', {}, 'Cómo se calcula todo esto'));
		raiz.append(hoja);
		const [recibo, prod, hor, params] = await Promise.all([carga.recibo(), carga.productosIndice(), carga.horizontesIndice(), carga.parametros()]);
		hoja.append(h('p', { class: 'lema' }, 'Todo lo que enseña Rumbo sale de estos ficheros. Nada está escrito a mano en la aplicación.'));
		hoja.append(seccion('La huella', h('dl', { class: 'dl-tecnica' },
			h('dt', {}, 'Motor'), h('dd', {}, `${man.engine_version} · bundle ${man.bundle_id.slice(0, 16)} · ${new Date(man.generated_at).toLocaleString('es-ES')}`),
			h('dt', {}, 'Parámetros'), h('dd', {}, `${man.params_hash.slice(0, 16)}${params ? ' · copia verificada' : ''}`),
			h('dt', {}, 'Datos del reto'), h('dd', {}, man.dataset_hash.slice(0, 16)),
			h('dt', {}, 'Recibo'), h('dd', {}, recibo ? (recibo.params_hash === man.params_hash && recibo.dataset_hash === man.dataset_hash ? 'coincide con el bundle' : 'no coincide con el bundle') : 'sin recibo'))));
		if (recibo) {
			const est: Record<string, string> = { pass: 'superada', fail: 'no superada', info: 'informativa', not_run: 'no ejecutada' };
			hoja.append(seccion(`Comprobaciones del motor · ${recibo.checks.filter((x) => x.status === 'pass').length} de ${recibo.checks.length} superadas`,
				h('ul', { class: 'checks' }, ...recibo.checks.map((ch) => h('li', { class: `check ${ch.status}` }, h('span', { class: 'versalita' }, est[ch.status]), h('b', {}, ch.title), h('p', {}, ch.summary),
					ch.metrics.length ? h('p', { class: 'nota' }, ch.metrics.slice(0, 6).map((mm) => `${mm.label}: ${f.valorUnidad(mm.value, mm.unit)}`).join(' · ')) : null)))));
			hoja.append(seccion('Lo que entra en el número', h('ul', { class: 'senales' }, ...recibo.signals.map((s) => h('li', {}, h('b', {}, s.label), ` · peso ${f.porcentaje(s.weight, 0)}`, h('p', {}, s.why))))));
			const porRazon = new Map<string, number>();
			for (const a of recibo.abstentions) porRazon.set(a.reason, (porRazon.get(a.reason) ?? 0) + 1);
			hoja.append(seccion('Dónde se abstiene', h('ul', { class: 'senales' }, ...[...porRazon].map(([r, n]) => h('li', {}, h('b', {}, man.glossary.reasons[r] ?? r), ` · ${f.plural(n, 'mes de entidad', 'meses de entidad')}`, h('p', {}, recibo.abstentions.find((a) => a.reason === r)?.unlock ?? ''))))));
		}
		if (hor) {
			const cal = hor.calibration as { h3?: { cov50: number; cov80: number }; h6?: { cov50: number; cov80: number }; mae_median?: number; mae_naive?: number; eval_cut?: string };
			hoja.append(seccion('El futuro', h('p', {}, `Para cada entidad se simulan 12 meses, 400 veces, a partir de sus propias variaciones, y cada mes simulado se puntúa con las funciones del motor. Comprobado contra lo que pasó de verdad desde ${cal.eval_cut ? f.mes(cal.eval_cut) : '—'}: a seis meses, la franja del 80 % acierta el ${f.porcentaje(cal.h6?.cov80 ?? 0, 0)} de las veces. La mediana se equivoca en ${f.numero(cal.mae_median ?? 0, 1)} puntos de media, frente a ${f.numero(cal.mae_naive ?? 0, 1)} de suponer que nada cambia.`),
				h('p', { class: 'nota' }, `El corte se reproduce con el motor en ${hor.checks.h0_reproduced} entidades; cada acción llega a la cifra del motor en ${hor.checks.actions_consistent}. Los horizontes nunca cambian un score, un veredicto ni un aviso.`)));
		}
		if (prod) {
			const p = prod.portfolio;
			hoja.append(seccion('Los productos', h('ul', { class: 'senales' }, ...Object.entries(p).map(([id, x]) => h('li', { class: 'prod-met' }, iconoProducto(id as never, { tam: 32 }), h('div', {}, h('b', {}, `${f.plural(x.companies, 'empresa', 'empresas')}`), ` en ${f.plural(x.groups, 'grupo', 'grupos')}: ${f.numero(x.declared)} declaradas por el banco, ${f.numero(x.inferred)} deducidas de sus movimientos`, h('p', { class: 'nota' }, (prod.rules[id] as { note?: string })?.note ?? '')))))));
		}
		cb.alCambiarArena();
	}

	return {
		raiz, miga, pintar: (e) => { void pintar(e); }, ocultar,
		placas: () => medirPlacas(raiz),
		franja: () => { const r = raiz.getBoundingClientRect(); return [r.top, r.bottom]; },
		desplazamiento: () => raiz.scrollTop,
	};
}

/** Las organizaciones que piden atención en el corte: avisos nuevos, cambios de banda y horizontes que caen. */
function piden(c: Cartera, corte: string, alertas: AlertaM[], hor: Record<string, { p_critical_h6: number | null; cross: { to: string; month: string; prob: number } | null; shown_at_cut: number | null }>, man: Manifiesto) {
	const t = c.months.indexOf(corte);
	const salida: { id: string; peso: number; texto: string }[] = [];
	for (const g of c.groups) {
		const m = g.meses[t], a = g.meses[t - 1];
		if (!m || m.shown === null) continue;
		const nuevos = alertas.filter((x) => x.entity_kind === 'group' && x.entity_id === g.id && x.month === corte && x.state === 'fired');
		const partes: string[] = []; let peso = 0;
		if (a?.band && m.band && a.band !== m.band) {
			const baja = man.bands.findIndex((b) => b.key === m.band) < man.bands.findIndex((b) => b.key === a.band);
			partes.push(`${baja ? 'baja' : 'sube'} a ${nombreBanda(man, m.band).toLowerCase()} este mes`); peso += baja ? 3 : 1;
		}
		if (nuevos.some((x) => x.kind === 'deterioration_structural' || x.kind === 'deterioration_drift')) { partes.push('deterioro confirmado'); peso += 3; }
		const hz = hor[g.id];
		if (hz?.cross && m.band !== hz.cross.to) {
			const baja = man.bands.findIndex((b) => b.key === hz.cross!.to) < man.bands.findIndex((b) => b.key === m.band);
			if (baja && hz.cross.prob >= 0.5) { partes.push(`${f.porcentaje(hz.cross.prob, 0)} de pasar a ${nombreBanda(man, hz.cross.to).toLowerCase()} hacia ${f.mes(hz.cross.month)}`); peso += 2 + hz.cross.prob; }
		}
		if (partes.length) salida.push({ id: g.id, peso, texto: `${f.score(m.shown)} · ${partes.join(' · ')}` });
	}
	return salida.sort((a, b) => b.peso - a.peso);
}

export type { EmpresaM };
