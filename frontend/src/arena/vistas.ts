// Las siete formas del monitor, en arena (propuesta 08, §3). Cada entidad es dueña de K granos,
// siempre los mismos y en el mismo orden (por id): al cambiar de forma, de orden o de filtro, sus
// granos viajan de un sitio a otro y se ve de dónde viene cada una y adónde va. Las entidades que no
// se ven reposan, invisibles, debajo de la caja.
//
// `disponer` es puro: calcula dónde va cada entidad (las anclas, que la página usa para rótulos y
// clics) y devuelve la función que dibuja los granos desplazados a la caja real.

import { TONO } from './arena';

export type FormaArena = 'ranking' | 'bandas' | 'plano' | 'tapiz' | 'flujo' | 'avisos' | 'horizonte';
export type BandaA = 'critical' | 'watch' | 'stable' | 'solid';

export interface EntArena {
	id: string;
	visible: boolean;
	/** Puesto en el orden elegido (0 = primero); −1 si no entra. */
	puesto: number;
	shown: number | null; // décimas
	prevShown: number | null;
	band: BandaA | null;
	prevBand: BandaA | null;
	ritmo: number | null;
	/** Últimos meses del score (décimas), alineados con `meses`. */
	serie: (number | null)[];
	bandas: (BandaA | null)[];
	p50: number | null; // décimas a seis meses
	pCritico: number | null;
	/** Avisos disparados en la ventana: [columna del mes, fila del tipo]. */
	avisos: [number, number][];
}

export interface DatosVista {
	forma: FormaArena;
	ents: EntArena[];
	/** Granos por entidad. */
	k: number;
	/** Número de columnas de meses (tapiz y avisos). */
	meses: number;
	/** Filas del calendario de avisos (tipos presentes). */
	tipos: { tono: 'baja' | 'sube' | 'neutro' }[];
	/** Filas visibles en ranking y tapiz. */
	filas: number;
	movil?: boolean;
}

export interface Ancla { x: number; y: number; r: number }
export interface Disposicion {
	anclas: Map<string, Ancla>;
	/** Geometría que la página necesita para sus rótulos. */
	guias: Record<string, number>;
	dibujar(add: (x: number, y: number, tono: number, alfa: number, talla: number) => void, ox: number, oy: number): void;
}

const ORDEN_BANDAS: BandaA[] = ['critical', 'watch', 'stable', 'solid'];
const rango = (b: BandaA | null) => (b ? ORDEN_BANDAS.indexOf(b) : -1);
const azar = (a: number) => (Math.random() - 0.5) * a;
/** Semilla estable por entidad, para que dos entidades no repitan el mismo dibujo de granos. */
const semilla = (id: string) => { let s = 0; for (let i = 0; i < id.length; i++) s = (s * 31 + id.charCodeAt(i)) >>> 0; return (s % 997) / 997; };
/** Punto i de la secuencia R2: reparte los granos por un hueco sin grumos ni calvas. */
const r2 = (i: number, s: number): [number, number] => [(s + i * 0.7548776662466927) % 1, (0.5 + s * 0.37 + i * 0.5698402909980532) % 1];
const suave = (u: number) => u * u * (3 - 2 * u);

/** Márgenes de cada forma (los rótulos HTML van ahí). */
export const MARGEN: Record<FormaArena, { i: number; d: number; a: number; b: number }> = {
	ranking: { i: 128, d: 90, a: 4, b: 26 },
	bandas: { i: 12, d: 12, a: 8, b: 46 },
	plano: { i: 44, d: 16, a: 12, b: 30 },
	tapiz: { i: 128, d: 12, a: 4, b: 46 },
	flujo: { i: 130, d: 130, a: 20, b: 24 },
	avisos: { i: 150, d: 12, a: 8, b: 26 },
	horizonte: { i: 130, d: 170, a: 20, b: 24 },
};

