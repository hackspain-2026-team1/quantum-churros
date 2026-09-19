// La mirada: desde dónde se mira Rumbo. Embat ve la cartera entera; el CFO de un grupo ve su grupo
// y sus empresas. El control vive en la cabecera, junto a la marca, y se lleva en la URL (?cfo=).
// Recorta lo que se enseña; no es un control de acceso: el bundle entero sigue en el navegador.

import { f } from '../datos/formato';
import type { Cartera } from '../datos/modelo';
import type { Almacen, Estado } from '../estado';
import { h, vaciar } from './dom';

export interface Mirada {
	raiz: HTMLElement;
	pintar(e: Estado): void;
}

export function crearMirada(S: Almacen, c: Cartera): Mirada {
	const raiz = h('div', { class: 'mirada' });
	const boton = h('button', { class: 'mirada-btn', type: 'button', 'aria-haspopup': 'true', 'aria-expanded': 'false' });
	const panel = h('div', { class: 'mirada-panel', role: 'menu', hidden: '' });
	raiz.append(boton, panel);

	const buscar = h('input', { class: 'buscar-sutil', type: 'search', placeholder: 'Buscar un grupo', 'aria-label': 'Buscar el grupo del CFO' }) as HTMLInputElement;
	const lista = h('div', { class: 'mirada-lista' });
	// Los grupos con más empresas primero: son los que enseñan de qué va el modo CFO.
	const grupos = [...c.groups].sort((a, b) => b.n_companies - a.n_companies || f.grupo(a.id).localeCompare(f.grupo(b.id), 'es'));

	function pintarLista() {
		vaciar(lista);
		const q = buscar.value.trim().toLowerCase();
		const vistos = grupos.filter((g) => !q || f.grupo(g.id).toLowerCase().includes(q)).slice(0, 40);
		for (const g of vistos) {
			const actual = S.e.modo === 'cfo' && S.e.cfo === g.id;
			const b = h('button', { type: 'button', class: `mirada-op ${actual ? 'actual' : ''}`, role: 'menuitemradio', 'aria-checked': String(actual) },
				h('span', {}, f.grupo(g.id)),
				h('small', {}, f.plural(g.n_companies, 'empresa', 'empresas')));
			b.addEventListener('click', () => { cerrar(); S.mirarComo('cfo', g.id); });
			lista.append(b);
		}
		if (!vistos.length) lista.append(h('p', { class: 'nota' }, 'Ningún grupo con ese nombre.'));
	}
	buscar.addEventListener('input', pintarLista);

	const embat = h('button', { type: 'button', class: 'mirada-op embat', role: 'menuitemradio' },
		h('span', {}, 'Superadmin de Embat'), h('small', {}, 'toda la cartera'));
	embat.addEventListener('click', () => { cerrar(); S.mirarComo('superadmin', null); });
	panel.append(h('p', { class: 'mirada-t' }, 'Ver Rumbo como'), embat, h('p', { class: 'mirada-t' }, 'CFO de'), buscar, lista);

	function abrir() {
		panel.hidden = false;
		boton.setAttribute('aria-expanded', 'true');
		buscar.value = '';
		pintarLista();
		buscar.focus();
	}
	function cerrar() {
		panel.hidden = true;
		boton.setAttribute('aria-expanded', 'false');
	}
	boton.addEventListener('click', () => (panel.hidden ? abrir() : cerrar()));
	addEventListener('pointerdown', (ev) => { if (!panel.hidden && !raiz.contains(ev.target as Node)) cerrar(); });
	addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && !panel.hidden) { cerrar(); boton.focus(); } });

	return {
		raiz,
		pintar(e) {
			const cfo = e.modo === 'cfo' && e.cfo;
			vaciar(boton);
			boton.append(h('i', { class: 'mirada-punto', 'aria-hidden': 'true' }), cfo ? `CFO de ${f.grupo(e.cfo!)}` : 'Superadmin de Embat');
			boton.classList.toggle('es-cfo', !!cfo);
			boton.title = cfo ? `Estás viendo Rumbo como el CFO de ${f.grupo(e.cfo!)}. Clic para cambiar de mirada.` : 'Estás viendo toda la cartera. Clic para verla como el CFO de un grupo.';
			boton.setAttribute('aria-label', `Mirada: ${cfo ? `CFO de ${f.grupo(e.cfo!)}` : 'superadmin de Embat'}. Cambiar.`);
			if (!panel.hidden) pintarLista();
		},
	};
}
