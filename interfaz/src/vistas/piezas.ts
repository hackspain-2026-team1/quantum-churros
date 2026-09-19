// Piezas con forma: cada control y cada dato pequeño lleva su significado en el dibujo.

import { NOMBRE_BANDA, type Banda, type Confianza, type Direccion, type Naturaleza } from '../datos/modelo';
import { h } from './dom';

const NS = 'http://www.w3.org/2000/svg';
function svg(w: number, hgt: number, clase = ''): SVGSVGElement {
	const s = document.createElementNS(NS, 'svg');
	s.setAttribute('width', String(w));
	s.setAttribute('height', String(hgt));
	s.setAttribute('viewBox', `0 0 ${w} ${hgt}`);
	s.setAttribute('aria-hidden', 'true');
	if (clase) s.setAttribute('class', clase);
	return s;
}
function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number>) {
	const e = document.createElementNS(NS, tag);
	for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
	return e;
}

// Pseudoaleatorio estable para que los glifos no cambien en cada repintado.
function rng(semilla: number) {
	let a = semilla >>> 0;
	return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// ─── Glifos de las fichas de la frase ─────────────────────────

/** Un montoncito de granos: su tamaño crece con la proporción de la cartera que se mira. */
export function glifoMonton(proporcion: number): SVGSVGElement {
	const s = svg(22, 16, 'glifo');
	const n = Math.max(1, Math.round(3 + 22 * Math.sqrt(Math.max(0, Math.min(1, proporcion)))));
	const r = rng(7);
	const ancho = 3 + 7.5 * Math.sqrt(Math.max(0.02, proporcion));
	const alto = 2.5 + 8 * Math.sqrt(Math.max(0.02, proporcion));
	for (let i = 0; i < n; i++) {
		const hh = Math.pow(r(), 0.8);
		const w = (1 - hh) * ancho;
		s.append(el('circle', { cx: 11 + (r() - 0.5) * 2 * w, cy: 14 - hh * alto, r: 0.95, class: 'grano' }));
	}
	return s;
}

/** Corchetes cuya apertura es proporcional a la duración del intervalo (en meses). */
export function glifoCorchete(meses: number): SVGSVGElement {
	const w = 10 + Math.min(12, meses * 0.9);
	const s = svg(w + 4, 16, 'glifo');
	const trazo = { fill: 'none', 'stroke-width': 1.4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'trazo' };
	s.append(el('path', { d: `M5 3 H2.5 V13 H5`, ...trazo }), el('path', { d: `M${w - 1} 3 H${w + 1.5} V13 H${w - 1}`, ...trazo }));
	for (let i = 0; i < Math.min(8, Math.max(1, Math.round(meses / 1.5))); i++) s.append(el('circle', { cx: 6 + ((i + 0.5) * (w - 9)) / Math.min(8, Math.max(1, Math.round(meses / 1.5))), cy: 8, r: 0.9, class: 'grano' }));
	return s;
}

/** Muescas de regla: una por periodo del año. */
export function glifoMuescas(n: number): SVGSVGElement {
	const s = svg(22, 16, 'glifo');
	s.append(el('line', { x1: 2, y1: 12.5, x2: 20, y2: 12.5, class: 'trazo', 'stroke-width': 1.3, 'stroke-linecap': 'round' }));
	for (let i = 0; i <= n; i++) {
		const x = 2 + (18 * i) / n;
		s.append(el('line', { x1: x, y1: 12.5, x2: x, y2: i === 0 || i === n ? 5.5 : 8, class: 'trazo', 'stroke-width': 1.2, 'stroke-linecap': 'round' }));
	}
	return s;
}

/** Dos puntos unidos: ahora y antes. */
export function glifoComparar(): SVGSVGElement {
	const s = svg(22, 16, 'glifo');
	s.append(el('path', { d: 'M5 11 Q11 2 17 6', fill: 'none', class: 'trazo', 'stroke-width': 1.2, 'stroke-dasharray': '1.5 2', 'stroke-linecap': 'round' }));
	s.append(el('circle', { cx: 5, cy: 11, r: 2.4, class: 'anillo', fill: 'none', 'stroke-width': 1.2 }), el('circle', { cx: 17, cy: 6, r: 2.6, class: 'grano' }));
	return s;
}

/** Orden: tres barras de granos decrecientes. */
export function glifoOrden(): SVGSVGElement {
	const s = svg(22, 16, 'glifo');
	[14, 10, 6].forEach((w, i) => { for (let k = 0; k < w; k += 2.2) s.append(el('circle', { cx: 3 + k, cy: 4 + i * 4.2, r: 0.9, class: 'grano' })); });
	return s;
}

// ─── Sellos y cifras ──────────────────────────────────────────

/** Sello de banda: el nombre y una línea de 0 a 100 con las bandas y un grano donde está el grupo. */
export function selloBanda(banda: Banda, puntos: number): HTMLElement {
	const s = svg(96, 10, 'sello-escala');
	const x = (v: number) => 3 + (v / 100) * 90;
	s.append(el('line', { x1: x(0), y1: 5, x2: x(100), y2: 5, class: 'escala-linea' }));
	for (const v of [40, 60, 80]) s.append(el('line', { x1: x(v), y1: 2.5, x2: x(v), y2: 7.5, class: 'escala-marca' }));
	s.append(el('circle', { cx: x(Math.max(0, Math.min(100, puntos))), cy: 5, r: 3.2, class: `escala-grano ${banda}` }));
	return h('span', { class: `sello banda ${banda}`, title: `${NOMBRE_BANDA[banda]}: ${Math.round(puntos)} sobre 100` }, h('span', { class: 'sello-texto' }, NOMBRE_BANDA[banda]), s);
}

/** Sello de movimiento: la misma forma que el cometa en la arena. */
export function selloMovimiento(dir: Direccion | null, nat: Naturaleza | null): HTMLElement {
	const baja = dir === 'deteriorating';
	const sube = dir === 'improving';
	if (nat === 'shock_pending') return h('span', { class: `sello mov confirmar ${baja ? 'baja' : 'sube'}` }, flecha(baja), baja ? 'Baja, por confirmar' : 'Sube, por confirmar');
	if (nat === 'structural') return h('span', { class: `sello mov estructural ${baja ? 'baja' : 'sube'}` }, flecha(baja), baja ? 'Deterioro confirmado' : 'Mejora confirmada');
	if (nat === 'bump') return h('span', { class: 'sello mov bache' }, 'Bache, ya revertido');
	if (dir === 'perimeter_shift') return h('span', { class: 'sello mov perimetro' }, 'Cambio de perímetro');
	void sube;
	return h('span', { class: 'sello mov quieto' }, 'Sin movimiento que confirmar');
}
function flecha(baja: boolean) {
	const s = svg(10, 12, 'flecha');
	for (let i = 0; i < 4; i++) s.append(el('circle', { cx: 5, cy: baja ? 2 + i * 2.2 : 10 - i * 2.2, r: 0.95, class: 'grano' }));
	s.append(el('path', { d: baja ? 'M2 7.5 L5 11 L8 7.5' : 'M2 4.5 L5 1 L8 4.5', fill: 'none', class: 'trazo', 'stroke-width': 1.2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
	return s;
}

/** Confianza en tres granos. */
export function granosConfianza(c: Confianza | null, conPalabra = true): HTMLElement {
	const n = c === 'high' ? 3 : c === 'medium' ? 2 : c === 'low' ? 1 : 0;
	const palabra = c === 'high' ? 'Confianza alta' : c === 'medium' ? 'Confianza media' : c === 'low' ? 'Confianza baja' : 'Sin confianza';
	const g = h('span', { class: 'granos-conf', title: palabra, 'aria-label': palabra });
	for (let i = 0; i < 3; i++) g.append(h('i', { class: i < n ? 'lleno' : '' }));
	return h('span', { class: 'confianza' }, g, conPalabra ? h('span', {}, palabra) : null);
}

/** Cola: la serie de un número, del tamaño de una palabra. */
export function cola(valores: (number | null)[], ancho = 96, alto = 22, clase = ''): SVGSVGElement {
	const s = svg(ancho, alto, `cola ${clase}`);
	const nums = valores.filter((v): v is number => v !== null);
	if (nums.length < 2) return s;
	const min = Math.min(...nums), max = Math.max(...nums);
	const rango = Math.max(60, max - min), medio = (min + max) / 2;
	const x = (i: number) => (i / Math.max(1, valores.length - 1)) * (ancho - 6) + 3;
	const y = (v: number) => alto / 2 - ((v - medio) / rango) * (alto - 6);
	let d = '', abierto = false;
	valores.forEach((v, i) => { if (v === null) { abierto = false; return; } d += `${abierto ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`; abierto = true; });
	s.append(el('path', { d, fill: 'none', class: 'trazo', 'stroke-width': 1.4, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
	const ult = valores.length - 1;
	if (valores[ult] !== null) s.append(el('circle', { cx: x(ult), cy: y(valores[ult] as number), r: 2.3, class: 'grano' }));
	return s;
}

/** Cifra con contexto: el número, qué es, su cola y la comparación. */
export function cifra(o: { valor: string; que: string; cola?: (number | null)[]; comparacion?: string; tono?: 'sube' | 'baja' | '' }): HTMLElement {
	return h('div', { class: `cifra ${o.tono ?? ''}` },
		h('div', { class: 'cifra-fila' }, h('span', { class: 'cifra-valor' }, o.valor), o.cola ? cola(o.cola, 70, 22) : null),
		h('div', { class: 'cifra-que' }, o.que),
		o.comparacion ? h('div', { class: 'cifra-comp' }, o.comparacion) : null,
	);
}

// ─── El reloj de arena ────────────────────────────────────────

/** Reproducir: un reloj de arena que se vacía mientras suena. */
let relojes = 0;

/**
 * El reloj de arena de Rumbo, grabado como los productos: marco torneado con dos columnas, el
 * vidrio en trazo fino y la arena hecha de granos. Al reproducir, la arena de arriba baja, cae
 * por el cuello grano a grano y el montón de abajo crece.
 */
export function relojArena(): SVGSVGElement {
	const id = `rj${++relojes}`;
	const s = svg(30, 40, 'reloj-arena');
	s.setAttribute('viewBox', '0 0 30 40');
	// Mitad del ancho interior del vidrio a una altura y (curva de Bézier del bulbo de arriba, reflejada abajo).
	const curva: [number, number][] = [];
	for (let k = 0; k <= 40; k++) {
		const t = k / 40, u = 1 - t;
		const x = u * u * u * 8.6 + 3 * u * u * t * 8.6 + 3 * u * t * t * 14 + t * t * t * 14;
		const y = u * u * u * 6.8 + 3 * u * u * t * 13.4 + 3 * u * t * t * 15.4 + t * t * t * 20;
		curva.push([y, 15 - x]);
	}
	const media = (y: number) => {
		const yy = y <= 20 ? y : 40 - y;
		for (let k = 1; k < curva.length; k++) if (curva[k][0] >= yy) { const [y0, w0] = curva[k - 1], [y1, w1] = curva[k]; return w0 + ((w1 - w0) * (yy - y0)) / (y1 - y0 || 1); }
		return 1;
	};
	const azar = rng(29);
	const grano = (x: number, y: number) => el('circle', { cx: x.toFixed(2), cy: y.toFixed(2), r: (0.36 + azar() * 0.16).toFixed(2) });
	const arriba = el('g', { class: 'arena-arriba', 'clip-path': `url(#${id}a)` });
	const abajo = el('g', { class: 'arena-abajo', 'clip-path': `url(#${id}b)` });
	for (let y = 10.6; y < 19.6; y += 0.82) for (let x = 15 - media(y) + 0.9; x < 15 + media(y) - 0.9; x += 0.86) arriba.append(grano(x + (azar() - 0.5) * 0.5, y + (azar() - 0.5) * 0.5));
	// El montón de abajo: más alto en el centro.
	for (let y = 24.4; y < 33; y += 0.8) for (let x = 15 - media(y) + 0.9; x < 15 + media(y) - 0.9; x += 0.84) {
		const cima = 25 + 3.4 * Math.pow(Math.abs(x - 15) / 5.6, 1.5);
		if (y >= cima) abajo.append(grano(x + (azar() - 0.5) * 0.45, y + (azar() - 0.5) * 0.45));
	}
	const chorro = el('g', { class: 'chorro' });
	for (const y of [20.4, 22, 23.6, 25.2]) chorro.append(el('circle', { cx: 15, cy: y, r: 0.45 }));
	const defs = el('defs', {});
	const ca = el('clipPath', { id: `${id}a` }); ca.append(el('rect', { class: 'clip-arriba', x: 0, y: 10, width: 30, height: 10.2 }));
	const cb = el('clipPath', { id: `${id}b` }); cb.append(el('rect', { class: 'clip-abajo', x: 0, y: 24, width: 30, height: 12 }));
	defs.append(ca, cb);
	s.append(defs, arriba, chorro, abajo,
		// Vidrio: trazo fino y un brillo.
		el('path', { d: 'M8.6 6.8C8.6 13.4 14 15.4 14 20C14 24.6 8.6 26.6 8.6 33.2M21.4 6.8C21.4 13.4 16 15.4 16 20C16 24.6 21.4 26.6 21.4 33.2', class: 'trazo vidrio', fill: 'none', 'stroke-width': 0.85, 'stroke-linecap': 'round' }),
		el('path', { d: 'M10.3 8.8C10.5 11.6 11.6 13.2 12.7 14.3', class: 'trazo brillo', fill: 'none', 'stroke-width': 0.5, 'stroke-linecap': 'round' }),
		// Marco torneado: tablas con grueso y fino, dos columnas con una cuenta en medio y patas.
		el('path', { d: 'M3.6 4.4H26.4M3.6 35.6H26.4', class: 'trazo', 'stroke-width': 2, 'stroke-linecap': 'round' }),
		el('path', { d: 'M5.2 6.5H24.8M5.2 33.5H24.8', class: 'trazo', 'stroke-width': 0.6, 'stroke-linecap': 'round' }),
		el('path', { d: 'M5.4 6.6V33.4M24.6 6.6V33.4', class: 'trazo', 'stroke-width': 1.05, 'stroke-linecap': 'round' }),
		el('ellipse', { cx: 5.4, cy: 20, rx: 1.05, ry: 1.7, class: 'cuenta' }), el('ellipse', { cx: 24.6, cy: 20, rx: 1.05, ry: 1.7, class: 'cuenta' }),
		el('path', { d: 'M5 2.2V2.9M25 2.2V2.9M5 37.1V37.8M25 37.1V37.8', class: 'trazo', 'stroke-width': 1.6, 'stroke-linecap': 'round' }),
	);
	return s;
}

// ─── Miniaturas vivas del selector de vista ──────────────────

export function miniatura(tipo: 'plano' | 'tapiz', puntos: { x: number; y: number; t: number }[]): HTMLCanvasElement {
	const dpr = Math.min(2, devicePixelRatio || 1);
	const c = document.createElement('canvas');
	c.width = 44 * dpr; c.height = 30 * dpr;
	c.style.width = '44px'; c.style.height = '30px';
	const x = c.getContext('2d')!;
	x.scale(dpr, dpr);
	const colores = ['#050b2c', '#c2401f', '#08ab39', '#3878f6'];
	if (tipo === 'plano') {
		x.fillStyle = 'rgba(5,11,44,.12)'; x.fillRect(4, 15, 36, 0.8); x.fillRect(22, 3, 0.8, 24);
		for (const p of puntos) { x.fillStyle = colores[p.t] ?? colores[0]; x.globalAlpha = 0.85; x.beginPath(); x.arc(4 + p.x * 36, 3 + p.y * 24, 1.1, 0, 7); x.fill(); }
	} else {
		// En el tapiz, x es la columna, y la fila y t el nivel (0–1): la tinta densa es score alto.
		x.fillStyle = colores[0];
		for (const p of puntos) { x.globalAlpha = 0.12 + 0.88 * p.t; x.fillRect(4 + p.x * 36, 3 + p.y * 24, 1.6, 1.3); }
	}
	return c;
}

/** El cometa de un grupo en pequeño (para volver del expediente al plano). */
export function cometaMini(serie: (number | null)[], ritmo: number | null): HTMLCanvasElement {
	const dpr = Math.min(2, devicePixelRatio || 1);
	const c = document.createElement('canvas');
	c.width = 36 * dpr; c.height = 28 * dpr;
	c.style.width = '36px'; c.style.height = '28px';
	const x = c.getContext('2d')!;
	x.scale(dpr, dpr);
	const vals = serie.filter((v): v is number => v !== null);
	const r = rng(3);
	vals.forEach((v, i) => {
		const u = i / Math.max(1, vals.length - 1);
		const px = 4 + u * 24 + (r() - 0.5);
		const py = 22 - ((v / 10 - 15) / 85) * 18 + (r() - 0.5);
		x.globalAlpha = 0.15 + 0.75 * u;
		x.fillStyle = '#3878f6';
		x.beginPath(); x.arc(px, py, 0.9 + u * 0.8, 0, 7); x.fill();
	});
	const ult = vals[vals.length - 1];
	if (ult !== undefined) {
		x.globalAlpha = 1; x.fillStyle = '#3878f6';
		const r2 = rng(11);
		for (let i = 0; i < 26; i++) { const a = r2() * 7, d = Math.sqrt(r2()) * 3.6; x.beginPath(); x.arc(29 + Math.cos(a) * d, 22 - ((ult / 10 - 15) / 85) * 18 + Math.sin(a) * d, 0.8, 0, 7); x.fill(); }
	}
	void ritmo;
	return c;
}
