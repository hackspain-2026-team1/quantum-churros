// La consulta: qué se mira (quién, cuándo, a qué escala, frente a qué) y todo lo que se deriva de ella.
// La frase, la arena y la regla leen de aquí; así las tres dicen siempre lo mismo.

import type { Cartera } from './modelo';
import { tendencia } from './derivados';
import { encajaAGrupo } from './encaje';
import { PRODUCTOS, type ProductoId } from './productos';
import { nombreGrupo } from './nombres';
import {
	ESCALAS, escalaDe, mesDeCorte, periodoAnioAnterior, periodoDeMes, periodosDe, valorEnPeriodo,
	type Agregado, type Escala, type Periodo,
} from './periodos';

export type Zona = 'mejora' | 'solida' | 'tuerce' | 'hunde';
export type Movimiento = 'deterioro' | 'mejora' | 'confirmar' | 'bache' | 'critica' | 'avisos';
export type Frente = 'nada' | 'anterior' | 'anio' | 'alta';
export type Orden = 'score' | 'ritmo' | 'alerta' | 'tamano';

export type Filtro =
	| { tipo: 'zona'; v: Zona }
	| { tipo: 'mov'; v: Movimiento }
	| { tipo: 'sector'; v: string }
	| { tipo: 'pais'; v: string }
	| { tipo: 'tamano'; v: string }
	| { tipo: 'mano'; v: string[] }
	| { tipo: 'grupo'; v: string }
	| { tipo: 'producto'; v: ProductoId; modo?: 'encaja' | 'tiene' };

export interface Consulta {
	filtros: Filtro[];
	escala: Escala;
	agregado: Agregado;
	/** Índices de periodo en la escala actual. desde ≤ hasta. */
	desde: number;
	hasta: number;
	frente: Frente;
	orden: Orden;
}

/** Umbral de score (puntos) que separa las zonas de la izquierda y la derecha del plano. */
export const CORTE_SCORE = 60;

export const PAISES: Record<string, string> = {
	ES: 'España', PT: 'Portugal', FR: 'Francia', DE: 'Alemania', IT: 'Italia', GB: 'Reino Unido', NL: 'Países Bajos', BE: 'Bélgica',
	DK: 'Dinamarca', NO: 'Noruega', US: 'Estados Unidos', AE: 'Emiratos Árabes Unidos', AD: 'Andorra', MY: 'Malasia',
};

export const ZONAS: { id: Zona; plural: string; singular: string; explica: string }[] = [
	{ id: 'mejora', plural: 'que mejoran', singular: 'que mejora', explica: 'Nivel bajo, pero subiendo' },
	{ id: 'solida', plural: 'sólidos', singular: 'sólido', explica: 'Nivel alto y estable o al alza' },
	{ id: 'tuerce', plural: 'que se tuercen', singular: 'que se tuerce', explica: 'Parecen sanos, pero bajan' },
	{ id: 'hunde', plural: 'que se hunden', singular: 'que se hunde', explica: 'Nivel bajo y cayendo' },
];
export const NOMBRE_ZONA: Record<Zona, string> = { mejora: 'Mejora', solida: 'Sólida', tuerce: 'Se tuerce', hunde: 'Se hunde' };

export const MOVIMIENTOS: { id: Movimiento; frase: string; singular: string; nombre: string }[] = [
	{ id: 'deterioro', frase: 'con un deterioro confirmado', singular: 'con un deterioro confirmado', nombre: 'Deterioro confirmado' },
	{ id: 'mejora', frase: 'con una mejora confirmada', singular: 'con una mejora confirmada', nombre: 'Mejora confirmada' },
	{ id: 'confirmar', frase: 'con un movimiento por confirmar', singular: 'con un movimiento por confirmar', nombre: 'Movimiento por confirmar' },
	{ id: 'bache', frase: 'que han tenido un bache', singular: 'que ha tenido un bache', nombre: 'Bache' },
	{ id: 'critica', frase: 'en banda crítica', singular: 'en banda crítica', nombre: 'En banda crítica' },
	{ id: 'avisos', frase: 'con algún aviso', singular: 'con algún aviso', nombre: 'Con algún aviso' },
];

