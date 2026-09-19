// Registro de placas: las páginas dejan huecos en el HTML y dicen qué arena va en cada uno.
// El controlador de páginas mide los huecos (en coordenadas de página) y compone la escena.

import type { Placa } from '../arena/placas';

export interface Caja { x: number; y: number; w: number; h: number }
type Hacedor = (c: Caja) => Placa | null;

const hacedores = new WeakMap<Element, Hacedor>();

/** Marca un elemento como hueco de arena. */
export function placa<T extends Element>(el: T, hacer: Hacedor): T {
	el.setAttribute('data-placa', '');
	hacedores.set(el, hacer);
	return el;
}

/** Las placas de un contenedor que se desplaza, en coordenadas de pantalla con desplazamiento 0. */
export function medirPlacas(contenedor: HTMLElement): Placa[] {
	const r0 = contenedor.getBoundingClientRect();
	const salida: Placa[] = [];
	contenedor.querySelectorAll('[data-placa]').forEach((el) => {
		const f = hacedores.get(el);
		if (!f) return;
		const r = el.getBoundingClientRect();
		if (!r.width || !r.height) return;
		const p = f({ x: r.left, y: r.top - r0.top + contenedor.scrollTop + r0.top, w: r.width, h: r.height });
		if (p) salida.push(p);
	});
	return salida;
}
