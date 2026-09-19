// La frase: el control principal. Dice exactamente qué se está mirando y cada trozo se cambia
// tocándolo. Reglas: cada opción enseña su consecuencia y se aplica en vivo al pasar por ella;
// todo se deshace; lo escrito en cualquier parte entra en la frase.

import { PRODUCTOS } from '../datos/productos';
import { iconoProducto } from './iconos';
import {
	ESCALAS, MOVIMIENTOS, PAISES, TEXTO_ORDEN, ZONAS, conEscala, cuantos, interpretar,
	textoAgregado, textoCuando, textoEscala, textoFrente, textoQuien,
	type Consulta, type Contexto, type Filtro, type Frente, type Orden, type Propuesta,
} from '../datos/consulta';
import type { Cartera } from '../datos/modelo';
import { escalaDe, periodoAnioAnterior, periodosDe, type Escala } from '../datos/periodos';
import type { Almacen, Estado } from '../estado';
import { h, vaciar } from './dom';
import { glifoComparar, glifoCorchete, glifoMonton, glifoMuescas, glifoOrden } from './piezas';

type Hueco = 'quien' | 'cuando' | 'escala' | 'agregado' | 'frente' | 'orden' | 'escritura';

interface Opcion {
	/** Acción en lugar de una consulta (volver, abrir un grupo). */
	accion?: () => void;
	seccion?: string;
	texto: string;
	detalle?: string;
	q: Consulta;
	activa?: boolean;
	glifo?: Element;
	desactivada?: boolean;
}

export interface Frase {
	raiz: HTMLElement;
	pintar(e: Estado, ctx: Contexto): void;
	/** Devuelve true si la tecla se ha usado en la frase (abrir, navegar o escribir). */
	tecla(ev: KeyboardEvent): boolean;
	abierta(): boolean;
	cerrar(): void;
	abrir(hueco: Hueco): void;
}

const mayuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const UNIDAD: Record<Escala, string> = { mes: 'mes', trimestre: 'trimestre', cuatrimestre: 'cuatrimestre', semestre: 'semestre', anio: 'año' };

export interface AccionesFrase { volver: () => void; abrirGrupo: (id: string) => void; orden: () => string[] }