// ─────────────────────────────────────────────── contexto derivado de una consulta

export interface Contexto {
	c: Cartera;
	q: Consulta;
	periodos: Periodo[];
	pDesde: Periodo;
	pHasta: Periodo;
	/** Mes de corte: todo lo «a fecha de» se mide aquí (último mes del periodo «hasta»). */
	corte: number;
	/** Meses que abarca el intervalo desde–hasta. */
	primerMes: number;
	/** Grupos con datos en el corte y que pasan el tamiz. */
	visibles: Set<number>;
	/** Grupos con datos en el corte que no pasan el tamiz (sedimento). */
	fuera: Set<number>;
	/** Grupos sin datos todavía en el corte. */
	sinDatos: Set<number>;
	valor: (gi: number, p: Periodo) => number | null;
	ritmo: (gi: number) => number | null;
	zona: (gi: number) => Zona | null;
	/** Periodo de origen de la comparación para un grupo (flechas y cifras), o null. */
	origen: (gi: number) => Periodo | null;
}

export function periodosConsulta(c: Cartera, q: Consulta) {
	return periodosDe(c.months, q.escala);
}

export function contexto(c: Cartera, q: Consulta): Contexto {
	const periodos = periodosConsulta(c, q);
	const hasta = Math.min(Math.max(0, Number.isFinite(q.hasta) ? q.hasta : periodos.length - 1), periodos.length - 1);
	const desde = Math.min(Math.max(0, q.desde), hasta);
	const pHasta = periodos[hasta], pDesde = periodos[desde];
	const corte = mesDeCorte(pHasta);
	const primerMes = pDesde.meses[0];
	const cacheValor = new Map<string, number | null>();
	const valor = (gi: number, p: Periodo) => {
		const k = `${gi}:${p.i}`;
		if (!cacheValor.has(k)) cacheValor.set(k, valorEnPeriodo(c.groups[gi], p, q.agregado).valor);
		return cacheValor.get(k)!;
	};
	const ritmo = (gi: number) => tendencia(c.groups[gi], corte);
	const zona = (gi: number): Zona | null => {
		const v = valor(gi, pHasta);
		if (v === null) return null;
		const r = ritmo(gi) ?? 0;
		if (v / 10 >= CORTE_SCORE) return r >= 0 ? 'solida' : 'tuerce';
		return r >= 0 ? 'mejora' : 'hunde';
	};
	const origen = (gi: number): Periodo | null => {
		let p: Periodo | null = null;
		if (q.frente === 'anio') p = periodoAnioAnterior(periodos, pHasta);
		else if (q.frente === 'anterior') p = periodos[pHasta.i - 1] ?? null;
		else if (q.frente === 'alta') p = periodos[periodoDeMes(periodos, c.groups[gi].first_month)];
		else p = desde < hasta ? pDesde : periodos[pHasta.i - 1] ?? null;
		if (p && valor(gi, p) === null) return null;
		return p;
	};
	const ctx: Contexto = { c, q: { ...q, desde, hasta }, periodos, pDesde, pHasta, corte, primerMes, visibles: new Set(), fuera: new Set(), sinDatos: new Set(), valor, ritmo, zona, origen };
	c.groups.forEach((g, gi) => {
		if (valor(gi, pHasta) === null || g.meses[corte].shown === null) { ctx.sinDatos.add(gi); return; }
		(pasa(ctx, gi, q.filtros) ? ctx.visibles : ctx.fuera).add(gi);
	});
	return ctx;
}

/** Meses del intervalo en el que se buscan movimientos: el periodo «hasta» o todo el intervalo. */
function mesesVentana(ctx: Contexto) {
	return [ctx.primerMes, ctx.corte] as const;
}

