// Magnitudes que la interfaz deriva de lo que da el motor. Todas son causales: en el mes t solo
// usan meses ≤ t, para que el reloj nunca enseñe información del futuro.

import type { Cartera, Grupo } from './modelo';
import { nombreEmpresa, nombreGrupo } from './nombres';

/**
 * Tendencia larga: pendiente de Theil–Sen del score sobre los últimos 12 meses, en puntos/mes.
 * La pedimos al motor (pregunta abierta Q-05: las derivas lentas salen «estable» con Δ3).
 * Mientras tanto se deriva aquí. Devuelve null con menos de 4 meses observados.
 */
const cacheTendencia = new WeakMap<Grupo, (number | null | undefined)[]>();

export function tendencia(g: Grupo, t: number, ventana = 12): number | null {
	if (ventana !== 12) return calcularTendencia(g, t, ventana);
	let c = cacheTendencia.get(g);
	if (!c) { c = []; cacheTendencia.set(g, c); }
	if (c[t] === undefined) c[t] = calcularTendencia(g, t, ventana);
	return c[t]!;
}

/** Pendiente robusta del score en puntos por mes, usando solo valores hasta el corte. */
export function pendienteTheilSen(valores: readonly (number | null | undefined)[], corte: number, ventana = 12): number | null {
	const xs: number[] = [];
	const ys: number[] = [];
	for (let k = Math.max(0, corte - ventana + 1); k <= corte; k++) {
		const s = valores[k];
		if (s !== null && s !== undefined) { xs.push(k); ys.push(s / 10); }
	}
	if (xs.length < 6) return null;
	const pendientes: number[] = [];
	for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) pendientes.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
	pendientes.sort((a, b) => a - b);
	const medio = pendientes.length >> 1;
	return pendientes.length % 2 ? pendientes[medio] : (pendientes[medio - 1] + pendientes[medio]) / 2;
}

function calcularTendencia(g: Grupo, t: number, ventana: number): number | null {
	const xs: number[] = [];
	const ys: number[] = [];
	for (let k = Math.max(g.first_month, t - ventana + 1); k <= t; k++) {
		const s = g.meses[k]?.shown;
		if (s !== null && s !== undefined) { xs.push(k); ys.push(s / 10); }
	}
	if (xs.length < 4) return null;
	const pend: number[] = [];
	for (let i = 0; i < xs.length; i++)
		for (let j = i + 1; j < xs.length; j++) pend.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
	pend.sort((a, b) => a - b);
	const m = pend.length >> 1;
	return pend.length % 2 ? pend[m] : (pend[m - 1] + pend[m]) / 2;
}

export type Lente = 'todas' | 'solidas' | 'mejoran' | 'tuercen' | 'hunden' | 'baches' | 'criticas';

export const LENTES: { id: Lente; nombre: string; tecla: string; ayuda: string }[] = [
	{ id: 'todas', nombre: 'Todas', tecla: '1', ayuda: 'Toda la cartera' },
	{ id: 'solidas', nombre: 'Sólidas', tecla: '2', ayuda: '¿Quién está sano?' },
	{ id: 'mejoran', nombre: 'Mejoran', tecla: '3', ayuda: '¿Quién está mejorando?' },
	{ id: 'tuercen', nombre: 'Se tuercen', tecla: '4', ayuda: '¿Quién empieza a torcerse?' },
	{ id: 'hunden', nombre: 'Se hunden', tecla: '5', ayuda: 'Nivel bajo y cayendo' },
	{ id: 'baches', nombre: 'Bache o caída', tecla: '6', ayuda: 'Movimientos por confirmar o revertidos' },
	{ id: 'criticas', nombre: 'Críticas', tecla: '7', ayuda: 'Banda crítica' },
];

/** Umbral de tendencia a partir del cual un grupo «se mueve» en el plano (puntos/mes). */
export const UMBRAL_TENDENCIA = 0.5;

export function enLente(g: Grupo, t: number, lente: Lente): boolean {
	const m = g.meses[t];
	if (!m || m.shown === null) return false;
	if (lente === 'todas') return true;
	const tr = tendencia(g, t) ?? 0;
	const s = m.shown;
	switch (lente) {
		case 'solidas': return m.band === 'solid' && tr > -UMBRAL_TENDENCIA;
		case 'mejoran': return m.direction === 'improving' || tr >= UMBRAL_TENDENCIA;
		case 'tuercen': return s >= 600 && (m.direction === 'deteriorating' || tr <= -UMBRAL_TENDENCIA);
		case 'hunden': return s < 600 && (m.direction === 'deteriorating' || tr <= -UMBRAL_TENDENCIA);
		case 'baches': return m.nature === 'bump' || m.nature === 'shock_pending';
		case 'criticas': return m.band === 'critical';
	}
}

export interface Pulso { movidos: number; empeoran: number; mejoran: number; porConfirmar: number; baches: number; observados: number }

export function pulso(c: Cartera, t: number): Pulso {
	const p: Pulso = { movidos: 0, empeoran: 0, mejoran: 0, porConfirmar: 0, baches: 0, observados: 0 };
	for (const g of c.groups) {
		const m = g.meses[t];
		if (!m || m.shown === null) continue;
		p.observados++;
		if (m.nature === 'structural') {
			p.movidos++;
			if (m.direction === 'deteriorating') p.empeoran++;
			else p.mejoran++;
		}
		if (m.nature === 'shock_pending') p.porConfirmar++;
		if (m.nature === 'bump') p.baches++;
	}
	return p;
}

// Formatos (docs/UI_FORMATTING.mdx): es-ES siempre, scores enteros, meses «09/26».
const MES_LARGO = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

export const fmt = {
	score: (decimas: number | null) => (decimas === null ? '—' : String(Math.round(decimas / 10))),
	decimas: (d: number) => new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'exceptZero' }).format(d / 10),
	pendiente: (p: number | null) =>
		p === null ? '—' : new Intl.NumberFormat('es-ES', { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'exceptZero' }).format(p),
	mesLargo: (iso: string) => {
		const [a, m] = iso.split('-').map(Number);
		return `${MES_LARGO[m - 1]} de ${a}`;
	},
	mesCorto: (iso: string) => {
		const [a, m] = iso.split('-').map(Number);
		return `${MES_CORTO[m - 1]} ${String(a).slice(2)}`;
	},
	mesEje: (iso: string) => {
		const [a, m] = iso.split('-');
		return `${m}/${a.slice(2)}`;
	},
	grupo: nombreGrupo,
	empresa: nombreEmpresa,
	entero: (n: number) => new Intl.NumberFormat('es-ES').format(n),
};
