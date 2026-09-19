// La marca de Rumbo: el monograma y el logotipo, trazo único de contraste cero.
//
// El monograma destila «rum» en un solo recorrido: el hombro de la r convertido en arco grande
// (unas 2,4 veces la altura de los pequeños, con la cima desplazada hacia la subida), el valle de
// la u y los dos arcos de la m como coda. El arranque es un gancho corto bajo la línea base (el
// ancla) y la salida, un golpe corto hacia la derecha (el avance). Inclinado 6° hacia delante.
// El logotipo «rumbo» usa el mismo módulo de arco; la o es la única forma cerrada.
//
// El trazo se dibuja como esqueleto y se engruesa con stroke: así el peso se ajusta de una vez.
// Por debajo de 20 px, el monograma pierde el segundo arco pequeño (si no, se empasta).

const NS = 'http://www.w3.org/2000/svg';

/** Esqueleto del monograma. Base y=86, arcos pequeños 51,6–86, arco grande 4,4–86. */
export const MONOGRAMA = [
	'M8.4 90.2 C10 92.4 12.8 91.6 13 86', // gancho: la pluma aterriza y gira
	'C13.6 50 16.4 5 31 4.4', // subida casi vertical; la cima queda del lado de la subida
	'C46 3.8 55 30 57.4 66', // bajada, más larga y empinada
	'C58.4 80.6 61.6 87.4 67 87.4', // valle (rebasa un poco la base)
	'C72.8 87.4 76 80.6 76 68 L76 62', // lado derecho de la u, que es la primera asta de la m
	'C76 55.4 80.6 51.6 86 51.6 C91.8 51.6 96 55.6 96 62.6 L96 86', // primer arco
	'M96 62.6 C96 55.6 100.4 51.6 106 51.6 C111.8 51.6 116 55.6 116 62.6 L116 84', // segundo arco
	'C116 87.4 118 88.6 121.4 87.6', // salida corta hacia la derecha
].join(' ');
/** Para tamaños diminutos: un solo arco pequeño. */
export const MONOGRAMA_SIMPLE = [
	'M8.4 90.2 C10 92.4 12.8 91.6 13 86', 'C13.6 50 16.4 5 31 4.4', 'C46 3.8 55 30 57.4 66', 'C58.4 80.6 61.6 87.4 67 87.4',
	'C72.8 87.4 76 80.6 76 68 L76 62', 'C76 55.4 80.6 51.6 86 51.6 C91.8 51.6 96 55.6 96 62.6 L96 84', 'C96 87.4 98 88.6 101.4 87.6',
].join(' ');
const CAJA_MONO = { x: -2, y: -4, w: 130, h: 102 };

/** Esqueleto del logotipo «rumbo». Base y=100, altura de la x 50, ascendente 14. */
export const LOGOTIPO = [
	'M4 100 L4 62 C4 55 9 50 15.6 50 C19.6 50 22.6 51.4 25 54', // r
	'M38 50 L38 84 C38 94.6 43.6 100.4 51 100.4 C58.4 100.4 64 94.6 64 84 L64 50 M64 50 L64 100', // u
	'M78 100 L78 62 C78 55 83 50 89 50 C95.2 50 100 55 100 62 L100 100 M100 62 C100 55 105 50 111 50 C117.2 50 122 55 122 62 L122 100', // m
	'M136 14 L136 100 M136 70 C136 57.4 143 50 151.6 50 C161.4 50 167.4 60 167.4 75 C167.4 90.6 160.6 100.4 151.4 100.4 C148.6 100.4 146.2 99.6 144.4 98.4', // b, con la panza abierta
	'M196.6 50 C206.6 50 212.6 60.6 212.6 75.2 C212.6 89.8 206.6 100.4 196.6 100.4 C186.6 100.4 180.6 89.8 180.6 75.2 C180.6 60.6 186.6 50 196.6 50 Z', // o, la única cerrada
].join(' ');
const CAJA_LOGO = { x: -2, y: 10, w: 222, h: 96 };

/** Inclinación del trazo (grados, hacia delante). */
const INCLINA = 6;
const TAN = Math.tan((INCLINA * Math.PI) / 180);

/** Grosor del trazo según el tamaño final: más fino en grande, con corrección óptica en pequeño. */
function grosor(alto: number, base: number) {
	return alto >= 100 ? base : alto >= 40 ? base * 1.08 : alto >= 24 ? base * 1.25 : base * 1.45;
}

