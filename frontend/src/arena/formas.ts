// Muestreadores de formas: convierten figuras (discos, líneas, texto, columnas) en listas de
// puntos donde se posan los granos. Todo devuelve arrays planos [x0, y0, x1, y1, …].

export type Puntos = number[];

const AUREO = Math.PI * (3 - Math.sqrt(5));

/** Disco relleno con la espiral de Vogel: densidad uniforme y aspecto de semilla de girasol. */
export function disco(cx: number, cy: number, r: number, n: number, fuera: Puntos = []): Puntos {
	for (let i = 0; i < n; i++) {
		const rr = r * Math.sqrt((i + 0.5) / n);
		const a = i * AUREO;
		fuera.push(cx + rr * Math.cos(a), cy + rr * Math.sin(a));
	}
	return fuera;
}

/** Anillo: los granos solo en la circunferencia (movimiento por confirmar). */
export function anillo(cx: number, cy: number, r: number, n: number, grosor = 1.1, fuera: Puntos = []): Puntos {
	for (let i = 0; i < n; i++) {
		const a = (i / n) * Math.PI * 2 + Math.random() * 0.2;
		const rr = r + (Math.random() - 0.5) * grosor;
		fuera.push(cx + rr * Math.cos(a), cy + rr * Math.sin(a));
	}
	return fuera;
}

/**
 * Polilínea muestreada por longitud de arco. `densidad(u)` (u ∈ [0,1] a lo largo del trazo)
 * permite estelas que se desvanecen. `grosor` separa los granos a ambos lados del trazo.
 */
export function linea(pts: Puntos, n: number, grosor = 1, densidad?: (u: number) => number, fuera: Puntos = []): Puntos {
	const m = pts.length / 2;
	if (m === 0 || n <= 0) return fuera;
	if (m === 1) {
		for (let i = 0; i < n; i++) fuera.push(pts[0] + (Math.random() - 0.5) * grosor, pts[1] + (Math.random() - 0.5) * grosor);
		return fuera;
	}
	const acum = [0];
	for (let i = 1; i < m; i++) acum.push(acum[i - 1] + Math.hypot(pts[i * 2] - pts[i * 2 - 2], pts[i * 2 + 1] - pts[i * 2 - 1]));
	const L = acum[m - 1] || 1;
	for (let i = 0; i < n; i++) {
		// Reparto uniforme con un poco de azar; con densidad, muestreo por rechazo invertido.
		let u = (i + Math.random()) / n;
		if (densidad) u = densidad(u);
		const s = u * L;
		let k = 1;
		while (k < m - 1 && acum[k] < s) k++;
		const s0 = acum[k - 1], s1 = acum[k];
		const f = s1 > s0 ? (s - s0) / (s1 - s0) : 0;
		const x0 = pts[k * 2 - 2], y0 = pts[k * 2 - 1], x1 = pts[k * 2], y1 = pts[k * 2 + 1];
		const dx = x1 - x0, dy = y1 - y0;
		const d = Math.hypot(dx, dy) || 1;
		const off = (Math.random() - 0.5) * grosor;
		fuera.push(x0 + dx * f - (dy / d) * off, y0 + dy * f + (dx / d) * off);
	}
	return fuera;
}

/** Rectángulo relleno al azar (columnas de la partitura, bloques del tapiz). */
export function rect(x: number, y: number, w: number, h: number, n: number, fuera: Puntos = []): Puntos {
	for (let i = 0; i < n; i++) fuera.push(x + Math.random() * w, y + Math.random() * h);
	return fuera;
}

/** Línea de puntos regulares (ejes y filetes hechos de arena). */
export function punteado(x0: number, y0: number, x1: number, y1: number, paso: number, fuera: Puntos = []): Puntos {
	const L = Math.hypot(x1 - x0, y1 - y0);
	const n = Math.max(1, Math.floor(L / paso));
	for (let i = 0; i <= n; i++) fuera.push(x0 + ((x1 - x0) * i) / n, y0 + ((y1 - y0) * i) / n);
	return fuera;
}

const lienzoTexto = document.createElement('canvas');
const ctxTexto = lienzoTexto.getContext('2d', { willReadFrequently: true })!;
const cacheTexto = new Map<string, Puntos>();

/**
 * Texto hecho de arena: se pinta en un canvas oculto y se muestrean los píxeles de tinta.
 * Devuelve puntos relativos a (0, 0) = esquina superior izquierda de la caja del texto.
 */