export function cumple(ctx: Contexto, gi: number, f: Filtro): boolean {
	const g = ctx.c.groups[gi];
	const [a, b] = mesesVentana(ctx);
	const enVentana = (kinds: string[]) => g.alerts.some((x) => x.state === 'fired' && x.month >= a && x.month <= b && kinds.includes(x.kind));
	switch (f.tipo) {
		case 'zona': return ctx.zona(gi) === f.v;
		case 'mov':
			switch (f.v) {
				case 'deterioro': return enVentana(['deterioration_structural', 'deterioration_drift']);
				case 'mejora': return enVentana(['improvement_structural', 'improvement_drift']);
				case 'confirmar': return g.meses[ctx.corte].nature === 'shock_pending';
				case 'bache': { for (let k = a; k <= b; k++) if (g.meses[k].nature === 'bump') return true; return false; }
				case 'critica': return g.meses[ctx.corte].band === 'critical';
				case 'avisos': return enVentana(['deterioration_structural', 'improvement_structural', 'deterioration_drift', 'improvement_drift', 'level_critical', 'cap_fired', 'stale_feed']);
			}
			return false;
		case 'sector': return g.industry === f.v;
		case 'pais': return g.country === f.v;
		case 'tamano': return g.size_band === f.v;
		case 'mano': return f.v.includes(g.id);
		case 'grupo': return g.id === f.v;
		case 'producto': return f.modo === 'tiene' ? (g.tenencia?.[f.v] ?? 0) > 0 : encajaAGrupo(g.meses[ctx.corte]?.acciones, g.tenencia, f.v);
	}
}

export function pasa(ctx: Contexto, gi: number, filtros: Filtro[]) {
	return filtros.every((f) => cumple(ctx, gi, f));
}

/** Cuántos grupos quedarían con estos filtros (para enseñar la consecuencia antes de elegir). */
export function cuantos(ctx: Contexto, filtros: Filtro[]) {
	let n = 0;
	ctx.c.groups.forEach((_, gi) => { if (!ctx.sinDatos.has(gi) && pasa(ctx, gi, filtros)) n++; });
	return n;
}

// ─────────────────────────────────────────────── la frase

const TAMANO_ADJ: Record<string, [string, string]> = { Grande: ['grandes', 'grande'], Mediana: ['medianos', 'mediano'], Pequeña: ['pequeños', 'pequeño'], Micro: ['de tamaño micro', 'de tamaño micro'] };

export function textoQuien(ctx: Contexto): string {
	const n = ctx.visibles.size;
	const fs = ctx.q.filtros;
	const grupo = fs.find((f) => f.tipo === 'grupo');
	if (grupo && fs.length === 1) return `El ${nombreGrupo(grupo.v as string)}`;
	if (!fs.length) return `Los ${n} grupos de la cartera`;
	const uno = n === 1;
	const partes: string[] = [];
	const tam = fs.find((f) => f.tipo === 'tamano');
	partes.push(n === 0 ? 'Ningún grupo' : uno ? 'El único grupo' : `Los ${n} grupos`);
	if (tam) partes.push(TAMANO_ADJ[tam.v as string]?.[uno || n === 0 ? 1 : 0] ?? '');
	for (const f of fs) {
		if (f.tipo === 'sector') partes.push(`de ${String(f.v).toLowerCase()}`);
		if (f.tipo === 'pais') partes.push(`de ${PAISES[f.v as string] ?? f.v}`);
	}
	for (const f of fs) {
		if (f.tipo === 'zona') {
			const z = ZONAS.find((x) => x.id === f.v)!;
			partes.push(uno || n === 0 ? z.singular : z.plural);
		}
		if (f.tipo === 'mov') {
			const m = MOVIMIENTOS.find((x) => x.id === f.v)!;
			partes.push(uno || n === 0 ? m.singular : m.frase);
		}
		if (f.tipo === 'mano') partes.push(uno ? 'elegido a mano' : 'elegidos a mano');
		if (f.tipo === 'grupo') partes.push(`(el ${nombreGrupo(f.v as string)})`);
	}
	const prod = fs.find((f) => f.tipo === 'producto');
	if (prod && prod.tipo === 'producto') partes.push(prod.modo === 'tiene' ? `que ya ${uno ? 'tiene' : 'tienen'} ${ARTICULO_PRODUCTO[prod.v]}` : `${uno || n === 0 ? 'al que le' : 'a los que les'} encaja ${ARTICULO_PRODUCTO[prod.v]}`);
	return partes.filter(Boolean).join(' ');
}