function dibujo(d: string, caja: typeof CAJA_MONO, alto: number, trazo: number, clase: string, titulo?: string): SVGSVGElement {
	const s = document.createElementNS(NS, 'svg');
	s.setAttribute('viewBox', `${caja.x} ${caja.y} ${caja.w} ${caja.h}`);
	s.setAttribute('height', String(alto));
	s.setAttribute('width', String(Math.round((alto * caja.w) / caja.h)));
	s.setAttribute('class', clase);
	if (titulo) { s.setAttribute('role', 'img'); s.setAttribute('aria-label', titulo); } else s.setAttribute('aria-hidden', 'true');
	const g = document.createElementNS(NS, 'g');
	// La inclinación gira alrededor de la base para que el pie no se desplace.
	g.setAttribute('transform', `translate(${(86 * TAN).toFixed(2)} 0) skewX(${-INCLINA})`);
	const p = document.createElementNS(NS, 'path');
	p.setAttribute('d', d);
	p.setAttribute('fill', 'none');
	p.setAttribute('stroke', 'currentColor');
	p.setAttribute('stroke-width', String(trazo));
	p.setAttribute('stroke-linecap', 'round');
	p.setAttribute('stroke-linejoin', 'round');
	g.append(p);
	s.append(g);
	return s;
}

export function monograma(alto: number, titulo?: string): SVGSVGElement {
	return dibujo(alto < 20 ? MONOGRAMA_SIMPLE : MONOGRAMA, CAJA_MONO, alto, grosor(alto, 6.2), 'monograma', titulo);
}

export function logotipo(alto: number, titulo = 'rumbo'): SVGSVGElement {
	return dibujo(LOGOTIPO, CAJA_LOGO, alto, grosor(alto, 6.2), 'logotipo', titulo);
}

// ─── El monograma hecho de arena ─────────────────────────────

let medidor: SVGPathElement | null = null;
function trazoMedible(d: string): SVGPathElement {
	if (!medidor) {
		const s = document.createElementNS(NS, 'svg');
		s.setAttribute('aria-hidden', 'true');
		s.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden;visibility:hidden';
		medidor = document.createElementNS(NS, 'path');
		s.append(medidor);
		document.body.append(s);
	}
	medidor.setAttribute('d', d);
	return medidor;
}

/**
 * Granos repartidos dentro del trazo del monograma, en coordenadas de pantalla: esquina superior
 * izquierda (x, y) y alto en píxeles. Cada grano lleva su sombra (0 en el borde claro, 1 en el
 * oscuro) para grabarlo como los iconos: un lado del trazo más denso que el otro.
 */
export function granosMonograma(x: number, y: number, alto: number, densidad = 0.8, trazo = 6.6): { pts: number[]; sombra: number[]; grosor: number } {
	const k = alto / CAJA_MONO.h;
	const ancho = trazo * k;
	const pts: number[] = [], sombra: number[] = [];
	for (const tramo of MONOGRAMA.split(/(?=M)/)) {
		const p = trazoMedible(tramo);
		const largo = p.getTotalLength();
		const n = Math.round(largo * k * ancho * densidad);
		for (let i = 0; i < n; i++) {
			const s = Math.random() * largo;
			const a = p.getPointAtLength(s), b = p.getPointAtLength(Math.min(largo, s + 0.5));
			const dx = b.x - a.x, dy = b.y - a.y, l = Math.hypot(dx, dy) || 1;
			const u = Math.random() - 0.5; // a lo ancho del trazo
			const px = a.x + (-dy / l) * u * trazo, py = a.y + (dx / l) * u * trazo;
			// Inclinación alrededor de la base, igual que en el SVG.
			const sx = px + (86 - py) * TAN;
			pts.push(x + (sx - CAJA_MONO.x) * k, y + (py - CAJA_MONO.y) * k);
			sombra.push(u + 0.5);
		}
	}
	return { pts, sombra, grosor: ancho };
}

/**
 * El monograma pequeño de la cabecera, en arena: granos que caen y se posan en el trazo al
 * aparecer, y que se apartan un poco al pasar el puntero. Lienzo 2D propio (no ocupa la arena
 * grande, que se recorta a la página).
 */
