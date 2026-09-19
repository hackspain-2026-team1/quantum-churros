// El controlador de las páginas de Rumbo: la entrada (elegir organización), la organización, la
// empresa y la metodología. Cada página es un documento que se desplaza; la arena la acompaña con
// las placas (registro.ts). La miga de pan va en la misma línea que la marca: Grupo › Empresa.

import { TONO } from '../arena/arena';
import type { Placa } from '../arena/placas';
import { carga } from '../datos/carga';
import type { EmpresaM, GrupoM, Manifiesto } from '../datos/contrato';
import type { Filtro } from '../datos/consulta';
import { f } from '../datos/formato';
import type { Cartera } from '../datos/modelo';
import { nombreBanda, movimiento } from '../datos/redaccion';
import { SECCIONES, type Almacen, type Estado, type Seccion } from '../estado';
import { cola, h, vaciar } from './dom';
import { crearMonitor, type Monitor } from './monitor';
import { cabecera, cargarFicha, contenidoSeccion, nombreEntidad, type Acciones, type DatosFicha, type FiltroEvidencia, type OpcionesGrafico } from './ficha';
import { iconoProducto } from './iconos';
import { logotipo, monograma } from './marca';
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
	/** El informe imprimible de la ficha abierta (las cuatro secciones seguidas) o del monitor, o null. */
	informe(): HTMLElement | null;
	/** Lleva a la bandeja de avisos de la portada. */
	irAvisos(): void;
}

const NOMBRE_SECCION: Record<Seccion, string> = { scoring: 'Scoring', productos: 'Productos', acciones: 'Acciones', tecnico: 'Detalles' };
const ROMANO: Record<Seccion, string> = { scoring: 'I', acciones: 'II', productos: 'III', tecnico: 'IV' };

