// Los 7 productos, dibujados a mano como pequeños grabados (propuesta 06, §7).
//   · Trazo con contraste grueso y fino: el contorno se dibuja fino y otra vez más grueso,
//     desplazado hacia la sombra (abajo a la derecha), como una plumilla inclinada.
//   · La sombra es un punteado de granos (la arena de Rumbo), más denso hacia abajo a la derecha,
//     recortado a la silueta del objeto.
//   · Sin baldosa: la familia se reconoce por el color de la tinta y por un filete debajo
//     (dos rayas en protección, un arco en cobertura, de uno a tres granos en inversión).
//   · Tamaños ópticos: a 26 px o menos el dibujo pierde trama y detalle y engorda el trazo.
//   · Cuatro estados: tiene (tinta entera), encaja (contorno y granos que llegan), bloqueado
//     (contorno cruzado) y no consta (contorno casi invisible).
// Retícula de 48. Todo sale como texto SVG: sirve para la interfaz y para exportar ficheros.

import type { ProductoId } from '../datos/contrato';
import { PRODUCTOS } from '../datos/productos';

export type EstadoIcono = 'tiene' | 'encaja' | 'bloqueado' | 'no_consta';

interface Dibujo {
	/** Siluetas que reciben la sombra punteada (y el recorte). */
	cuerpo: string[];
	/** Contornos principales: llevan el grueso de la sombra. */
	contorno: string[];
	/** Detalles finos. Los marcados con «!» se conservan en tamaño pequeño. */
	detalle: string[];
	/** Rellenos de tinta plena (sellos, ojos). */
	lleno?: string[];
	/** Densidad de la sombra: 0 ligera, 1 cargada. */
	carga: number;
}

// Rueda dentada, trazada con arcos entre diente y diente (confirming).
function rueda(cx: number, cy: number, r: number, dientes: number, alto: number): string {
	const p = (a: number, rr: number) => `${(cx + Math.cos(a) * rr).toFixed(2)} ${(cy + Math.sin(a) * rr).toFixed(2)}`;
	const tramos: string[] = [];
	for (let i = 0; i < dientes; i++) {
		const t = (k: number) => ((i + k) / dientes) * Math.PI * 2;
		tramos.push(`${i === 0 ? 'M' : 'L'}${p(t(0), r)} L${p(t(0.12), r + alto)} L${p(t(0.42), r + alto)} L${p(t(0.54), r)} A${r} ${r} 0 0 1 ${p(t(1), r)}`);
	}
	return tramos.join(' ') + ' Z';
}