export function monogramaArena(alto: number): HTMLCanvasElement {
	const ancho = Math.round((alto * CAJA_MONO.w) / CAJA_MONO.h);
	const dpr = Math.min(3, devicePixelRatio || 1);
	const c = document.createElement('canvas');
	c.width = Math.round((ancho + 8) * dpr); c.height = Math.round((alto + 8) * dpr);
	c.style.width = `${ancho + 8}px`; c.style.height = `${alto + 8}px`;
	c.className = 'monograma-arena';
	c.setAttribute('aria-hidden', 'true');
	const x = c.getContext('2d')!;
	const reducido = matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('captura');
	let g: ReturnType<typeof granosMonograma> | null = null;
	let px: Float32Array, py: Float32Array, vx: Float32Array, vy: Float32Array, espera: Float32Array;
	let raf = 0, t0 = 0, puntero: { x: number; y: number } | null = null;

	function preparar() {
		// En pequeño, trazo algo más grueso (corrección óptica) y muy denso: si no, se deshace.
		g = granosMonograma(4, 4, alto, 3.2, 8.4);
		const n = g.pts.length / 2;
		px = new Float32Array(n); py = new Float32Array(n); vx = new Float32Array(n); vy = new Float32Array(n); espera = new Float32Array(n);
		for (let i = 0; i < n; i++) {
			px[i] = g.pts[i * 2] + (Math.random() - 0.5) * 6;
			py[i] = reducido ? g.pts[i * 2 + 1] : -Math.random() * alto * 0.8;
			// Cae antes lo de la izquierda: el trazo se escribe en el orden de la pluma.
			espera[i] = reducido ? 0 : (g.pts[i * 2] / ancho) * 0.5 + Math.random() * 0.25;
			if (reducido) px[i] = g.pts[i * 2];
		}
	}
	function pintar() {
		x.setTransform(dpr, 0, 0, dpr, 0, 0);
		x.clearRect(0, 0, ancho + 8, alto + 8);
		const n = px.length;
		const color = getComputedStyle(c).color || '#050b2c';
		x.fillStyle = color;
		for (let i = 0; i < n; i++) {
			x.globalAlpha = 0.5 + 0.5 * g!.sombra[i];
			x.fillRect(px[i] - 0.4, py[i] - 0.4, 0.8, 0.8);
		}
		x.globalAlpha = 1;
	}
	function paso(t: number) {
		if (!t0) t0 = t;
		const tt = (t - t0) / 1000;
		const dt = 1 / 60;
		let energia = 0;
		for (let i = 0; i < px.length; i++) {
			if (tt < espera[i]) continue;
			let ax = (g!.pts[i * 2] - px[i]) * 90, ay = (g!.pts[i * 2 + 1] - py[i]) * 90;
			if (puntero) {
				const dx = px[i] - puntero.x, dy = py[i] - puntero.y, d = Math.hypot(dx, dy);
				if (d < 7 && d > 0.01) { ax += (dx / d) * (7 - d) * 260; ay += (dy / d) * (7 - d) * 260; }
			}
			vx[i] = (vx[i] + ax * dt) * 0.8; vy[i] = (vy[i] + ay * dt) * 0.8;
			px[i] += vx[i] * dt; py[i] += vy[i] * dt;
			energia += Math.abs(vx[i]) + Math.abs(vy[i]) + (tt < espera[i] ? 1 : 0);
		}
		pintar();
		if (energia / px.length > 0.02 || puntero || tt < 1.4) raf = requestAnimationFrame(paso);
		else raf = 0;
	}
	function arrancar() { if (!raf && !reducido) { t0 = 0; raf = requestAnimationFrame(paso); } }
	// Con setTimeout y no con rAF: el lienzo ya está en la página y se pinta aunque no haya fotogramas.
	setTimeout(() => {
		preparar();
		pintar();
		arrancar();
	});
	if (!reducido) {
		c.addEventListener('pointermove', (ev) => { const r = c.getBoundingClientRect(); puntero = { x: ev.clientX - r.left, y: ev.clientY - r.top }; arrancar(); });
		c.addEventListener('pointerleave', () => { puntero = null; arrancar(); });
	}
	return c;
}

/** Una línea de granos (el horizonte de arena bajo la cabecera), como imagen de fondo. */
export function lineaGranos(ancho = 640, alto = 7): string {
	const dpr = 2;
	const c = document.createElement('canvas');
	c.width = ancho * dpr; c.height = alto * dpr;
	const x = c.getContext('2d')!;
	x.scale(dpr, dpr);
	x.fillStyle = '#050b2c';
	for (let i = 0; i < ancho * 1.6; i++) {
		const px = Math.random() * ancho;
		// Más densa en el centro del grosor, como una raya trazada con arena.
		const py = alto / 2 + (Math.random() + Math.random() + Math.random() - 1.5) * 1.5;
		x.globalAlpha = 0.1 + Math.random() * 0.28;
		x.fillRect(px, py, 0.9, 0.9);
	}
	return c.toDataURL();
}
