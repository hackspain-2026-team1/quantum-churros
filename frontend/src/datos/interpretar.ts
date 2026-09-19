// «Dile qué quieres ver»: de una frase a una vista del monitor. Dos capas:
//   1. palabras clave, al instante y sin red (también es la reserva si Jev no responde);
//   2. Jev, a través del Worker rumbo-vista, que elige entre los mismos vocabularios cerrados y
//      devuelve probabilidades. Aquí se decide con ellas qué se aplica, qué se pregunta y qué no.
// Las cifras (un número de grupo o de empresa) las resuelve siempre el código.

import type { ProductoId } from './contrato';
import { PAISES, type Zona } from './consulta';
import { ESTADO_INICIAL, type EstadoMonitor, type FiltrosM, type Forma, type Modo, type MovM, type OrdenM, type Unidad } from './monitorCartera';
import type { Banda } from './modelo';

/** Dirección del Worker (se fija al construir; vacía = sin Jev). */
export const URL_VISTA: string = import.meta.env.VITE_VISTA_URL || '';

export type Campo = 'forma' | 'modo' | 'unidad' | 'orden' | 'banda' | 'mov' | 'zona' | 'sector' | 'pais' | 'tamano' | 'producto';

export interface Duda { campo: Campo; opciones: { valor: string; p: number }[] }

export interface Interpretacion {
	/** Abrir una entidad concreta en vez de cambiar la vista. */
	abrir?: { kind: 'group' | 'company'; numero: number };
	estado: EstadoMonitor;
	/** Campos que ha fijado la frase (el resto, por defecto). */
	fijados: Campo[];
	dudas: Duda[];
	fuente: 'palabras' | 'jev';
	ms?: number;
	/** Probabilidad de que la frase tenga que ver con la cartera (solo con Jev). */
	relevante?: number;
}

const normal = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/\s+/g, ' ').trim();

// ─── 1. Palabras clave ───────────────────────────────────────

