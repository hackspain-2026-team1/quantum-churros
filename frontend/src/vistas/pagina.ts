// El controlador de las páginas de Rumbo: la entrada (elegir organización), la organización, la
// empresa y la metodología. Cada página es un documento que se desplaza; la arena la acompaña con
// las placas (registro.ts). La miga de pan va en la misma línea que la marca: Grupo › Empresa.

import { TONO, type Hilo } from '../arena/arena';
import type { Placa } from '../arena/placas';
import { carga } from '../datos/carga';
import type { GrupoM, Manifiesto } from '../datos/contrato';
import type { Filtro } from '../datos/consulta';
import { f } from '../datos/formato';
import type { Cartera } from '../datos/modelo';
import { nombreBanda, movimiento } from '../datos/redaccion';
import { SECCIONES, type Almacen, type Estado, type Seccion } from '../estado';
import { conCifras } from './cifras';
import { cola, h, vaciar } from './dom';
import { desplegable } from './desplegable';
import { cabecera, cargarFicha, contenidoSeccion, graficoHorizonte, nombreEntidad, TONO_BANDA, type Acciones, type DatosFicha, type FiltroEvidencia } from './ficha';
import { crearFinanciacion } from './financiacion';
import { iconoProducto } from './iconos';
import { logotipo, monograma } from './marca';
import { crearMonitor, type Monitor } from './monitor';
import { glifoExtender } from './piezas';
import { cabecerasOrdenables, granos3, reglaBanda, seccion } from './primitivos';
import { medirFijas, medirPlacas, placa } from './registro';

export interface Paginas {
	raiz: HTMLElement;
	miga: HTMLElement;
	pintar(e: Estado): void;
	placas(): Placa[];
	/** Franja de pantalla que ocupa la página [arriba, abajo]. */
	franja(): [number, number];
	desplazamiento(): number;
	ocultar(): void;
	/** Los avisos confirmados de la entidad abierta, para la regla (índice de mes y si es mejora). */
	avisosPropios(): { month: string; mejora: boolean }[] | null;
	/** El informe imprimible de la ficha abierta (las cuatro secciones seguidas), o null. */
	informe(): HTMLElement | null;
	/** Lleva a la bandeja de avisos de la portada. */
	irAvisos(): void;
}

const NOMBRE_SECCION: Record<Seccion, string> = { scoring: 'Detalle', productos: 'Productos', acciones: 'Acciones', tecnico: 'Desglose', conciliacion: 'Conciliación' };
// En una organización, la sección de scoring es la lista de sus empresas.
const nombreSeccion = (s: Seccion, vista: Estado['vista']) => s === 'scoring' && vista === 'organizacion' ? 'Empresas' : NOMBRE_SECCION[s];

