// Geometría compartida por la arena (WebGL) y la capa HTML. Responsive: se recalcula con el tamaño
// del lienzo y con la altura real de la frase (que puede ocupar una, dos o tres líneas).
// El tiempo se mide en celdas de mes: la regla, el tapiz y el expediente usan las mismas, así que
// todo lo que pasa en un mes cae en la misma vertical, sea cual sea la escala.

export interface Caja { x: number; y: number; w: number; h: number }

export interface Marco {
	W: number;
	H: number;
	movil: boolean;
	estrecho: boolean;
	pad: number;
	/** Zona de datos: plano, tapiz o expediente. */
	zona: Caja;
	/** Eje del tiempo (celdas de mes): común a la regla, el tapiz y el expediente. */
	tiempo: { x: number; w: number; celda: number };
	regla: Caja;
	sedimento: Caja;
	/** Columna lateral del expediente en pantallas anchas; null en el resto. */
	lateral: Caja | null;
	/** Borde inferior medido de la cabecera HTML del expediente (título, frase, sellos y cifras). */
	expCab?: number;
}

export const N_MESES = 24;

/** Alto de la cabecera y de la regla, que va pegada debajo: el tiempo es del marco y lo gobierna todo. */
export const alturas = (W: number) => ({ barra: W < 700 ? 52 : 64, regla: W < 700 ? 54 : 60 });

export function marco(W: number, H: number, fraseAbajo: number, conLateral: boolean): Marco {
	const movil = W < 700;
	const estrecho = W < 1100;
	const pad = movil ? 16 : estrecho ? 28 : 44;
	const lateralW = conLateral && !estrecho ? Math.min(360, Math.round(W * 0.26)) : 0;
	const contenidoW = W - pad * 2 - (lateralW ? lateralW + 36 : 0);
	const A = alturas(W);
	const regla = { x: pad, y: A.barra, w: contenidoW, h: A.regla };
	const margen = movil ? 58 : 96; // hueco a la izquierda del tiempo: el reloj de arena
	const tiempoX = pad + margen;
	const tiempoW = contenidoW - margen - (movil ? 4 : 10);
	const tiempo = { x: tiempoX, w: tiempoW, celda: tiempoW / N_MESES };
	const arriba = fraseAbajo + (movil ? 16 : 26);
	const sedimento = { x: pad + (movil ? 30 : 48), y: H - (movil ? 30 : 36), w: contenidoW - (movil ? 30 : 48), h: 18 };
	const zona = { x: pad + (movil ? 30 : 48), y: arriba, w: contenidoW - (movil ? 30 : 48), h: Math.max(160, sedimento.y - 10 - arriba) };
	const lateral = lateralW ? { x: W - pad - lateralW, y: arriba - 4, w: lateralW, h: H - arriba - 16 } : null;
	return { W, H, movil, estrecho, pad, zona, tiempo, regla, sedimento, lateral };
}

/** Altura de la línea de la regla dentro de su caja. */
export const baseRegla = (m: Marco) => m.regla.y + (m.movil ? 22 : 24);

/** Borde izquierdo y centro de la celda de un mes. */
export const xCeldaMes = (m: Marco, k: number) => m.tiempo.x + k * m.tiempo.celda;
export const xMes = (m: Marco, k: number) => m.tiempo.x + (k + 0.5) * m.tiempo.celda;

/** Tramo horizontal de un periodo (lista de índices de mes). */
export function tramo(m: Marco, meses: number[]) {
	const x0 = xCeldaMes(m, meses[0]);
	const x1 = xCeldaMes(m, meses[meses.length - 1] + 1);
	return { x0, x1, xc: (x0 + x1) / 2, w: x1 - x0 };
}

// ─── El plano: score (puntos) en horizontal, ritmo (puntos/mes) en vertical ───
// Los dominios se ajustan a la cartera al cargarla (los datos reales se mueven mucho más que los sintéticos).
export let DOMINIO_SCORE: [number, number] = [15, 100];
export let DOMINIO_RITMO = 2.6;

/** Ajusta los ejes del plano: el suelo del score al percentil 2 y el ritmo al percentil 95 de |ritmo|. */
export function ajustarDominios(scores: number[], ritmos: number[]) {
	const q = (xs: number[], p: number) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))] : 0; };
	if (scores.length) DOMINIO_SCORE = [Math.max(0, Math.min(15, Math.floor((q(scores, 0.02) - 2) / 5) * 5)), 100];
	if (ritmos.length) DOMINIO_RITMO = Math.max(2.6, Math.ceil(q(ritmos.map(Math.abs), 0.95) * 2) / 2);
}

/** Marcas del eje del ritmo para el dominio actual. */
export function marcasRitmo(movil: boolean): number[] {
	const d = DOMINIO_RITMO;
	const base = movil ? [1, d >= 4 ? 4 : 2].filter((v) => v <= d) : [0.5, 1, 2, 4, 8].filter((v) => v <= d && (d < 6 || v >= 1));
	return [...base.map((v) => -v).reverse(), 0, ...base];
}

export const xScore = (m: Marco, puntos: number) => {
	const [a, b] = DOMINIO_SCORE;
	return m.zona.x + ((Math.max(a, Math.min(b, puntos)) - a) / (b - a)) * m.zona.w;
};
export const scoreEnX = (m: Marco, x: number) => DOMINIO_SCORE[0] + ((x - m.zona.x) / m.zona.w) * (DOMINIO_SCORE[1] - DOMINIO_SCORE[0]);

/** Escala raíz con signo: abre el centro, donde está casi toda la cartera. */
export const yRitmo = (m: Marco, p: number) => {
	const c = Math.max(-DOMINIO_RITMO, Math.min(DOMINIO_RITMO, p));
	const u = Math.sign(c) * Math.sqrt(Math.abs(c) / DOMINIO_RITMO);
	return m.zona.y + m.zona.h / 2 - u * (m.zona.h / 2 - 22);
};

/** Diseño del expediente dentro de la zona. La cabecera HTML se mide y la arena se coloca debajo. */
export function cajasExpediente(m: Marco) {
	const z = m.zona;
	const numH = m.movil ? 70 : Math.round(Math.min(132, Math.max(92, z.h * 0.2)));
	const numeral = { x: m.pad, y: z.y + (m.movil ? 42 : 50), w: m.movil ? 110 : 250, h: numH };
	const cabAbajo = Math.max(numeral.y + numH, m.expCab ?? 0);
	const trayY = cabAbajo + (m.movil ? 30 : 38);
	const empresasH = m.movil ? 26 : Math.max(30, Math.min(52, z.h * 0.08));
	const fondo = m.sedimento.y + m.sedimento.h;
	const resto = Math.max(120, fondo - trayY - empresasH - 20);
	// Si falta alto, cede la trayectoria: la partitura necesita al menos 22 px por pilar para leerse.
	const sepPart = m.movil ? 30 : 36;
	const tray = { x: m.tiempo.x, y: trayY, w: m.tiempo.w, h: Math.max(48, Math.min(resto * 0.36, resto - 5 * 22 - sepPart)) };
	const partY = tray.y + tray.h + sepPart;
	const partH = Math.max(5 * 22, fondo - empresasH - 12 - partY);
	return {
		numeral,
		tray,
		part: { x: m.tiempo.x, y: partY, w: m.tiempo.w, h: partH },
		fila: partH / 5,
		empresas: { x: m.tiempo.x, y: fondo - empresasH, w: m.tiempo.w, h: empresasH },
	};
}
