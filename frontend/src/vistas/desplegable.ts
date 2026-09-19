// El desplegable de la casa, para no usar el del sistema operativo: el `<select>` nativo se pinta
// con el cromo de macOS o de Windows y no se puede peinar, así que rompe la letra y los colores de
// Rumbo. Este se dibuja con la misma lengua que el resto (papel, tinta, la marca en azul) y se
// comporta como un `combobox` de manual: teclado completo, foco visible y lectores de pantalla.
//
// Uso:
//   const orden = desplegable({ etiqueta: 'Orden', opciones: ORDENES.map((o) => ({ valor: o.id, texto: o.nombre })),
//                               valor: est.orden, alElegir: (v) => cambiar({ orden: v }) });
//   barra.append(orden.raiz);
//   orden.fijar(otroValor); // si el valor cambia desde fuera

import { h, vaciar } from './dom';
import './desplegable.css';

export interface OpcionDesplegable<V extends string = string> {
	valor: V;
	texto: string;
	/** Segunda línea, para matizar la opción. */
	detalle?: string;
	desactivada?: boolean;
}

export interface Desplegable<V extends string = string> {
	raiz: HTMLElement;
	/** Pone el valor sin avisar a `alElegir` (para reflejar un cambio de fuera). */
	fijar(valor: V): void;
	get valor(): V;
}

export interface OpcionesDesplegable<V extends string = string> {
	etiqueta: string;
	opciones: OpcionDesplegable<V>[];
	valor: V;
	alElegir(valor: V): void;
	/** Texto cuando el valor no está entre las opciones. */
	vacio?: string;
	/** Clases extra para el disparador (por ejemplo, `sutil`). */
	clase?: string;
}

let n = 0;

