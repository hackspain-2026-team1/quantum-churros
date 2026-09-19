// Placas de arena para las páginas de Rumbo (entrada, organización, empresa). La página HTML deja
// huecos marcados y aquí se dibuja la arena encima, en coordenadas de página (la arena sigue al
// desplazamiento con arena.desplazar). Cuatro piezas:
//   · numeral: el score acuñado en arena;
//   · serie: una línea de tiempo que cruza el presente, con la estela asentada (lo observado) y el
//     futuro como arena suelta (cada grano es una de las simulaciones de los horizontes);
//   · flota: las empresas de un grupo en un plano pequeño (score y ritmo);
//   · rosa: la rosa de los vientos de Rumbo, el objeto de la portada. En el monitor, sus puntas
//     diagonales son las cuatro zonas del plano (su largo, cuántas hay en cada una) y la aguja
//     azul apunta hacia donde va la cartera;
//   · vista: una de las siete formas del monitor (arena/vistas.ts).

import { escenaVacia, TONO, type Escena } from './arena';
import { ajustar, anillo, disco, linea, punteado, texto, type Puntos } from './formas';
import { SERIF } from './escenas';
import { disponer, type DatosVista } from './vistas';

export interface PlacaNumeral { tipo: 'numeral'; x: number; y: number; h: number; texto: string; tono?: number }
export interface Futuro {
	/** Pares [mes 1..12, décimas] de las trayectorias simuladas. */
	granos: [number, number][];
	tono: number;
	alfa: number;
	/** Mediana mes a mes (décimas), dibujada como hilo. */
	mediana?: number[];
	/**
	 * 0 = definido (el escenario elegido: granos apretados); 1 = suelto (las alternativas: más
	 * dispersos y más finos). Cada simulación tiene siempre el mismo número de granos, así que al
	 * elegir otro escenario la arena se reorganiza: unos se aprietan y otros se sueltan.
	 */
	suelto?: number;
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
export interface PlacaRosa {
	tipo: 'rosa'; cx: number; cy: number; r: number;
	/** Cuántas entidades hay en cada zona del plano (sólidas NE, se tuercen SE, se hunden SO, mejoran NO). */
	zonas?: { solida: number; mejora: number; tuerce: number; hunde: number };
	/** Ángulo de la aguja en radianes (0 = norte, en sentido horario). */
	aguja?: number;
}
export interface PlacaVista { tipo: 'vista'; x: number; y: number; w: number; h: number; datos: DatosVista }
export type Placa = PlacaNumeral | PlacaSerie | PlacaFlota | PlacaRosa | PlacaVista;

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
	// Futuro: arena suelta. Cada grano de la simulación son cuatro granos de arena.
	for (const fu of s.futuros ?? []) {
		const su = fu.suelto ?? 0;
		const jx = cw * (0.9 + su * 1.4), jy = 3 + su * 11, talla = 1.6 - su * 0.25;
		for (const [m, d] of fu.granos) {
			const x0 = X(s.hoy + m), y0 = Y(d / 10);
			for (let k = 0; k < 4; k++) l.add([x0 + (Math.random() - 0.5) * jx, y0 + (Math.random() - 0.5) * jy], fu.tono, fu.alfa, talla);
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
	// Las puntas diagonales, en el orden de las agujas del reloj desde el nordeste.
	const diagonal: ('solida' | 'tuerce' | 'hunde' | 'mejora')[] = ['solida', 'tuerce', 'hunde', 'mejora'];
	const total = r.zonas ? Math.max(1, r.zonas.solida + r.zonas.mejora + r.zonas.tuerce + r.zonas.hunde) : 0;
	// Cuatro puntas largas y cuatro cortas, rellenas de arena (más densas en la mitad de sombra).
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

/**
 * Compone la escena de una página. Los granos que sobran reposan en la franja de abajo, invisibles.
 * `ancho`/`alto`: tamaño de la ventana, para el reposo.
 */
export function escenaPlacas(placas: Placa[], n: number, ancho: number, alto: number, movil: boolean): Escena {
	const e = escenaVacia(n);
	const l = new Lote();
	// La vista del monitor va primero: así sus granos conservan siempre el mismo número y cada
	// entidad viaja con los suyos al cambiar de forma, aunque cambie el resto de la página.
	for (const p of placas) if (p.tipo === 'vista') vista(l, p);
	for (const p of placas) {
		if (p.tipo === 'vista') continue;
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
