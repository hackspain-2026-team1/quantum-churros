// Los primitivos de Rumbo que sustituyen a píldoras, tarjetas y paneles (propuesta 06, §8):
//   · línea de estado: una sola línea tipográfica, sin cajas (banda con su regla grabada,
//     movimiento con flecha de granos y confianza en tres granos);
//   · asiento: una entrada de catálogo sin caja, separada por un filete;
//   · sello: el «contratado» grabado, con la entidad alrededor;
//   · hilo: de dónde sale un número, nudo a nudo hasta los ficheros;
//   · sección: título en el margen y filete encima;
//   · llamada: la nota al margen de una compuerta o un tope (¹ ²).

import type { Manifiesto, MesM } from '../datos/contrato';
import { f } from '../datos/formato';
import { movimiento, nombreBanda } from '../datos/redaccion';
import { h } from './dom';

const NS = 'http://www.w3.org/2000/svg';
function svg(w: number, alto: number, clase = ''): SVGSVGElement {
	const s = document.createElementNS(NS, 'svg');
	s.setAttribute('width', String(w)); s.setAttribute('height', String(alto));
	s.setAttribute('viewBox', `0 0 ${w} ${alto}`); s.setAttribute('aria-hidden', 'true');
	if (clase) s.setAttribute('class', clase);
	return s;
}
function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>) {
	const e = document.createElementNS(NS, tag);
	for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
	return e;
}

/** Regla grabada de 0 a 100 con las marcas de banda del manifiesto y un grano donde está la entidad. */
export function reglaBanda(man: Manifiesto, decimas: number, banda: string): SVGSVGElement {
	const w = 96, s = svg(w + 8, 14, 'regla-banda');
	const x = (v: number) => 4 + (v / 1000) * w;
	s.append(el('line', { x1: 4, y1: 9, x2: 4 + w, y2: 9, class: 'rb-linea' }));
	for (const b of man.bands) if (b.min > 0) s.append(el('line', { x1: x(b.min), y1: 5.5, x2: x(b.min), y2: 12, class: 'rb-marca' }));
	s.append(el('line', { x1: 4, y1: 6.5, x2: 4, y2: 11.5, class: 'rb-marca' }), el('line', { x1: 4 + w, y1: 6.5, x2: 4 + w, y2: 11.5, class: 'rb-marca' }));
	s.append(el('circle', { cx: x(Math.max(0, Math.min(1000, decimas))), cy: 9, r: 3, class: `rb-grano banda-${banda}` }));
	return s;
}

/** Flecha de granos: la misma forma que el cometa del plano. */
export function flechaGranos(dir: string, naturaleza: string | null): SVGSVGElement {
	const s = svg(18, 14, `flecha-granos ${naturaleza ?? ''}`);
	if (dir === 'stable' || dir === 'perimeter_shift') { for (let i = 0; i < 4; i++) s.append(el('circle', { cx: 2.5 + i * 4.2, cy: 7, r: 1.1 })); return s; }
	const sube = dir === 'improving';
	for (let i = 0; i < 5; i++) {
		const t = i / 4;
		s.append(el('circle', { cx: 2 + t * 13, cy: sube ? 12 - t * 10 : 2 + t * 10, r: 0.8 + t * 0.9, class: naturaleza === 'shock_pending' && i === 4 ? 'hueco' : '' }));
	}
	return s;
}

export function granos3(label: string): SVGSVGElement {
	const s = svg(20, 8, 'granos3');
	const n = label === 'high' ? 3 : label === 'medium' ? 2 : 1;
	for (let i = 0; i < 3; i++) s.append(el('circle', { cx: 3 + i * 7, cy: 4, r: 2.4, class: i < n ? 'lleno' : 'vacio' }));
	return s;
}

const CONFIANZA: Record<string, string> = { high: 'alta', medium: 'media', low: 'baja' };

/** La línea de estado. `nota` es la frase del motor cuando los dos horizontes se contradicen. */
export function lineaEstado(man: Manifiesto, m: MesM, nota?: string | null): HTMLElement {
	const partes: (Node | string)[] = [];
	partes.push(h('span', { class: 'le-banda', title: `Bandas del motor: ${man.bands.map((b) => `${b.label} desde ${f.score(b.min)}`).join(', ')}` }, h('span', { class: 'versalita' }, nombreBanda(man, m.band)), ' ', h('b', {}, f.score(m.shown)), reglaBanda(man, m.shown, m.band)));
	partes.push(h('span', { class: 'le-sep' }, '·'));
	partes.push(h('span', { class: `le-mov ${m.verdict.direction}`, title: m.verdict.available ? `Δ3 ${m.verdict.delta3 === null ? '—' : f.delta(m.verdict.delta3)} frente a ${m.verdict.compared_to ? f.mes(m.verdict.compared_to) : '—'}` : (m.verdict.reason ?? 'Sin veredicto') }, flechaGranos(m.verdict.direction, m.verdict.nature), h('span', { class: 'versalita' }, movimiento(m))));
	partes.push(h('span', { class: 'le-sep' }, '·'));
	partes.push(h('span', { class: 'le-conf', title: `Confianza ${f.porcentaje(m.conf.value, 0)}: historia ${f.porcentaje(m.conf.history, 0)} × cobertura ${f.porcentaje(m.conf.coverage, 0)} × calidad ${f.porcentaje(m.conf.quality, 0)}. Nunca cambia el score.` }, h('span', { class: 'versalita' }, 'confianza'), ' ', granos3(m.conf.label), h('span', { class: 'le-conf-t' }, ` ${CONFIANZA[m.conf.label] ?? m.conf.label}`)));
	const linea = h('div', { class: 'linea-estado' }, ...partes);
	if (nota) linea.append(h('div', { class: 'le-nota' }, nota));
	return linea;
}

