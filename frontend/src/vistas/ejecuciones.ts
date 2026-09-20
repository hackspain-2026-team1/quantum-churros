import { ejecuciones, avanceEjecucion, estadosEjecucion, pasosEjecucion, situacionAccion, valorEjecucion, ErrorEjecuciones, type Ejecucion, type EstadoEjecucion, type SituacionAccion } from '../datos/ejecuciones';
import { f } from '../datos/formato';
import { voz } from '../datos/redaccion';
import type { DatosFicha } from './ficha';
import { h } from './dom';
import { seccion } from './primitivos';
import './ejecuciones.css';
import { abrirConfirmacionAcciones } from './propuesta';

/** Lo que el seguimiento necesita de la lista de acciones: repintarla y soltar lo ya ejecutado. */
export interface EnlaceLista {
	/** Las decisiones guardadas han cambiado: las filas tienen que contar otra cosa. */
	alCambiar(): void;
	/** Estas acciones ya no son una simulación: salen de la selección del horizonte. */
	soltar(ids: string[]): void;
}

const ORDEN: Record<EstadoEjecucion, number> = { en_curso: 0, pausada: 1, completada: 2 };

/** Selection is a simulation; only an acknowledged API write starts execution. */
export function seguimientoAcciones(d: DatosFicha, seleccion: () => Set<string>, enlace: EnlaceLista) {
	const ambito = { entity_id: d.id, group_id: d.grupoId, kind: d.kind };
	const actor = voz('Embat', 'CFO');
	const ultimoCierre = d.corte === d.ent.months.at(-1)?.month;
	const lista = h('div', { class: 'ejecuciones-lista' });
	const aviso = h('p', { class: 'nota', role: 'status', 'aria-live': 'polite' });
	const error = h('p', { class: 'ejecuciones-error', role: 'alert' });
	const refrescar = h('button', { type: 'button', class: 'miga-accion' }, 'Actualizar seguimiento');
	const raiz = seccion('Acciones en marcha', h('div', { class: 'ejecuciones-cabecera' }, h('p', { class: 'nota' }, 'Qué estás llevando a cabo y cómo evoluciona frente al objetivo que elegiste.'), refrescar), aviso, error, lista);
	raiz.classList.add('ejecuciones');
	const boton = h('button', { type: 'button', class: 'boton-propuesta' }, 'Ejecutar acciones');
	const mensaje = h('p', { class: 'nota', role: 'status', 'aria-live': 'polite' });
	let registros: Ejecucion[] = [], cargado = false, ocupado = false, historialAbierto = false;
	/** Las recién tocadas se señalan una vez, para que el ojo las encuentre tras el cambio. */
	let recientes = new Set<string>();

	const situacion = (id: string): SituacionAccion => situacionAccion(registros, id, d.corte);
	const ocupadas = () => new Set(registros.filter(e => situacion(e.snapshot.id).registro === e).map(e => e.snapshot.id));
	const ids = () => [...seleccion()].filter(id => d.mes?.actions?.some(a => a.id === id) && situacion(id).estado === 'disponible');
	const actualizarBoton = () => {
		const n = ids().length;
		boton.disabled = ocupado || !cargado || !ultimoCierre;
		boton.textContent = ocupado ? 'Guardando…' : n ? `Ejecutar ${f.plural(n, 'acción', 'acciones')}` : 'Ejecutar acciones';
		if (!ultimoCierre) mensaje.textContent = 'Vuelve al último cierre para poner acciones en marcha.';
	};
	const resumen = () => {
		const n = (e: EstadoEjecucion) => registros.filter(v => v.status === e).length;
		const partes = [n('en_curso') ? f.plural(n('en_curso'), 'acción en curso', 'acciones en curso') : '', n('pausada') ? `${n('pausada')} en pausa` : ''].filter(Boolean);
		return partes.length ? partes.join(' · ') : 'No hay acciones en curso. Puedes elegir una nueva acción o consultar las decisiones anteriores.';
	};

	function tarjeta(e: Ejecucion): HTMLElement {
		const s = e.snapshot, avance = avanceEjecucion(e, d.corte);
		const abierta = e.status !== 'completada';
		const abrir = h('button', { type: 'button', class: 'ejecucion-abrir' }, abierta ? 'Actualizar avance' : 'Ver decisión', h('span', { 'aria-hidden': 'true' }, ' ↗'));
		const ficha = h('article', { class: `ejecucion estado-${e.status}${recientes.has(e.id) ? ' reciente' : ''}`, 'data-ejecucion': e.id, 'data-estado': e.status, tabindex: '-1' },
			h('header', {}, h('h4', { title: s.title }, s.title)),
			h('p', { class: 'ejecucion-fecha' }, h('span', { class: `ejecucion-estado estado-${e.status}` }, estadosEjecucion[e.status]), ` · desde ${f.mesCorto(s.corte)}`),
			s.financing ? h('div', { class: 'ejecucion-cifras ejecucion-bancos' }, h('span', {}, 'Bancos elegidos'), h('b', {}, s.banks?.length ? s.banks.join(' · ') : 'Buscar ofertas con Embat')) :
			h('div', { class: 'ejecucion-cifras' },
				h('p', {}, h('span', {}, 'Inicio'), h('b', {}, valorEjecucion(s.baseline, s.unit))),
				h('p', {}, h('span', {}, avance.mes ? f.mesCorto(avance.mes) : 'Nuevo cierre'), h('b', {}, avance.mes ? valorEjecucion(avance.actual, s.unit) : 'Pendiente')),
				h('p', {}, h('span', {}, 'Objetivo'), h('b', {}, valorEjecucion(s.target, s.unit)))),
			h('div', { class: 'ejecucion-progreso' }, h('p', { class: 'ejecucion-avance' }, s.financing ? 'Gestión con los bancos' : avance.texto,
				avance.barra !== null ? h('b', { class: 'num' }, f.porcentaje(avance.barra, 0)) : null),
				avance.barra !== null ? h('progress', { max: 1, value: avance.barra, 'aria-label': `Avance medido de ${s.title}` }) : h('span', { class: 'ejecucion-sin-medida', 'aria-hidden': 'true' })),
			h('p', { class: 'ejecucion-demo' }, s.demo ? 'Demo · cifras históricas del motor' : ''), abrir);
		abrir.addEventListener('click', () => abrirDialogo(e, abrir));
		return ficha;
	}

	function abrirDialogo(e: Ejecucion, origen: HTMLElement) {
		const s = e.snapshot;
		const dialogo = h('dialog', { class: 'ejecucion-dialogo', 'aria-label': s.title }) as HTMLDialogElement;
		const nota = h('textarea', { rows: 3, maxlength: 2000, placeholder: e.status === 'completada' ? 'Por qué se reabre (opcional)' : 'Qué avanzó y cuál es el próximo paso', 'aria-label': `Nota de seguimiento: ${s.title}` }) as HTMLTextAreaElement;
		const respuesta = h('p', { class: 'nota', role: 'status', 'aria-live': 'polite' });
		const cerrar = h('button', { type: 'button', class: 'miga-accion' }, 'Cerrar');
		const guardar = h('button', { type: 'button', class: 'boton-propuesta' }, 'Guardar nota');
		guardar.disabled = true;
		const pasos = pasosEjecucion[e.status].map(p => ({ ...p, boton: h('button', { type: 'button', class: 'miga-accion' }, p.verbo) }));
		const botones = [guardar, ...pasos.map(p => p.boton)];
		let guardando = false;
		nota.addEventListener('input', () => { guardar.disabled = guardando || !nota.value.trim(); });
		cerrar.addEventListener('click', () => dialogo.close());
		dialogo.addEventListener('cancel', ev => { if (guardando) ev.preventDefault(); });
		dialogo.addEventListener('close', () => { dialogo.remove(); if (origen.isConnected) origen.focus(); });
		dialogo.addEventListener('keydown', ev => ev.stopPropagation());

		const historial = h('ol', { class: 'ejecucion-historial' });
		for (const ev of e.events.filter(v => v.kind === 'decision')) {
			const p = ev.payload;
			const hecho = p.previous_status === undefined ? 'Puesta en marcha' : p.previous_status === p.status ? 'Nota' : p.status === 'en_curso' ? (p.previous_status === 'completada' ? 'Reabierta' : 'Reanudada') : estadosEjecucion[p.status!];
			historial.append(h('li', {}, h('span', {}, `${f.fecha(ev.created_at)} · ${ev.actor} · `), h('b', {}, hecho), p.note && p.note !== hecho ? h('p', {}, p.note) : null));
		}
		const medidas = h('ul', { class: 'ejecucion-medidas' });
		for (const ev of e.events.filter(v => v.kind === 'measurement' && v.payload.month! <= d.corte)) medidas.append(h('li', {}, `${f.mesCorto(ev.payload.month!)} · ${valorEjecucion(ev.payload.value ?? null, s.unit)} · observado el ${f.fecha(ev.created_at)}`));

		const enviar = async (estado: EstadoEjecucion) => {
			guardando = true; cerrar.disabled = true; nota.readOnly = true;
			for (const b of botones) b.disabled = true;
			respuesta.textContent = 'Guardando…';
			try {
				const actualizado = await ejecuciones.guardar(e, d.grupoId, estado, nota.value, actor);
				guardando = false; dialogo.close();
				registros = registros.map(v => v.id === e.id ? actualizado : v);
				recientes = new Set([e.id]);
				if (estado === 'completada') historialAbierto = true;
				pintar(); enlace.alCambiar();
				aviso.textContent = estado === e.status ? `Nota guardada en «${s.title}».` : `«${s.title}»: ${estadosEjecucion[estado].toLowerCase()}.${estado === 'completada' ? ' Queda en el historial con su resultado medido.' : ''}`;
				enfocar(e.id);
			} catch (err) {
				guardando = false;
				if (err instanceof ErrorEjecuciones && (err.estado === 409 || err.estado === 404)) {
					// Otra sesión se adelantó: lo que se ve ya no es verdad. Se recarga en vez de reintentar a ciegas.
					dialogo.close(); await cargar(); error.textContent = `${err.message} Se ha recargado el seguimiento.`;
					return;
				}
				respuesta.textContent = (err as Error).message;
				cerrar.disabled = false; nota.readOnly = false;
				for (const p of pasos) p.boton.disabled = false;
				guardar.disabled = !nota.value.trim();
			}
		};
		guardar.addEventListener('click', () => void enviar(e.status));
		for (const p of pasos) p.boton.addEventListener('click', () => void enviar(p.a));

		const explicacion = e.status === 'completada'
			? 'Reabrirla la devuelve a tu seguimiento activo. El historial conserva cuándo se finalizó.'
			: 'Pausar la mantiene a la vista sin darla por hecha. Finalizar la retira del seguimiento activo; el resultado medido y el historial se conservan.';
		dialogo.append(h('header', {}, h('div', {}, h('p', { class: `ejecucion-estado estado-${e.status}` }, estadosEjecucion[e.status]), h('h2', {}, s.title)), cerrar),
			h('p', { class: 'nota' }, `Registrada el ${f.fecha(e.created_at)}${s.demo ? ' · Ejemplo de demostración' : ''}`),
			h('div', { class: 'ejecucion-edicion' }, nota, h('div', { class: 'ejecucion-controles' }, guardar, ...pasos.map(p => p.boton))), respuesta,
			h('p', { class: 'nota' }, explicacion),
			h('h3', {}, 'Historial de decisiones'), historial,
			h('div', {}, medidas.childElementCount ? h('h3', {}, 'Cierres observados') : null, medidas));
		document.body.append(dialogo); dialogo.showModal();
	}

	function pintar() {
		const abiertas = registros.filter(e => e.status !== 'completada').sort((a, b) => ORDEN[a.status] - ORDEN[b.status]);
		const cerradas = registros.filter(e => e.status === 'completada');
		aviso.textContent = resumen();
		const enCurso = h('div', { class: 'ejecuciones-activas', 'aria-label': 'Acciones en curso y en pausa' }, ...abiertas.map(tarjeta));
		lista.replaceChildren(enCurso);
		if (cerradas.length) {
			const archivo = h('details', { class: 'ejecuciones-archivo', open: historialAbierto }, h('summary', {}, `Historial · ${f.plural(cerradas.length, 'acción finalizada', 'acciones finalizadas')}`), h('div', {}, ...cerradas.map(tarjeta))) as HTMLDetailsElement;
			archivo.addEventListener('toggle', () => { historialAbierto = archivo.open; });
			lista.append(archivo);
		}
		recientes = new Set();
		actualizarBoton();
	}

	/** Lleva la vista a la decisión de una acción, esté activa o en el historial. */
	function enfocar(idEjecucion: string) {
		const ficha = lista.querySelector<HTMLElement>(`[data-ejecucion="${CSS.escape(idEjecucion)}"]`);
		if (!ficha) { raiz.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
		const archivo = ficha.closest('details');
		if (archivo) { archivo.open = true; historialAbierto = true; }
		ficha.classList.remove('reciente'); void ficha.offsetWidth; ficha.classList.add('reciente');
		ficha.scrollIntoView({ behavior: 'smooth', block: 'center' });
		ficha.focus({ preventScroll: true });
	}
	const irA = (idAccion: string) => { const r = situacion(idAccion).registro; if (r) enfocar(r.id); else raiz.scrollIntoView({ behavior: 'smooth', block: 'start' }); };

	async function cargar() {
		cargado = false; actualizarBoton();
		refrescar.disabled = true; error.textContent = ''; aviso.textContent = 'Consultando decisiones guardadas…';
		try {
			registros = await ejecuciones.listar(ambito);
			try { registros = await ejecuciones.actualizarMedidas(ambito); }
			catch (err) { error.textContent = `Se muestran las decisiones guardadas. ${(err as Error).message}`; }
			cargado = true; pintar(); enlace.alCambiar();
		} catch (err) { error.textContent = (err as Error).message; aviso.textContent = ''; }
		finally { refrescar.disabled = false; actualizarBoton(); }
	}
	refrescar.addEventListener('click', () => void cargar());
	boton.addEventListener('click', () => {
		abrirConfirmacionAcciones(d, seleccion(), ocupadas(), async (elegidas, financiacion) => {
			ocupado = true; actualizarBoton();
			try {
				const antes = new Set(registros.map(e => e.id));
				registros = await ejecuciones.iniciar(ambito, d.corte, d.man.bundle_id, elegidas, actor, financiacion);
				const nuevas = registros.filter(e => !antes.has(e.id));
				recientes = new Set(nuevas.map(e => e.id));
				// Lo ejecutado deja de ser una simulación marcada: sale del horizonte y pasa al seguimiento.
				enlace.soltar(elegidas);
				pintar(); enlace.alCambiar();
				mensaje.textContent = nuevas.length ? `${f.plural(nuevas.length, 'decisión puesta', 'decisiones puestas')} en marcha. Su evolución se mide desde el próximo cierre.` : 'Esas decisiones ya estaban registradas en el seguimiento.';
				if (nuevas[0]) enfocar(nuevas[0].id); else raiz.scrollIntoView({ behavior: 'smooth', block: 'start' });
			} finally { ocupado = false; actualizarBoton(); }
		});
	});
	void cargar(); actualizarBoton();
	return { raiz, boton, mensaje, actualizarBoton, situacion, irA, cargado: () => cargado };
}
