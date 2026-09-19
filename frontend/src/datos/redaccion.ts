// La voz de Rumbo: frases cortas y el formato del equipo. Habla de la empresa en tercera persona
// cuando mira Embat, y de tú cuando mira el CFO de su grupo: es su dinero, no el de un tercero.
// Las acciones del motor traen campos (palanca, de cuánto a cuánto, unidad) y un texto propio en
// segunda persona; aquí se redactan de nuevo a partir de los campos. El texto del motor se conserva
// para la sección técnica.

import type { AccionM, AlertaM, Manifiesto, MesM } from './contrato';
import { f } from './formato';

export type Palanca = 'liquidity-buffer' | 'payments-punctuality' | 'collections-speed' | 'activity-coverage' | 'debt-burden';

/** Tipo de palanca: el id del motor es «<pilar>-<clase>», estable entre meses. */
export const palanca = (a: AccionM) => a.id as Palanca;

export interface Importe {
	/** Euros. */
	valor: number;
	/** «de una vez» (colchón), «al mes» (cobertura), «al año» (deuda). */
	cada: 'una vez' | 'mes' | 'año';
	sentido: 'más caja o líneas' | 'más cobros' | 'menos pagos' | 'menos cuotas';
}

let tuteo = false;
/** Fija la voz: `true` cuando Rumbo se dirige al CFO de la empresa que enseña. */
export const fijarVoz = (tu: boolean) => { tuteo = tu; };
/** El par de la misma frase: la de Embat y la del CFO. */
export const voz = (deEl: string, deTu: string) => (tuteo ? deTu : deEl);

const numeroMotor = (s: string) => Number(s.replace(/\./g, '').replace(',', '.'));

/**
 * El importe de una acción. El motor todavía no lo exporta como campo: se lee de su texto, y la
 * sección técnica lo dice. Devuelve [] si el texto no lo trae.
 */
export function importes(a: AccionM): Importe[] {
	const t = a.detail;
	let m: RegExpMatchArray | null;
	switch (palanca(a)) {
		case 'liquidity-buffer':
			m = t.match(/unos ([\d.]+) EUR más entre caja/);
			return m ? [{ valor: numeroMotor(m[1]), cada: 'una vez', sentido: 'más caja o líneas' }] : [];
		case 'activity-coverage':
			m = t.match(/unos ([\d.]+) EUR más de cobros al mes o ([\d.]+) EUR menos de pagos al mes/);
			return m ? [{ valor: numeroMotor(m[1]), cada: 'mes', sentido: 'más cobros' }, { valor: numeroMotor(m[2]), cada: 'mes', sentido: 'menos pagos' }] : [];
		case 'debt-burden':
			m = t.match(/unos ([\d.]+) EUR menos al año/);
			return m ? [{ valor: numeroMotor(m[1]), cada: 'año', sentido: 'menos cuotas' }] : [];
		default:
			return [];
	}
}

/** Titular de la acción, en infinitivo y con sus cifras. */
export function tituloAccion(a: AccionM): string {
	const de = a.current, a_ = a.target;
	switch (palanca(a)) {
		case 'liquidity-buffer':
			return `Subir el colchón de caja de ${f.dias(Math.max(0, de))} a ${f.dias(a_)}`;
		case 'collections-speed':
			return a_ <= 0.5 ? `Cobrar a ${voz('sus', 'tus')} clientes al vencimiento (hoy, ${f.dias(de)} tarde)` : `Cobrar ${f.dias(de - a_)} antes (de ${f.dias(de)} de retraso a ${f.dias(a_)})`;
		case 'payments-punctuality':
			return a_ <= 0.5 ? `Pagar a ${voz('sus', 'tus')} proveedores al vencimiento (hoy, ${f.dias(de)} tarde)` : `Pagar a proveedores ${f.dias(de - a_)} antes (de ${f.dias(de)} de retraso a ${f.dias(a_)})`;
		case 'activity-coverage':
			return `Que los cobros cubran ${f.ratio(a_)} veces los pagos (hoy, ${f.ratio(de)})`;
		case 'debt-burden':
			return `Bajar el peso de la deuda del ${f.puntosPorcentaje(de)} al ${f.puntosPorcentaje(a_)} de los cobros`;
		default:
			return a.title;
	}
}