const DIBUJOS: Record<ProductoId, Dibujo> = {
	// Escudo de heráldica con el € grabado en el campo: la red de seguridad.
	linea_credito: {
		cuerpo: ['M24 4.5C30 7.8 35.6 8.6 40.5 8.4V21.6C40.5 31.4 33.6 38.8 24 43C14.4 38.8 7.5 31.4 7.5 21.6V8.4C12.4 8.6 18 7.8 24 4.5Z'],
		contorno: ['M24 4.5C30 7.8 35.6 8.6 40.5 8.4V21.6C40.5 31.4 33.6 38.8 24 43C14.4 38.8 7.5 31.4 7.5 21.6V8.4C12.4 8.6 18 7.8 24 4.5Z'],
		detalle: [
			'M24 8.2C28.8 10.7 33.2 11.5 37.2 11.5V21.6C37.2 29.6 31.6 35.6 24 39.2C16.4 35.6 10.8 29.6 10.8 21.6V11.5C14.8 11.5 19.2 10.7 24 8.2Z',
			'!M29.8 17.2C28.4 15.8 26.6 15 24.6 15C20.4 15 17.4 18.6 17.4 23.1C17.4 27.6 20.4 31.2 24.6 31.2C26.6 31.2 28.4 30.4 29.8 29',
			'!M15.2 21.2H26.4', '!M15.2 25.2H25.6',
		],
		carga: 0.9,
	},
	// Fajo de facturas atado con cordel que, por un lado, se abre en monedas apiladas.
	factoring: {
		cuerpo: [
			'M6.5 12.5H22.5L27.5 17.5V40.5H6.5Z',
			'M29.5 36.8C29.5 35.2 32.6 34 36.5 34C40.4 34 43.5 35.2 43.5 36.8V41.2C43.5 42.8 40.4 44 36.5 44C32.6 44 29.5 42.8 29.5 41.2Z',
		],
		contorno: [
			'M10.5 8.5H26.5L31.5 13.5V33',
			'M8.5 10.5H24.5L29.5 15.5V34.4',
			'M6.5 12.5H22.5L27.5 17.5V40.5H6.5Z',
			'M29.5 36.8C29.5 35.2 32.6 34 36.5 34C40.4 34 43.5 35.2 43.5 36.8V41.2C43.5 42.8 40.4 44 36.5 44C32.6 44 29.5 42.8 29.5 41.2Z',
			'M31.8 31.4C31.8 29.9 34.6 28.8 38 28.8C41.4 28.8 44.2 29.9 44.2 31.4V33.8',
			'M33.2 26.4C33.2 24.9 35.8 23.8 39 23.8C42.2 23.8 44.8 24.9 44.8 26.4C44.8 27.9 42.2 29 39 29C35.8 29 33.2 27.9 33.2 26.4Z',
		],
		detalle: [
			'M22.5 12.5V17.5H27.5',
			'!M10 22H21', '!M10 25.5H23', 'M10 29H19', 'M10 34.5H15',
			'!M17 12.6V40.4', 'M18.6 12.6V40.4',
			'M17.8 12.4C16.2 9.6 14 9.2 13.4 10.6C12.8 12 15.6 12.6 17.8 12.4C20 12.6 22.8 12 22.2 10.6C21.6 9.2 19.4 9.6 17.8 12.4',
			'M29.5 36.8C29.5 38.4 32.6 39.6 36.5 39.6C40.4 39.6 43.5 38.4 43.5 36.8',
			'M41.2 25.4C40.6 24.9 39.8 24.7 39 24.7C37.6 24.7 36.6 25.5 36.6 26.4C36.6 27.3 37.6 28.1 39 28.1C39.8 28.1 40.6 27.9 41.2 27.4', 'M35.6 26H38.8', 'M35.6 27H38.6',
		],
		carga: 0.85,
	},
	// Rueda dentada de reloj de bolsillo engranada con la esquina de un calendario de taco.
	confirming: {
		cuerpo: ['M20.5 7.5H42.5V33.5H20.5Z', rueda(16, 32, 8.6, 11, 2.4)],
		contorno: ['M20.5 7.5H42.5V33.5H20.5Z', rueda(16, 32, 8.6, 11, 2.4)],
		detalle: [
			'!M20.5 13.5H42.5', '!M25.5 5V10', '!M37.5 5V10',
			'M26 18.5H26.8', 'M30 18.5H30.8', 'M34 18.5H34.8', 'M38 18.5H38.8',
			'M26 23H26.8', 'M30 23H30.8', 'M34 23H34.8', 'M38 23H38.8',
			'M30 27.5H30.8', 'M38 27.5H38.8',
			'!M12.8 32a3.2 3.2 0 1 0 6.4 0a3.2 3.2 0 1 0-6.4 0',
			'M16 26.6V28.8', 'M16 35.2V37.4', 'M10.6 32H12.8', 'M19.2 32H21.4',
		],
		lleno: ['M32.6 27.5a1.8 1.8 0 1 0 3.6 0a1.8 1.8 0 1 0-3.6 0Z'],
		carga: 0.75,
	},
	// Paraguas abierto con varillas y tela sombreada sobre una cartera de cuero con facturas asomando.
	seguro_credito: {
		cuerpo: [
			'M5.5 21.5C7 12.5 14.8 6.5 24 6.5C33.2 6.5 41 12.5 42.5 21.5C40.4 19.6 37.2 19.6 35.2 21.5C33 19.6 29.4 19.6 27.4 21.5C25.4 19.6 22.6 19.6 20.6 21.5C18.6 19.6 15 19.6 12.8 21.5C10.8 19.6 7.6 19.6 5.5 21.5Z',
			'M11.5 31.5H36.5V43.5H11.5Z',
		],
		contorno: [
			'M5.5 21.5C7 12.5 14.8 6.5 24 6.5C33.2 6.5 41 12.5 42.5 21.5C40.4 19.6 37.2 19.6 35.2 21.5C33 19.6 29.4 19.6 27.4 21.5C25.4 19.6 22.6 19.6 20.6 21.5C18.6 19.6 15 19.6 12.8 21.5C10.8 19.6 7.6 19.6 5.5 21.5Z',
			'M11.5 31.5H36.5V43.5H11.5Z',
		],
		detalle: [
			'M24 6.5C21 10.5 20.4 16 20.6 21.5', 'M24 6.5C27 10.5 27.6 16 27.4 21.5', 'M24 6.5C16.4 10.2 13.4 15.4 12.8 21.5', 'M24 6.5C31.6 10.2 34.6 15.4 35.2 21.5',
			'!M24 4V6.5', '!M24 21V28.6C24 30.2 25.4 30.8 26.4 29.8',
			'!M20.5 31.5V29.2H27.5V31.5',
			'!M11.5 35.5H36.5', 'M22.6 35.5V38H25.4V35.5',
			'M15 31.5V26.5H21.5', 'M31 31.5V28H35.5',
		],
		carga: 0.8,
	},
	// Hucha de cerámica bajo una lluvia fina de monedas diminutas.
	cuenta_remunerada: {
		cuerpo: ['M9.5 29C9.5 21.6 16.2 16.5 25 16.5C33 16.5 39.5 21.2 39.8 27.6C39.9 31.6 37.8 34.4 34.5 36V40.5H30V37.6C27.2 38.2 22.8 38.2 20 37.6V40.5H15.5V35.8C11.6 34 9.5 31.8 9.5 29Z'],
		contorno: ['M9.5 29C9.5 21.6 16.2 16.5 25 16.5C33 16.5 39.5 21.2 39.8 27.6C39.9 31.6 37.8 34.4 34.5 36V40.5H30V37.6C27.2 38.2 22.8 38.2 20 37.6V40.5H15.5V35.8C11.6 34 9.5 31.8 9.5 29Z'],
		detalle: [
			'!M39.6 25.2H42.2C43.4 25.2 44.2 26.2 44.2 27.4C44.2 28.6 43.4 29.6 42.2 29.6H39.8',
			'!M31.4 17.4L33.6 12.8L35.8 18.6',
			'!M22 19.4H28.6',
			'M9.7 27C7.2 27.2 6.2 25.2 7.6 24.2C8.8 23.4 9.6 25 8.6 25.8',
			'!M24 7.5C24 6.7 24.7 6 25.4 6C26.1 6 26.8 6.7 26.8 7.5C26.8 8.3 26.1 9 25.4 9C24.7 9 24 8.3 24 7.5Z',
			'M17 5.2C17 4.6 17.5 4.2 18 4.2C18.5 4.2 19 4.6 19 5.2C19 5.8 18.5 6.2 18 6.2C17.5 6.2 17 5.8 17 5.2Z',
			'M31.5 4.6C31.5 4 32 3.6 32.5 3.6C33 3.6 33.5 4 33.5 4.6C33.5 5.2 33 5.6 32.5 5.6C32 5.6 31.5 5.2 31.5 4.6Z',
			'M25.4 10.6V12.2', 'M18 7.6V9', 'M32.5 7V8.4',
		],
		lleno: ['M34.6 22.4a1 1 0 1 0 2 0a1 1 0 1 0-2 0Z'],
		carga: 0.7,
	},
	// Cofre con sello de lacre y el reloj de arena de Rumbo en la tapa: capital con vencimiento.
	depositos: {
		cuerpo: ['M8.5 24.5C8.5 17.5 15.4 15 24 15C32.6 15 39.5 17.5 39.5 24.5V41.5H8.5Z'],
		contorno: ['M8.5 24.5C8.5 17.5 15.4 15 24 15C32.6 15 39.5 17.5 39.5 24.5V41.5H8.5Z'],
		detalle: [
			'!M8.5 24.5H39.5', 'M8.5 27H39.5',
			'M14.5 15.9V41.5', 'M33.5 15.9V41.5',
			'!M20.5 2.8H27.5', '!M20.5 12.6H27.5', '!M21.2 3C21.2 6.4 24 7 24 7.7C24 8.4 21.2 9 21.2 12.4', '!M26.8 3C26.8 6.4 24 7 24 7.7C24 8.4 26.8 9 26.8 12.4',
		],
		lleno: [
			'M24 29.6C25 29 26.4 29.4 26.8 30.4C27.8 30.8 28.2 32.2 27.6 33.2C28.2 34.2 27.8 35.6 26.8 36C26.4 37 25 37.4 24 36.8C23 37.4 21.6 37 21.2 36C20.2 35.6 19.8 34.2 20.4 33.2C19.8 32.2 20.2 30.8 21.2 30.4C21.6 29.4 23 29 24 29.6Z',
			'M22.2 10.8C22.8 10 25.2 10 25.8 10.8L26.2 12.2H21.8Z',
		],
		carga: 0.85,
	},
	// Árbol grabado con copas escalonadas y las raíces a la vista: composición a muy largo plazo.
	plan_pensiones: {
		cuerpo: [
			'M9 27.6C7 25.4 8.2 21.8 11.4 21.4C12 18.2 16 16.8 18.6 18.4C20.4 16.2 24.8 16 26.8 18C29.4 16.4 33.4 17.4 34.2 20.4C37.6 20.2 39.8 23.4 38.6 26.4C40.4 28.6 38.6 31.8 35.6 31.4C34 33.4 30.2 33.6 28.4 31.8C26.2 33.4 22.2 33.4 20 31.8C18 33.6 14 33.2 12.8 31C10.2 31.6 8 29.8 9 27.6Z',
			'M14.6 17.2C13.2 14.8 15 12 17.8 12.2C18.8 9.6 22.6 8.8 24.6 10.8C26.8 9 30.6 10 31.2 12.8C33.8 13 35 16 33.4 17.8Z',
			'M18.4 10.2C17.8 7.8 19.8 5.6 22.2 6C23.2 3.8 26.6 3.8 27.6 6C29.8 5.8 31.4 8 30.4 10Z',
			'M22.6 33L21.8 40.5H26.2L25.4 33Z',
		],
		contorno: [
			'M9 27.6C7 25.4 8.2 21.8 11.4 21.4C12 18.2 16 16.8 18.6 18.4C20.4 16.2 24.8 16 26.8 18C29.4 16.4 33.4 17.4 34.2 20.4C37.6 20.2 39.8 23.4 38.6 26.4C40.4 28.6 38.6 31.8 35.6 31.4C34 33.4 30.2 33.6 28.4 31.8C26.2 33.4 22.2 33.4 20 31.8C18 33.6 14 33.2 12.8 31C10.2 31.6 8 29.8 9 27.6Z',
			'M14.6 17.2C13.2 14.8 15 12 17.8 12.2C18.8 9.6 22.6 8.8 24.6 10.8C26.8 9 30.6 10 31.2 12.8C33.8 13 35 16 33.4 17.8',
			'M18.4 10.2C17.8 7.8 19.8 5.6 22.2 6C23.2 3.8 26.6 3.8 27.6 6C29.8 5.8 31.4 8 30.4 10',
			'M22.6 33L21.8 40.5M25.4 33L26.2 40.5',
		],
		detalle: [
			'!M8 40.5H40', 'M21.8 40.5C19.6 41.6 16.4 41.8 13.6 43.2', 'M26.2 40.5C28.4 41.6 31.6 41.8 34.4 43.2', 'M23.2 40.5C22.6 42 21.8 43.4 20.8 44.4', 'M24.8 40.5C25.4 42 26.2 43.4 27.2 44.4',
			'M24 33V28.4', 'M24 29.6L20.8 26.8', 'M24 28.6L27.4 25.8',
		],
		carga: 0.8,
	},
};