export function crearFrase(c: Cartera, S: Almacen, ctxDe: (q: Consulta) => Contexto, alCambiar: () => void, esMovil: () => boolean, acc: AccionesFrase): Frase {
	const raiz = h('div', { class: 'frase', role: 'group', 'aria-label': 'Qué estás mirando' });
	const linea = h('p', { class: 'frase-linea' });
	const ejemplos = h('div', { class: 'ejemplos' });
	const panel = h('div', { class: 'panel', role: 'listbox', 'aria-label': 'Opciones' });
	const velo = h('div', { class: 'panel-velo', onclick: () => cerrar() });
	raiz.append(linea, ejemplos);
	document.body.append(velo, panel);

	let abierto: Hueco | null = null;
	let fichaAbierta: HTMLElement | null = null;
	let opciones: Opcion[] = [];
	let marcada = -1;
	let escrito = '';
	let ultimo: { e: Estado; ctx: Contexto } | null = null;
	const fichas = new Map<Hueco, HTMLButtonElement>();

	// ─── Pintar la frase ────────────────────────────────────
	function ficha(hueco: Hueco, texto: string, glifo: Element | null, etiqueta: string, extra = '') {
		const b = h('button', { class: `ficha ficha-${hueco} ${extra}`, type: 'button', 'aria-haspopup': 'listbox', 'aria-expanded': String(abierto === hueco), 'aria-label': `${etiqueta}: ${texto}` });
		if (glifo) b.append(glifo);
		b.append(h('span', { class: 'ficha-texto' }, texto));
		b.addEventListener('click', (ev) => { ev.stopPropagation(); abierto === hueco ? cerrar() : abrir(hueco); });
		b.addEventListener('keydown', (ev) => { if (ev.key === 'ArrowDown') { ev.preventDefault(); ev.stopPropagation(); abrir(hueco); } });
		fichas.set(hueco, b);
		return b;
	}

	function pintar(e: Estado, ctx: Contexto) {
		ultimo = { e, ctx };
		const q = ctx.q;
		vaciar(linea);
		fichas.clear();
		linea.classList.toggle('previa', e.previa);
		const total = c.groups.length - ctx.sinDatos.size;
		const enExp = e.vista === 'organizacion' && !!e.sel;
		const quien = enExp ? `El Grupo ${Number(e.sel!.split('_')[1])}` : mayuscula(textoQuien(ctx));
		const fQuien = ficha('quien', quien, glifoMonton(enExp ? 0.004 : total ? ctx.visibles.size / total : 0), 'Quién');
		if (q.filtros.length && !enExp) {
			const quitar = h('span', { class: 'ficha-quitar', role: 'button', tabindex: 0, 'aria-label': 'Quitar el último filtro', title: 'Quitar el último filtro' }, '×');
			const quitarUno = (ev: Event) => { ev.stopPropagation(); S.consulta({ ...S.confirmado.q, filtros: S.confirmado.q.filtros.slice(0, -1) }); };
			quitar.addEventListener('click', quitarUno);
			quitar.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') quitarUno(ev); });
			fQuien.append(quitar);
		}
		const meses = ctx.pHasta.meses[ctx.pHasta.meses.length - 1] - ctx.pDesde.meses[0] + 1;
		const enCurso = ctx.pHasta.estado !== 'completo';
		const fCuando = ficha('cuando', textoCuando(ctx), glifoCorchete(meses), 'Cuándo', enCurso ? 'en-curso' : '');
		if (enCurso) fCuando.append(h('span', { class: 'ficha-nota' }, ctx.pHasta.estado));
		linea.append(fQuien, ', ', fCuando, ', ', ficha('escala', textoEscala(q), glifoMuescas(escalaDe(q.escala).muescas), 'Escala'));
		if (q.escala !== 'mes') linea.append(' ', ficha('agregado', textoAgregado(q), null, 'Resumen de cada periodo', 'ficha-ligera'));
		const frente = textoFrente(ctx);
		if (frente) linea.append(', ', ficha('frente', frente, glifoComparar(), 'Frente a'));
		if (e.vista === 'tapiz') linea.append(', ', ficha('orden', TEXTO_ORDEN[q.orden], glifoOrden(), 'Orden'));
		linea.append('.');
		if (!frente) linea.append(' ', ficha('frente', 'comparar con…', null, 'Comparar', 'fantasma'));
		if (abierto === 'escritura') linea.append(' ', fichaEscritura());
		pintarEjemplos(e);
		if (abierto && abierto !== 'escritura') {
			fichaAbierta = fichas.get(abierto) ?? null;
			fichaAbierta?.setAttribute('aria-expanded', 'true');
			fichaAbierta?.classList.add('abierta');
			colocarPanel();
		}
		alCambiar();
	}

	function fichaEscritura() {
		const b = h('span', { class: 'ficha ficha-escritura abierta', role: 'textbox', 'aria-label': 'Lo que estás escribiendo' }, h('span', { class: 'ficha-texto' }, escrito), h('span', { class: 'cursor' }));
		fichaAbierta = b;
		return b;
	}

	function pintarEjemplos(e: Estado) {
		vaciar(ejemplos);
		if (localStorage.getItem('xray.ejemplos') === 'vistos' || e.vista !== 'plano' && e.vista !== 'tapiz') { ejemplos.hidden = true; return; }
		ejemplos.hidden = false;
		const base = S.confirmado.q;
		const ej: [string, Consulta][] = [
			['los que se tuercen', { ...base, filtros: [{ tipo: 'zona', v: 'tuerce' }] }],
			['por trimestres', conEscala(c, base, 'trimestre')],
			['frente al año pasado', { ...base, frente: 'anio' }],
		];
		ejemplos.append(h('span', { class: 'ejemplos-tit' }, 'Prueba '));
		ej.forEach(([t, q], i) => {
			const b = h('button', { class: 'ejemplo', type: 'button' }, `«${t}»`);
			b.addEventListener('mouseenter', () => S.previsualizar(q));
			b.addEventListener('mouseleave', () => S.previsualizar(null));
			b.addEventListener('click', () => { localStorage.setItem('xray.ejemplos', 'vistos'); S.consulta(q); });
			ejemplos.append(b, i < ej.length - 1 ? ', ' : '');
		});
		ejemplos.append(h('span', { class: 'ejemplos-tit' }, ' o escribe lo que buscas.'));
	}

	// ─── Opciones de cada hueco ─────────────────────────────
	function opcionesDe(hueco: Hueco): Opcion[] {
		const q = S.confirmado.q;
		const ctx = ctxDe(q);
		const n = (filtros: Filtro[]) => String(cuantos(ctx, filtros));
		const igual = (a: Filtro[], b: Filtro[]) => JSON.stringify(a) === JSON.stringify(b);
		const o: Opcion[] = [];
		switch (hueco) {
			case 'quien': {
				const con = (f: Filtro[]) => ({ ...q, filtros: f });
				if (escrito) {
					for (const p of interpretar(c, q, escrito)) o.push(propuestaAOpcion(p, q, ctx));
					break;
				}
				if (S.confirmado.vista === 'organizacion') {
					o.push({ seccion: 'Este grupo', texto: 'Volver a la cartera', detalle: S.confirmado.cartera === 'plano' ? 'al plano' : 'al tapiz', q, accion: acc.volver });
					const orden = acc.orden();
					const i = orden.indexOf(S.confirmado.sel ?? '');
					for (const id of [...orden.slice(i + 1, i + 7), ...orden.slice(Math.max(0, i - 3), Math.max(0, i))]) {
						const gi = c.groups.findIndex((g) => g.id === id);
						o.push({ seccion: 'Otros grupos, en el mismo orden', texto: `Grupo ${Number(id.split('_')[1])}`, detalle: String(Math.round((ctx.valor(gi, ctx.pHasta) ?? 0) / 10)), q, accion: () => acc.abrirGrupo(id) });
					}
					break;
				}
				if (q.filtros.length) o.push({ seccion: 'Afinar', texto: 'Quitar el último filtro', detalle: n(q.filtros.slice(0, -1)), q: con(q.filtros.slice(0, -1)) });
				o.push({ seccion: 'Todos', texto: 'Toda la cartera', detalle: n([]), q: con([]), activa: !q.filtros.length });
				for (const z of ZONAS) o.push({ seccion: 'Por zona del plano', texto: mayuscula(z.plural.replace(/^que /, '')), detalle: n([{ tipo: 'zona', v: z.id }]), q: con([{ tipo: 'zona', v: z.id }]), activa: igual(q.filtros, [{ tipo: 'zona', v: z.id }]) });
				for (const m of MOVIMIENTOS) o.push({ seccion: 'Por lo que les ha pasado', texto: m.nombre, detalle: n([{ tipo: 'mov', v: m.id }]), q: con([{ tipo: 'mov', v: m.id }]), activa: igual(q.filtros, [{ tipo: 'mov', v: m.id }]) });
				for (const p of PRODUCTOS) o.push({ seccion: 'Por producto que les encaja', texto: p.nombre, glifo: iconoProducto(p.id, { tam: 22, titulo: false }), detalle: n([{ tipo: 'producto', v: p.id }]), q: con([{ tipo: 'producto', v: p.id }]), activa: igual(q.filtros, [{ tipo: 'producto', v: p.id }]) });
				const sectores = [...new Set(c.groups.map((g) => g.industry).filter(Boolean))] as string[];
				sectores.sort((a, b) => cuantos(ctx, [{ tipo: 'sector', v: b }]) - cuantos(ctx, [{ tipo: 'sector', v: a }]));
				for (const s of sectores) o.push({ seccion: 'Por sector', texto: s, detalle: n([{ tipo: 'sector', v: s }]), q: con([{ tipo: 'sector', v: s }]), activa: igual(q.filtros, [{ tipo: 'sector', v: s }]) });
				for (const [cod, nombre] of Object.entries(PAISES)) {
					const k = cuantos(ctx, [{ tipo: 'pais', v: cod }]);
					if (k) o.push({ seccion: 'Por país', texto: nombre, detalle: String(k), q: con([{ tipo: 'pais', v: cod }]), activa: igual(q.filtros, [{ tipo: 'pais', v: cod }]) });
				}
				for (const [t, nombre] of [['Grande', 'Grandes'], ['Mediana', 'Medianos'], ['Pequeña', 'Pequeños'], ['Micro', 'Micro']]) if (cuantos(ctx, [{ tipo: 'tamano', v: t }]) || t !== 'Micro') o.push({ seccion: 'Por tamaño', texto: nombre, detalle: n([{ tipo: 'tamano', v: t }]), q: con([{ tipo: 'tamano', v: t }]), activa: igual(q.filtros, [{ tipo: 'tamano', v: t }]) });
				break;
			}
			case 'cuando': {
				const ps = periodosDe(c.months, q.escala);
				const ult = ps.length - 1;
				const ultimoCerrado = [...ps].reverse().find((p) => p.completo)?.i ?? ult;
				const unidad = UNIDAD[q.escala];
				const nAnio = Math.max(1, Math.round(12 / escalaDe(q.escala).meses));
				const es = (d: number, hh: number) => q.desde === d && q.hasta === hh;
				o.push({ seccion: 'Rápido', texto: `El último ${unidad}`, detalle: ps[ult].corta + (ps[ult].estado !== 'completo' ? ` (${ps[ult].estado})` : ''), q: { ...q, desde: ult, hasta: ult }, activa: es(ult, ult) });
				if (ultimoCerrado !== ult) o.push({ seccion: 'Rápido', texto: `El último ${unidad} cerrado`, detalle: ps[ultimoCerrado].corta, q: { ...q, desde: ultimoCerrado, hasta: ultimoCerrado }, activa: es(ultimoCerrado, ultimoCerrado) });
				if (q.escala !== 'anio') { const d = Math.max(0, ult - nAnio + 1); o.push({ seccion: 'Rápido', texto: 'El último año', detalle: `de ${ps[d].corta} a ${ps[ult].corta}`, q: { ...q, desde: d, hasta: ult }, activa: es(d, ult) }); }
				o.push({ seccion: 'Rápido', texto: 'Toda la historia', detalle: `de ${ps[0].corta} a ${ps[ult].corta}`, q: { ...q, desde: 0, hasta: ult }, activa: es(0, ult) });
				const visita = leerVisita();
				if (visita !== null) {
					const pv = ps.findIndex((p) => p.meses.includes(visita));
					if (pv >= 0 && pv < ult) o.push({ seccion: 'Rápido', texto: 'Desde tu última visita', detalle: ps[pv].corta, q: { ...q, desde: pv, hasta: ult }, activa: es(pv, ult) });
				}
				for (const p of [...ps].reverse()) o.push({ seccion: `${p.anio}`, texto: mayuscula(p.larga), detalle: p.estado !== 'completo' ? p.estado : undefined, q: { ...q, desde: p.i, hasta: p.i }, activa: es(p.i, p.i) });
				break;
			}
			case 'escala': {
				for (const esc of ESCALAS) o.push({ seccion: 'Ver', texto: mayuscula(esc.frase), glifo: glifoMuescas(esc.muescas), q: conEscala(c, q, esc.id as Escala), activa: q.escala === esc.id });
				o.push({ seccion: 'Cómo se resume cada periodo', texto: 'Al cierre', detalle: 'el score del último mes', q: { ...q, agregado: 'cierre' }, activa: q.agregado === 'cierre', desactivada: q.escala === 'mes' });
				o.push({ seccion: 'Cómo se resume cada periodo', texto: 'De media', detalle: 'la media de sus meses', q: { ...q, agregado: 'media' }, activa: q.agregado === 'media', desactivada: q.escala === 'mes' });
				break;
			}
			case 'agregado': {
				o.push({ texto: 'Al cierre', detalle: 'el score del último mes del periodo', q: { ...q, agregado: 'cierre' }, activa: q.agregado === 'cierre' });
				o.push({ texto: 'De media', detalle: 'la media de los meses del periodo', q: { ...q, agregado: 'media' }, activa: q.agregado === 'media' });
				break;
			}
			case 'frente': {
				const ps = ctx.periodos;
				const ant = ps[ctx.pHasta.i - 1];
				const anio = periodoAnioAnterior(ps, ctx.pHasta);
				const f = (v: Frente) => ({ ...q, frente: v });
				o.push({ texto: 'Sin comparar', detalle: 'las flechas salen de «desde»', q: f('nada'), activa: q.frente === 'nada' });
				o.push({ texto: 'Frente al periodo anterior', detalle: ant ? ant.corta : 'no hay', q: f('anterior'), activa: q.frente === 'anterior', desactivada: !ant });
				o.push({ texto: 'Frente al mismo periodo del año pasado', detalle: anio ? anio.corta : 'fuera de la ventana', q: f('anio'), activa: q.frente === 'anio', desactivada: !anio });
				o.push({ texto: 'Frente a su primer mes en la plataforma', detalle: 'cada grupo, el suyo', q: f('alta'), activa: q.frente === 'alta' });
				break;
			}
			case 'orden': {
				const f = (v: Orden) => ({ ...q, orden: v });
				for (const [v, t] of [['score', 'Por score, los más altos arriba'], ['ritmo', 'Por ritmo, los que más caen arriba'], ['alerta', 'Por su primer aviso'], ['tamano', 'Por tamaño']] as [Orden, string][]) o.push({ texto: t, q: f(v), activa: q.orden === v });
				break;
			}
			case 'escritura': {
				for (const p of interpretar(c, q, escrito)) o.push(propuestaAOpcion(p, q, ctx));
				break;
			}
		}
		return o;
	}

	function propuestaAOpcion(p: Propuesta, q: Consulta, ctx: Contexto): Opcion {
		const nq = p.aplicar(q);
		const unGrupo = nq.filtros.length === 1 && nq.filtros[0].tipo === 'grupo' ? (nq.filtros[0].v as string) : null;
		// Un grupo concreto se abre directamente en su expediente.
		if (unGrupo) return { seccion: p.tipo, texto: `Abrir el ${p.texto.replace(/^el /, '')}`, q, accion: () => acc.abrirGrupo(unGrupo) };
		return { seccion: p.tipo, texto: p.texto, detalle: p.tipo === 'Quién' ? String(cuantos(ctx, nq.filtros)) : undefined, q: nq };
	}

	// ─── Panel ──────────────────────────────────────────────
	function abrir(hueco: Hueco) {
		if (!ultimo) return;
		abierto = hueco;
		if (hueco !== 'escritura') escrito = '';
		opciones = opcionesDe(hueco);
		marcada = hueco === 'escritura' ? (opciones.length ? 0 : -1) : opciones.findIndex((x) => x.activa);
		pintar(S.e, ultimo.ctx);
		pintarPanel();
		panel.classList.add('ver');
		velo.classList.add('ver');
		if (hueco === 'escritura' && opciones[0]) S.previsualizar(opciones[0].q);
		if (hueco === 'quien' && entrada && !esMovil()) requestAnimationFrame(() => entrada?.focus({ preventScroll: true }));
		else if (hueco !== 'escritura') requestAnimationFrame(() => (panel.querySelector('.opcion.marcada, .opcion') as HTMLElement | null)?.focus({ preventScroll: true }));
	}

	function cerrar() {
		if (!abierto) return;
		const hueco = abierto;
		abierto = null;
		escrito = '';
		panel.classList.remove('ver');
		velo.classList.remove('ver');
		fichaAbierta?.classList.remove('abierta');
		fichaAbierta = null;
		S.previsualizar(null);
		if (ultimo) pintar(S.e, ctxDe(S.e.q));
		if (hueco !== 'escritura') fichas.get(hueco)?.focus({ preventScroll: true });
	}

	function elegir(i: number) {
		const o = opciones[i];
		if (!o || o.desactivada) return;
		localStorage.setItem('xray.ejemplos', 'vistos');
		abierto = null; escrito = '';
		panel.classList.remove('ver'); velo.classList.remove('ver');
		fichaAbierta = null;
		S.previsualizar(null);
		if (o.accion) o.accion(); else S.consulta(o.q);
	}

	function pintarPanel() {
		vaciar(panel);
		panel.append(h('div', { class: 'panel-asa', 'aria-hidden': 'true' }));
		if (abierto === 'escritura' && !opciones.length) {
			panel.append(h('div', { class: 'panel-vacio' },
				h('p', {}, escrito ? `No reconozco «${escrito}».` : 'Escribe lo que buscas.'),
				h('p', { class: 'panel-pista' }, 'Prueba con «se tuercen», «T2», «factoring», «42», «trimestres» o «año pasado».')));
			return;
		}
		if (abierto === 'escritura') panel.append(h('div', { class: 'panel-cab' }, 'Así quedaría la frase. Pulsa ↵ para aplicarlo.'));
		if (abierto === 'quien') panel.append(buscador());
		const lista = h('div', { class: 'panel-lista' });
		panel.append(lista);
		pintarLista(lista);
		colocarPanel();
		requestAnimationFrame(() => (lista.querySelector('.marcada') as HTMLElement | null)?.scrollIntoView({ block: 'nearest' }));
	}

	let entrada: HTMLInputElement | null = null;
	function buscador() {
		const inp = h('input', { class: 'panel-buscar', type: 'search', placeholder: 'Escribe: un grupo, un sector, «se tuercen», «T2»…', 'aria-label': 'Buscar', autocomplete: 'off', enterkeyhint: 'go' });
		inp.value = escrito;
		inp.addEventListener('input', () => {
			escrito = inp.value.trim();
			opciones = opcionesDe('quien');
			marcada = escrito ? (opciones.length ? 0 : -1) : opciones.findIndex((x) => x.activa);
			const lista = panel.querySelector('.panel-lista') as HTMLElement;
			pintarLista(lista);
			const o = opciones[marcada];
			S.previsualizar(o && !o.accion ? o.q : null);
		});
		inp.addEventListener('keydown', (ev) => {
			if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
				ev.preventDefault();
				if (!opciones.length) return;
				marcada = (marcada + (ev.key === 'ArrowDown' ? 1 : -1) + opciones.length) % opciones.length;
				marcar();
				const o = opciones[marcada];
				if (!o.accion) S.previsualizar(o.q);
			} else if (ev.key === 'Enter') { ev.preventDefault(); elegir(marcada); }
			else if (ev.key === 'Escape') { ev.preventDefault(); cerrar(); }
			ev.stopPropagation();
		});
		entrada = inp;
		return h('div', { class: 'panel-buscar-caja' }, inp);
	}

	function pintarLista(lista: HTMLElement) {
		vaciar(lista);
		if (!opciones.length) {
			lista.append(h('div', { class: 'panel-vacio' }, h('p', {}, `No reconozco «${escrito}».`), h('p', { class: 'panel-pista' }, 'Prueba con «se tuercen», «T2», «factoring», «42», «trimestres» o «año pasado».')));
			return;
		}
		let seccion = '';
		opciones.forEach((o, i) => {
			if (o.seccion && o.seccion !== seccion) { seccion = o.seccion; lista.append(h('div', { class: 'panel-seccion' }, seccion)); }
			const b = h('button', { class: `opcion ${o.activa ? 'activa' : ''} ${i === marcada ? 'marcada' : ''}`, type: 'button', role: 'option', 'aria-selected': String(!!o.activa), disabled: o.desactivada || undefined },
				o.glifo ?? null, h('span', { class: 'opcion-texto' }, o.texto), o.detalle ? h('span', { class: 'opcion-detalle' }, o.detalle) : null);
			b.addEventListener('mouseenter', () => { marcada = i; marcar(); if (!o.desactivada && !o.accion) S.previsualizar(o.q); });
			b.addEventListener('focus', () => { marcada = i; marcar(); if (!o.desactivada && !o.accion) S.previsualizar(o.q); });
			b.addEventListener('click', (ev) => { ev.stopPropagation(); elegir(i); });
			lista.append(b);
		});
		lista.onmouseleave = () => { if (abierto !== 'escritura' && !escrito) S.previsualizar(null); };
	}

	function marcar() {
		const bs = panel.querySelectorAll<HTMLElement>('.opcion');
		bs.forEach((b, i) => b.classList.toggle('marcada', i === marcada));
		bs[marcada]?.scrollIntoView({ block: 'nearest' });
	}

	function colocarPanel() {
		if (!abierto) return;
		const movil = esMovil();
		panel.classList.toggle('hoja', movil);
		if (movil) { Object.assign(panel.style, { left: '', top: '', width: '', maxHeight: '' }); return; }
		const ref = (fichaAbierta ?? linea).getBoundingClientRect();
		const ancho = Math.min(400, innerWidth - 32);
		const x = Math.max(16, Math.min(ref.left, innerWidth - ancho - 16));
		Object.assign(panel.style, { left: `${x}px`, top: `${ref.bottom + 8}px`, width: `${ancho}px`, maxHeight: `${Math.max(220, innerHeight - ref.bottom - 32)}px` });
	}

	// ─── Teclado y escritura ───────────────────────────────
	function tecla(ev: KeyboardEvent): boolean {
		if (abierto && abierto !== 'escritura') {
			if (ev.key === 'Escape') { ev.preventDefault(); cerrar(); return true; }
			if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
				ev.preventDefault();
				const d = ev.key === 'ArrowDown' ? 1 : -1;
				let i = marcada;
				for (let n = 0; n < opciones.length; n++) { i = (i + d + opciones.length) % opciones.length; if (!opciones[i].desactivada) break; }
				marcada = i;
				(panel.querySelectorAll<HTMLElement>('.opcion')[i])?.focus({ preventScroll: true });
				marcar();
				S.previsualizar(opciones[i].q);
				return true;
			}
			if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); elegir(marcada); return true; }
			if (ev.key === 'Tab') { cerrar(); return false; }
			return true;
		}
		const escribible = ev.key.length === 1 && !ev.metaKey && !ev.ctrlKey && !ev.altKey;
		if (abierto === 'escritura') {
			if (ev.key === 'Escape') { ev.preventDefault(); cerrar(); return true; }
			if (ev.key === 'Enter') { ev.preventDefault(); if (marcada >= 0) elegir(marcada); return true; }
			if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
				ev.preventDefault();
				if (!opciones.length) return true;
				marcada = (marcada + (ev.key === 'ArrowDown' ? 1 : -1) + opciones.length) % opciones.length;
				marcar(); S.previsualizar(opciones[marcada].q); return true;
			}
			if (ev.key === 'Backspace') { ev.preventDefault(); escrito = escrito.slice(0, -1); if (!escrito) { cerrar(); return true; } refrescarEscritura(); return true; }
			if (escribible) { escrito += ev.key; refrescarEscritura(); ev.preventDefault(); return true; }
			return false;
		}
		// Empezar a escribir: solo con letras o números (el espacio y las teclas de mando son atajos).
		if (escribible && /[\p{L}\p{N}]/u.test(ev.key)) {
			escrito = ev.key;
			abrir('escritura');
			refrescarEscritura();
			ev.preventDefault();
			return true;
		}
		return false;
	}

	function refrescarEscritura() {
		opciones = opcionesDe('escritura');
		marcada = opciones.length ? 0 : -1;
		pintar(S.e, ultimo!.ctx);
		pintarPanel();
		S.previsualizar(opciones[0]?.q ?? null);
	}

	addEventListener('resize', () => colocarPanel());

	return { raiz, pintar, tecla, abierta: () => abierto !== null, cerrar, abrir };
}

// Última visita: el mes que se miraba al salir la vez anterior.
export function leerVisita(): number | null {
	const v = localStorage.getItem('xray.visita');
	return v === null || Number.isNaN(Number(v)) ? null : Number(v);
}
export function guardarVisita(mes: number) { localStorage.setItem('xray.visita', String(mes)); }
