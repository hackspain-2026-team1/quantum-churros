// Placas de arena para las páginas de Rumbo (entrada, organización, empresa). La página HTML deja
// huecos marcados y aquí se dibuja la arena encima, en coordenadas de página (la arena sigue al
// desplazamiento con arena.desplazar). Cuatro piezas:
//   · numeral: el score acuñado en arena;
//   · serie: una línea de tiempo que cruza el presente, con la estela asentada (lo observado) y el
//     futuro como arena suelta (cada grano es una de las simulaciones de los horizontes);
//   · flota: las empresas de un grupo en un plano pequeño (score y ritmo);
//   · rosa: la rosa de los vientos de Rumbo, en la entrada.

import { escenaVacia, TONO, type Escena } from './arena';
import { ajustar, anillo, disco, linea, punteado, texto, type Puntos } from './formas';
import { SERIF } from './escenas';

export interface PlacaNumeral { tipo: 'numeral'; x: number; y: number; h: number; texto: string; tono?: number }
export interface Futuro {
	/** Pares [mes 1..12, décimas] de las trayectorias simuladas. */
	granos: [number, number][];
	tono: number;
	alfa: number;
	/** Mediana mes a mes (décimas), dibujada como hilo. */
	mediana?: number[];
}
export interface PlacaSerie {
	tipo: 'serie';
	x: number; y: number; w: number; h: number;
	lo: number; hi: number; // puntos
	/** Columnas totales (pasado + futuro). */
	columnas: number;
	/** Índice de la columna de «hoy». */
	hoy: number;
	/** Pasado: [columna, puntos | null, tono]. */
	pasado: [number, number | null, number?][];
	/** Pasado de otras entidades, fino (empresas de un grupo). */
	hilos?: [number, number | null][][];
	futuros?: Futuro[];
	/** Umbrales de banda en puntos (del manifiesto). */
	bandas: number[];
	/** Marca en el futuro (cifra del motor al acabar la subida): [columna, puntos]. */
	marcas?: [number, number][];
}
export interface PlacaFlota { tipo: 'flota'; x: number; y: number; w: number; h: number; puntos: { x: number; y: number; r: number; tono: number; alfa?: number }[] }
export interface PlacaRosa { tipo: 'rosa'; cx: number; cy: number; r: number }
export type Placa = PlacaNumeral | PlacaSerie | PlacaFlota | PlacaRosa;

class Lote {
	p: Puntos = []; tono: number[] = []; alfa: number[] = []; talla: number[] = [];
	add(pts: Puntos, tono: number, alfa: number, talla: number) {
		for (let i = 0; i < pts.length; i += 2) { this.p.push(pts[i], pts[i + 1]); this.tono.push(tono); this.alfa.push(alfa); this.talla.push(talla); }
	}
	get n() { return this.p.length / 2; }
}

function numeral(l: Lote, p: PlacaNumeral, movil: boolean) {
	const t = texto(p.texto, p.h, 600, movil ? 1.35 : 1.55, SERIF);
	const pts: Puntos = [];
	for (let i = 0; i < t.puntos.length; i += 2) pts.push(p.x + t.puntos[i], p.y + t.puntos[i + 1]);
	l.add(pts.length / 2 > 14000 ? ajustar(pts, 14000) : pts, p.tono ?? TONO.tinta, 1, movil ? 1.5 : 1.9);
}

function serie(l: Lote, s: PlacaSerie) {
	const cw = s.w / s.columnas;
	const X = (c: number) => s.x + (c + 0.5) * cw;
	const Y = (v: number) => s.y + s.h - Math.max(0, Math.min(1, (v - s.lo) / (s.hi - s.lo))) * s.h;
	// Bandas y la raya de hoy.
	for (const b of s.bandas) if (b > s.lo && b < s.hi) l.add(punteado(s.x, Y(b), s.x + s.w, Y(b), 6), TONO.filete, 0.8, 1.15);
	const xh = s.x + (s.hoy + 1) * cw;
	l.add(punteado(xh, s.y - 6, xh, s.y + s.h + 6, 4), TONO.apagado, 0.55, 1.2);
	// Hilos finos (empresas), por debajo.
	for (const hilo of s.hilos ?? []) {
		const pts = hilo.filter((q) => q[1] !== null).flatMap((q) => [X(q[0]), Y(q[1]!)]);
		if (pts.length >= 4) l.add(linea(pts, Math.round(pts.length * 9), 0.7), TONO.apagado, 0.45, 1.1);
	}
	// Estela: lo observado, asentado.
	const obs = s.pasado.filter((q) => q[1] !== null);
	for (let i = 1; i < obs.length; i++) {
		const a = obs[i - 1], b = obs[i];
		if (b[0] - a[0] > 1) continue; // un hueco sin datos no se une
		const n = Math.round(Math.hypot(X(b[0]) - X(a[0]), Y(b[1]!) - Y(a[1]!)) * 1.7);
		l.add(linea([X(a[0]), Y(a[1]!), X(b[0]), Y(b[1]!)], n, 1.2), TONO.tinta, 0.9, 1.5);
	}
	obs.forEach((q, i) => l.add(disco(X(q[0]), Y(q[1]!), i === obs.length - 1 ? 4.4 : 2.4, i === obs.length - 1 ? 34 : 12), q[2] ?? TONO.tinta, 1, 1.6));
	// Futuro: arena suelta. Cada grano de la simulación son tres granos de arena.
	for (const fu of s.futuros ?? []) {
		for (const [m, d] of fu.granos) {
			const x0 = X(s.hoy + m), y0 = Y(d / 10);
			for (let k = 0; k < 4; k++) l.add([x0 + (Math.random() - 0.5) * cw * 1.05, y0 + (Math.random() - 0.5) * 4], fu.tono, fu.alfa, 1.55);
		}
		if (fu.mediana) {
			const pts = [X(s.hoy), Y(obs.length ? obs[obs.length - 1][1]! : fu.mediana[0] / 10), ...fu.mediana.flatMap((d, i) => [X(s.hoy + i + 1), Y(d / 10)])];
			l.add(linea(pts, Math.round(s.w * 0.9), 0.8), fu.tono, Math.min(1, fu.alfa + 0.45), 1.4);
		}
	}
	for (const [c, v] of s.marcas ?? []) l.add(anillo(X(c), Y(v), 6, 40, 0.9), TONO.info, 1, 1.5);
}

