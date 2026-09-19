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
const tonoBanda = (b: BandaA | null) => (b === 'critical' ? TONO.peligro : TONO.tinta);
const rango = (b: BandaA | null) => (b ? ORDEN_BANDAS.indexOf(b) : -1);
const azar = (a: number) => (Math.random() - 0.5) * a;

/** Márgenes de cada forma (los rótulos HTML van ahí). */
export const MARGEN: Record<FormaArena, { i: number; d: number; a: number; b: number }> = {
	ranking: { i: 128, d: 90, a: 4, b: 26 },
	bandas: { i: 12, d: 12, a: 8, b: 46 },
	plano: { i: 44, d: 16, a: 12, b: 30 },
	tapiz: { i: 128, d: 12, a: 4, b: 46 },
	flujo: { i: 130, d: 130, a: 10, b: 10 },
	avisos: { i: 150, d: 12, a: 8, b: 26 },
	horizonte: { i: 70, d: 150, a: 16, b: 26 },
};

/** En el móvil los rótulos se reducen y los márgenes también. */
export const MARGEN_MOVIL: Record<FormaArena, { i: number; d: number; a: number; b: number }> = {
	ranking: { i: 84, d: 40, a: 4, b: 26 },
	bandas: { i: 6, d: 6, a: 6, b: 46 },
	plano: { i: 30, d: 8, a: 10, b: 26 },
	tapiz: { i: 74, d: 6, a: 4, b: 42 },
	flujo: { i: 78, d: 78, a: 8, b: 8 },
	avisos: { i: 96, d: 6, a: 6, b: 22 },
	horizonte: { i: 34, d: 96, a: 14, b: 24 },
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
		for (let i = 0; i < k; i++) { const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * r; add(cx + Math.cos(a) * d, cy + Math.sin(a) * d, tono, alfa, talla); }
	};

	switch (v.forma) {
		case 'ranking': {
			const alto = (Y1 - Y0) / Math.max(1, v.filas);
			guias.fila = alto;
			const X = (d: number) => X0 + Math.max(0, Math.min(1, d / 1000)) * (X1 - X0);
			for (const e of v.ents) {
				if (!e.visible || e.puesto < 0 || e.puesto >= v.filas || e.shown === null) continue;
				const y = Y0 + (e.puesto + 0.5) * alto;
				anclas.set(e.id, { x: X(e.shown), y, r: alto / 2 });
				const s = e.shown, p = e.prevShown ?? s;
				pintores.set(e.id, (add) => {
					// La barra hasta lo que se conserva, en tinta; lo que se pierde este mes, suelto en rojo; lo que se gana, en verde.
					const firme = Math.min(s, p), largoF = X(firme) - X0, largoC = Math.abs(X(s) - X(p));
					const nC = Math.round((k * largoC) / Math.max(1, largoF + largoC));
					const tono = tonoBanda(e.band);
					for (let i = 0; i < k; i++) {
						const enCambio = i < nC;
						const x = enCambio ? X(firme) + Math.random() * largoC : X0 + Math.random() * largoF;
						const t = enCambio ? (s < p ? TONO.peligro : TONO.exito) : tono;
						add(x, y + azar(alto * 0.3), t, enCambio ? (s < p ? 0.6 : 0.95) : 0.9, 1.9);
					}
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
					pintores.set(e.id, disco(cx, cy, celda * 0.42, entra ? (rango(e.band) < rango(e.prevBand) ? TONO.peligro : TONO.exito) : tonoBanda(e.band), entra ? 1 : 0.5, celda > 8 ? 1.5 : 1.3));
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
				pintores.set(e.id, disco(x, y, rr, tonoBanda(e.band), 0.85));
			}
			break;
		}
		case 'tapiz': {
			const alto = (Y1 - Y0) / Math.max(1, v.filas), ancho = (X1 - X0) / Math.max(1, v.meses);
			guias.fila = alto; guias.col = ancho;
			for (const e of v.ents) {
				if (!e.visible || e.puesto < 0 || e.puesto >= v.filas) continue;
				const y = Y0 + (e.puesto + 0.5) * alto;
				const celdas = e.serie.map((s, i) => [i, s] as const).filter(([, s]) => s !== null);
				if (!celdas.length) continue;
				anclas.set(e.id, { x: X1 - ancho / 2, y, r: alto / 2 });
				pintores.set(e.id, (add) => {
					for (let i = 0; i < k; i++) {
						const [c, s] = celdas[i % celdas.length];
						// Tinta densa, score alto; el mes en crítico, en rojo.
						add(X0 + (c + Math.random()) * ancho, y + azar(alto * 0.8), e.bandas[c] === 'critical' ? TONO.peligro : TONO.tinta, 0.28 + 0.72 * Math.max(0, Math.min(1, (s! / 10 - 20) / 70)), 2);
					}
				});
			}
			break;
		}
		case 'flujo': {
			// Dos columnas: la banda del mes pasado (izquierda) y la de este (derecha). Lo mejor, arriba.
			const arriba = [...ORDEN_BANDAS].reverse();
			const vis = v.ents.filter((e) => e.visible && e.band && e.prevBand);
			const hueco = 10, util = Y1 - Y0 - hueco * 3;
			const bloques = (lado: 'prev' | 'now') => {
				const cuenta = arriba.map((b) => vis.filter((e) => (lado === 'prev' ? e.prevBand : e.band) === b).length);
				const total = Math.max(1, cuenta.reduce((a, b) => a + b, 0));
				let y = Y0;
				return arriba.map((b, i) => { const alto = (cuenta[i] / total) * util; const r = { b, y, alto, n: cuenta[i] }; y += alto + hueco; return r; });
			};
			const izq = bloques('prev'), der = bloques('now');
			const xa = X0, xb = X1, xm = (xa + xb) / 2;
			arriba.forEach((b, i) => { guias[`i_${b}`] = izq[i].y + izq[i].alto / 2; guias[`in_${b}`] = izq[i].n; guias[`d_${b}`] = der[i].y + der[i].alto / 2; guias[`dn_${b}`] = der[i].n; });
			// Posición de cada entidad dentro de su bloque: por score.
			const lugar = (lado: 'prev' | 'now') => {
				const bl = lado === 'prev' ? izq : der;
				const pos = new Map<string, number>();
				for (const blq of bl) {
					const l = vis.filter((e) => (lado === 'prev' ? e.prevBand : e.band) === blq.b).sort((a, b) => ((lado === 'prev' ? b.prevShown : b.shown) ?? 0) - ((lado === 'prev' ? a.prevShown : a.shown) ?? 0));
					l.forEach((e, i) => pos.set(e.id, blq.y + ((i + 0.5) / Math.max(1, l.length)) * blq.alto));
				}
				return pos;
			};
			const pi = lugar('prev'), pd = lugar('now');
			for (const e of vis) {
				const ya = pi.get(e.id)!, yb = pd.get(e.id)!;
				const cambia = e.band !== e.prevBand;
				const baja = rango(e.band) < rango(e.prevBand);
				anclas.set(e.id, { x: cambia ? xm : xb - 8, y: cambia ? (ya + yb) / 2 : yb, r: 5 });
				pintores.set(e.id, (add) => {
					for (let i = 0; i < k; i++) {
						const u = Math.random();
						if (!cambia) {
							// Las que no cambian: un hilo tenue y recto dentro de su banda.
							add(xa + u * (xb - xa), ya + (yb - ya) * u + azar(1.5), TONO.apagado, 0.16, 1.2);
						} else {
							// Curva en S del bloque de origen al de destino.
							const s = u * u * (3 - 2 * u);
							add(xa + u * (xb - xa), ya + (yb - ya) * s + azar(2.2), baja ? TONO.peligro : TONO.exito, 0.85, 1.5);
						}
					}
				});
			}
			guias.xm = xm;
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
			const Y = (d: number) => Y1 - Math.max(0, Math.min(1, d / 1000)) * (Y1 - Y0);
			for (const b of [400, 600, 800]) guias[`b${b}`] = Y(b);
			for (const e of v.ents) {
				if (!e.visible || e.shown === null || e.p50 === null) continue;
				const ya = Y(e.shown), yb = Y(e.p50);
				const riesgo = e.band !== 'critical' && (e.pCritico ?? 0) >= 0.5;
				const sube = e.p50 - e.shown >= 50, cae = e.shown - e.p50 >= 50;
				const tono = riesgo || cae ? TONO.peligro : sube ? TONO.exito : TONO.tinta;
				const alfa = riesgo ? 0.95 : sube || cae ? 0.55 : 0.07;
				anclas.set(e.id, { x: X1, y: yb, r: 5 });
				pintores.set(e.id, (add) => { for (let i = 0; i < k; i++) { const u = Math.random(); add(X0 + u * (X1 - X0), ya + (yb - ya) * u + azar(1.6), tono, alfa, 1.4); } });
			}
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