const FORMAS_PAL: [RegExp, Forma][] = [
	[/\b(ranking|clasificacion|lista|listado|top|peores|mejores|prioridad)\b/, 'ranking'],
	[/\b(flujo|que ha cambiado|han cambiado|cambios de banda|entre bandas|transiciones|movimientos)\b/, 'flujo'],
	[/\b(bandas?|montones|por banda|distribucion)\b/, 'bandas'],
	[/\b(plano|mapa|cuadrantes?|nivel y ritmo)\b/, 'plano'],
	[/\b(tapiz|historia|mes a mes|evolucion|historico)\b/, 'tapiz'],
	[/\b(flujo|que ha cambiado|han cambiado|cambios de banda|transiciones|movimientos)\b/, 'flujo'],
	[/\b(?<!con |mas )(avisos|alertas|notificaciones)\b/, 'avisos'],
	[/\b(horizonte|futuro|prevision|previsto|seis meses|6 meses|dentro de|como estaran|donde estaran)\b/, 'horizonte'],
];
const MOVS_PAL: [RegExp, MovM][] = [
	[/\b(entran?|nuevas?|acaban de entrar) en critic/, 'entra_critico'],
	[/\bbajan? de banda\b/, 'baja_banda'],
	[/\bsuben? de banda\b/, 'sube_banda'],
	[/\b(hacia critic|van a critic|riesgo de (ser |estar |pasar a )?critic|en riesgo)/, 'hacia_critico'],
	[/\bdeterioro/, 'deterioro'],
	[/\bmejora confirmada|mejoras? estructural/, 'mejora'],
	[/\b(golpe|por confirmar|shock)\b/, 'por_confirmar'],
	[/\b(sin actualizar|datos del banco|sin datos|desactualizad)/, 'sin_datos'],
	[/\bcon (avisos|alertas)\b/, 'avisos'],
	[/\b(caen|empeoran|bajan|se desploman|caida)\b/, 'cae'],
	[/\b(crecen|suben|remontan)\b/, 'crece'],
];
const ZONAS_PAL: [RegExp, Zona][] = [[/\bse hunden?\b|\bhunden\b/, 'hunde'], [/\bse tuercen?\b|\btuercen\b/, 'tuerce'], [/\bmejoran\b/, 'mejora']];
const BANDAS_PAL: [RegExp, Banda][] = [[/\bcritic(a|as|o|os)\b|\ben rojo\b/, 'critical'], [/\bvigilancia\b/, 'watch'], [/\bestables?\b/, 'stable'], [/\bsolid(a|as|o|os)\b|\bsanas\b/, 'solid']];
const ORDEN_PAL: [RegExp, OrdenM][] = [
	[/\b(por gravedad|mas urgentes?|por prioridad)\b/, 'gravedad'], [/\bpor (score|puntuacion|nota)\b/, 'score'],
	[/\b(por (el )?cambio|que mas (caen|bajan)|mas caen)\b/, 'cambio'], [/\b(tres meses|trimestre)\b/, 'cambio3'],
	[/\bpor (riesgo|probabilidad)\b/, 'horizonte'], [/\b(por avisos|mas avisos|mas alertas)\b/, 'avisos'], [/\b(por tamano|mas grandes)\b/, 'tamano'],
];
const SECTORES_PAL: [RegExp, string][] = [
	[/\benergi/, 'Energía y utilities'], [/\blogistic|cadena de suministro/, 'Logística y cadena de suministro'], [/\bmanufactur|industria|fabric/, 'Manufactura'],
	[/\bmarketing|publicidad/, 'Marketing y publicidad'], [/\bservicios empresariales/, 'Servicios empresariales'], [/\bfinancier/, 'Servicios financieros'],
	[/\bprofesionales/, 'Servicios profesionales'], [/\btecnolog/, 'Servicios tecnológicos'], [/\bsoftware/, 'Software'],
];
const GENTILICIOS: Record<string, string> = { espanol: 'ES', portugues: 'PT', frances: 'FR', aleman: 'DE', italian: 'IT', britanic: 'GB', ingles: 'GB', holandes: 'NL', neerlandes: 'NL', belga: 'BE', danes: 'DK', noruego: 'NO', estadounidense: 'US', americana: 'US', emirati: 'AE', andorran: 'AD', malasi: 'MY' };
const PRODUCTOS_PAL: [RegExp, ProductoId][] = [
	[/\blinea(s)? de credito|poliza/, 'linea_credito'], [/\bfactoring/, 'factoring'], [/\bconfirming/, 'confirming'], [/\bseguros? de credito/, 'seguro_credito'],
	[/\bcuentas? remunerada/, 'cuenta_remunerada'], [/\bdeposito|\bletras\b/, 'depositos'], [/\bplan(es)? de pensiones/, 'plan_pensiones'],
];

