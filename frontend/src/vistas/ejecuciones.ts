import { ejecuciones, avanceEjecucion, estadosEjecucion, pasosEjecucion, situacionAccion, valorEjecucion, ErrorEjecuciones, type Ejecucion, type EstadoEjecucion, type SituacionAccion } from '../datos/ejecuciones';
import { f } from '../datos/formato';
import { voz } from '../datos/redaccion';
import type { DatosFicha } from './ficha';
import { h } from './dom';
import { marcaBanco, seccion } from './primitivos';
import './ejecuciones.css';
import { abrirConfirmacionAcciones } from './propuesta';

/** Lo que el seguimiento necesita de la lista de acciones. */
export interface EnlaceLista {
	/** Las decisiones guardadas han cambiado: las filas tienen que contar otra cosa. */
	alCambiar(): void;
	/** Estas acciones ya no son una simulación: salen de la selección del horizonte. */
	soltar(ids: string[]): void;
	/** Si la acción tiene fila en la lista: su decisión se sigue ahí y no se repite debajo. */
	enLista(idAccion: string): boolean;
}

/** Las piezas del seguimiento de una decisión, para montarlas en la fila de su acción o en una tarjeta. */
export interface PiezasSeguimiento { registro: Ejecucion; medida: HTMLElement; mandos: HTMLElement; panel: HTMLElement; reciente: boolean }

const ORDEN: Record<EstadoEjecucion, number> = { en_curso: 0, pausada: 1, completada: 2 };