export function crearPaginas(app: HTMLElement, S: Almacen, c: Cartera, man: Manifiesto, cb: { alCambiarArena(): void; alDesplazar(): void; irCartera(v?: 'plano' | 'tapiz'): void; esMovil(): boolean; corte(): string; imprimir(): void }): Paginas {
	const raiz = h('main', { class: 'pagina', tabindex: '-1' });
	const miga = h('nav', { class: 'miga', 'aria-label': 'Dónde estás' });
	app.append(raiz);
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

	// ─── Miga de pan (en la cabecera, junto a la marca) ─────
	function pintarMiga(e: Estado) {
		vaciar(miga);
		const pasos = h('span', { class: 'miga-pasos' });
		const paso = (texto: string, accion: (() => void) | null, actual = false) => {
			const b = h(accion ? 'button' : 'span', { class: `miga-paso ${actual ? 'actual' : ''}`, type: accion ? 'button' : undefined, 'aria-current': actual ? 'page' : undefined }, texto);
			if (accion) b.addEventListener('click', accion);
			pasos.append(b);
		};
		const sep = () => pasos.append(h('span', { class: 'miga-sep', 'aria-hidden': 'true' }, '›'));
		if (e.vista === 'metodologia') paso('Metodología', null, true);
		if ((e.vista === 'organizacion' || e.vista === 'empresa') && e.sel) {
			paso(f.grupo(e.sel), e.vista === 'empresa' ? () => acc.abrirGrupo(e.sel!) : null, e.vista === 'organizacion');
			if (e.vista === 'empresa' && e.emp) { sep(); paso(f.empresa(e.emp), null, true); }
			pasos.append(h('span', { class: 'miga-cuando' }, f.mes(cb.corte())));
		}
		miga.append(pasos, h('span', { class: 'hueco' }));
		if (e.vista === 'organizacion' || e.vista === 'empresa') {
			const pdf = h('button', { type: 'button', class: 'miga-accion', title: 'Las cuatro secciones, listas para imprimir o guardar en PDF (⌘P)' }, 'Informe en PDF');
			pdf.addEventListener('click', () => cb.imprimir());
			miga.append(pdf);
		}
		const mapa = h('button', { type: 'button', class: 'miga-accion' }, 'Mapa de la cartera');
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
		const soloSeccion = nueva === clave && datos && (e.vista === 'organizacion' || e.vista === 'empresa');
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
		// Las empresas de su tamaño, del índice de entidades derivado del mismo bundle: mismo corte, mismo tramo.
		if (d && kind === 'company') {
			const ix = await carga.entidades();
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
			const et = h('button', { type: 'button', class: 'flota-etq', title: `${f.empresa(x.em.res.id)} · ${x.em.res.role} · ${f.score(x.mes!.shown)}` }, f.empresa(x.em.res.id));
			et.style.left = `${(x.mes!.shown / 1000) * 100}%`;
			et.style.top = `${(0.5 - ((x.mes!.verdict.delta3 ?? 0) / maxD) * 0.45) * 100}%`;
			et.addEventListener('click', () => acc.abrirEmpresa(x.em.res.id));
			plano.append(et);
		}
		plano.append(h('span', { class: 'flota-eje x' }, 'score →'));
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
		return seccion(`Las ${f.plural(g.companies.length, 'empresa', 'empresas')}`, plano, h('div', { class: 'tabla-caja' }, tabla), hereda ? h('p', { class: 'nota' }, `${f.plural(hereda, 'empresa hereda', 'empresas heredan')} la liquidez del grupo: su colchón es el del grupo.`) : null);
	}

	// ─── Entrada: el monitor de la cartera (vistas/monitor.ts) ─
	let monitor: Monitor | null = null;
	function pintarEntrada() {
		vaciar(raiz);
		monitor = crearMonitor({
			c, man, corte: cb.corte,
			abrirGrupo: (id) => acc.abrirGrupo(id),
			abrirEmpresa: (grupo, id) => { raiz.scrollTop = 0; S.fijar({ vista: 'empresa', sel: grupo, emp: id, sec: 'scoring' }, true); },
			irMapa: (v, est) => {
				// Los filtros que el mapa también entiende viajan con él.
				const filtros: Filtro[] = [];
				if (est.filtros.zona) filtros.push({ tipo: 'zona', v: est.filtros.zona });
				if (est.filtros.sector) filtros.push({ tipo: 'sector', v: est.filtros.sector });
				if (est.filtros.pais) filtros.push({ tipo: 'pais', v: est.filtros.pais });
				if (est.filtros.tamano) filtros.push({ tipo: 'tamano', v: est.filtros.tamano });
				if (est.filtros.banda === 'critical') filtros.push({ tipo: 'mov', v: 'critica' });
				if (est.filtros.mov === 'deterioro') filtros.push({ tipo: 'mov', v: 'deterioro' });
				if (est.filtros.mov === 'mejora') filtros.push({ tipo: 'mov', v: 'mejora' });
				if (est.filtros.mov === 'por_confirmar') filtros.push({ tipo: 'mov', v: 'confirmar' });
				if (est.filtros.producto) filtros.push({ tipo: 'producto', v: est.filtros.producto.id, modo: est.filtros.producto.modo });
				S.fijar({ vista: v, q: { ...S.confirmado.q, filtros } }, true);
			},
			repintarArena: () => requestAnimationFrame(() => cb.alCambiarArena()),
			esMovil: cb.esMovil,
			metodologia: () => S.fijar({ vista: 'metodologia' }, true),
		});
		raiz.append(monitor.raiz);
		if (avisosPendiente) { avisosPendiente = false; requestAnimationFrame(() => monitor?.irAvisos()); }
		cb.alCambiarArena();
	}
	let avisosPendiente = false;

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
			const x = hor as unknown as {
				model?: { version?: string; type?: string; features?: string[] };
				validation?: { cortes?: string[]; por_horizonte?: Record<string, { error_mediana: number; error_sin_cambio: number; acierta_80: number; n: number }> };
				calibration?: { h6?: { cov80: number }; mae_median?: number; mae_naive?: number; eval_cut?: string };
				checks?: Record<string, string>;
			};
			const checks = Object.entries(x.checks ?? {}).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ');
			if (x.model && x.validation?.por_horizonte?.h6) {
				// forecast-v1: regresión cuantílica con calibración conformal, validada hacia atrás en varios cortes.
				const v6 = x.validation.por_horizonte.h6, cortes = x.validation.cortes ?? [];
				hoja.append(seccion('El futuro', h('p', {}, `Para cada entidad, un modelo (${x.model.version}) predice el cambio del score a cada horizonte con ${f.plural(x.model.features?.length ?? 0, 'señal', 'señales')} del motor: su nivel, sus pilares y cómo se ha movido. La franja se calibra con lo que pasó de verdad. Comprobado en ${f.plural(cortes.length, 'corte', 'cortes')} ${cortes.length ? `(de ${f.mes(cortes[0])} a ${f.mes(cortes[cortes.length - 1])})` : ''}: a seis meses, la franja del 80 % acierta el ${f.porcentaje(v6.acierta_80, 0)} de las veces, y la mediana se equivoca en ${f.numero(v6.error_mediana, 1)} puntos de media, frente a ${f.numero(v6.error_sin_cambio, 1)} de suponer que nada cambia.`),
					h('p', { class: 'nota' }, `${checks}${checks ? '. ' : ''}Los horizontes nunca cambian un score, un veredicto ni un aviso.`)));
			} else if (x.calibration) {
				const cal = x.calibration;
				hoja.append(seccion('El futuro', h('p', {}, `Para cada entidad se simulan 12 meses, 400 veces, a partir de sus propias variaciones, y cada mes simulado se puntúa con las funciones del motor. Comprobado contra lo que pasó de verdad desde ${cal.eval_cut ? f.mes(cal.eval_cut) : '—'}: a seis meses, la franja del 80 % acierta el ${f.porcentaje(cal.h6?.cov80 ?? 0, 0)} de las veces. La mediana se equivoca en ${f.numero(cal.mae_median ?? 0, 1)} puntos de media, frente a ${f.numero(cal.mae_naive ?? 0, 1)} de suponer que nada cambia.`),
					h('p', { class: 'nota' }, `${checks}${checks ? '. ' : ''}Los horizontes nunca cambian un score, un veredicto ni un aviso.`)));
			}
		}
		if (prod) {
			const p = prod.portfolio;
			hoja.append(seccion('Los productos', h('ul', { class: 'senales' }, ...Object.entries(p).map(([id, x]) => h('li', { class: 'prod-met' }, iconoProducto(id as never, { tam: 32 }), h('div', {}, h('b', {}, `${f.plural(x.companies, 'empresa', 'empresas')}`), ` en ${f.plural(x.groups, 'grupo', 'grupos')}: ${f.numero(x.declared)} declaradas por el banco, ${f.numero(x.inferred)} deducidas de sus movimientos`, h('p', { class: 'nota' }, (prod.rules[id] as { note?: string })?.note ?? '')))))));
		}
		cb.alCambiarArena();
	}

	// ─── Informe para imprimir ─────────────────────────────
	// El mismo HTML de las cuatro secciones, seguido, con el estado que se ve (escenario elegido,
	// acciones marcadas). Sin controles: nada se puede tocar en papel.
	function informe(): HTMLElement | null {
		const e = S.e;
		if (e.vista === 'entrada' && monitor) {
			const hoja = monitor.informe();
			hoja.prepend(h('header', { class: 'informe-cab' }, h('span', { class: 'informe-marca' }, monograma(26), logotipo(18)), h('span', { class: 'informe-que' }, `Monitor de la cartera · ${f.mes(cb.corte())}`)));
			return hoja;
		}
		if (!datos || (e.vista !== 'organizacion' && e.vista !== 'empresa')) return null;
		const d = datos;
		const quieto: Acciones = { abrirEmpresa: () => {}, abrirGrupo: () => {}, irSeccion: () => {}, repintarArena: () => {}, irBandeja: () => {} };
		const hoja = h('article', { class: `hoja-ficha informe ${d.kind}` });
		hoja.append(h('header', { class: 'informe-cab' },
			h('span', { class: 'informe-marca' }, monograma(26), logotipo(18)),
			h('span', { class: 'informe-que' }, `Informe de ${nombreEntidad(d.kind, d.id)}${d.kind === 'company' ? ` (${f.grupo(d.grupoId)})` : ''} · ${f.mes(d.corte)}`)));
		hoja.append(cabecera(d, false, quieto));
		for (const sec of SECCIONES) {
			const cuerpo = h('section', { class: 'informe-seccion' }, h('h2', { class: 'informe-titulo' }, h('span', { class: 'sec-marca-n' }, ROMANO[sec]), ` ${NOMBRE_SECCION[sec]}`));
			if (d.kind === 'group' && sec === 'scoring') cuerpo.append(flota(d));
			cuerpo.append(contenidoSeccion(d, sec, { ...estadoUI, acciones: new Set(estadoUI.acciones), filtro: null }, quieto, false));
			hoja.append(cuerpo);
		}
		hoja.append(h('footer', { class: 'informe-pie' },
			`Rumbo · motor ${man.engine_version} · bundle ${man.bundle_id.slice(0, 12)} · parámetros ${man.params_hash.slice(0, 12)} · datos ${man.dataset_hash.slice(0, 12)} · impreso el ${new Date().toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' })}. Todo sale de los ficheros del motor y de los procesos de Rumbo.`));
		return hoja;
	}

	return {
		raiz, miga, pintar: (e) => { void pintar(e); }, ocultar, informe,
		irAvisos: () => { if (S.e.vista === 'entrada' && monitor?.raiz.isConnected) monitor.irAvisos(); else { avisosPendiente = true; S.fijar({ vista: 'entrada', sel: null, emp: null }, true); } },
		placas: () => medirPlacas(raiz),
		franja: () => { const r = raiz.getBoundingClientRect(); return [r.top, r.bottom]; },
		desplazamiento: () => raiz.scrollTop,
	};
}

export type { EmpresaM };