export function porPalabras(texto: string, actual: EstadoMonitor): Interpretacion {
	const t = normal(texto);
	const num = t.match(/^(?:(grupo|organizacion|org|empresa|filial)\s*)?(\d{1,4})$/);
	if (num) return { abrir: { kind: num[1] === 'empresa' || num[1] === 'filial' ? 'company' : 'group', numero: Number(num[2]) }, estado: actual, fijados: [], dudas: [], fuente: 'palabras' };
	const fl: FiltrosM = {};
	const fijados: Campo[] = [];
	const e: EstadoMonitor = { ...ESTADO_INICIAL, modo: actual.modo, filtros: fl };
	const primero = <T>(pares: [RegExp, T][]) => pares.find(([r]) => r.test(t))?.[1];
	const forma = primero(FORMAS_PAL); if (forma) { e.forma = forma; fijados.push('forma'); }
	if (/\b(tabla|tablas|numeros|fija|sin arena)\b/.test(t)) { e.modo = 'tabla'; fijados.push('modo'); }
	else if (/\b(arena|grafico|visual|dibujo)\b/.test(t)) { e.modo = 'arena'; fijados.push('modo'); }
	if (/\b(empresas|filiales|empresa|filial|sociedades)\b/.test(t)) { e.unidad = 'empresas'; fijados.push('unidad'); }
	else if (/\b(organizaciones|grupos)\b/.test(t)) { e.unidad = 'organizaciones'; fijados.push('unidad'); }
	const orden = primero(ORDEN_PAL); if (orden) { e.orden = orden; fijados.push('orden'); }
	const mov = primero(MOVS_PAL); if (mov) { fl.mov = mov; fijados.push('mov'); }
	const zona = primero(ZONAS_PAL); if (zona) { fl.zona = zona; fijados.push('zona'); if (fl.mov === 'cae' || fl.mov === 'crece') { delete fl.mov; fijados.splice(fijados.indexOf('mov'), 1); } }
	const banda = mov === 'entra_critico' || mov === 'hacia_critico' ? undefined : primero(BANDAS_PAL);
	if (banda) { fl.banda = banda; fijados.push('banda'); }
	const sector = primero(SECTORES_PAL); if (sector) { fl.sector = sector; fijados.push('sector'); }
	let pais = Object.entries(PAISES).find(([, n]) => t.includes(normal(n)))?.[0];
	if (!pais) pais = Object.entries(GENTILICIOS).find(([g]) => t.includes(g))?.[1];
	if (pais) { fl.pais = pais; fijados.push('pais'); }
	const tam = t.match(/\b(micro|pequenas?|medianas?|grandes)\b/)?.[1];
	if (tam && !/mas grandes/.test(t)) { fl.tamano = tam.startsWith('micro') ? 'Micro' : tam.startsWith('peque') ? 'Pequeña' : tam.startsWith('median') ? 'Mediana' : 'Grande'; fijados.push('tamano'); }
	const prod = primero(PRODUCTOS_PAL);
	if (prod) { fl.producto = { id: prod, modo: /\b(tienen|tiene|con |usan|contratad)/.test(t) && !/encaj|candidat|ofrecer|podria/.test(t) ? 'tiene' : 'encaja' }; fijados.push('producto'); }
	const fs = new Set(fijados);
	podar(e, fs);
	return { estado: e, fijados: [...fs], dudas: [], fuente: 'palabras' };
}

// ─── 2. Jev ──────────────────────────────────────────────────

interface Respuesta { type: 'choice' | 'noul'; choice?: string; probabilities?: Record<string, number>; confidence?: number; noul?: number }

/** Umbral de probabilidad para aplicar sin preguntar: los filtros piden más que la forma. */
const UMBRAL: Record<Campo, number> = { forma: 0.5, modo: 0.55, unidad: 0.85, orden: 0.6, banda: 0.7, mov: 0.7, zona: 0.75, sector: 0.9, pais: 0.8, tamano: 0.8, producto: 0.7 };
const NADA = new Set(['no_dice', 'ninguno', 'ninguna']);
const PREGUNTA: Record<Campo, string> = { forma: 'forma', modo: 'modo', unidad: 'unidad', orden: 'orden', banda: 'banda', mov: 'movimiento', zona: 'zona', sector: 'sector', pais: 'pais', tamano: 'tamano', producto: 'producto' };

