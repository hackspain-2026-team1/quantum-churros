// Placas de arena para las páginas de Rumbo. La página HTML deja huecos marcados y aquí se dibuja la
// arena encima. Las placas de página van en coordenadas de página (siguen al desplazamiento); las
// fijas (el horizonte y el número, siempre a la vista) van en coordenadas de pantalla.
//   · numeral: el score acuñado en arena, dentro de su círculo, que es su escala de 0 a 100;
//   · serie: el tiempo que cruza el presente: lo observado asentado, lo que pasó después (si la
//     regla está en un mes pasado) y el futuro como arena suelta (cada grano, una trayectoria);
//   · flota: las empresas de un grupo en un plano con sus dos ejes;
//   · rosa: la rosa de los vientos de Rumbo, el objeto de la portada.

import { escenaVacia, TONO, type Escena } from './arena';
import { ajustar, anillo, disco, linea, punteado, texto, type Puntos } from './formas';
import { SERIF } from './escenas';
import { disponer, type DatosVista } from './vistas';

export interface MarcaAnillo { v: number; tipo: 'pares' | 'grupo' }
export interface PlacaNumeral {
	tipo: 'numeral'; x: number; y: number; h: number; texto: string; tono?: number; fijo?: boolean;
	/** El círculo: centro, radio, valor 0–100, cortes de banda (puntos) y marcas de comparación. */
	anillo?: { cx: number; cy: number; r: number; valor: number; bandas: number[]; tono: number; marcas: MarcaAnillo[] };
}
export interface Futuro {
	/** Pares [mes 1..12, décimas] de las trayectorias. */
	granos: [number, number][];
	tono: number;
	alfa: number;
	/** Mediana mes a mes (décimas), dibujada como hilo. */
	mediana?: number[];
	/** Columna desde la que empieza (por defecto, la de hoy). */
	desde?: number;
}
export interface LineaSerie { puntos: [number, number][]; tono: number; alfa: number; punteada?: boolean; grosor?: number }
export interface PlacaSerie {
	tipo: 'serie';
	fijo?: boolean;
	x: number; y: number; w: number; h: number;
	lo: number; hi: number; // puntos
	/** Columnas totales (calendario entero: pasado + 12 meses). */
	columnas: number;
	/** Índice de la columna de «hoy» (el corte de la regla). */
	hoy: number;
	/** Pasado: [columna, puntos | null, tono]. */
	pasado: [number, number | null, number?][];
	/** Lo que pasó después del corte (cuando la regla está en un mes pasado): asentado y tenue. */
	despues?: [number, number | null][];
	/** Pasado de otras entidades, fino (empresas de un grupo). */
	hilos?: [number, number | null][][];
	futuros?: Futuro[];
	/** Líneas de referencia: medianas de los «qué pasaría si», contorno fantasma de «no hacer nada». */
	lineas?: LineaSerie[];
	/** Umbrales de banda en puntos (del manifiesto). */
	bandas: number[];
	/** Marcas del eje vertical (rejilla fina). */
	rejilla: number[];
	/** Marca en el futuro (cifra del motor al acabar la subida): [columna, puntos]. */
	marcas?: [number, number][];
	/** Avisos confirmados posados en su mes: arriba mejoras, abajo deterioros. */
	avisos?: { col: number; v: number; mejora: boolean }[];
	/** Un pilar señalado, encima, en fino. */
	pilar?: [number, number | null][];
}
export interface PlacaFlota {
	tipo: 'flota'; fijo?: boolean; x: number; y: number; w: number; h: number;
	puntos: { x: number; y: number; r: number; tono: number; alfa?: number }[];
	/** Rejilla: posiciones 0–1 en x (bandas) y en y (cero y marcas). */
	rejillaX: { u: number; fuerte: boolean }[];
	rejillaY: { u: number; fuerte: boolean }[];
}
export interface PlacaRosa {
	tipo: 'rosa'; cx: number; cy: number; r: number; fijo?: boolean;
	zonas?: { solida: number; mejora: number; tuerce: number; hunde: number };
	aguja?: number;
}
export interface PlacaVista { tipo: 'vista'; x: number; y: number; w: number; h: number; datos: DatosVista; fijo?: boolean }
export type Placa = PlacaNumeral | PlacaSerie | PlacaFlota | PlacaRosa | PlacaVista;

