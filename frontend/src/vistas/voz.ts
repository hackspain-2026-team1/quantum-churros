// La voz del sistema: tercera persona y frases cortas. Cada cifra sale de un campo del modelo.

import { NOMBRE_BANDA, NOMBRE_PILAR, PILARES, type Alerta, type Grupo } from '../datos/modelo';
import { fmt, tendencia } from '../datos/derivados';
import { nombreGrupo } from '../datos/nombres';

export { nombreGrupo };

/** El pilar que más ha movido el score entre dos meses. */
export function pilarQueEmpuja(g: Grupo, desde: number, hasta: number) {
	const a = g.meses[desde], b = g.meses[hasta];
	if (!a || !b || a.shown === null || b.shown === null) return null;
	let mejor: { pilar: (typeof PILARES)[number]; delta: number } | null = null;
	PILARES.forEach((p, i) => {
		const d = b.pillars[i].contrib - a.pillars[i].contrib;
		if (!mejor || Math.abs(d) > Math.abs(mejor.delta)) mejor = { pilar: p, delta: d };
	});
	return mejor as { pilar: (typeof PILARES)[number]; delta: number } | null;
}

/** Una línea por aviso: «Grupo 121 · deterioro confirmado · de 56 a 48 · pesa la liquidez». */
export function lineaAviso(g: Grupo, a: Pick<Alerta, 'kind' | 'month'>): string {
	const desde = Math.max(g.first_month, a.month - 3);
	const s0 = g.meses[desde].shown, s1 = g.meses[a.month].shown;
	const empuje = pilarQueEmpuja(g, desde, a.month);
	const tipo = a.kind === 'improvement_structural' ? 'mejora confirmada' : a.kind === 'improvement_drift' ? 'sube poco a poco' : a.kind === 'deterioration_drift' ? 'baja poco a poco' : a.kind === 'level_critical' ? 'entra en nivel crítico' : a.kind === 'cap_fired' ? 'salta un tope' : a.kind === 'stale_feed' ? 'datos sin actualizar' : 'deterioro confirmado';
	const partes = [nombreGrupo(g.id), tipo, `de ${fmt.score(s0)} a ${fmt.score(s1)}`];
	if (empuje && empuje.delta !== 0) partes.push(`pesa ${articulo(NOMBRE_PILAR[empuje.pilar])}`);
	return partes.join(' · ');
}

const articulo = (pilar: string) => `${pilar === 'Deuda' || pilar === 'Liquidez' || pilar === 'Actividad' ? 'la' : 'los'} ${pilar.toLowerCase()}`;

/** El ritmo en palabras: «baja 0,7 al mes». */
export function ritmoEnPalabras(r: number | null): string {
	if (r === null) return 'aún sin historia';
	if (Math.abs(r) < 0.2) return 'estable';
	return `${r > 0 ? 'sube' : 'baja'} ${fmt.pendiente(Math.abs(r)).replace('+', '')} al mes`;
}

/** La frase que explica el número del expediente. */
export function explicacion(g: Grupo, corte: number, puntos: number | null): string[] {
	const m = g.meses[corte];
	if (puntos === null || !m.band) return ['Todavía no hay datos suficientes para puntuar este grupo.'];
	const frases: string[] = [];
	const tr = tendencia(g, corte);
	let desdeBanda = corte;
	while (desdeBanda - 1 >= g.first_month && g.meses[desdeBanda - 1].band === m.band) desdeBanda--;
	frases.push(`${nombreGrupo(g.id)} está en ${NOMBRE_BANDA[m.band].toLowerCase()} con ${Math.round(puntos)} puntos${desdeBanda < corte ? `, desde ${fmt.mesLargo(mesIso(desdeBanda))}` : ''}.`);
	if (tr !== null && Math.abs(tr) >= 0.3) {
		const lento = m.direction === 'stable' || m.direction === null;
		frases.push(tr < 0
			? `Lleva un año bajando ${Math.abs(tr) < 1 ? 'despacio' : 'deprisa'}, ${fmt.pendiente(Math.abs(tr)).replace('+', '')} puntos al mes.${lento ? ' Ningún tramo de tres meses ha caído lo bastante para una alerta; la suma, sí.' : ''}`
			: `Lleva un año subiendo, ${fmt.pendiente(tr).replace('+', '')} puntos al mes.${lento ? ' Todavía sin una mejora confirmada.' : ''}`);
	} else if (tr !== null) frases.push('Se ha mantenido estable durante el último año.');
	if (m.nature === 'shock_pending') frases.push('Este mes se ha movido de golpe y falta confirmar si es un bache.');
	if (m.nature === 'bump') frases.push('El golpe del mes pasado se ha revertido: fue un bache.');
	const empuje = pilarQueEmpuja(g, Math.max(g.first_month, corte - 12), corte);
	if (empuje && Math.abs(empuje.delta) >= 5) frases.push(`Lo que más ha pesado en el año: ${articulo(NOMBRE_PILAR[empuje.pilar])}.`);
	if (m.abstained) frases.push('Con tan poca historia, el score se enseña pero no dispara avisos.');
	return frases;
}

let MESES_ISO: string[] = [];
export function fijarMeses(m: string[]) { MESES_ISO = m; }
const mesIso = (k: number) => MESES_ISO[k];
