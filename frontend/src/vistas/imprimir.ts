// Imprimir y guardar en PDF. El informe es el HTML de las cuatro secciones, montado en una capa
// aparte con el ancho de una hoja A4. La arena no se imprime (es WebGL y sigue al desplazamiento),
// así que cada placa se vuelve a componer con la misma escena y se pinta grano a grano en una
// imagen: el papel lleva la misma arena que la pantalla, quieta.

import { PALETA } from '../arena/arena';
import { escenaPlacas } from '../arena/placas';
import { h } from './dom';
import { hacerPlaca } from './registro';

/** Ancho útil de un A4 con márgenes de 14 mm, en píxeles CSS (182 mm). */
const ANCHO_HOJA = 688;
/** Resolución de la arena impresa (píxeles por píxel CSS). */
const RESOLUCION = 3;

let capa: HTMLElement | null = null;

/** Monta el informe en su capa (o el aviso de que no hay ficha abierta) y cuece la arena. */
export function prepararInforme(informe: HTMLElement | null) {
	quitarInforme();
	capa = h('div', { class: 'capa-informe' });
	capa.style.width = `${ANCHO_HOJA}px`;
	capa.append(informe ?? h('div', { class: 'informe-vacio' }, h('p', {}, 'Rumbo imprime el informe de una organización o de una empresa. Abre una y vuelve a imprimir.')));
	document.body.append(capa);
	document.documentElement.classList.add('con-informe');
	cocerArena(capa);
}

export function quitarInforme() {
	capa?.remove();
	capa = null;
	document.documentElement.classList.remove('con-informe');
}

export const hayInforme = () => !!capa;

function cocerArena(raiz: HTMLElement) {
	raiz.querySelectorAll('[data-placa]').forEach((el) => {
		const r = el.getBoundingClientRect();
		if (!r.width || !r.height) return;
		const p = hacerPlaca(el, { x: 0, y: 0, w: r.width, h: r.height });
		if (!p) return;
		const esc = escenaPlacas([p], 60000, r.width, r.height, false);
		const c = document.createElement('canvas');
		c.width = Math.round(r.width * RESOLUCION); c.height = Math.round(r.height * RESOLUCION);
		const x = c.getContext('2d')!;
		x.scale(RESOLUCION, RESOLUCION);
		for (let i = 0; i < esc.x.length; i++) {
			const a = esc.alfa[i];
			if (a <= 0.01) continue;
			const [cr, cg, cb] = PALETA[esc.tono[i]];
			x.fillStyle = `rgb(${cr},${cg},${cb})`;
			x.globalAlpha = Math.min(1, a);
			x.beginPath();
			// El grano del shader: un disco de diámetro «talla» con el borde suave (≈ 0,8 de la talla).
			x.arc(esc.x[i], esc.y[i], esc.talla[i] * 0.42, 0, Math.PI * 2);
			x.fill();
		}
		const img = h('img', { class: 'arena-impresa', alt: '', src: c.toDataURL('image/png') });
		el.append(img);
	});
}