export function desplegable<V extends string = string>(o: OpcionesDesplegable<V>): Desplegable<V> {
	const id = `desp-${++n}`;
	let valor = o.valor;
	let abierto = false;
	let marcada = 0;

	const texto = h('span', { class: 'desp-texto' });
	const boton = h('button', {
		type: 'button', class: `desp-boton ${o.clase ?? ''}`, id: `${id}-b`,
		role: 'combobox', 'aria-haspopup': 'listbox', 'aria-expanded': 'false', 'aria-controls': `${id}-l`, 'aria-label': o.etiqueta,
	}, texto, h('span', { class: 'desp-punta', 'aria-hidden': 'true' }));
	const lista = h('div', { class: 'desp-lista', id: `${id}-l`, role: 'listbox', 'aria-label': o.etiqueta, hidden: true });
	const raiz = h('div', { class: 'desp' }, boton, lista);

	const indiceDe = (v: V) => o.opciones.findIndex((x) => x.valor === v);
	const pintarBoton = () => {
		const op = o.opciones[indiceDe(valor)];
		vaciar(texto);
		texto.append(op ? op.texto : (o.vacio ?? '—'));
		texto.classList.toggle('vacio', !op);
	};

	function pintarLista() {
		vaciar(lista);
		o.opciones.forEach((op, i) => {
			const b = h('button', {
				type: 'button', id: `${id}-o${i}`, class: `desp-opcion ${op.valor === valor ? 'activa' : ''} ${i === marcada ? 'marcada' : ''}`,
				role: 'option', 'aria-selected': String(op.valor === valor), disabled: op.desactivada || undefined, tabindex: '-1',
			}, h('span', { class: 'desp-opcion-texto' }, op.texto), op.detalle ? h('span', { class: 'desp-opcion-detalle' }, op.detalle) : null);
			b.addEventListener('click', () => elegir(i));
			b.addEventListener('pointermove', () => marcar(i));
			lista.append(b);
		});
		boton.setAttribute('aria-activedescendant', abierto ? `${id}-o${marcada}` : '');
	}

	function marcar(i: number) {
		if (i === marcada) return;
		marcada = Math.max(0, Math.min(o.opciones.length - 1, i));
		for (const [j, el] of [...lista.children].entries()) el.classList.toggle('marcada', j === marcada);
		boton.setAttribute('aria-activedescendant', `${id}-o${marcada}`);
		(lista.children[marcada] as HTMLElement | undefined)?.scrollIntoView({ block: 'nearest' });
	}

	function abrir() {
		if (abierto) return;
		abierto = true;
		marcada = Math.max(0, indiceDe(valor));
		pintarLista();
		// La lista se cuelga del documento, no del sitio donde está el botón: así se pinta por encima
		// de todo y no la recorta ninguna caja con desbordamiento oculto ni la tapa nada.
		document.body.append(lista);
		lista.hidden = false;
		boton.setAttribute('aria-expanded', 'true');
		raiz.classList.add('abierto');
		colocarLista();
		(lista.children[marcada] as HTMLElement | undefined)?.scrollIntoView({ block: 'nearest' });
		addEventListener('pointerdown', fuera, true);
		addEventListener('resize', cerrarSuelto);
		addEventListener('scroll', cerrarSuelto, true);
	}

	/** Bajo el botón, o encima si no cabe; y siempre dentro de la pantalla. */
	function colocarLista() {
		const c = boton.getBoundingClientRect();
		lista.style.minWidth = `${Math.round(c.width)}px`;
		const alto = lista.offsetHeight;
		const arriba = c.bottom + alto + 12 > innerHeight && c.top > alto;
		lista.classList.toggle('arriba', arriba);
		lista.style.top = arriba ? '' : `${Math.round(c.bottom + 5)}px`;
		lista.style.bottom = arriba ? `${Math.round(innerHeight - c.top + 5)}px` : '';
		const ancho = lista.offsetWidth;
		lista.style.left = `${Math.round(Math.max(8, Math.min(c.left, innerWidth - ancho - 8)))}px`;
	}

	function cerrar(devolverFoco = false) {
		if (!abierto) return;
		abierto = false;
		lista.hidden = true;
		// De vuelta a su sitio: así el componente se clona entero (el informe) y no deja nada suelto.
		lista.removeAttribute('style');
		raiz.append(lista);
		boton.setAttribute('aria-expanded', 'false');
		boton.setAttribute('aria-activedescendant', '');
		raiz.classList.remove('abierto');
		removeEventListener('pointerdown', fuera, true);
		removeEventListener('resize', cerrarSuelto);
		removeEventListener('scroll', cerrarSuelto, true);
		if (devolverFoco) boton.focus();
	}

	const fuera = (ev: Event) => { const t = ev.target as Node; if (!raiz.contains(t) && !lista.contains(t)) cerrar(); };
	const cerrarSuelto = () => cerrar();

	function elegir(i: number) {
		const op = o.opciones[i];
		cerrar(true);
		if (!op || op.desactivada || op.valor === valor) return;
		valor = op.valor;
		pintarBoton();
		o.alElegir(valor);
	}

	boton.addEventListener('click', () => (abierto ? cerrar(true) : abrir()));
	boton.addEventListener('keydown', (ev) => {
		const k = ev.key;
		if (k === 'Enter' || k === ' ' || k === 'ArrowDown' || k === 'ArrowUp') {
			ev.preventDefault();
			if (!abierto) return abrir();
			if (k === 'Enter' || k === ' ') return elegir(marcada);
			return marcar(marcada + (k === 'ArrowDown' ? 1 : -1));
		}
		if (!abierto) return;
		// Con la lista abierta, las teclas son suyas: Esc la cierra y no sube de nivel en la página.
		if (k === 'Escape') { ev.preventDefault(); ev.stopPropagation(); return cerrar(true); }
		if (k === 'Home') { ev.preventDefault(); return marcar(0); }
		if (k === 'End') { ev.preventDefault(); return marcar(o.opciones.length - 1); }
		if (k === 'Tab') return cerrar();
		// Buscar por la primera letra, como en un desplegable de siempre.
		if (k.length === 1) {
			const l = k.toLowerCase();
			const desde = marcada + 1;
			const i = o.opciones.findIndex((x, j) => j >= desde && x.texto.toLowerCase().startsWith(l));
			const j = i >= 0 ? i : o.opciones.findIndex((x) => x.texto.toLowerCase().startsWith(l));
			if (j >= 0) marcar(j);
		}
	});

	pintarBoton();
	return {
		raiz,
		fijar(v) { valor = v; pintarBoton(); if (abierto) pintarLista(); },
		get valor() { return valor; },
	};
}