export function texto(cadena: string, cuerpo: number, peso = 700, paso = 2.2, familia = "'Inter Variable', Inter, system-ui"): { puntos: Puntos; ancho: number; alto: number } {
	const clave = `${cadena}|${cuerpo}|${peso}|${paso}|${familia}`;
	const fuente = `${peso} ${cuerpo}px ${familia}`;
	ctxTexto.font = fuente;
	const ancho = Math.ceil(ctxTexto.measureText(cadena).width) + 4;
	const alto = Math.ceil(cuerpo * 1.05);
	const cacheado = cacheTexto.get(clave);
	if (cacheado) return { puntos: cacheado, ancho, alto };
	lienzoTexto.width = ancho;
	lienzoTexto.height = alto;
	ctxTexto.font = fuente;
	ctxTexto.textBaseline = 'alphabetic';
	ctxTexto.fillStyle = '#000';
	ctxTexto.clearRect(0, 0, ancho, alto);
	ctxTexto.fillText(cadena, 2, cuerpo * 0.86);
	const img = ctxTexto.getImageData(0, 0, ancho, alto).data;
	const puntos: Puntos = [];
	for (let y = 0; y < alto; y += paso) {
		for (let x = 0; x < ancho; x += paso) {
			const jx = x + Math.random() * paso * 0.9, jy = y + Math.random() * paso * 0.9;
			const i = (Math.floor(jy) * ancho + Math.floor(jx)) * 4 + 3;
			if (img[i] > 110) puntos.push(jx, jy);
		}
	}
	cacheTexto.set(clave, puntos);
	return { puntos, ancho, alto };
}

/** Ajusta una lista de puntos a exactamente n (repite con temblor o submuestrea). */
export function ajustar(p: Puntos, n: number, temblor = 0.6): Puntos {
	const m = p.length / 2;
	if (m === n) return p;
	const fuera: Puntos = [];
	if (m === 0) { for (let i = 0; i < n; i++) fuera.push(0, 0); return fuera; }
	if (m > n) {
		const paso = m / n;
		for (let i = 0; i < n; i++) { const k = Math.floor(i * paso); fuera.push(p[k * 2], p[k * 2 + 1]); }
		return fuera;
	}
	for (let i = 0; i < n; i++) {
		const k = i % m;
		const extra = i >= m;
		fuera.push(p[k * 2] + (extra ? (Math.random() - 0.5) * temblor : 0), p[k * 2 + 1] + (extra ? (Math.random() - 0.5) * temblor : 0));
	}
	return fuera;
}

/** Índice de Hilbert en una rejilla de 2^orden: ordena puntos 2D conservando la cercanía. */
function hilbert(x: number, y: number, orden = 10): number {
	const n = 1 << orden;
	let d = 0;
	for (let s = n >> 1; s > 0; s >>= 1) {
		const rx = (x & s) > 0 ? 1 : 0;
		const ry = (y & s) > 0 ? 1 : 0;
		d += s * s * ((3 * rx) ^ ry);
		if (ry === 0) {
			if (rx === 1) { x = s - 1 - x; y = s - 1 - y; }
			const t = x; x = y; y = t;
		}
	}
	return d;
}

/**
 * Empareja granos con destinos del mismo tamaño siguiendo el orden de Hilbert de ambos:
 * cada grano va a un destino de su vecindad y el cambio de figura se lee como un flujo.
 * Devuelve, para cada grano (posición en `granos`), el índice del destino.
 */
export function emparejar(gx: ArrayLike<number>, gy: ArrayLike<number>, granos: number[], destinos: Puntos, ancho: number, alto: number): Int32Array {
	const escala = 1023 / Math.max(ancho, alto, 1);
	const clave = (x: number, y: number) => hilbert(Math.max(0, Math.min(1023, Math.round(x * escala))), Math.max(0, Math.min(1023, Math.round(y * escala))));
	const og = granos.map((g, i) => [clave(gx[g], gy[g]), i]).sort((a, b) => a[0] - b[0]);
	const nd = destinos.length / 2;
	const od: number[][] = [];
	for (let j = 0; j < nd; j++) od.push([clave(destinos[j * 2], destinos[j * 2 + 1]), j]);
	od.sort((a, b) => a[0] - b[0]);
	const asignado = new Int32Array(granos.length);
	for (let k = 0; k < og.length; k++) asignado[og[k][1]] = od[Math.min(k, nd - 1)][1];
	return asignado;
}
