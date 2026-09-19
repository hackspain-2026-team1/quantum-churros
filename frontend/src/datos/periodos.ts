// El tiempo de la interfaz: escalas de calendario, periodos y cómo se resume un grupo en un periodo.
// Los periodos son de calendario (el T1 es enero–marzo). La ventana de datos empieza en septiembre de
// 2024 y acaba en agosto de 2026, así que el primer y el último periodo pueden quedar incompletos:
// el primero es «parcial» y el último, «en curso».

import type { Grupo } from './modelo';

export type Escala = 'mes' | 'trimestre' | 'cuatrimestre' | 'semestre' | 'anio';
export type Agregado = 'cierre' | 'media';

export const ESCALAS: { id: Escala; nombre: string; frase: string; meses: number; muescas: number }[] = [
	{ id: 'mes', nombre: 'Meses', frase: 'mes a mes', meses: 1, muescas: 12 },
	{ id: 'trimestre', nombre: 'Trimestres', frase: 'por trimestres', meses: 3, muescas: 4 },
	{ id: 'cuatrimestre', nombre: 'Cuatrimestres', frase: 'por cuatrimestres', meses: 4, muescas: 3 },
	{ id: 'semestre', nombre: 'Semestres', frase: 'por semestres', meses: 6, muescas: 2 },
	{ id: 'anio', nombre: 'Años', frase: 'por años', meses: 12, muescas: 1 },
];
export const escalaDe = (e: Escala) => ESCALAS.find((x) => x.id === e)!;

export interface Periodo {
	i: number;
	/** Índices de mes de la ventana que caen en el periodo. */
	meses: number[];
	/** Meses que tendría el periodo completo. */
	largo: number;
	completo: boolean;
	/** Parcial al principio de la ventana o en curso al final. */
	estado: 'completo' | 'parcial' | 'en curso';
	anio: number;
	/** Índice dentro del año: 1.º trimestre, 2.º cuatrimestre… (mes: 1–12). */
	orden: number;
	corta: string; // «T3 26», «sep 25», «2025»
	larga: string; // «tercer trimestre de 2026»
	enFrase: string; // «el T3 de 2026», «septiembre de 2025»
}

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MESES_C = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const ORDINAL = ['primer', 'segundo', 'tercer', 'cuarto'];
const ORD_C = ['1.er', '2.º', '3.er', '4.º'];

/** Construye los periodos de una escala sobre la ventana de meses ('YYYY-MM'). */
export function periodosDe(meses: string[], escala: Escala, ultimoMesDatos = meses.length - 1): Periodo[] {
	const e = escalaDe(escala);
	const mapa = new Map<string, Periodo>();
	const lista: Periodo[] = [];
	meses.forEach((iso, k) => {
		const [a, m] = iso.split('-').map(Number);
		const orden = Math.floor((m - 1) / e.meses) + 1;
		const clave = `${a}-${orden}`;
		let p = mapa.get(clave);
		if (!p) {
			const corta =
				escala === 'mes' ? `${MESES_C[m - 1]} ${String(a).slice(2)}`
				: escala === 'trimestre' ? `T${orden} ${String(a).slice(2)}`
				: escala === 'cuatrimestre' ? `C${orden} ${String(a).slice(2)}`
				: escala === 'semestre' ? `S${orden} ${String(a).slice(2)}`
				: String(a);
			const larga =
				escala === 'mes' ? `${MESES[m - 1]} de ${a}`
				: escala === 'trimestre' ? `${ORDINAL[orden - 1]} trimestre de ${a}`
				: escala === 'cuatrimestre' ? `${ORDINAL[orden - 1]} cuatrimestre de ${a}`
				: escala === 'semestre' ? `${ORDINAL[orden - 1]} semestre de ${a}`
				: `${a}`;
			const enFrase =
				escala === 'mes' ? `${MESES[m - 1]} de ${a}`
				: escala === 'trimestre' ? `el T${orden} de ${a}`
				: escala === 'cuatrimestre' ? `el ${ORD_C[orden - 1]} cuatrimestre de ${a}`
				: escala === 'semestre' ? `el ${ORD_C[orden - 1]} semestre de ${a}`
				: `${a}`;
			p = { i: lista.length, meses: [], largo: e.meses, completo: false, estado: 'completo', anio: a, orden, corta, larga, enFrase };
			mapa.set(clave, p);
			lista.push(p);
		}
		p.meses.push(k);
	});
	for (const p of lista) {
		p.completo = p.meses.length === p.largo && p.meses[p.meses.length - 1] <= ultimoMesDatos;
		p.estado = p.completo ? 'completo' : p.i === 0 ? 'parcial' : 'en curso';
	}
	return lista;
}

export interface ValorPeriodo {
	/** Score del periodo en décimas (al cierre o de media); null si el grupo no tenía datos. */
	valor: number | null;
	/** Mes (índice) del que sale el valor al cierre. */
	mes: number;
	/** Desviación típica del score dentro del periodo, en puntos. */
	dispersion: number;
}

/** Resume un grupo en un periodo. Solo usa los meses del periodo (causal). */
export function valorEnPeriodo(g: Grupo, p: Periodo, agregado: Agregado): ValorPeriodo {
	const vals: number[] = [];
	let ultimo = -1;
	for (const k of p.meses) {
		const s = g.meses[k]?.shown;
		if (s !== null && s !== undefined) { vals.push(s); ultimo = k; }
	}
	if (!vals.length) return { valor: null, mes: p.meses[p.meses.length - 1], dispersion: 0 };
	const media = vals.reduce((a, b) => a + b, 0) / vals.length;
	const disp = vals.length > 1 ? Math.sqrt(vals.reduce((s, v) => s + (v - media) ** 2, 0) / (vals.length - 1)) / 10 : 0;
	return { valor: agregado === 'cierre' ? g.meses[ultimo].shown! : Math.round(media), mes: ultimo, dispersion: disp };
}

/** Último mes con datos de la ventana hasta el final del periodo (para lo que se mide «a fecha de»). */
export const mesDeCorte = (p: Periodo) => p.meses[p.meses.length - 1];

/** Índice del periodo que contiene un mes. */
export function periodoDeMes(periodos: Periodo[], mes: number) {
	return periodos.find((p) => p.meses.includes(mes))?.i ?? periodos.length - 1;
}

/** Periodo equivalente un año antes (mismo orden), o null si cae fuera de la ventana. */
export function periodoAnioAnterior(periodos: Periodo[], p: Periodo): Periodo | null {
	return periodos.find((q) => q.anio === p.anio - 1 && q.orden === p.orden) ?? null;
}