export function crearPaginas(app: HTMLElement, S: Almacen, c: Cartera, man: Manifiesto, cb: { alCambiarArena(): void; alDesplazar(): void; irCartera(v?: 'plano' | 'tapiz'): void; esMovil(): boolean; corte(): string; desde(): string; imprimir(): void; hilo(hs: Hilo[]): void }): Paginas {
	// La página: el escenario (el protagonista, fijo) y el cuerpo, que se desplaza debajo.
	const raiz = h('main', { class: 'pagina', tabindex: '-1' });
	const escenario = h('section', { class: 'escenario', 'aria-label': 'Dónde está y hacia dónde va' });
	const cuerpoP = h('div', { class: 'pagina-cuerpo' });
	raiz.append(escenario, cuerpoP);
	const miga = h('nav', { class: 'miga', 'aria-label': 'Dónde estás' });
	app.append(raiz);
	cuerpoP.addEventListener('scroll', () => { cb.alDesplazar(); cb.hilo([]); marcarHorizonte(); }, { passive: true });
	// El horizonte se queda fijo arriba o se desplaza con las secciones, y entonces estas ocupan la
	// pantalla entera. Lo decide quien mira, desde las pestañas, y se recuerda en este navegador.
	// En pantallas bajas o móviles no hay elección: el escenario no cabe fijo y siempre se desplaza.
	const CLAVE_EXTENDIDA = 'rumbo.ficha.extendida.v1';
	let extendida = (() => { try { return localStorage.getItem(CLAVE_EXTENDIDA) !== 'no'; } catch { return true; } })();
	const cabeFijo = () => !cb.esMovil() && innerHeight >= 620;
	const escenarioFijo = () => cabeFijo() && !extendida;
	/** Alto del escenario cuando se desplaza: dice cuándo el horizonte se ha ido de la pantalla. */
	let altoEscenario = 0;
	const marcarHorizonte = () => raiz.classList.toggle('horizonte-fuera', altoEscenario > 0 && cuerpoP.scrollTop > altoEscenario - 44);
	const medirEscenario = () => { altoEscenario = escenarioFijo() || escenario.hidden ? 0 : escenario.offsetHeight; marcarHorizonte(); };
	const comoSeMueve = (): ScrollBehavior => (matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth');
	const subirAlHorizonte = () => cuerpoP.scrollTo({ top: 0, behavior: comoSeMueve() });
	/** Marcar una acción trae el horizonte a la vista: lo que cambia se ve. */
	const traerHorizonte = () => { if (raiz.classList.contains('horizonte-fuera')) subirAlHorizonte(); };
	/** Extender o recoger: el mismo sitio del documento, con el horizonte fuera o dentro del texto. */
	function alternarExtendida() {
		const alto = escenario.getBoundingClientRect().height;
		extendida = !extendida;
		try { localStorage.setItem(CLAVE_EXTENDIDA, extendida ? 'si' : 'no'); } catch { /* sin almacenamiento: vale para esta sesión */ }
		const y = cuerpoP.scrollTop;
		pintarFicha(S.e);
		cuerpoP.scrollTop = Math.max(0, extendida ? y + alto : y - alto);
		medirEscenario();
		cb.alDesplazar();
	}

	let clave = '';
	/** Qué ficha y qué sección están pintadas: cambiar de pestaña empieza arriba, en el horizonte. */
	let pintada = '';
	let datos: DatosFicha | null = null;
	const financiacion = crearFinanciacion(S, () => cb.alCambiarArena());
	const estadoUI = { metrica: 'score', escenario: 'base' as 'base' | 'drift' | 'stress', acciones: new Set<string>(), previa: null as string[] | null, pilar: null as string | null, filtro: null as FiltroEvidencia | null, ancla: null as string | null, tendencia: true };
	let accionPendiente: string | null = null;
	/** Ancla pendiente en Metodología (una sola vez): la consume pintarMetodologia al terminar. */
	let anclaMetodo: string | null = null;
	const irAMetodologia = (ancla: string) => { anclaMetodo = ancla; S.fijar({ vista: 'metodologia' }, true); };

	const acc: Acciones = {
		abrirEmpresa: (id) => { cuerpoP.scrollTop = 0; S.fijar({ vista: 'empresa', emp: id, sec: S.e.sec }, true); },
		abrirGrupo: (id) => { cuerpoP.scrollTop = 0; S.fijar({ vista: 'organizacion', sel: id, emp: null }, true); },
		irSeccion: (s, accion, filtro) => {
			if (accion) { estadoUI.acciones.add(accion); accionPendiente = accion; }
			estadoUI.filtro = filtro ?? null;
			if (S.e.sec === s) pintarFicha(S.e); else S.fijar({ sec: s }, true);
		},
		irBandeja: () => {
			estadoUI.ancla = 'bandeja-avisos';
			if (S.e.sec === 'tecnico') pintarFicha(S.e); else S.fijar({ sec: 'tecnico' }, true);
		},
		repintarArena: () => requestAnimationFrame(() => cb.alCambiarArena()),
		horizonte: {
			elegidas: () => estadoUI.acciones,
			alternar: (id, si) => { if (si) estadoUI.acciones.add(id); else estadoUI.acciones.delete(id); estadoUI.previa = null; pintarHorizonte(); traerHorizonte(); },
			previa: (ids) => { const k = JSON.stringify(ids); if (k === JSON.stringify(estadoUI.previa)) return; estadoUI.previa = ids; pintarHorizonte(); },
			pilar: (k) => { if (k === estadoUI.pilar) return; estadoUI.pilar = k; pintarHorizonte(); },
		},
		hilo: (hs) => cb.hilo(hs),
	};

	// ─── El protagonista: el número y el horizonte ─────────
	const zonaHorizonte = h('div', { class: 'zona-grafico' });
	const controles = h('div', { class: 'controles-grafico' });
	let temporizadorH = 0;
	function pintarHorizonte() {
		if (!datos) return;
		// Tantear es inmediato para la vista, pero la arena se recompone una vez por gesto.
		clearTimeout(temporizadorH);
		temporizadorH = window.setTimeout(() => {
			const d = datos!;
			const alto = Math.round(Math.max(170, Math.min(300, innerHeight * (cb.esMovil() ? 0.3 : 0.27))));
			zonaHorizonte.replaceChildren(graficoHorizonte(d, { metrica: estadoUI.metrica, escenario: estadoUI.escenario, acciones: estadoUI.acciones, previa: estadoUI.previa, pilar: estadoUI.pilar, tendencia: estadoUI.tendencia, alMetodologia: () => irAMetodologia('met-tendencia'), alto, desde: cb.desde(), alHilo: (hs) => cb.hilo(hs), alElegir: (k) => { estadoUI.escenario = k; pintarHorizonte(); } }, true));
			pintarControles(d);
			medirEscenario();
			cb.alCambiarArena();
		}, estadoUI.previa || estadoUI.pilar ? 40 : 0);
	}
	function pintarControles(d: DatosFicha) {
		vaciar(controles);
		const metricas: [string, string][] = [['score', 'Score'], ...d.ent.series.filter((s) => ['buffer_days', 'cash_month_end', 'headroom', 'ar_days_beyond_terms', 'ap_days_beyond_terms', 'activity_coverage', 'debt_burden', 'op_inflow_1m', 'op_outflow_1m'].includes(s.key)).map((s) => [s.key, s.label] as [string, string])];
		const selM = desplegable({
			etiqueta: 'Qué se dibuja', valor: estadoUI.metrica,
			opciones: metricas.map(([k, n]) => ({ valor: k, texto: n })),
			alElegir: (v) => { estadoUI.metrica = v; pintarHorizonte(); },
		});
		controles.append(selM.raiz);
		if (estadoUI.metrica === 'score') {
			// La línea de tendencia Theil–Sen: se puede quitar; «¿Qué es?» lleva a cómo se mide.
			const grupo = h('span', { class: 'tendencia-ctrl' });
			const ten = h('button', { type: 'button', class: `chip-tendencia ${estadoUI.tendencia ? 'activo' : ''}`, 'aria-pressed': String(estadoUI.tendencia), title: 'La línea de tendencia robusta (Theil–Sen) de los últimos doce meses de score' }, 'Tendencia');
			ten.addEventListener('click', () => { estadoUI.tendencia = !estadoUI.tendencia; pintarHorizonte(); });
			const queEs = h('button', { type: 'button', class: 'enlace-met', title: 'Qué mide esta línea y por qué es robusta' }, '¿Qué es?');
			queEs.addEventListener('click', () => irAMetodologia('met-tendencia'));
			grupo.append(ten, queEs);
			controles.append(grupo);
		}
		if (estadoUI.metrica === 'score' && d.hor?.scenarios && d.hor.cut === d.corte) {
			const sup = h('div', { class: 'escenarios', role: 'radiogroup', 'aria-label': 'Escenario' });
			const nombres = { base: 'Si todo sigue igual', drift: 'Si sigue al mismo ritmo', stress: 'Si se repite su peor trimestre' } as const;
			for (const k of ['base', 'drift', 'stress'] as const) {
				if (k !== 'base' && !d.hor.scenarios[k]) continue;
				const b = h('button', { type: 'button', class: `esc esc-${k} ${estadoUI.escenario === k ? 'activo' : ''}`, 'data-escenario': k, role: 'radio', 'aria-checked': String(estadoUI.escenario === k), title: k === 'drift' ? 'Qué pasaría si: prolonga la pendiente de los últimos doce meses. No es una predicción.' : k === 'stress' ? 'Los tres primeros meses repiten su peor trimestre observado. No es una predicción.' : undefined }, h('span', { class: 'esc-granos', 'aria-hidden': 'true' }), nombres[k]);
				b.addEventListener('click', () => { if (estadoUI.escenario !== k) { estadoUI.escenario = k; pintarHorizonte(); } });
				sup.append(b);
			}
			controles.append(sup);
		}
		if (estadoUI.acciones.size) {
			const quitar = h('button', { type: 'button', class: 'chip-acciones' }, `${f.plural(estadoUI.acciones.size, 'acción marcada', 'acciones marcadas')} · quitar`);
			quitar.addEventListener('click', () => { estadoUI.acciones.clear(); estadoUI.previa = null; pintarFicha(S.e); });
			controles.append(quitar);
		}
		// Extender es un mando del horizonte, no una pestaña: vive aquí, junto a lo que dibuja, y
		// la palabra no cambia nunca. Lo que cambia es si está pulsado.
		if (cabeFijo()) {
			const ext = h('button', { type: 'button', class: `ctrl-extender ${extendida ? 'activa' : ''}`, 'aria-pressed': String(extendida),
				title: extendida
					? 'El horizonte se desplaza con las secciones, que ocupan la pantalla entera. Púlsalo para dejarlo fijo arriba, siempre a la vista.'
					: 'El horizonte se queda fijo arriba, siempre a la vista. Púlsalo para que se desplace con las secciones y estas ocupen la pantalla entera.' },
				glifoExtender(extendida), 'Extender');
			ext.addEventListener('click', alternarExtendida);
			controles.append(ext);
		}
	}

	function ocultar() { raiz.hidden = true; miga.hidden = true; clave = ''; cb.hilo([]); altoEscenario = 0; marcarHorizonte(); }

	// ─── Miga de pan (en la cabecera, junto a la marca) ─────
	function pintarMiga(e: Estado) {
		vaciar(miga);
		const pasos = h('span', { class: 'miga-pasos' });
		const paso = (texto: string, accion: (() => void) | null, actual = false, vuelta = false) => {
			const b = h(accion ? 'button' : 'span', { class: `miga-paso ${actual ? 'actual' : ''} ${vuelta ? 'vuelta' : ''}`, type: accion ? 'button' : undefined, title: vuelta ? `Volver a ${texto} (Esc)` : undefined, 'aria-current': actual ? 'page' : undefined },
				vuelta ? h('span', { class: 'miga-flecha', 'aria-hidden': 'true' }, '‹') : null, texto);
			if (accion) b.addEventListener('click', accion);
			pasos.append(b);
		};
		const sep = () => pasos.append(h('span', { class: 'miga-sep', 'aria-hidden': 'true' }, '›'));
		if (e.vista === 'metodologia') paso('Metodología', null, true);
		if (e.vista === 'financiacion') paso('Financiación', null, true);
		if ((e.vista === 'organizacion' || e.vista === 'empresa') && e.sel) {
			paso(f.grupo(e.sel), e.vista === 'empresa' ? () => acc.abrirGrupo(e.sel!) : null, e.vista === 'organizacion', e.vista === 'empresa');
			if (e.vista === 'empresa' && e.emp) { sep(); paso(f.empresa(e.emp), null, true); }
		}
		miga.append(pasos, h('span', { class: 'hueco' }));
		if (e.vista === 'organizacion' || e.vista === 'empresa') {
			const pdf = h('button', { type: 'button', class: 'miga-accion', title: 'Las cuatro secciones, listas para imprimir o guardar en PDF (⌘P)' }, 'Informe en PDF');
			pdf.addEventListener('click', () => cb.imprimir());
			miga.append(pdf);
		}
		if (e.modo === 'cfo') {
			const mias = h('button', { type: 'button', class: 'miga-accion' }, 'Mis empresas');
			mias.addEventListener('click', () => S.fijar({ vista: 'entrada', emp: null }, true));
			miga.append(mias);
		} else {
			const mapa = h('button', { type: 'button', class: 'miga-accion' }, 'Mapa de la cartera');
			mapa.addEventListener('click', () => cb.irCartera());
			miga.append(mapa);
		}
	}

	// ─── Secciones: tres que actúan sobre el horizonte y, aparte, el reverso técnico ───
	function marcas(e: Estado): HTMLElement {
		const nav = h('nav', { class: 'sec-marcas', 'aria-label': 'Secciones' });
		for (const s of SECCIONES) {
			const b = h('button', { type: 'button', class: `sec-marca ${s === 'tecnico' ? 'reverso' : ''} ${e.sec === s ? 'activa' : ''}`, 'aria-current': e.sec === s ? 'true' : undefined, title: `${nombreSeccion(s, e.vista)} (${SECCIONES.indexOf(s) + 1})` }, nombreSeccion(s, e.vista));
			b.addEventListener('click', () => { if (S.e.sec !== s) S.fijar({ sec: s }, true); });
			nav.append(b);
		}
		// Con el horizonte desplazado fuera de la pantalla, el número sigue aquí y lleva de vuelta.
		const m = datos?.mes;
		if (m) {
			const volver = h('button', { type: 'button', class: `sec-volver banda-${m.band}`, title: 'Volver arriba, al horizonte' },
				h('span', { class: 'versalita' }, nombreBanda(man, m.band)), h('b', {}, f.score(m.shown)), reglaBanda(man, m.shown, m.band));
			volver.addEventListener('click', subirAlHorizonte);
			nav.insertBefore(volver, nav.querySelector('.reverso'));
		}
		return nav;
	}

	// ─── Pintar ──────────────────────────────────────────────
	async function pintar(e: Estado) {
		raiz.hidden = false; miga.hidden = false;
		const ficha = e.vista === 'organizacion' || e.vista === 'empresa';
		raiz.classList.toggle('con-escenario', ficha);
		document.body.dataset.pagina = e.vista;
		pintarMiga(e);
		const corte = cb.corte();
		const nueva = `${e.modo}|${e.cfo}|${e.vista}|${e.sel}|${e.emp}|${e.finRol}|${e.finCaso}|${corte}`;
		const soloSeccion = (e.vista === 'organizacion' || e.vista === 'empresa') && nueva === clave && datos;
		const k = `${nueva}|${e.sec}`;
		if (soloSeccion) { pintarFicha(e); return; }
		clave = nueva;
		if (!ficha) { vaciar(escenario); escenario.hidden = true; altoEscenario = 0; marcarHorizonte(); }
		if (e.vista === 'entrada') return pintarEntrada();
		if (e.vista === 'metodologia') return pintarMetodologia();
		if (e.vista === 'financiacion') {
			vaciar(cuerpoP);
			cuerpoP.append(financiacion.raiz);
			financiacion.pintar(e);
			cb.alCambiarArena();
			return;
		}
		if (!datos || datos.id !== (e.vista === 'empresa' ? e.emp : e.sel)) { vaciar(escenario); vaciar(cuerpoP); cuerpoP.append(h('div', { class: 'cargando' }, h('p', {}, 'Leyendo la ficha…'))); }
		const kind = e.vista === 'empresa' ? 'company' : 'group';
		const id = kind === 'company' ? e.emp! : e.sel!;
		const d = await cargarFicha(kind, id, e.sel!, corte, man);
		if (`${clave}|${S.e.sec}` !== k && clave !== nueva) return;
		// Las organizaciones de su tamaño, del portfolio: el mismo corte y el mismo tramo de tamaño.
		// Son datos de otros clientes de Embat: desde la silla del CFO no se enseñan.
		if (d && kind === 'group' && e.modo !== 'cfo') {
			const g = c.groups.find((x) => x.id === id);
			const t = c.months.indexOf(corte);
			if (g?.size_band && t >= 0) {
				const vals = c.groups.filter((x) => x.size_band === g.size_band && x.meses[t]?.shown != null).map((x) => x.meses[t].shown!).sort((a, b) => a - b);
				if (vals.length >= 5) d.pares = { mediana: vals[Math.floor(vals.length / 2)], n: vals.length, tamano: g.size_band };
			}
		}
		// Las empresas de su tamaño, del índice de entidades derivado del mismo bundle: mismo corte, mismo tramo.
		if (d && kind === 'company' && e.modo !== 'cfo') {
			const ix = await carga.entidades();
			const yo = ix?.companies[id];
			if (ix && ix.cut === corte && yo?.size) {
				const vals = Object.values(ix.companies).filter((x) => x.size === yo.size && x.shown !== null).map((x) => x.shown!).sort((a, b) => a - b);
				if (vals.length >= 5) d.pares = { mediana: vals[Math.floor(vals.length / 2)], n: vals.length, tamano: yo.size };
			}
		}
		datos = d;
		if (!d) { vaciar(cuerpoP); cuerpoP.append(h('p', { class: 'vacio' }, `No hay fichero de ${nombreEntidad(kind, id)} en el bundle.`)); cb.alCambiarArena(); return; }
		// Las acciones marcadas se conservan al mover la regla dentro de la misma entidad.
		if (!datos || datos.id !== d.id) estadoUI.acciones = accionPendiente ? new Set([accionPendiente]) : new Set();
		accionPendiente = null;
		estadoUI.previa = null; estadoUI.pilar = null;
		pintarFicha(S.e);
	}

	function pintarFicha(e: Estado) {
		const d = datos!;
		const y = cuerpoP.scrollTop;
		if (accionPendiente) { estadoUI.acciones.add(accionPendiente); accionPendiente = null; }
		const movil = cb.esMovil();
		// El protagonista: número y horizonte, arriba y siempre a la vista.
		escenario.hidden = false;
		vaciar(escenario);
		escenario.append(h('div', { class: `escenario-hoja ${d.kind}` }, cabecera(d, movil, acc), h('div', { class: 'horizonte' }, controles, zonaHorizonte)));
		const fijo = escenarioFijo();
		raiz.classList.toggle('escenario-fijo', fijo);
		vaciar(cuerpoP);
		if (!fijo) cuerpoP.append(escenario);
		const hoja = h('article', { class: `hoja-ficha ${d.kind}` });
		hoja.append(marcas(e));
		hoja.append(contenidoSeccion(d, e.sec, acc, estadoUI.filtro, d.kind === 'group' ? flota(d) : null));
		cuerpoP.append(hoja);
		if (fijo) raiz.insertBefore(escenario, cuerpoP);
		pintarHorizonte();
		const misma = pintada === `${e.vista}|${e.sel}|${e.emp}|${e.sec}`;
		pintada = `${e.vista}|${e.sel}|${e.emp}|${e.sec}`;
		cuerpoP.scrollTop = misma ? y : 0;
		if (estadoUI.filtro && e.sec === 'conciliacion') {
			const ev = cuerpoP.querySelector('.evidencia-filtrada') as HTMLElement | null;
			if (ev) cuerpoP.scrollTop = ev.offsetTop - 70;
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
		medirEscenario();
		cb.alCambiarArena();
	}

	// ─── Organización: la flota de empresas ────────────────
	function flota(d: DatosFicha): HTMLElement {
		const g = d.ent as GrupoM;
		const filas = d.empresas.map((em) => ({ em, mes: em.ent?.months.find((m) => m.month === d.corte) ?? null }));
		const conScore = filas.filter((x) => x.mes);
		// El eje vertical es simétrico y redondo: el cambio en tres meses, en puntos.
		const maxP = Math.max(6, ...conScore.map((x) => Math.abs(x.mes!.verdict.delta3 ?? 0) / 10));
		const paso = maxP <= 10 ? 5 : maxP <= 20 ? 10 : maxP <= 40 ? 20 : 25;
		const tope = Math.ceil(maxP / paso) * paso;
		const uY = (dp: number) => 0.5 - (dp / tope) * 0.5;
		const plano = h('div', { class: 'flota-plano', 'aria-label': 'Empresas del grupo: score en horizontal, cambio en tres meses en vertical' });
		const bandas = man.bands.filter((b) => b.min > 0).map((b) => b.min / 1000);
		placa(plano, (cj) => ({
			tipo: 'flota', x: cj.x, y: cj.y, w: cj.w, h: cj.h,
			puntos: conScore.map((x) => ({ x: x.mes!.shown / 1000, y: uY((x.mes!.verdict.delta3 ?? 0) / 10), r: 5.5, tono: TONO_BANDA[x.mes!.band] ?? TONO.tinta, alfa: 0.9 })),
			rejillaX: [0.2, 0.4, 0.6, 0.8].map((u) => ({ u, fuerte: bandas.some((b) => Math.abs(b - u) < 1e-6) })).concat(bandas.filter((b) => ![0.2, 0.4, 0.6, 0.8].some((u) => Math.abs(u - b) < 1e-6)).map((u) => ({ u, fuerte: true }))),
			rejillaY: [-tope, -tope / 2, 0, tope / 2, tope].map((v) => ({ u: uY(v), fuerte: v === 0 })),
		}));
		for (const v of [0, 20, 40, 60, 80, 100]) { const t = h('span', { class: 'flota-tick x' }, String(v)); t.style.left = `${v}%`; plano.append(t); }
		for (const v of [-tope, -tope / 2, 0, tope / 2, tope]) { const t = h('span', { class: 'flota-tick y' }, v === 0 ? '0' : `${v > 0 ? '+' : '−'}${Math.abs(v)}`); t.style.top = `${uY(v) * 100}%`; plano.append(t); }
		for (const b of man.bands) { const t = h('span', { class: 'flota-banda' }, b.label.toLowerCase()); t.style.left = `${((b.min + (man.bands[man.bands.indexOf(b) + 1]?.min ?? 1000)) / 20)}%`; plano.append(t); }
		for (const x of conScore) {
			const et = h('button', { type: 'button', class: 'flota-etq', title: `${f.empresa(x.em.res.id)} · ${x.em.res.role} · score ${f.score(x.mes!.shown)} · ${f.delta(x.mes!.verdict.delta3 ?? 0)} en tres meses` }, f.empresa(x.em.res.id));
			et.style.left = `${(x.mes!.shown / 1000) * 100}%`;
			et.style.top = `${uY((x.mes!.verdict.delta3 ?? 0) / 10) * 100}%`;
			et.addEventListener('click', () => acc.abrirEmpresa(x.em.res.id));
			// El hilo en cruz: del punto a sus dos ejes, para leerlo exacto.
			et.addEventListener('pointerenter', () => {
				const r = plano.getBoundingClientRect();
				const px = r.left + (x.mes!.shown / 1000) * r.width, py = r.top + uY((x.mes!.verdict.delta3 ?? 0) / 10) * r.height;
				cb.hilo([{ x0: px, y0: py, x1: px, y1: r.bottom, tono: TONO.info }, { x0: px, y0: py, x1: r.left, y1: py, tono: TONO.info }]);
			});
			et.addEventListener('pointerleave', () => cb.hilo([]));
			plano.append(et);
		}
		plano.append(h('span', { class: 'flota-eje x' }, 'score →'), h('span', { class: 'flota-eje y' }, 'cambio en tres meses, en puntos'));
		const ordenConfianza: Record<string, number> = { high: 3, medium: 2, low: 1 };
		const cuerpotabla = h('tbody', {});
		const pares = filas.map((dato) => {
			const { em, mes } = dato;
			const tr = h('tr', { class: 'tocable', tabindex: '0' },
				h('td', {}, h('b', {}, f.empresa(em.res.id))),
				h('td', {}, em.res.role, h('span', { class: 'sub' }, em.res.inherits_liquidity ? 'hereda la liquidez del grupo' : em.res.treasury_class ?? '')),
				h('td', { class: 'num' }, mes ? h('span', { class: `cel-banda banda-${mes.band}` }, h('b', {}, f.score(mes.shown)), ' ', h('span', { class: 'sub' }, nombreBanda(man, mes.band).toLowerCase())) : '—'),
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
		return seccion(`Las ${f.plural(g.companies.length, 'empresa', 'empresas')}`, h('div', { class: 'tabla-caja' }, tabla), plano, hereda ? h('p', { class: 'nota' }, ...conCifras(`${f.plural(hereda, 'empresa hereda', 'empresas heredan')} la liquidez del grupo: su colchón es el del grupo.`, { que: 'Empresas cuya liquidez decide el grupo' })) : null);
	}

	// ─── Entrada: el monitor de la cartera ─────────────────
	let monitor: Monitor | null = null;
	let avisosPendiente = false;
	function pintarEntrada() {
		vaciar(cuerpoP);
		monitor = crearMonitor({
			c, man, corte: cb.corte,
			cfo: () => (S.e.modo === 'cfo' ? S.e.cfo : null),
			abrirGrupo: (id) => acc.abrirGrupo(id),
			abrirEmpresa: (grupo, id) => { cuerpoP.scrollTop = 0; S.fijar({ vista: 'empresa', sel: grupo, emp: id, sec: 'scoring' }, true); },
			irMapa: (vista, est) => {
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
				S.fijar({ vista, q: { ...S.confirmado.q, filtros } }, true);
			},
			repintarArena: () => requestAnimationFrame(() => cb.alCambiarArena()),
			esMovil: cb.esMovil,
			metodologia: () => S.fijar({ vista: 'metodologia' }, true),
		});
		cuerpoP.append(monitor.raiz);
		if (avisosPendiente) { avisosPendiente = false; requestAnimationFrame(() => monitor?.irAvisos()); }
		cb.alCambiarArena();
	}

	// ─── Metodología ───────────────────────────────────────
	async function pintarMetodologia() {
		vaciar(cuerpoP);
		const hoja = h('article', { class: 'metodologia' }, h('h1', {}, 'Cómo se calcula todo esto'));
		cuerpoP.append(hoja);
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
		if (hor) hoja.append(seccion('El futuro: la previsión del motor', validacion(hor)));
		// La wiki de la tendencia: lo que mide la línea Theil–Sen del horizonte, dicho en llano.
		const secTend = seccion('La tendencia: Theil–Sen',
			h('p', {}, 'La línea de tendencia del horizonte resume hacia dónde va el score: una pendiente robusta, la de Theil–Sen, la mediana de las pendientes entre cada par de meses con dato de los últimos doce.'),
			h('p', {}, 'La mediana aguanta hasta la mitad de los meses raros: un bache puntual no arrastra la línea ni la esconde. Por eso no usamos la recta de mínimos cuadrados ni su R²: la media se deja llevar por un solo mes malo, y el R² mide cuánto de recta es la serie, no hacia dónde va — con un bache, engaña.'),
			h('p', {}, 'Solo mira el pasado: se ancla en el mes que miras, necesita historia suficiente y nunca entra en el score ni en la previsión. El motor la usa para nombrar la deriva lenta cuando el movimiento acumulado pesa frente al vaivén propio de la entidad, y el escenario «Si sigue al mismo ritmo» prolonga exactamente esta pendiente.'));
		secTend.id = 'met-tendencia';
		hoja.append(secTend);
		if (prod) {
			const p = prod.portfolio;
			hoja.append(seccion('Los productos', h('ul', { class: 'senales' }, ...Object.entries(p).map(([id, x]) => h('li', { class: 'prod-met' }, iconoProducto(id as never, { tam: 32 }), h('div', {}, h('b', {}, ...conCifras(`${f.plural(x.companies, 'empresa', 'empresas')}`, { que: 'Empresas con el producto' })), ...conCifras(` en ${f.plural(x.groups, 'grupo', 'grupos')}: ${f.numero(x.declared)} declaradas por el banco, ${f.numero(x.inferred)} deducidas de sus movimientos`, { que: 'De dónde sale que lo tienen' }), h('p', { class: 'nota' }, (prod.rules[id] as { note?: string })?.note ?? '')))))));
		}
		if (anclaMetodo) {
			const destino = anclaMetodo;
			anclaMetodo = null;
			requestAnimationFrame(() => hoja.querySelector(`#${destino}`)?.scrollIntoView({ block: 'center' }));
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
			hoja.prepend(h('header', { class: 'informe-cab' }, h('span', { class: 'informe-marca' }, monograma(26), logotipo(18)), h('span', { class: 'informe-que' }, S.e.modo === 'cfo' && S.e.cfo ? `${f.grupo(S.e.cfo)} · ${f.mes(cb.corte())}` : `Monitor de la cartera · ${f.mes(cb.corte())}`)));
			return hoja;
		}
		if (!datos || (e.vista !== 'organizacion' && e.vista !== 'empresa')) return null;
		const d = datos;
		const quieto: Acciones = { abrirEmpresa: () => {}, abrirGrupo: () => {}, irSeccion: () => {}, irBandeja: () => {}, repintarArena: () => {}, horizonte: { elegidas: () => estadoUI.acciones, alternar: () => {}, previa: () => {}, pilar: () => {} }, hilo: () => {} };
		const hoja = h('article', { class: `hoja-ficha informe ${d.kind}` });
		hoja.append(h('header', { class: 'informe-cab' },
			h('span', { class: 'informe-marca' }, monograma(26), logotipo(18)),
			h('span', { class: 'informe-que' }, `Informe de ${nombreEntidad(d.kind, d.id)}${d.kind === 'company' ? ` (${f.grupo(d.grupoId)})` : ''} · ${f.mes(d.corte)}`)));
		hoja.append(cabecera(d, false, acc), h('div', { class: 'horizonte' }, graficoHorizonte(d, { metrica: 'score', escenario: estadoUI.escenario, acciones: new Set(estadoUI.acciones), previa: null, pilar: null, tendencia: estadoUI.tendencia, alto: 240 }, true)));
		for (const sec of SECCIONES) {
			const cuerpo = h('section', { class: 'informe-seccion' }, h('h2', { class: 'informe-titulo' }, nombreSeccion(sec, e.vista)));
			cuerpo.append(contenidoSeccion(d, sec, quieto, null, d.kind === 'group' && sec === 'scoring' ? flota(d) : null));
			hoja.append(cuerpo);
		}
		hoja.append(h('footer', { class: 'informe-pie' },
			`Rumbo · motor ${man.engine_version} · bundle ${man.bundle_id.slice(0, 12)} · parámetros ${man.params_hash.slice(0, 12)} · datos ${man.dataset_hash.slice(0, 12)} · impreso el ${new Date().toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' })}. Todo sale de los ficheros del motor y de los procesos de Rumbo.`));
		return hoja;
	}

	return {
		raiz, miga, pintar: (e) => { void pintar(e); }, ocultar, informe,
		irAvisos: () => { if (S.e.vista === 'entrada' && monitor?.raiz.isConnected) monitor.irAvisos(); else { avisosPendiente = true; S.fijar({ vista: 'entrada', sel: null, emp: null }, true); } },
		placas: () => [...(raiz.classList.contains('escenario-fijo') && !escenario.hidden ? medirFijas(escenario) : []), ...medirPlacas(cuerpoP)],
		franja: () => { const r = cuerpoP.getBoundingClientRect(); return [r.top, r.bottom]; },
		desplazamiento: () => cuerpoP.scrollTop,
		avisosPropios: () => {
			const e = S.e;
			if (!datos || (e.vista !== 'organizacion' && e.vista !== 'empresa')) return null;
			return datos.ent.alerts.filter((a) => a.state === 'fired' && /structural|drift/.test(a.kind)).map((a) => ({ month: a.month, mejora: a.kind.startsWith('improvement') }));
		},
	};
}

/** La previsión del motor contada con sus pruebas: contra qué se compara y cuánto acierta. */
function validacion(ix: NonNullable<Awaited<ReturnType<typeof carga.horizontesIndice>>>): HTMLElement {
	const v = ix.validation;
	const caja = h('div', { class: 'validacion' });
	const tipo = ix.model?.type ?? 'previsión';
	caja.append(h('p', {}, `El motor aprende de la historia de toda la cartera cómo cambia el score en los meses siguientes: un modelo por horizonte (${tipo}). Cada previsión solo usa lo que se sabía en su mes.`));
	const por = v?.por_horizonte ?? {};
	const filas = Object.entries(por).map(([k, r]) => ({ h: Number(k.slice(1)), ...r })).sort((a, b) => a.h - b.h);
	if (filas.length) {
		const maxE = Math.max(...filas.map((r) => Math.max(r.error_mediana, r.error_sin_cambio)));
		caja.append(h('div', { class: 'tabla-caja' }, h('table', { class: 'tabla-sutil validacion-t' },
			h('thead', {}, h('tr', {}, h('th', {}, 'Meses'), h('th', {}, 'Error de la previsión frente a «no cambia nada» (puntos)'), h('th', { class: 'num' }, 'Franja del 80 %'), h('th', { class: 'num' }, 'Casos'))),
			h('tbody', {}, ...filas.map((r) => h('tr', {}, h('td', {}, String(r.h)),
				h('td', {}, h('span', { class: 'vt-barras' }, h('i', { class: 'modelo', style: { width: `${(r.error_mediana / maxE) * 100}%` } }), h('i', { class: 'naive', style: { width: `${(r.error_sin_cambio / maxE) * 100}%` } })), ` ${f.numero(r.error_mediana, 1)} frente a ${f.numero(r.error_sin_cambio, 1)}`),
				h('td', { class: 'num' }, f.porcentaje(r.acierta_80, 0)), h('td', { class: 'num' }, f.numero(r.n))))))));
	}
	const cortes = v?.cortes ?? [];
	if (cortes.length && v) {
		caja.append(h('p', {}, ...conCifras(`Validado fuera de muestra hasta ${f.plural(v.validado_hasta, 'mes', 'meses')}: en cada corte de ${f.mes(cortes[0])} a ${f.mes(cortes[cortes.length - 1])} se entrenó solo con lo anterior y se comparó con lo que pasó. Más allá, la arena se aclara y se marca «sin validar».`, { que: 'Hasta dónde está comprobada la previsión con lo que pasó después' })));
	} else {
		const viejo = ix as unknown as { calibration?: { eval_cut?: string; mae_median?: number; mae_naive?: number; h6?: { cov80?: number; n?: number } } };
		const c = viejo.calibration;
		if (c) {
			const trozos = [`Prueba hacia atrás${c.eval_cut ? ` desde ${f.mes(c.eval_cut)}` : ''}, comparando con lo que pasó de verdad`];
			if (c.mae_median != null && c.mae_naive != null) trozos.push(`: se equivoca ${f.numero(c.mae_median, 1)} puntos de media, frente a ${f.numero(c.mae_naive, 1)} de suponer que no cambia nada`);
			if (c.h6?.cov80 != null) trozos.push(`; la franja del 80 % acierta el ${f.porcentaje(c.h6.cov80, 0)}${c.h6.n != null ? ` (${f.numero(c.h6.n)} casos)` : ''}`);
			caja.append(h('p', {}, ...conCifras(`${trozos.join('')}.`, { que: 'Prueba de la previsión contra lo que pasó de verdad' })));
		} else {
			caja.append(h('p', { class: 'aviso-datos' }, 'Este índice de horizontes no trae la validación en el formato que lee Rumbo.'));
		}
	}
	caja.append(h('p', {}, `Las acciones no son predicciones: el motor da el score con el pilar en su objetivo y el modelo prevé desde ahí. «Si sigue al mismo ritmo» y «si se repite su peor trimestre» son supuestos, no previsiones.`));
	return caja;
}