function flota(l: Lote, f: PlacaFlota) {
	l.add(punteado(f.x, f.y + f.h / 2, f.x + f.w, f.y + f.h / 2, 7), TONO.filete, 0.7, 1.1);
	l.add(punteado(f.x + f.w * 0.6, f.y, f.x + f.w * 0.6, f.y + f.h, 7), TONO.filete, 0.7, 1.1);
	for (const q of f.puntos) l.add(disco(f.x + q.x * f.w, f.y + q.y * f.h, q.r, Math.round(10 + q.r * q.r * 2.2)), q.tono, q.alfa ?? 1, 1.6);
}

function rosa(l: Lote, r: PlacaRosa) {
	const { cx, cy } = r;
	l.add(anillo(cx, cy, r.r, Math.round(r.r * 5), 1), TONO.tinta, 0.5, 1.2);
	l.add(anillo(cx, cy, r.r * 0.72, Math.round(r.r * 3), 0.8), TONO.filete, 0.8, 1.1);
	// Cuatro puntas largas y cuatro cortas, rellenas de arena (más densas en la mitad de sombra).
	for (let k = 0; k < 8; k++) {
		const a = (k / 8) * Math.PI * 2 - Math.PI / 2;
		const largo = k % 2 === 0 ? r.r * 1.18 : r.r * 0.62;
		const ancho = k % 2 === 0 ? r.r * 0.16 : r.r * 0.1;
		const n = Math.round(largo * (k % 2 === 0 ? 9 : 5));
		for (let i = 0; i < n; i++) {
			const u = Math.random(), lado = Math.random() < 0.5 ? -1 : 1;
			const w = (1 - u) * ancho * Math.random();
			const x = cx + Math.cos(a) * largo * u + Math.cos(a + Math.PI / 2) * w * lado;
			const y = cy + Math.sin(a) * largo * u + Math.sin(a + Math.PI / 2) * w * lado;
			l.add([x, y], k === 0 ? TONO.info : TONO.tinta, lado > 0 ? 0.95 : 0.45, 1.35);
		}
	}
	l.add(disco(cx, cy, r.r * 0.06, 20), TONO.tinta, 1, 1.4);
}

/**
 * Compone la escena de una página. Los granos que sobran reposan en la franja de abajo, invisibles.
 * `ancho`/`alto`: tamaño de la ventana, para el reposo.
 */
export function escenaPlacas(placas: Placa[], n: number, ancho: number, alto: number, movil: boolean): Escena {
	const e = escenaVacia(n);
	const l = new Lote();
	for (const p of placas) {
		if (p.tipo === 'numeral') numeral(l, p, movil);
		else if (p.tipo === 'serie') serie(l, p);
		else if (p.tipo === 'flota') flota(l, p);
		else rosa(l, p);
	}
	let pts = l.p, tonos = l.tono, alfas = l.alfa, tallas = l.talla;
	if (l.n > n) { pts = ajustar(l.p, n); tonos = tonos.slice(0, n); alfas = alfas.slice(0, n); tallas = tallas.slice(0, n); }
	const usados = Math.min(n, l.n);
	for (let i = 0; i < n; i++) {
		if (i < usados) {
			e.x[i] = pts[i * 2]; e.y[i] = pts[i * 2 + 1]; e.tono[i] = tonos[i]; e.alfa[i] = alfas[i]; e.talla[i] = tallas[i];
		} else {
			e.x[i] = Math.random() * ancho; e.y[i] = alto + 40 + Math.random() * 60; e.tono[i] = TONO.filete; e.alfa[i] = 0; e.talla[i] = 1;
		}
		e.espera[i] = i < usados ? Math.random() * 0.25 : 0;
	}
	e.turbulencia = 0.45;
	e.rigidez = 7.2;
	return e;
}