/** Sello de «contratado» grabado, con la entidad escrita alrededor. */
export function sello(entidad: string | null, fuente: 'declarado' | 'movimientos'): SVGSVGElement {
	const s = svg(58, 58, `sello-grabado ${fuente}`);
	const id = `s${Math.random().toString(36).slice(2, 8)}`;
	const defs = el('defs', {});
	defs.append(el('path', { id, d: 'M29 29 m-21 0 a21 21 0 1 1 42 0 a21 21 0 1 1 -42 0' }));
	s.append(defs);
	s.append(el('circle', { cx: 29, cy: 29, r: 27, class: 'sello-aro' }), el('circle', { cx: 29, cy: 29, r: 15, class: 'sello-aro fino' }));
	const t = el('text', { class: 'sg-texto' });
	const tp = el('textPath', { href: `#${id}`, startOffset: '50%', 'text-anchor': 'middle' });
	const nombre = (entidad ?? (fuente === 'movimientos' ? 'visto en movimientos' : 'declarado')).toUpperCase().slice(0, 26);
	tp.textContent = `${nombre} · ${fuente === 'movimientos' ? 'DEDUCIDO' : 'CONTRATADO'}`;
	t.append(tp); s.append(t);
	s.append(el('path', { d: 'M22.5 29.5l4.4 4.4 8.6-9.2', class: 'sello-marca' }));
	s.setAttribute('aria-label', `${fuente === 'movimientos' ? 'Deducido de sus movimientos' : 'Contratado'}${entidad ? ` con ${entidad}` : ''}`);
	s.removeAttribute('aria-hidden');
	return s;
}

export interface OpcionesAsiento {
	icono?: Element;
	titulo: string;
	estado?: string;
	hechos?: (string | Node)[];
	texto?: string;
	enlace?: { texto: string; accion: () => void };
	sello?: Element;
	clase?: string;
	color?: string;
}

/** Un asiento de catálogo: sin caja, con el grabado en el margen y un filete debajo. */
export function asiento(o: OpcionesAsiento): HTMLElement {
	const cuerpo = h('div', { class: 'as-cuerpo' },
		h('div', { class: 'as-cab' }, h('span', { class: 'as-titulo' }, o.titulo), o.estado ? h('span', { class: 'as-estado versalita' }, o.estado) : null),
		o.texto ? h('p', { class: 'as-texto' }, o.texto) : null,
		o.hechos?.length ? h('p', { class: 'as-hechos' }, ...o.hechos.flatMap((x, i) => (i ? [h('span', { class: 'as-punto' }, ' · '), x] : [x]))) : null);
	if (o.enlace) {
		const b = h('button', { class: 'as-enlace', type: 'button' }, o.enlace.texto);
		b.addEventListener('click', o.enlace.accion);
		cuerpo.append(b);
	}
	const a = h('div', { class: `asiento ${o.clase ?? ''}` }, h('div', { class: 'as-margen' }, o.icono ?? null), cuerpo, o.sello ? h('div', { class: 'as-sello' }, o.sello) : null);
	if (o.color) a.style.setProperty('--tinta-producto', o.color);
	return a;
}

export interface Nudo { valor: string; texto: string; detalle?: string; accion?: () => void }

/** El hilo: de un número hasta los ficheros de los que sale, nudo a nudo. */
export function hilo(nudos: Nudo[], compacto = false): HTMLElement {
	const lista = h('ol', { class: `hilo ${compacto ? 'compacto' : ''}` });
	nudos.forEach((n, i) => {
		const li = h('li', { class: `nudo ${i === 0 ? 'raiz' : ''}` }, h('span', { class: 'nudo-valor' }, n.valor), h('span', { class: 'nudo-texto' }, n.texto, n.detalle ? h('span', { class: 'nudo-detalle' }, n.detalle) : null));
		if (n.accion) { li.classList.add('tocable'); li.tabIndex = 0; li.addEventListener('click', n.accion); li.addEventListener('keydown', (e) => { if (e.key === 'Enter') n.accion!(); }); }
		lista.append(li);
	});
	return lista;
}

/** Una sección de página: título en el margen, filete encima. */
export function seccion(titulo: string, ...hijos: (Node | null | false | undefined)[]): HTMLElement {
	const s = h('section', { class: 'seccion' }, h('h2', { class: 'sec-titulo' }, titulo), h('div', { class: 'sec-cuerpo' }));
	for (const x of hijos) if (x) (s.lastElementChild as HTMLElement).append(x);
	return s;
}

/** Llamada de nota: el número en el texto y la nota en el margen. */
export function llamadas(textos: string[]): { marcas: HTMLElement[]; notas: HTMLElement | null } {
	if (!textos.length) return { marcas: [], notas: null };
	const sup = '¹²³⁴⁵⁶⁷⁸⁹';
	return {
		marcas: textos.map((_, i) => h('sup', { class: 'llamada' }, sup[i] ?? String(i + 1))),
		notas: h('ol', { class: 'notas-margen' }, ...textos.map((t, i) => h('li', {}, h('span', { class: 'llamada' }, sup[i] ?? String(i + 1)), ' ', t))),
	};
}

/** Cifra con contexto: número, qué es, comparación. */
export function cifraC(valor: string, que: string, comparacion?: string | Node | null, tono?: 'sube' | 'baja' | ''): HTMLElement {
	return h('div', { class: `cifra-c ${tono ?? ''}` }, h('div', { class: 'cc-valor' }, valor), h('div', { class: 'cc-que' }, que), comparacion ? h('div', { class: 'cc-comp' }, comparacion) : null);
}