// PRNG determinista (mulberry32): el punteado de cada icono es siempre el mismo.
function azar(semilla: number) {
	let a = semilla >>> 0;
	return () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = Math.imul(a ^ (a >>> 15), 1 | a);
		t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
}

let contador = 0;

export interface OpcionesIcono {
	/** Lado en píxeles. */
	tam?: number;
	estado?: EstadoIcono;
	/** Título accesible. */
	titulo?: boolean;
	/** Sin el filete de familia debajo. */
	sinFilete?: boolean;
}

/** El icono de un producto como texto SVG. */
export function svgProducto(id: ProductoId, o: OpcionesIcono = {}): string {
	const p = PRODUCTOS.find((x) => x.id === id)!;
	const d = DIBUJOS[id];
	const tam = o.tam ?? 48;
	const estado = o.estado ?? 'tiene';
	const pequeno = tam <= 26;
	const uid = `gr${++contador}`;
	const tinta = estado === 'no_consta' ? '#c9cad3' : estado === 'bloqueado' ? '#9a9cab' : p.color;
	const fino = pequeno ? 1.7 : 1.05;
	const grueso = pequeno ? 2.3 : 1.8;
	const conGrano = estado === 'tiene' || estado === 'encaja';

	// Punteado: rejilla con temblor, más densa hacia abajo a la derecha (la luz viene de arriba a la izquierda).
	let granos = '';
	if (conGrano) {
		const r = azar(id.split('').reduce((s, c) => (s * 31 + c.charCodeAt(0)) >>> 0, 7));
		const paso = pequeno ? 2.6 : 1.25;
		const radio = pequeno ? 0.7 : 0.36;
		for (let y = 2; y < 46; y += paso) {
			for (let x = 2; x < 46; x += paso) {
				const jx = x + (r() - 0.5) * paso * 0.9, jy = y + (r() - 0.5) * paso * 0.9;
				const luz = (jx * 0.9 + jy * 1.1) / 96;
				const dens = Math.max(0, Math.min(1, (luz - 0.28) * 1.9)) * d.carga * (pequeno ? 0.5 : 1);
				const u = r(), v = r();
				if (u < dens) {
					const retraso = estado === 'encaja' ? ` style="animation-delay:${(120 + v * 900).toFixed(0)}ms"` : '';
					granos += `<circle class="grano" cx="${jx.toFixed(2)}" cy="${jy.toFixed(2)}" r="${(radio * (0.75 + v * 0.5)).toFixed(2)}"${retraso}/>`;
				}
			}
		}
	}

	const trazos = (lista: string[]) => lista.map((c) => `<path d="${c.replace(/^!/, '')}"/>`).join('');
	const cuerpo = trazos(d.cuerpo);
	const contorno = trazos(d.contorno);
	const detalle = trazos(pequeno ? d.detalle.filter((x) => x.startsWith('!')) : d.detalle);
	const lleno = trazos(d.lleno ?? []);

	// Filete de familia.
	let filete = '';
	if (!o.sinFilete) {
		const w = pequeno ? 1.4 : 0.85;
		if (p.familia === 'proteccion') filete = `<path d="M17 45.4H31M19.5 47.4H28.5" stroke="${tinta}" stroke-width="${w}" fill="none" stroke-linecap="round"/>`;
		else if (p.familia === 'cobertura') filete = `<path d="M16.5 47.4C20 44.6 28 44.6 31.5 47.4" stroke="${tinta}" stroke-width="${w}" fill="none" stroke-linecap="round"/>`;
		else for (let i = 0; i < 3; i++) filete += `<circle cx="${19 + i * 5}" cy="46.3" r="${pequeno ? 1.5 : 1.05}" fill="${i < (p.nivel ?? 0) ? tinta : 'none'}" stroke="${tinta}" stroke-width="${pequeno ? 1 : 0.65}"/>`;
	}
	const tachado = estado === 'bloqueado' ? `<path d="M9 41.5L39.5 6.5" stroke="#6e707c" stroke-width="${pequeno ? 1.6 : 1}" stroke-linecap="round"/>` : '';
	const alto = o.sinFilete ? 45 : 48;

	return `<svg xmlns="http://www.w3.org/2000/svg" width="${tam}" height="${Math.round((tam * alto) / 48)}" viewBox="0 0 48 ${alto}" role="img" aria-label="${p.nombre}" class="grabado estado-${estado}">`
		+ (o.titulo === false ? '' : `<title>${p.nombre}</title>`)
		+ `<defs><clipPath id="${uid}c">${cuerpo}</clipPath>`
		+ `<linearGradient id="${uid}g" x1="0" y1="0" x2="1" y2="1"><stop offset="0.45" stop-color="#fff" stop-opacity="0"/><stop offset="0.62" stop-color="#fff" stop-opacity="1"/></linearGradient>`
		+ `<mask id="${uid}m" maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48"><rect width="48" height="48" fill="url(#${uid}g)"/></mask></defs>`
		+ (granos ? `<g clip-path="url(#${uid}c)" fill="${tinta}">${granos}</g>` : '')
		+ `<g fill="none" stroke="${tinta}" stroke-linecap="round" stroke-linejoin="round">`
		+ (estado === 'tiene' ? `<g stroke-width="${grueso}" mask="url(#${uid}m)" transform="translate(0.35 0.4)">${contorno}</g>` : '')
		+ `<g stroke-width="${fino}">${contorno}</g>`
		+ `<g stroke-width="${pequeno ? fino * 0.85 : fino * 0.72}">${detalle}</g>`
		+ `</g>`
		+ (lleno ? `<g fill="${tinta}">${lleno}</g>` : '')
		+ filete + tachado + `</svg>`;
}

/** El mismo icono como elemento DOM. */
export function iconoProducto(id: ProductoId, o: OpcionesIcono = {}): SVGSVGElement {
	const t = document.createElement('template');
	t.innerHTML = svgProducto(id, o).trim();
	const el = t.content.firstElementChild as SVGSVGElement;
	el.classList.add('icono-producto');
	return el;
}
