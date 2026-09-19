// La cifra: cualquier número que aparece dentro de una frase se marca, se lee en tipografía mono y
// lleva a donde sale. Al pasar por encima dice su procedencia (qué es, de qué pilar, de qué fichero
// y con cuántas filas detrás); al pulsar, abre la evidencia ya filtrada en ese dato.
// Las tablas y los ejes no pasan por aquí: ahí el número ya está en su columna.

import { f } from '../datos/formato';
import { h, vaciar } from './dom';

export interface Origen {
	/** Qué es la cifra, en una línea: «colchón de caja», «aportación del pilar de liquidez». */
	que?: string;
	/** Pilar del que sale (nombre ya legible), para filtrar la evidencia. */
	pilar?: string | null;
	/** Fichero del bundle del que sale. */
	fichero?: string;
	/** Filas del fichero que la sostienen. */
	filas?: number;
	/** Mes al que corresponde. */
	mes?: string;
	/** Qué hace al pulsar. Sin esto, la cifra se ve pero no se toca. */
	ir?: () => void;
}

/**
 * Números dentro de una frase: entero o con decimales, con su signo y con la unidad pegada
 * («−4,5», «289.611 €», «37,3 días», «20 %»). No marca lo que va dentro de una palabra
 * (un identificador, un nombre de fichero) ni los años sueltos, que no son cifras que se puedan rastrear.
 */
const CIFRA = /(?<![\p{L}\w])([+−-]?\d{1,3}(?:\.\d{3})*(?:,\d+)?)([\s ]?(?:%|€|×|veces|puntos|pts|días|día|meses|mes))?(?![\p{L}\w])/gu;
const esAnno = (n: string, unidad: string | undefined) => !unidad && /^(19|20)\d{2}$/.test(n);

let nota: HTMLElement | null = null;
function laNota(): HTMLElement {
	if (!nota) {
		nota = h('div', { class: 'nota-cifra', role: 'tooltip', hidden: true });
		document.body.append(nota);
	}
	return nota;
}

function mostrar(el: HTMLElement, o: Origen) {
	const n = laNota();
	vaciar(n);
	const lineas: (Node | string)[] = [];
	if (o.que) lineas.push(h('b', {}, o.que));
	const rastro: string[] = [];
	if (o.pilar) rastro.push(`pilar de ${o.pilar.toLowerCase()}`);
	if (o.mes) rastro.push(f.mes(o.mes));
	if (o.fichero) rastro.push(o.filas ? `${o.fichero} · ${f.plural(o.filas, 'fila', 'filas')}` : o.fichero);
	if (rastro.length) lineas.push(h('span', { class: 'nota-cifra-rastro' }, rastro.join(' · ')));
	if (o.ir) lineas.push(h('span', { class: 'nota-cifra-pie' }, 'Pulsa para ver la evidencia'));
	if (!lineas.length) return;
	n.append(...lineas);
	n.hidden = false;
	const r = el.getBoundingClientRect();
	const ancho = n.offsetWidth;
	n.style.left = `${Math.max(8, Math.min(r.left + r.width / 2 - ancho / 2, innerWidth - ancho - 8))}px`;
	// Debajo del número salvo que no quepa; entonces, encima.
	const abajo = r.bottom + 8;
	n.style.top = `${abajo + n.offsetHeight > innerHeight - 8 ? r.top - n.offsetHeight - 8 : abajo}px`;
}

function esconder() {
	if (nota) nota.hidden = true;
}

/** Una cifra suelta, ya formateada. */
export function cifra(texto: string, o: Origen = {}): HTMLElement {
	const tocable = !!o.ir;
	const el = h(tocable ? 'button' : 'span', {
		class: `cifra ${tocable ? 'tocable' : ''}`,
		type: tocable ? 'button' : undefined,
		'aria-label': o.que ? `${texto} · ${o.que}` : undefined,
	}, texto);
	if (o.que || o.pilar || o.fichero) {
		el.addEventListener('pointerenter', () => mostrar(el, o));
		el.addEventListener('focus', () => mostrar(el, o));
		el.addEventListener('pointerleave', esconder);
		el.addEventListener('blur', esconder);
	}
	if (o.ir) el.addEventListener('click', (ev) => { ev.stopPropagation(); esconder(); o.ir!(); });
	return el;
}

/** La misma frase, con sus números convertidos en cifras trazables. */
export function conCifras(texto: string, o: Origen = {}): (Node | string)[] {
	const salida: (Node | string)[] = [];
	let ultimo = 0;
	for (const m of texto.matchAll(CIFRA)) {
		const [todo, numero, unidad] = m;
		if (esAnno(numero, unidad)) continue;
		if (m.index > ultimo) salida.push(texto.slice(ultimo, m.index));
		salida.push(cifra(todo, o));
		ultimo = m.index + todo.length;
	}
	if (!salida.length) return [texto];
	if (ultimo < texto.length) salida.push(texto.slice(ultimo));
	return salida;
}

/** Un párrafo de prosa con sus cifras marcadas. */
export function parrafo(clase: string, texto: string, o: Origen = {}): HTMLElement {
	return h('p', { class: clase }, ...conCifras(texto, o));
}