/** Una frase que explica el porqué y el cuánto. */
export function explicacionAccion(a: AccionM): string {
	const imp = importes(a);
	switch (palanca(a)) {
		case 'liquidity-buffer':
			return imp.length ? `${voz('Le hacen', 'Te hacen')} falta unos ${f.euros(imp[0].valor)} más entre caja y líneas sin disponer, a fin de mes y en el peor día del mes.` : 'Más caja o más línea sin disponer, a fin de mes y en el peor día del mes.';
		case 'collections-speed':
			return `${voz('Sus', 'Tus')} clientes pagan tarde, ponderado por importe. Recordatorios, anticipo de facturas o domiciliación acortan el ciclo de caja.`;
		case 'payments-punctuality':
			return `${voz('Paga tarde a sus proveedores', 'Pagas tarde a tus proveedores')}, ponderado por importe. Empezar por las facturas grandes mejora la puntualidad y puede levantar el tope que limita el score.`;
		case 'activity-coverage':
			return imp.length === 2 ? `Supone unos ${f.euros(imp[0].valor)} más de cobros al mes o ${f.euros(imp[1].valor)} menos de pagos al mes.` : 'Más cobros operativos o menos pagos cada mes.';
		case 'debt-burden':
			return imp.length ? `Supone pagar unos ${f.euros(imp[0].valor)} menos al año en cuotas e intereses: refinanciar a más plazo o amortizar lo más caro.` : 'Menos cuotas e intereses: refinanciar a más plazo o amortizar lo más caro.';
		default:
			return a.detail;
	}
}

export const ESFUERZO: Record<AccionM['effort'], string> = { bajo: 'esfuerzo bajo', medio: 'esfuerzo medio', alto: 'esfuerzo alto' };

/** Una línea por aviso del motor. `umbralCritico` sale de los parámetros. */
export function lineaAvisoM(a: AlertaM, man: Manifiesto, umbralCritico: number | null): string {
	switch (a.kind) {
		case 'level_critical': return umbralCritico !== null ? `Baja de ${f.numero(umbralCritico)} puntos: nivel crítico (${f.score(a.shown)})` : `Nivel crítico (${f.score(a.shown)})`;
		case 'deterioration_structural': return `Deterioro confirmado (${f.score(a.shown)})`;
		case 'improvement_structural': return `Mejora confirmada (${f.score(a.shown)})`;
		case 'deterioration_drift': return `Deriva lenta a la baja (${f.score(a.shown)})`;
		case 'improvement_drift': return `Deriva lenta al alza (${f.score(a.shown)})`;
		case 'cap_fired': return `Salta un tope y limita el score (${f.score(a.shown)})`;
		case 'stale_feed': return 'Los datos del banco dejan de llegar';
		default: return a.title || man.glossary.flags[a.kind] || a.kind;
	}
}

export const ESTADO_AVISO: Record<AlertaM['state'], string> = { fired: 'disparado', suppressed: 'silenciado', abstained: 'sin veredicto' };

/** Movimiento en palabras, con la misma lógica que el sello. */
export function movimiento(m: MesM): string {
	const v = m.verdict;
	if (!v.available) return 'sin veredicto';
	if (v.direction === 'perimeter_shift') return 'cambio de perímetro';
	if (v.direction === 'stable') return v.nature === 'bump' ? 'estable, tras un bache' : 'estable';
	const dir = v.direction === 'improving' ? 'sube' : 'baja';
	if (v.nature === 'shock_pending') return `${dir}, por confirmar`;
	if (v.nature === 'structural') return v.detected_since ? `${dir} desde ${f.mes(v.detected_since)}` : `${dir}, confirmado`;
	return dir;
}

/** Palabra de banda desde el manifiesto (nunca escrita a mano). */
export const nombreBanda = (man: Manifiesto, b: string | null | undefined) => man.bands.find((x) => x.key === b)?.label ?? '—';
export const nombrePilar = (man: Manifiesto, p: string) => man.pillars.find((x) => x.key === p)?.label ?? p;