class Lote {
	p: Puntos = []; tono: number[] = []; alfa: number[] = []; talla: number[] = []; fijo: number[] = [];
	actual = 0;
	add(pts: Puntos, tono: number, alfa: number, talla: number) {
		for (let i = 0; i < pts.length; i += 2) { this.p.push(pts[i], pts[i + 1]); this.tono.push(tono); this.alfa.push(alfa); this.talla.push(talla); this.fijo.push(this.actual); }
	}
	get n() { return this.p.length / 2; }
}

/** Arco de circunferencia en sentido horario desde las doce (u de 0 a 1). */
function arco(cx: number, cy: number, r: number, u0: number, u1: number, n: number, grosor: number): Puntos {
	const pts: Puntos = [];
	for (let i = 0; i < n; i++) {
		const u = u0 + ((i + Math.random()) / n) * (u1 - u0);
		const a = -Math.PI / 2 + u * Math.PI * 2;
		const rr = r + (Math.random() - 0.5) * grosor;
		pts.push(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
	}
	return pts;
}
const enAnillo = (cx: number, cy: number, r: number, u: number): [number, number] => {
	const a = -Math.PI / 2 + u * Math.PI * 2;
	return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
};

function numeral(l: Lote, p: PlacaNumeral, movil: boolean) {
	const an = p.anillo;
	const alto = an ? an.r * (p.texto.length >= 3 ? 0.62 : 0.8) : p.h;
	const t = texto(p.texto, alto, 600, movil ? 1.35 : 1.5, SERIF);
	const ox = an ? an.cx - t.ancho / 2 : p.x;
	const oy = an ? an.cy - t.alto / 2 - an.r * 0.1 : p.y;
	const pts: Puntos = [];
	for (let i = 0; i < t.puntos.length; i += 2) pts.push(ox + t.puntos[i], oy + t.puntos[i + 1]);
	l.add(pts.length / 2 > 12000 ? ajustar(pts, 12000) : pts, p.tono ?? TONO.tinta, 1, movil ? 1.5 : 1.8);
	if (!an) return;
	const { cx, cy, r } = an;
	const u = Math.max(0, Math.min(1, an.valor / 100));
	// La escala entera, fina; lo recorrido hasta el score, apretado y en su tono.
	l.add(arco(cx, cy, r, 0, 1, Math.round(r * 10), 0.8), TONO.filete, 1, 1.3);
	l.add(arco(cx, cy, r, 0, u, Math.round(r * 16 * u) + 4, 3.2), an.tono, 0.95, 1.6);
	// Los cortes de banda, como muescas hacia fuera.
	for (const b of an.bandas) {
		const [x0, y0] = enAnillo(cx, cy, r + 4, b / 100), [x1, y1] = enAnillo(cx, cy, r + 11, b / 100);
		l.add(punteado(x0, y0, x1, y1, 1.6), TONO.apagado, 0.9, 1.3);
	}
	// Comparaciones: las de su tamaño (anillo hueco) y su grupo (grano).
	for (const m of an.marcas) {
		const [mx, my] = enAnillo(cx, cy, r, Math.max(0, Math.min(1, m.v / 100)));
		if (m.tipo === 'pares') l.add(anillo(mx, my, 5, 26, 0.7), TONO.apagado, 1, 1.3);
		else l.add(disco(mx, my, 3.4, 16), TONO.apagado, 1, 1.4);
	}
	const [vx, vy] = enAnillo(cx, cy, r, u);
	l.add(disco(vx, vy, 5.6, 46), an.tono, 1, 1.6);
}

function serie(l: Lote, s: PlacaSerie) {
	const cw = s.w / s.columnas;
	const X = (c: number) => s.x + (c + 0.5) * cw;
	const Y = (v: number) => s.y + s.h - Math.max(0, Math.min(1, (v - s.lo) / (s.hi - s.lo))) * s.h;
	// Ejes: la base y la vertical izquierda; rejilla fina; bandas más marcadas.
	l.add(punteado(s.x, s.y + s.h, s.x + s.w, s.y + s.h, 2.4), TONO.apagado, 0.8, 1.2);
	l.add(punteado(s.x, s.y, s.x, s.y + s.h, 2.4), TONO.apagado, 0.8, 1.2);
	for (const v of s.rejilla) if (v > s.lo && v < s.hi && !s.bandas.includes(v)) l.add(punteado(s.x, Y(v), s.x + s.w, Y(v), 9), TONO.filete, 0.55, 1.05);
	for (const b of s.bandas) if (b > s.lo && b < s.hi) l.add(punteado(s.x, Y(b), s.x + s.w, Y(b), 5), TONO.filete, 0.95, 1.2);
	// Marcas del eje de meses.
	for (let c = 0; c <= s.columnas; c += 1) {
		const x = s.x + c * cw;
		l.add(punteado(x, s.y + s.h, x, s.y + s.h + (c % 3 === 0 ? 6 : 3), 1.5), TONO.apagado, 0.7, 1.1);
	}
	// La raya de hoy: la misma que el tirador de la regla.
	const xh = X(s.hoy);
	l.add(punteado(xh, s.y - 4, xh, s.y + s.h, 3), TONO.info, 0.8, 1.35);
	for (const hilo of s.hilos ?? []) {
		const pts = hilo.filter((q) => q[1] !== null).flatMap((q) => [X(q[0]), Y(q[1]!)]);
		if (pts.length >= 4) l.add(linea(pts, Math.round(pts.length * 9), 0.7), TONO.apagado, 0.4, 1.1);
	}
	const tramo = (serieP: [number, number | null, number?][], tono: number, alfa: number, talla: number, denso: number) => {
		const obs = serieP.filter((q) => q[1] !== null);
		for (let i = 1; i < obs.length; i++) {
			const a = obs[i - 1], b = obs[i];
			if (b[0] - a[0] > 1) continue; // un hueco sin datos no se une
			const n = Math.round(Math.hypot(X(b[0]) - X(a[0]), Y(b[1]!) - Y(a[1]!)) * denso);
			l.add(linea([X(a[0]), Y(a[1]!), X(b[0]), Y(b[1]!)], n, 1.1), tono, alfa, talla);
		}
		return obs;
	};
	// Lo que pasó después del corte: asentado, pero tenue.
	if (s.despues?.length) {
		const obs = tramo([[s.hoy, s.pasado.filter((q) => q[1] !== null).at(-1)?.[1] ?? null], ...s.despues], TONO.apagado, 0.5, 1.3, 1.1);
		obs.slice(1).forEach((q) => l.add(disco(X(q[0]), Y(q[1]!), 1.8, 8), TONO.apagado, 0.6, 1.3));
	}
	if (s.pilar) tramo(s.pilar, TONO.info, 0.75, 1.3, 1.2);
	const obs = tramo(s.pasado, TONO.tinta, 0.92, 1.5, 1.7);
	obs.forEach((q, i) => l.add(disco(X(q[0]), Y(q[1]!), i === obs.length - 1 ? 4.6 : 2.3, i === obs.length - 1 ? 36 : 12), q[2] ?? TONO.tinta, 1, 1.6));
	// Avisos: un montoncito sobre el punto (mejora) o bajo él (deterioro).
	for (const a of s.avisos ?? []) {
		const x = X(a.col), y = Y(a.v) + (a.mejora ? -9 : 9);
		const pts: Puntos = [];
		for (let i = 0; i < 34; i++) { const hh = Math.pow(Math.random(), 0.8); const w = (1 - hh) * 4.5; pts.push(x + (Math.random() - 0.5) * 2 * w, y + (a.mejora ? -1 : 1) * hh * 7); }
		l.add(pts, a.mejora ? TONO.exito : TONO.peligro, 0.95, 1.5);
	}
	for (const ln of s.lineas ?? []) {
		const pts = ln.puntos.flatMap(([c, v]) => [X(c), Y(v)]);
		if (pts.length < 4) continue;
		if (ln.punteada) {
			for (let i = 2; i < pts.length; i += 2) l.add(punteado(pts[i - 2], pts[i - 1], pts[i], pts[i + 1], 4), ln.tono, ln.alfa, 1.2);
		} else l.add(linea(pts, Math.round(s.w * 0.5), ln.grosor ?? 0.8), ln.tono, ln.alfa, 1.3);
	}
	// Futuro: arena suelta, pero precisa: cada trayectoria cae en su mes, sin salirse de la columna.
	for (const fu of s.futuros ?? []) {
		const c0 = fu.desde ?? s.hoy;
		for (const [m, d] of fu.granos) {
			const x0 = X(c0 + m), y0 = Y(d / 10);
			for (let k = 0; k < 3; k++) l.add([x0 + (Math.random() - 0.5) * cw * 1.05, y0 + (Math.random() - 0.5) * 3], fu.tono, fu.alfa, 1.55);
		}
		if (fu.mediana) {
			const ini = s.pasado.filter((q) => q[1] !== null && q[0] === c0).at(-1)?.[1] ?? fu.mediana[0] / 10;
			const pts = [X(c0), Y(ini), ...fu.mediana.flatMap((d, i) => [X(c0 + i + 1), Y(d / 10)])];
			l.add(linea(pts, Math.round(s.w * 0.7), 0.9), fu.tono, Math.min(1, fu.alfa + 0.4), 1.45);
		}
	}
	for (const [c, v] of s.marcas ?? []) l.add(anillo(X(c), Y(v), 6.5, 42, 0.9), TONO.info, 1, 1.5);
}

function flota(l: Lote, f: PlacaFlota) {
	l.add(punteado(f.x, f.y + f.h, f.x + f.w, f.y + f.h, 2.4), TONO.apagado, 0.8, 1.2);
	l.add(punteado(f.x, f.y, f.x, f.y + f.h, 2.4), TONO.apagado, 0.8, 1.2);
	for (const g of f.rejillaX) l.add(punteado(f.x + g.u * f.w, f.y, f.x + g.u * f.w, f.y + f.h, g.fuerte ? 5 : 9), TONO.filete, g.fuerte ? 0.95 : 0.55, 1.15);
	for (const g of f.rejillaY) l.add(punteado(f.x, f.y + g.u * f.h, f.x + f.w, f.y + g.u * f.h, g.fuerte ? 4 : 9), g.fuerte ? TONO.apagado : TONO.filete, g.fuerte ? 0.7 : 0.55, 1.15);
	for (const q of f.puntos) l.add(disco(f.x + q.x * f.w, f.y + q.y * f.h, q.r, Math.round(10 + q.r * q.r * 2.2)), q.tono, q.alfa ?? 1, 1.6);
}

function rosa(l: Lote, r: PlacaRosa) {
	const { cx, cy } = r;
	l.add(anillo(cx, cy, r.r, Math.round(r.r * 5), 1), TONO.tinta, 0.5, 1.2);
	l.add(anillo(cx, cy, r.r * 0.72, Math.round(r.r * 3), 0.8), TONO.filete, 0.8, 1.1);
	const diagonal: ('solida' | 'tuerce' | 'hunde' | 'mejora')[] = ['solida', 'tuerce', 'hunde', 'mejora'];
	const total = r.zonas ? Math.max(1, r.zonas.solida + r.zonas.mejora + r.zonas.tuerce + r.zonas.hunde) : 0;
	for (let k = 0; k < 8; k++) {
		const a = (k / 8) * Math.PI * 2 - Math.PI / 2;
		const zona = k % 2 ? diagonal[(k - 1) / 2] : null;
		const cuota = zona && r.zonas ? r.zonas[zona] / total : null;
		const largo = k % 2 === 0 ? r.r * 1.18 : cuota !== null ? r.r * (0.3 + 1.25 * Math.sqrt(cuota)) : r.r * 0.62;
		const ancho = k % 2 === 0 ? r.r * 0.16 : r.r * (cuota !== null ? 0.08 + 0.1 * Math.sqrt(cuota) : 0.1);
		const n = Math.round(largo * (k % 2 === 0 ? 9 : 6));
		// Con el monitor, el norte deja de ser la aguja: la aguja va aparte y apunta a los datos.
		const tono = k === 0 && r.aguja === undefined ? TONO.info : zona === 'hunde' ? TONO.peligro : TONO.tinta;
		for (let i = 0; i < n; i++) {
			const u = Math.random(), lado = Math.random() < 0.5 ? -1 : 1;
			const w = (1 - u) * ancho * Math.random();
			const x = cx + Math.cos(a) * largo * u + Math.cos(a + Math.PI / 2) * w * lado;
			const y = cy + Math.sin(a) * largo * u + Math.sin(a + Math.PI / 2) * w * lado;
			l.add([x, y], tono, (lado > 0 ? 0.95 : 0.45) * (k % 2 === 0 && r.aguja !== undefined ? 0.55 : 1), 1.35);
		}
	}
	if (r.aguja !== undefined) {
		const a = r.aguja - Math.PI / 2;
		const largo = r.r * 1.05, n = Math.round(largo * 7);
		for (let i = 0; i < n; i++) {
			const u = Math.random(), lado = Math.random() < 0.5 ? -1 : 1, w = (1 - u) * r.r * 0.07 * Math.random();
			l.add([cx + Math.cos(a) * largo * u + Math.cos(a + Math.PI / 2) * w * lado, cy + Math.sin(a) * largo * u + Math.sin(a + Math.PI / 2) * w * lado], TONO.info, 1, 1.45);
		}
	}
	l.add(disco(cx, cy, r.r * 0.06, 20), TONO.tinta, 1, 1.4);
}

function vista(l: Lote, p: PlacaVista) {
	disponer(p.datos, p.w, p.h).dibujar((x, y, t, a, s) => l.add([x, y], t, a, s), p.x, p.y);
}

/** Puntos sueltos que se añaden a la escena de una página (la regla, fija arriba). */
export interface Extra { p: Puntos; tono: number[]; alfa: number[]; talla: number[] }

/**
 * Compone la escena de una página. Los granos que sobran reposan en la franja de abajo, invisibles.
 * `ancho`/`alto`: tamaño de la ventana, para el reposo.
 */
export function escenaPlacas(placas: Placa[], n: number, ancho: number, alto: number, movil: boolean, extra?: Extra): Escena {
	const e = escenaVacia(n);
	const l = new Lote();
	if (extra) { l.actual = 1; for (let i = 0; i < extra.tono.length; i++) l.add([extra.p[i * 2], extra.p[i * 2 + 1]], extra.tono[i], extra.alfa[i], extra.talla[i]); }
	for (const p of placas) {
		l.actual = p.fijo ? 1 : 0;
		if (p.tipo === 'numeral') numeral(l, p, movil);
		else if (p.tipo === 'serie') serie(l, p);
		else if (p.tipo === 'flota') flota(l, p);
		else if (p.tipo === 'rosa') rosa(l, p);
		else vista(l, p);
	}
	let pts = l.p, tonos = l.tono, alfas = l.alfa, tallas = l.talla, fijos = l.fijo;
	if (l.n > n) { pts = ajustar(l.p, n); tonos = tonos.slice(0, n); alfas = alfas.slice(0, n); tallas = tallas.slice(0, n); fijos = fijos.slice(0, n); }
	const usados = Math.min(n, l.n);
	for (let i = 0; i < n; i++) {
		if (i < usados) {
			e.x[i] = pts[i * 2]; e.y[i] = pts[i * 2 + 1]; e.tono[i] = tonos[i]; e.alfa[i] = alfas[i]; e.talla[i] = tallas[i]; e.fijo[i] = fijos[i];
		} else {
			e.x[i] = Math.random() * ancho; e.y[i] = alto + 40 + Math.random() * 60; e.tono[i] = TONO.filete; e.alfa[i] = 0; e.talla[i] = 1; e.fijo[i] = 1;
		}
		e.espera[i] = i < usados ? Math.random() * 0.2 : 0;
	}
	e.turbulencia = 0.35;
	e.rigidez = 7.4;
	return e;
}