/** «la línea de crédito», «el factoring», «los depósitos y letras». */
export const ARTICULO_PRODUCTO: Record<ProductoId, string> = {
	linea_credito: 'una línea de crédito', factoring: 'el factoring', confirming: 'el confirming', seguro_credito: 'un seguro de crédito',
	cuenta_remunerada: 'una cuenta remunerada', depositos: 'un depósito o letras', plan_pensiones: 'un plan de pensiones',
};

/** «entre mayo y agosto de 2026», «en el T3 de 2026». */
export function textoCuando(ctx: Contexto): string {
	const { pDesde: a, pHasta: b } = ctx;
	if (a.i === b.i) return `en ${b.enFrase}`;
	if (ctx.q.escala === 'anio') return `entre ${a.anio} y ${b.anio}`;
	if (a.anio === b.anio) {
		const sinAnio = (p: Periodo) => p.enFrase.replace(` de ${p.anio}`, '');
		return `entre ${sinAnio(a)} y ${sinAnio(b)} de ${b.anio}`;
	}
	return `entre ${a.enFrase} y ${b.enFrase}`;
}

export function textoEscala(q: Consulta) { return escalaDe(q.escala).frase; }
export function textoAgregado(q: Consulta) { return q.agregado === 'cierre' ? 'al cierre' : 'de media'; }

export function textoFrente(ctx: Contexto): string | null {
	const q = ctx.q;
	if (q.frente === 'nada') return null;
	if (q.frente === 'alta') return 'frente a su primer mes en la plataforma';
	if (q.frente === 'anterior') {
		const p = ctx.periodos[ctx.pHasta.i - 1];
		return p ? `frente a ${p.enFrase}` : 'frente al periodo anterior';
	}
	const p = periodoAnioAnterior(ctx.periodos, ctx.pHasta);
	if (!p) return 'frente al mismo periodo del año pasado (sin datos)';
	return q.escala === 'mes' ? `frente a ${p.enFrase}` : `frente ${p.enFrase.startsWith('el ') ? 'al ' + p.enFrase.slice(3) : 'a ' + p.enFrase}`;
}

export const TEXTO_ORDEN: Record<Orden, string> = { score: 'ordenados por score', ritmo: 'ordenados por ritmo', alerta: 'ordenados por su primer aviso', tamano: 'ordenados por tamaño' };

// ─────────────────────────────────────────────── cambios de escala sin perder el sitio

/** Cambia la escala manteniendo el intervalo en los mismos meses. */
export function conEscala(c: Cartera, q: Consulta, escala: Escala): Consulta {
	const antes = periodosDe(c.months, q.escala);
	const despues = periodosDe(c.months, escala);
	const mesHasta = mesDeCorte(antes[Math.min(q.hasta, antes.length - 1)]);
	const mesDesde = antes[Math.min(q.desde, antes.length - 1)].meses[0];
	const h = periodoDeMes(despues, mesHasta);
	const d = Math.min(h, periodoDeMes(despues, mesDesde));
	return { ...q, escala, hasta: h, desde: d };
}

export function consultaInicial(c: Cartera): Consulta {
	const periodos = periodosDe(c.months, 'mes');
	return { filtros: [], escala: 'mes', agregado: 'cierre', desde: periodos.length - 1, hasta: periodos.length - 1, frente: 'nada', orden: 'score' };
}

export { ESCALAS };

// ─────────────────────────────────────────────── el intérprete de lo que se escribe

export interface Propuesta {
	texto: string; // cómo quedaría, en palabras
	tipo: 'Quién' | 'Cuándo' | 'Escala' | 'Frente a' | 'Orden';
	aplicar: (q: Consulta) => Consulta;
	peso: number;
}

const normal = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
const NOMBRES_MES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

/**
 * Convierte lo escrito en propuestas de cambio. Vocabulario cerrado con sinónimos: nunca inventa,
 * y si no entiende nada devuelve una lista vacía (la interfaz lo dice y sugiere).
 */