/** En el móvil los rótulos se reducen y los márgenes también. */
export const MARGEN_MOVIL: Record<FormaArena, { i: number; d: number; a: number; b: number }> = {
	ranking: { i: 84, d: 40, a: 4, b: 26 },
	bandas: { i: 6, d: 6, a: 6, b: 46 },
	plano: { i: 30, d: 8, a: 10, b: 26 },
	tapiz: { i: 74, d: 6, a: 4, b: 42 },
	flujo: { i: 78, d: 78, a: 18, b: 22 },
	avisos: { i: 96, d: 6, a: 6, b: 22 },
	horizonte: { i: 78, d: 96, a: 18, b: 22 },
};
export const margen = (forma: FormaArena, movil = false) => (movil ? MARGEN_MOVIL : MARGEN)[forma];

export function disponer(v: DatosVista, w: number, h: number): Disposicion {
	const m = margen(v.forma, v.movil);
	const X0 = m.i, X1 = Math.max(m.i + 40, w - m.d), Y0 = m.a, Y1 = Math.max(m.a + 40, h - m.b);
	const anclas = new Map<string, Ancla>();
	const guias: Record<string, number> = { x0: X0, x1: X1, y0: Y0, y1: Y1 };
	// Cada entidad pinta sus K granos con una función; las que no, reposan.
	const pintores = new Map<string, (add: Add) => void>();
	type Add = (x: number, y: number, tono: number, alfa: number, talla: number) => void;
	const k = v.k;
	const disco = (cx: number, cy: number, r: number, tono: number, alfa: number, talla = 1.5) => (add: Add) => {
		// Girasol: los granos cubren el disco de forma pareja, sin grumos ni calvas.
		for (let i = 0; i < k; i++) { const a = i * 2.399963, d = Math.sqrt((i + 0.5) / k) * r; add(cx + Math.cos(a) * d, cy + Math.sin(a) * d, tono, alfa, talla); }
	};

	/**
	 * Aluvial de dos columnas: a cada lado, un bloque por banda con alto proporcional a cuántas hay; entre
	 * medias, una cinta por entidad del mismo grosor, de su hueco de la izquierda al de la derecha. Cada
	 * entidad llena su hueco con sus K granos, así que el área de cada bloque y de cada cinta es el recuento.
	 */
	const aluvial = (lista: EntArena[], de: (e: EntArena) => BandaA, a: (e: EntArena) => BandaA, valorDe: (e: EntArena) => number, valorA: (e: EntArena) => number) => {
		const arriba = [...ORDEN_BANDAS].reverse();
		const pos = (b: BandaA) => arriba.indexOf(b);
		const hueco = 12, bw = 16;
		const u = (Y1 - Y0 - hueco * 3) / Math.max(1, lista.length);
		const lugar = (banda: (e: EntArena) => BandaA, otra: (e: EntArena) => BandaA, valor: (e: EntArena) => number, pref: string) => {
			const y = new Map<string, number>();
			let y0 = Y0;
			for (const b of arriba) {
				const miembros = lista.filter((e) => banda(e) === b).sort((p, q) => pos(otra(p)) - pos(otra(q)) || valor(q) - valor(p));
				miembros.forEach((e, i) => y.set(e.id, y0 + i * u));
				guias[`${pref}_${b}`] = y0 + (miembros.length * u) / 2;
				guias[`${pref}n_${b}`] = miembros.length;
				y0 += miembros.length * u + hueco;
			}
			return y;
		};
		const yi = lugar(de, a, valorDe, 'i'), yd = lugar(a, de, valorA, 'd');
		const xa = X0 + bw, xb = X1 - bw;
		guias.xm = (xa + xb) / 2; guias.bw = bw;
		// Los bloques se llevan una parte fija de los granos: son montones, más densos que las cintas.
		const enBloque = Math.max(2, Math.round(k * 0.15));
		for (const e of lista) {
			const ya = yi.get(e.id)!, yb = yd.get(e.id)!;
			const cambia = de(e) !== a(e);
			const baja = pos(a(e)) > pos(de(e));
			const s = semilla(e.id);
			guias[`fin:${e.id}`] = yb + u / 2;
			anclas.set(e.id, cambia ? { x: (xa + xb) / 2, y: (ya + yb) / 2 + u / 2, r: Math.max(3, u / 2) } : { x: xb, y: yb + u / 2, r: Math.max(3, u / 2) });
			pintores.set(e.id, (add) => {
				for (let i = 0; i < k; i++) {
					const [p, q] = r2(i, s);
					if (i < enBloque * 2) {
						const izq = i < enBloque;
						add((izq ? X0 : xb) + p * bw, (izq ? ya : yb) + q * u, TONO.tinta, 0.85, 1.5);
					} else {
						// Un poco de azar para que la secuencia no dibuje un rayado.
						const y = ya + (yb - ya) * suave(p) + q * u + azar(0.8);
						add(xa + p * (xb - xa) + azar(3), y, cambia ? (baja ? TONO.peligro : TONO.exito) : TONO.apagado, cambia ? 0.9 : 0.22, cambia ? 1.6 : 1.4);
					}
				}
			});
		}
	};

	switch (v.forma) {
		case 'ranking': {
			const alto = (Y1 - Y0) / Math.max(1, v.filas);
			guias.fila = alto;
			const X = (d: number) => X0 + Math.max(0, Math.min(1, d / 1000)) * (X1 - X0);
			const rPunto = Math.max(2.5, Math.min(4.5, alto * 0.24));
			for (const e of v.ents) {
				if (!e.visible || e.puesto < 0 || e.puesto >= v.filas || e.shown === null) continue;
				const y = Y0 + (e.puesto + 0.5) * alto;
				anclas.set(e.id, { x: X(e.shown), y, r: alto / 2 });
				const s = e.shown, p = e.prevShown ?? s;
				// Un punto macizo en el score de hoy, un tallo tenue desde el cero y el cambio del mes como tramo
				// aparte: en rojo hacia donde estaba si ha bajado, en verde desde donde estaba si ha subido.
				const cambio = Math.abs(s - p) >= 10;
				// El tramo del cambio lleva granos según su largo, para que se vea igual de denso sea corto o largo.
				const nTallo = Math.round(k * 0.16), nCambio = cambio ? Math.round(Math.min(k * 0.45, Math.max(10, Math.abs(X(s) - X(p)) / 2.5))) : 0, nPunto = k - nTallo - nCambio;
				pintores.set(e.id, (add) => {
					const xs = X(s), xp = X(p), fin = cambio && p < s ? xp : xs;
					for (let i = 0; i < nTallo; i++) add(X0 + ((i + 0.5) / nTallo) * (fin - X0), y, TONO.apagado, 0.45, 1.2);
					for (let i = 0; i < nCambio; i++) add(xs + ((i + 0.5) / nCambio) * (xp - xs), y + azar(1.2), s < p ? TONO.peligro : TONO.exito, 0.9, 1.7);
					for (let i = 0; i < nPunto; i++) { const a = i * 2.399963, d = Math.sqrt((i + 0.5) / nPunto) * rPunto; add(xs + Math.cos(a) * d, y + Math.sin(a) * d, TONO.tinta, 0.95, 1.5); }
				});
			}
			break;
		}
		case 'bandas': {
			const colW = (X1 - X0) / 4;
			const grupos = ORDEN_BANDAS.map((b) => v.ents.filter((e) => e.visible && e.band === b));
			const maxN = Math.max(1, ...grupos.map((g) => g.length));
			// Celda para que el montón más grande quepa en la altura.
			let celda = 30;
			for (; celda > 4; celda -= 0.5) { const porFila = Math.max(1, Math.floor((colW - 16) / celda)); if (Math.ceil(maxN / porFila) * celda <= Y1 - Y0) break; }
			guias.celda = celda;
			grupos.forEach((lista, bi) => {
				// Las que entran este mes, arriba del montón.
				const orden = [...lista].sort((a, b) => Number(a.prevBand !== a.band) - Number(b.prevBand !== b.band) || (a.shown ?? 0) - (b.shown ?? 0));
				const porFila = Math.max(1, Math.floor((colW - 16) / celda));
				const cx0 = X0 + bi * colW + (colW - porFila * celda) / 2;
				orden.forEach((e, i) => {
					const fila = Math.floor(i / porFila), col = i % porFila;
					// El montón crece desde abajo y se apila hacia el centro (una duna, no un muro).
					const cx = cx0 + (col + 0.5) * celda, cy = Y1 - (fila + 0.5) * celda;
					const entra = !!e.prevBand && e.prevBand !== e.band;
					anclas.set(e.id, { x: cx, y: cy, r: celda / 2 });
					// La banda la dice el montón; el color solo marca a las que acaban de entrar: rojo si bajan, verde si suben.
					pintores.set(e.id, disco(cx, cy, celda * 0.4, entra ? (rango(e.band) < rango(e.prevBand) ? TONO.peligro : TONO.exito) : TONO.tinta, entra ? 1 : 0.8, celda > 8 ? 1.5 : 1.3));
				});
			});
			guias.colW = colW;
			break;
		}
		case 'plano': {
			const X = (d: number) => X0 + Math.max(0, Math.min(1, d / 1000)) * (X1 - X0);
			const Y = (r: number) => (Y0 + Y1) / 2 - Math.max(-1, Math.min(1, r / 5)) * (Y1 - Y0) / 2;
			guias.xCorte = X(600); guias.yCero = Y(0);
			const rr = k >= 60 ? 5.5 : 2.8;
			for (const e of v.ents) {
				if (!e.visible || e.shown === null) continue;
				const x = X(e.shown), y = Y(e.ritmo ?? 0);
				anclas.set(e.id, { x, y, r: rr + 2 });
				// La banda la dice la posición; el color, solo el cambio de banda de este mes.
				const cambia = !!e.prevBand && !!e.band && e.prevBand !== e.band;
				const tono = cambia ? (rango(e.band) < rango(e.prevBand) ? TONO.peligro : TONO.exito) : TONO.tinta;
				// Si el ritmo se sale de la escala, el punto va al borde y hueco: un anillo avisa de que está recortado.
				if (Math.abs(e.ritmo ?? 0) > 5) pintores.set(e.id, (add) => { for (let i = 0; i < k; i++) { const a = (i / k) * Math.PI * 2; add(x + Math.cos(a) * rr, y + Math.sin(a) * rr, tono, 0.9, 1.3); } });
				else pintores.set(e.id, disco(x, y, rr, tono, 0.85));
			}
			break;
		}
		case 'tapiz': {
			const alto = (Y1 - Y0) / Math.max(1, v.filas), ancho = (X1 - X0) / Math.max(1, v.meses);
			guias.fila = alto; guias.col = ancho;
			// Cada fila es la trayectoria del score (0 a 100 dentro de la fila), una línea de arena; el tramo de un mes
			// en crítico, en rojo. Los meses sin dato quedan en blanco.
			const Ys = (base: number, d: number) => base - 1 - Math.max(0, Math.min(1, d / 1000)) * (alto - 3);
			for (const e of v.ents) {
				if (!e.visible || e.puesto < 0 || e.puesto >= v.filas) continue;
				const base = Y0 + (e.puesto + 1) * alto;
				const hay = e.serie.map((s) => s !== null);
				// Tramos entre meses consecutivos con dato; un mes aislado, un punto.
				const tramos: [number, number][] = [];
				e.serie.forEach((s, c) => { if (s === null) return; if (hay[c + 1]) tramos.push([c, c + 1]); else if (!hay[c - 1]) tramos.push([c, c]); });
				if (!tramos.length) continue;
				anclas.set(e.id, { x: X1 - ancho / 2, y: base - alto / 2, r: alto / 2 });
				pintores.set(e.id, (add) => {
					for (let i = 0; i < k; i++) {
						const pos = ((i + 0.5) / k) * tramos.length, j = Math.min(tramos.length - 1, Math.floor(pos)), u = pos - j;
						const [c0, c1] = tramos[j];
						const d = e.serie[c0]! + (e.serie[c1]! - e.serie[c0]!) * u;
						const c = u < 0.5 ? c0 : c1;
						add(X0 + (c0 + 0.5 + (c1 - c0) * u) * ancho, Ys(base, d) + azar(0.6), e.bandas[c] === 'critical' ? TONO.peligro : TONO.tinta, 0.9, 1.6);
					}
				});
			}
			break;
		}
		case 'flujo': {
			// De la banda del mes pasado (izquierda) a la de este (derecha). Lo mejor, arriba.
			const lista = v.ents.filter((e) => e.visible && e.band && e.prevBand);
			aluvial(lista, (e) => e.prevBand!, (e) => e.band!, (e) => e.prevShown ?? 0, (e) => e.shown ?? 0);
			break;
		}
		case 'avisos': {
			const filas = Math.max(1, v.tipos.length), cols = Math.max(1, v.meses);
			const cw = (X1 - X0) / cols, ch = (Y1 - Y0) / filas;
			guias.col = cw; guias.fila = ch;
			const cuenta = new Map<string, number>();
			for (const e of v.ents) if (e.visible) for (const [c, f] of e.avisos) cuenta.set(`${c}:${f}`, (cuenta.get(`${c}:${f}`) ?? 0) + 1);
			const maxC = Math.max(1, ...cuenta.values());
			const radio = (c: number, f: number) => (Math.min(cw, ch) / 2 - 2) * Math.sqrt((cuenta.get(`${c}:${f}`) ?? 0) / maxC);
			for (const e of v.ents) {
				if (!e.visible || !e.avisos.length) continue;
				const [c0, f0] = e.avisos[e.avisos.length - 1];
				anclas.set(e.id, { x: X0 + (c0 + 0.5) * cw, y: Y0 + (f0 + 0.5) * ch, r: 6 });
				pintores.set(e.id, (add) => {
					for (let i = 0; i < k; i++) {
						const [c, f] = e.avisos[i % e.avisos.length];
						const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * radio(c, f);
						const tono = v.tipos[f].tono === 'baja' ? TONO.peligro : v.tipos[f].tono === 'sube' ? TONO.exito : TONO.apagado;
						add(X0 + (c + 0.5) * cw + Math.cos(a) * d, Y0 + (f + 0.5) * ch + Math.sin(a) * d, tono, 0.8, 1.4);
					}
				});
			}
			break;
		}
		case 'horizonte': {
			// De la banda de hoy (izquierda) a la de la mediana dentro de seis meses (derecha), si nada cambia.
			const bandaDe = (d: number): BandaA => (d >= 800 ? 'solid' : d >= 600 ? 'stable' : d >= 400 ? 'watch' : 'critical');
			const lista = v.ents.filter((e) => e.visible && e.band && e.shown !== null && e.p50 !== null);
			aluvial(lista, (e) => e.band!, (e) => bandaDe(e.p50!), (e) => e.shown!, (e) => e.p50!);
			break;
		}
	}

	return {
		anclas, guias,
		dibujar(add, ox, oy) {
			const reposo = (add2: Add) => { for (let i = 0; i < k; i++) add2(w / 2 + azar(w), h + 60 + Math.random() * 40, TONO.filete, 0, 1); };
			const off: Add = (x, y, t, a, s) => add(x + ox, y + oy, t, a, s);
			// Siempre en el orden de v.ents (por id) y siempre K granos por entidad.
			for (const e of v.ents) (pintores.get(e.id) ?? reposo)(off);
		},
	};
}