/** Selection is a simulation; only an acknowledged API write starts execution. */
export function seguimientoAcciones(d: DatosFicha, seleccion: () => Set<string>, enlace: EnlaceLista) {
	const ambito = { entity_id: d.id, group_id: d.grupoId, kind: d.kind };
	const actor = voz('Embat', 'CFO');
	const ultimoCierre = d.corte === d.ent.months.at(-1)?.month;
	const lista = h('div', { class: 'ejecuciones-lista' });
	const raiz = seccion('También en marcha', lista);
	raiz.classList.add('ejecuciones');
	raiz.hidden = true;
	const boton = h('button', { type: 'button', class: 'boton-propuesta' }, 'Ejecutar acciones');
	const mensaje = h('p', { class: 'nota ejecuciones-mensaje', role: 'status', 'aria-live': 'polite' });
	let registros: Ejecucion[] = [], cargado = false, ocupado = false, historialAbierto = false;
	/** Las recién tocadas se señalan una vez, para que el ojo las encuentre tras el cambio. */
	let recientes = new Set<string>();
	/** Decisiones con la nota y el historial desplegados, y las que están guardando o han fallado. */
	const abiertas = new Set<string>(), guardando = new Set<string>(), fallos = new Map<string, string>(), borradores = new Map<string, string>();

	const situacion = (id: string): SituacionAccion => situacionAccion(registros, id, d.corte);
	const enSuFila = (e: Ejecucion) => enlace.enLista(e.snapshot.id) && situacion(e.snapshot.id).registro === e;
	const ocupadas = () => new Set(registros.filter(e => situacion(e.snapshot.id).registro === e).map(e => e.snapshot.id));
	const ids = () => [...seleccion()].filter(id => d.mes?.actions?.some(a => a.id === id) && situacion(id).estado === 'disponible');
	const actualizarBoton = () => {
		const n = ids().length;
		boton.disabled = ocupado || !cargado || !ultimoCierre;
		boton.textContent = ocupado ? 'Guardando…' : n ? `Ejecutar ${f.plural(n, 'acción', 'acciones')}` : 'Ejecutar acciones';
		if (!ultimoCierre) mensaje.textContent = 'Vuelve al último cierre para poner acciones en marcha.';
	};
	const repintar = () => { pintar(); enlace.alCambiar(); };

	async function cambiar(e: Ejecucion, estado: EstadoEjecucion) {
		if (guardando.has(e.id)) return;
		guardando.add(e.id); fallos.delete(e.id); repintar();
		try {
			const actualizado = await ejecuciones.guardar(e, d.grupoId, estado, borradores.get(e.id) ?? '', actor);
			registros = registros.map(v => v.id === e.id ? actualizado : v);
			borradores.delete(e.id); recientes = new Set([e.id]);
			if (estado === 'completada') abiertas.delete(e.id);
			guardando.delete(e.id); repintar();
		} catch (err) {
			guardando.delete(e.id);
			// Otra sesión se adelantó: lo que se ve ya no es verdad. Se recarga en vez de reintentar a ciegas.
			if (err instanceof ErrorEjecuciones && (err.estado === 409 || err.estado === 404)) { await cargar(); mensaje.textContent = `${err.message} Se ha recargado el seguimiento.`; return; }
			fallos.set(e.id, (err as Error).message); repintar();
		}
	}

	/** De dónde salió, dónde está en el último cierre medido y adónde va. */
	function medida(e: Ejecucion): HTMLElement {
		const s = e.snapshot, avance = avanceEjecucion(e, d.corte);
		if (s.financing) return h('div', { class: 'seg-medida seg-bancos' }, h('span', {}, 'Bancos'), s.banks?.length ? h('ul', { class: 'seg-banco-lista' }, ...s.banks.map(b => h('li', {}, marcaBanco(b, 20), h('b', {}, b)))) : h('b', {}, 'Buscar ofertas con Embat'));
		return h('div', { class: 'seg-medida' },
			h('p', {}, h('span', {}, 'Inicio'), h('b', {}, valorEjecucion(s.baseline, s.unit))),
			h('p', { class: avance.mes ? '' : 'pendiente' }, h('span', {}, avance.mes ? f.mesCorto(avance.mes) : 'Próximo cierre'), h('b', {}, avance.mes ? valorEjecucion(avance.actual, s.unit) : '—')),
			h('p', {}, h('span', {}, 'Objetivo'), h('b', { class: 'meta' }, valorEjecucion(s.target, s.unit))),
			avance.barra !== null ? h('progress', { max: 1, value: avance.barra, 'aria-label': `${avance.texto}: ${s.title}`, title: `${avance.texto} · ${f.porcentaje(avance.barra, 0)}` }) : null);
	}

	/** El estado y lo que se puede hacer desde él, a un clic y sin diálogo. */
	function mandos(e: Ejecucion): HTMLElement {
		const ocupada = guardando.has(e.id);
		const otroCierre = e.snapshot.corte !== d.corte;
		const pasos = pasosEjecucion[e.status].map(p => {
			const b = h('button', { type: 'button', class: 'seg-paso', disabled: ocupada }, p.verbo);
			b.addEventListener('click', ev => { ev.stopPropagation(); void cambiar(e, p.a); });
			return b;
		});
		const nota = h('button', { type: 'button', class: 'seg-paso seg-nota', 'aria-expanded': String(abiertas.has(e.id)) }, 'Notas');
		nota.addEventListener('click', ev => { ev.stopPropagation(); alternarPanel(e.id); });
		return h('div', { class: 'seg-mandos' },
			h('p', { class: `seg-estado estado-${e.status}` }, ocupada ? 'Guardando…' : estadosEjecucion[e.status], otroCierre ? h('span', {}, ` · ${f.mesCorto(e.snapshot.corte)}`) : null),
			h('div', { class: 'seg-pasos' }, ...pasos, nota),
			fallos.has(e.id) ? h('p', { class: 'ejecuciones-error', role: 'alert' }, fallos.get(e.id)!) : null);
	}

	/** La nota y lo ocurrido hasta ahora. Se despliega bajo la decisión; no tapa la página. */
	function panel(e: Ejecucion): HTMLElement {
		const s = e.snapshot;
		const caja = h('div', { class: 'seg-panel', hidden: !abiertas.has(e.id) });
		if (!abiertas.has(e.id)) return caja;
		const texto = h('textarea', { rows: 2, maxlength: 2000, placeholder: 'Qué avanzó y cuál es el próximo paso', 'aria-label': `Nota de seguimiento: ${s.title}`, disabled: guardando.has(e.id) }) as HTMLTextAreaElement;
		texto.value = borradores.get(e.id) ?? '';
		const guardar = h('button', { type: 'button', class: 'seg-paso', disabled: !texto.value.trim() || guardando.has(e.id) }, 'Guardar nota');
		texto.addEventListener('input', () => { borradores.set(e.id, texto.value); guardar.disabled = !texto.value.trim(); });
		texto.addEventListener('keydown', ev => ev.stopPropagation());
		guardar.addEventListener('click', () => void cambiar(e, e.status));
		const hechos = h('ol', { class: 'seg-historial' });
		for (const ev of e.events.filter(v => v.kind === 'decision')) {
			const p = ev.payload;
			const hecho = p.previous_status === undefined ? 'Puesta en marcha' : p.previous_status === p.status ? 'Nota' : p.status === 'en_curso' ? (p.previous_status === 'completada' ? 'Reabierta' : 'Reanudada') : estadosEjecucion[p.status!];
			hechos.append(h('li', {}, h('span', {}, `${f.fecha(ev.created_at)} · ${ev.actor}`), h('b', {}, hecho), p.note && p.note !== hecho ? h('p', {}, p.note) : null));
		}
		for (const ev of e.events.filter(v => v.kind === 'measurement' && v.payload.month! <= d.corte))
			hechos.append(h('li', { class: 'cierre' }, h('span', {}, `${f.fecha(ev.created_at)} · Motor`), h('b', {}, `Cierre de ${f.mesCorto(ev.payload.month!)}`), h('p', {}, valorEjecucion(ev.payload.value ?? null, s.unit))));
		caja.append(h('div', { class: 'seg-escribir' }, texto, guardar), hechos);
		caja.addEventListener('click', ev => ev.stopPropagation());
		return caja;
	}
	function alternarPanel(id: string) {
		if (abiertas.has(id)) abiertas.delete(id); else abiertas.add(id);
		repintar();
		if (abiertas.has(id)) document.querySelector<HTMLElement>(`[data-ejecucion="${CSS.escape(id)}"] textarea`)?.focus();
	}

	/** Lo que no tiene fila en la lista de acciones: financiación, decisiones de otros cierres, ejemplos. */
	function tarjeta(e: Ejecucion): HTMLElement {
		const s = e.snapshot;
		return h('article', { class: `ejecucion estado-${e.status}${recientes.has(e.id) ? ' reciente' : ''}`, 'data-ejecucion': e.id, 'data-estado': e.status, tabindex: '-1' },
			h('h4', { title: s.title }, s.title, s.demo ? h('span', { class: 'ejecucion-demo' }, 'Ejemplo de demostración') : null),
			medida(e), mandos(e), panel(e));
	}

	function pintar() {
		const resto = registros.filter(e => !enSuFila(e));
		const vivas = resto.filter(e => e.status !== 'completada').sort((a, b) => ORDEN[a.status] - ORDEN[b.status]);
		const cerradas = resto.filter(e => e.status === 'completada');
		raiz.hidden = !resto.length;
		raiz.querySelector('.sec-titulo')!.textContent = vivas.length ? 'También en marcha' : 'Historial';
		lista.replaceChildren(...vivas.map(tarjeta));
		if (cerradas.length && vivas.length) {
			const archivo = h('details', { class: 'ejecuciones-archivo', open: historialAbierto }, h('summary', {}, `Historial · ${f.numero(cerradas.length)}`), ...cerradas.map(tarjeta)) as HTMLDetailsElement;
			archivo.addEventListener('toggle', () => { historialAbierto = archivo.open; });
			lista.append(archivo);
		} else lista.append(...cerradas.map(tarjeta));
		actualizarBoton();
	}

	/** Las piezas de la decisión que ocupa una acción, para que su fila las monte. */
	function enFila(idAccion: string): PiezasSeguimiento | null {
		const r = situacion(idAccion).registro;
		return r ? { registro: r, medida: medida(r), mandos: mandos(r), panel: panel(r), reciente: recientes.has(r.id) } : null;
	}
	function enfocar(idEjecucion: string) {
		const el = document.querySelector<HTMLElement>(`[data-ejecucion="${CSS.escape(idEjecucion)}"]`);
		if (!el) return;
		const archivo = el.closest('details'); if (archivo) archivo.open = true;
		el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		el.focus({ preventScroll: true });
	}

	async function cargar() {
		cargado = false; actualizarBoton();
		try {
			registros = await ejecuciones.listar(ambito);
			try { registros = await ejecuciones.actualizarMedidas(ambito); } catch { /* Las decisiones guardadas bastan; las medidas llegan en la próxima carga. */ }
			cargado = true; mensaje.replaceChildren(); repintar();
		} catch (err) {
			const reintentar = h('button', { type: 'button', class: 'as-enlace' }, 'Reintentar');
			reintentar.addEventListener('click', () => void cargar());
			mensaje.replaceChildren(h('span', { class: 'ejecuciones-error' }, (err as Error).message), ' ', reintentar);
		} finally { actualizarBoton(); }
	}
	boton.addEventListener('click', () => {
		abrirConfirmacionAcciones(d, seleccion(), ocupadas(), async (elegidas, financiacion) => {
			ocupado = true; actualizarBoton();
			try {
				const antes = new Set(registros.map(e => e.id));
				registros = await ejecuciones.iniciar(ambito, d.corte, d.man.bundle_id, elegidas, actor, financiacion);
				const nuevas = registros.filter(e => !antes.has(e.id));
				recientes = new Set(nuevas.map(e => e.id));
				// Lo ejecutado deja de ser una simulación marcada: sale del horizonte y su fila pasa a seguirlo.
				enlace.soltar(elegidas);
				mensaje.replaceChildren();
				repintar();
				if (nuevas[0]) enfocar(nuevas[0].id);
			} finally { ocupado = false; actualizarBoton(); }
		});
	});
	void cargar(); actualizarBoton();
	const tras = () => { recientes = new Set(); };
	return { raiz, boton, mensaje, actualizarBoton, situacion, enFila, alternarPanel, tras };
}