export function interpretar(c: Cartera, _q: Consulta, escrito: string): Propuesta[] {
	const t = normal(escrito);
	if (!t) return [];
	const props: Propuesta[] = [];
	const empieza = (palabra: string, min = 3) => t.length >= min && (normal(palabra).startsWith(t) || t.startsWith(normal(palabra)) || normal(palabra).split(' ').some((w) => w.startsWith(t) && t.length >= min));
	const periodosMes = periodosDe(c.months, 'mes');
	const anioEscrito = t.match(/20(2[4-6])/)?.[0];

	// Un número: un grupo o un año.
	const num = t.match(/^(grupo\s*)?(\d{1,4})$/);
	if (num) {
		const n = Number(num[2]);
		if (n >= 1 && n <= c.groups.length) {
			const id = `GROUP_${String(n).padStart(4, '0')}`;
			props.push({ tipo: 'Quién', texto: `el ${nombreGrupo(id)}`, peso: 10, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'grupo', v: id }] }) });
		}
		if (n >= 2024 && n <= 2026) {
			props.push({
				tipo: 'Cuándo', texto: `todo ${n}`, peso: 9, aplicar: (x) => {
					const ps = periodosDe(c.months, x.escala).filter((p) => p.anio === n);
					return ps.length ? { ...x, desde: ps[0].i, hasta: ps[ps.length - 1].i } : x;
				},
			});
		}
	}
	// Meses con o sin año.
	NOMBRES_MES.forEach((m, i) => {
		const palabra = t.split(/\s+/)[0];
		if (palabra.length >= 3 && m.startsWith(palabra)) {
			const candidatos = periodosMes.filter((p) => p.orden === i + 1 && (!anioEscrito || String(p.anio) === anioEscrito));
			const p = candidatos[candidatos.length - 1];
			if (p) props.push({ tipo: 'Cuándo', texto: p.enFrase, peso: 8, aplicar: (x) => ({ ...x, escala: 'mes', desde: p.i, hasta: p.i }) });
		}
	});
	// Trimestres: «t2», «t2 2025», «segundo trimestre».
	const tri = t.match(/^t\s*([1-4])/) ?? t.match(/^(primer|segundo|tercer|cuarto)\s+trim/);
	if (tri) {
		const o = /\d/.test(tri[1]) ? Number(tri[1]) : ['primer', 'segundo', 'tercer', 'cuarto'].indexOf(tri[1]) + 1;
		const ps = periodosDe(c.months, 'trimestre').filter((p) => p.orden === o && (!anioEscrito || String(p.anio) === anioEscrito));
		const p = ps[ps.length - 1];
		if (p) props.push({ tipo: 'Cuándo', texto: p.enFrase, peso: 9, aplicar: (x) => ({ ...x, escala: 'trimestre', desde: p.i, hasta: p.i }) });
	}
	// Escalas.
	const escalas: [string[], Escala][] = [[['mes', 'meses', 'mensual'], 'mes'], [['trimestre', 'trimestres', 'trimestral'], 'trimestre'], [['cuatrimestre', 'cuatrimestres'], 'cuatrimestre'], [['semestre', 'semestres', 'semestral'], 'semestre'], [['año', 'años', 'anual', 'anio'], 'anio']];
	for (const [palabras, e] of escalas) if (palabras.some((w) => empieza(w, 3)) && !tri) props.push({ tipo: 'Escala', texto: escalaDe(e).frase, peso: 7, aplicar: (x) => conEscala(c, x, e) });
	if (['media', 'promedio', 'medio'].some((w) => empieza(w))) props.push({ tipo: 'Escala', texto: 'de media', peso: 6, aplicar: (x) => ({ ...x, agregado: 'media' }) });
	if (['cierre', 'al cierre', 'final'].some((w) => empieza(w))) props.push({ tipo: 'Escala', texto: 'al cierre', peso: 6, aplicar: (x) => ({ ...x, agregado: 'cierre' }) });
	// Comparaciones.
	if (['año pasado', 'interanual', 'hace un año', 'mismo periodo'].some((w) => empieza(w, 4))) props.push({ tipo: 'Frente a', texto: 'frente al mismo periodo del año pasado', peso: 8, aplicar: (x) => ({ ...x, frente: 'anio' }) });
	if (['anterior', 'periodo anterior', 'mes anterior'].some((w) => empieza(w, 4))) props.push({ tipo: 'Frente a', texto: 'frente al periodo anterior', peso: 7, aplicar: (x) => ({ ...x, frente: 'anterior' }) });
	if (['alta', 'inicio', 'primer mes', 'desde el principio'].some((w) => empieza(w, 4))) props.push({ tipo: 'Frente a', texto: 'frente a su primer mes', peso: 6, aplicar: (x) => ({ ...x, frente: 'alta' }) });
	if (['sin comparar', 'no comparar'].some((w) => empieza(w, 4))) props.push({ tipo: 'Frente a', texto: 'sin comparar', peso: 6, aplicar: (x) => ({ ...x, frente: 'nada' }) });
	// Zonas y movimientos.
	const zonas: [string[], Zona][] = [[['tuercen', 'tuerce', 'torcidos', 'empeoran'], 'tuerce'], [['mejoran', 'mejora', 'suben'], 'mejora'], [['hunden', 'hunde', 'caen'], 'hunde'], [['solidos', 'solidas', 'sanos', 'sanas', 'solida'], 'solida']];
	for (const [palabras, z] of zonas) if (palabras.some((w) => empieza(w, 3))) {
		const zz = ZONAS.find((x) => x.id === z)!;
		props.push({ tipo: 'Quién', texto: `los ${zz.plural}`, peso: 8, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'zona', v: z }] }) });
	}
	const movs: [string[], Movimiento][] = [[['baches', 'bache'], 'bache'], [['criticos', 'criticas', 'critica'], 'critica'], [['avisos', 'alertas'], 'avisos'], [['deterioro', 'deterioros'], 'deterioro'], [['confirmar', 'pendientes'], 'confirmar']];
	for (const [palabras, m] of movs) if (palabras.some((w) => empieza(w, 3))) {
		const mm = MOVIMIENTOS.find((x) => x.id === m)!;
		props.push({ tipo: 'Quién', texto: `los ${mm.frase}`, peso: 7, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'mov', v: m }] }) });
	}
	// Sectores, países y tamaños.
	const sectores = [...new Set(c.groups.map((g) => g.industry).filter(Boolean))] as string[];
	for (const s of sectores) if (empieza(s, 3)) props.push({ tipo: 'Quién', texto: `los de ${s.toLowerCase()}`, peso: 7, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'sector', v: s }] }) });
	for (const [cod, nombre] of Object.entries(PAISES)) if (empieza(nombre, 3) || t === normal(cod)) props.push({ tipo: 'Quién', texto: `los de ${nombre}`, peso: 6, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'pais', v: cod }] }) });
	for (const [tam, [pl]] of Object.entries(TAMANO_ADJ)) if (empieza(pl, 4)) props.push({ tipo: 'Quién', texto: `los grupos ${pl}`, peso: 6, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'tamano', v: tam }] }) });
	if (['todos', 'todo', 'cartera', 'toda la cartera'].some((w) => empieza(w, 4))) props.push({ tipo: 'Quién', texto: 'toda la cartera', peso: 5, aplicar: (x) => ({ ...x, filtros: [] }) });
	// Productos: «factoring», «línea», «seguro», «depósito», «pensiones», «ofrecer»…
	const palabrasProducto: Record<ProductoId, string[]> = {
		linea_credito: ['linea de credito', 'linea', 'credito', 'poliza'], factoring: ['factoring', 'anticipo de facturas'], confirming: ['confirming', 'pago a proveedores'],
		seguro_credito: ['seguro de credito', 'seguro', 'cobertura'], cuenta_remunerada: ['cuenta remunerada', 'remunerada'], depositos: ['depositos', 'letras', 'deposito'], plan_pensiones: ['plan de pensiones', 'pensiones', 'jubilacion'],
	};
	for (const p of PRODUCTOS) if (palabrasProducto[p.id].some((w) => empieza(w, 4))) props.push({ tipo: 'Quién', texto: `a los que les encaja ${ARTICULO_PRODUCTO[p.id]}`, peso: 7, aplicar: (x) => ({ ...x, filtros: [{ tipo: 'producto', v: p.id }] }) });
	// Orden.
	if (['ordenar', 'orden'].some((w) => empieza(w, 4))) props.push({ tipo: 'Orden', texto: 'ordenados por ritmo', peso: 3, aplicar: (x) => ({ ...x, orden: 'ritmo' }) });

	return props.sort((a, b) => b.peso - a.peso).slice(0, 6);
}