export async function porJev(texto: string, vocab: { sectores: string[]; paises: string[] }, local: Interpretacion, senal?: AbortSignal): Promise<Interpretacion | null> {
	if (!URL_VISTA) return null;
	const t0 = performance.now();
	let datos: { respuestas: Record<string, Respuesta> };
	try {
		const r = await fetch(`${URL_VISTA.replace(/\/$/, '')}/vista`, {
			method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: senal,
			body: JSON.stringify({ texto, sectores: vocab.sectores, paises: Object.fromEntries(vocab.paises.map((c) => [c, PAISES[c] ?? c])) }),
		});
		if (!r.ok) return null;
		datos = await r.json();
	} catch { return null; }
	const R = datos.respuestas;
	const e: EstadoMonitor = { ...local.estado, filtros: { ...local.estado.filtros } };
	const fijados = new Set(local.fijados);
	const dudas: Duda[] = [];
	for (const campo of Object.keys(UMBRAL) as Campo[]) {
		const a = R[PREGUNTA[campo]];
		if (!a?.probabilities || !a.choice) continue;
		const orden = Object.entries(a.probabilities).sort((x, y) => y[1] - x[1]);
		const [v1, p1] = orden[0], [v2, p2] = orden[1] ?? ['', 0];
		if (NADA.has(v1)) continue; // Jev dice que no lo pide: queda lo que digan las palabras
		if (p1 >= UMBRAL[campo]) { aplicar(e, campo, v1, R); fijados.add(campo); continue; }
		// Dos opciones cerca y ninguna es «no lo dice»: se pregunta en vez de adivinar.
		if (p2 >= 0.25 && !NADA.has(v2) && !fijados.has(campo)) dudas.push({ campo, opciones: [{ valor: v1, p: p1 }, { valor: v2, p: p2 }] });
	}
	// Lo que dicen las palabras sobre si ya lo tienen manda: «tienen» es literal.
	if (local.estado.filtros.producto && e.filtros.producto?.id === local.estado.filtros.producto.id) e.filtros.producto = { ...local.estado.filtros.producto };
	podar(e, fijados);
	return { estado: e, fijados: [...fijados], dudas, fuente: 'jev', ms: Math.round(performance.now() - t0), relevante: R.relevante?.noul };
}

/** Quita piezas redundantes que solo estrechan la vista (una zona que repite la banda, un «cae» que repite el orden…). */
export function podar(e: EstadoMonitor, fijados: Set<Campo>) {
	const fl = e.filtros;
	const quita = (k: keyof FiltrosM, c: Campo) => { delete fl[k]; fijados.delete(c); };
	if (fl.mov === 'entra_critico') { if (fl.banda) quita('banda', 'banda'); if (fl.zona) quita('zona', 'zona'); }
	if (fl.mov === 'hacia_critico' && fl.banda === 'critical') quita('banda', 'banda');
	if (fl.banda && fl.zona && ((fl.banda === 'solid' && fl.zona === 'solida') || (fl.banda === 'critical' && fl.zona === 'hunde'))) quita('zona', 'zona');
	if (fl.zona === 'mejora' && (fl.mov === 'mejora' || fl.mov === 'crece')) quita('mov', 'mov');
	if (fl.zona && (fl.mov === 'cae' || fl.mov === 'crece')) quita('mov', 'mov');
	if ((e.orden === 'cambio' || e.orden === 'cambio3') && fl.mov === 'cae') quita('mov', 'mov');
}

export function aplicar(e: EstadoMonitor, campo: Campo, valor: string, R?: Record<string, Respuesta>) {
	const fl = e.filtros;
	switch (campo) {
		case 'forma': e.forma = valor as Forma; break;
		case 'modo': e.modo = valor as Modo; break;
		case 'unidad': e.unidad = valor as Unidad; break;
		case 'orden': e.orden = valor as OrdenM; break;
		case 'banda': fl.banda = valor as Banda; break;
		case 'mov': fl.mov = valor as MovM; break;
		case 'zona': fl.zona = valor as Zona; break;
		case 'sector': fl.sector = valor; break;
		case 'pais': fl.pais = valor; break;
		case 'tamano': fl.tamano = valor; break;
		case 'producto': {
			const modo = R?.producto_modo?.choice === 'tiene' ? 'tiene' : 'encaja';
			fl.producto = { id: valor as ProductoId, modo };
			break;
		}
	}
}
