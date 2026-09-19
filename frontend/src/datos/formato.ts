// Formato es-ES de Rumbo, según las reglas del equipo (docs/UI_FORMATTING.mdx en main):
// coma decimal y punto de miles; «1.234,56 €» con espacio fino no separable; «1,2 M€» y «185 k€»;
// «42,5 %»; «19 días»; meses con nombre («septiembre de 2026») y en el eje «09/26».

import { nombreEmpresa, nombreGrupo } from './nombres';

const NBSP = ' ';
const nf = (min: number, max: number, signo = false) =>
	new Intl.NumberFormat('es-ES', { minimumFractionDigits: min, maximumFractionDigits: max, signDisplay: signo ? 'exceptZero' : 'auto', useGrouping: true });
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/** Intl.NumberFormat no agrupa los miles en es-ES con cuatro cifras: «1234». La regla del equipo quiere «1.234». */
function agrupar(texto: string) {
	return texto.replace(/^([-+−]?)(\d{4})(?=[,\s]|$)/, (_, s: string, d: string) => `${s}${d[0]}.${d.slice(1)}`);
}

export const f = {
	numero: (v: number | null | undefined, dec = 0) => (v === null || v === undefined || Number.isNaN(v) ? '—' : agrupar(nf(0, dec).format(v))),
	fijo: (v: number, dec: number) => agrupar(nf(dec, dec).format(v)),
	signo: (v: number, dec = 1) => agrupar(nf(0, dec, true).format(v)).replace('-', '−'),
	euros: (v: number | null | undefined, dec = 0) => (v === null || v === undefined ? '—' : `${agrupar(nf(0, dec).format(v))}${NBSP}€`),
	eurosCorto: (v: number | null | undefined) => {
		if (v === null || v === undefined) return '—';
		const a = Math.abs(v);
		if (a >= 1e6) return `${nf(0, 1).format(v / 1e6)}${NBSP}M€`;
		if (a >= 1e3) return `${nf(0, 0).format(v / 1e3)}${NBSP}k€`;
		return `${nf(0, 0).format(v)}${NBSP}€`;
	},
	/** Importe en una unidad fija y sin sufijo: la unidad vive en la cabecera de la columna
	 *  cuando se repite en todas las filas (docs/DESIGN_UX.mdx, «Tablas»). */
	eurosEn: (v: number | null | undefined, unidad: '€' | 'k€' | 'M€') => {
		if (v === null || v === undefined) return '—';
		const escala = unidad === 'M€' ? 1e6 : unidad === 'k€' ? 1e3 : 1;
		return nf(0, unidad === 'M€' ? 1 : 0).format(v / escala);
	},
	porcentaje: (ratio: number | null | undefined, dec = 1) => (ratio === null || ratio === undefined ? '—' : `${nf(0, dec).format(ratio * 100)}${NBSP}%`),
	puntosPorcentaje: (v: number, dec = 1) => `${nf(0, dec).format(v)}${NBSP}%`,
	dias: (v: number | null | undefined) => {
		if (v === null || v === undefined) return '—';
		const n = Math.round(v);
		return `${agrupar(nf(0, 0).format(n))}${NBSP}${Math.abs(n) === 1 ? 'día' : 'días'}`;
	},
	ratio: (v: number | null | undefined) => (v === null || v === undefined ? '—' : nf(2, 2).format(v)),
	/** Score en décimas → puntos enteros. */
	score: (decimas: number | null | undefined) => (decimas === null || decimas === undefined ? '—' : String(Math.round(decimas / 10))),
	/** Score en décimas → puntos con un decimal (cascada, donde tiene que cuadrar). */
	scoreDec: (decimas: number | null | undefined) => (decimas === null || decimas === undefined ? '—' : nf(1, 1).format(decimas / 10)),
	/** Diferencia en décimas → «+2,1» / «−0,4». */
	delta: (decimas: number) => nf(1, 1, true).format(decimas / 10).replace('-', '−'),
	deltaEntero: (decimas: number) => nf(0, 0, true).format(Math.round(decimas / 10)).replace('-', '−'),
	mes: (iso: string) => { const [a, m] = iso.split('-').map(Number); return `${MESES[m - 1]} de ${a}`; },
	mesCorto: (iso: string) => { const [a, m] = iso.split('-').map(Number); return `${MESES_CORTOS[m - 1]} ${a}`; },
	mesEje: (iso: string) => { const [a, m] = iso.split('-'); return `${m}/${a.slice(2)}`; },
	/** «2026-06-03..2026-08-31» o «2026-03..2026-08» → «de marzo a agosto de 2026». */
	periodo: (p: string) => {
		if (!p) return '—';
		const [a, b] = p.split('..');
		const mesDe = (s: string) => s.slice(0, 7);
		if (!b) return /^\d{4}-\d{2}$/.test(a) ? f.mes(a) : a;
		const ma = mesDe(a), mb = mesDe(b);
		if (ma === mb) return f.mes(ma);
		const [aa] = ma.split('-'), [ab] = mb.split('-');
		const nombre = (s: string) => MESES[Number(s.split('-')[1]) - 1];
		return aa === ab ? `de ${nombre(ma)} a ${nombre(mb)} de ${ab}` : `de ${f.mes(ma)} a ${f.mes(mb)}`;
	},
	grupo: nombreGrupo,
	empresa: nombreEmpresa,
	plural: (n: number, uno: string, varios: string) => `${f.numero(n)} ${n === 1 ? uno : varios}`,
	/** Valor de una fila de evidencia con su unidad del motor. */
	valorUnidad: (v: number | string | null, unidad: string) => {
		if (v === null || v === undefined) return '—';
		if (typeof v === 'string') return v;
		switch (unidad) {
			case 'EUR': return f.euros(v);
			case 'días': return `${nf(0, 1).format(v)}${NBSP}días`;
			case 'ratio': return nf(2, 2).format(v);
			case 'cuota': return f.porcentaje(v);
			case 'proporción': return f.porcentaje(v);
			case 'facturas': return f.plural(Math.round(v), 'factura', 'facturas');
			case 'meses': return f.plural(Math.round(v), 'mes', 'meses');
			case 'puntos': return `${nf(0, 1).format(v)}${NBSP}puntos`;
			case '': return agrupar(nf(0, 2).format(v));
			default: return `${agrupar(nf(0, 2).format(v))}${NBSP}${unidad}`;
		}
	},
};

export const primeraMayuscula = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
