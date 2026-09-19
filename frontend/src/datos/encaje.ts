// Qué productos encajan a una entidad, sin umbrales inventados (propuesta 07, §6.2):
//   · la NECESIDAD la dice el motor: sus acciones del mes (palanca, de cuánto a cuánto, subida);
//   · el INSTRUMENTO lo pone el catálogo: qué producto resuelve cada palanca;
//   · lo CONTRATADO (products/<id>.json) decide la forma: contratar, ampliar o usarlo más.
// Los únicos umbrales son los del manifiesto (bandas) y los hechos del motor (papel, liquidez
// heredada, abstención, feed vivo). El efecto sobre el score es siempre el de la acción del motor.

import type { AccionM, AtributoM, Manifiesto, MesM, ProductoId, ProductosEmpresaM, TenenciaM } from './contrato';
import { f } from './formato';
import { PRODUCTOS } from './productos';
import { palanca, tituloAccion, voz, type Palanca } from './redaccion';

export type Estado = 'tiene' | 'encaja' | 'bloqueado' | 'no_consta';
export type Forma = 'contratar' | 'ampliar' | 'usar_mas' | 'siguiente_nivel';

export interface EstadoProducto {
	id: ProductoId;
	estado: Estado;
	tiene: boolean;
	/** Si además de tenerlo le conviene hacer algo con él. */
	forma?: Forma;
	/** Por qué encaja (o por qué lo tiene), en una frase. */
	motivo: string;
	/** Si encaja pero hoy no conviene ofrecerlo. */
	bloqueo?: string;
	/** La acción del motor que resuelve, si la hay: de ahí sale el efecto. */
	accion?: AccionM;
	/** Si el producto no mueve el score, se dice. */
	sinEfecto?: string;
	/** Un dato corto de uso («al 94 % de su límite», «deducido de 14 movimientos»). */
	dato?: string;
}

/** Qué producto resuelve cada palanca del motor. La cobertura y la deuda no tienen producto de los siete. */
export const PRODUCTOS_DE_PALANCA: Record<Palanca, ProductoId[]> = {
	'liquidity-buffer': ['linea_credito'],
	'collections-speed': ['factoring'],
	'payments-punctuality': ['confirming'],
	'activity-coverage': [],
	'debt-burden': [],
};

export const PALANCA_PROPIA: Record<Palanca, string | null> = {
	'liquidity-buffer': null,
	'collections-speed': null,
	'payments-punctuality': null,
	'activity-coverage': 'Palanca del negocio: más ventas cobradas o menos gasto. No la resuelve un producto financiero.',
	'debt-burden': 'Refinanciar a más plazo o amortizar lo más caro. No está entre los siete productos.',
};

export interface Hechos {
	mes: MesM;
	man: Manifiesto;
	tenencia: TenenciaM[];
	perfil: AtributoM[];
	/** Papel en el grupo (companies) o null en un grupo. */
	papel?: string | null;
	heredaLiquidez?: boolean;
}

const atributo = (perfil: AtributoM[], clave: string) => perfil.find((a) => a.key === clave)?.value ?? null;

/** Dato corto de lo contratado. */
export function datoTenencia(t: TenenciaM): string {
	const ev = Array.isArray(t.evidence) ? t.evidence : [t.evidence];
	if (t.source === 'movimientos') {
		const e = ev[0];
		return e?.rows ? `deducido de ${f.plural(e.rows, 'movimiento', 'movimientos')}` : 'deducido de sus movimientos';
	}
	const validos = t.items.filter((i) => !i.inconsistent);
	const concedido = validos.reduce((s, i) => s + (i.granted ?? 0), 0);
	const dispuesto = validos.reduce((s, i) => s + (i.outstanding ?? 0), 0);
	if (t.product === 'linea_credito' && concedido > 0) return `${validos.length > 1 ? `${validos.length} líneas, ` : ''}al ${f.porcentaje(dispuesto / concedido, 0)} de ${f.eurosCorto(concedido)}`;
	if ((t.product === 'factoring' || t.product === 'confirming') && concedido > 0) return `${f.eurosCorto(dispuesto)} de ${f.eurosCorto(concedido)}`;
	const saldo = t.items.reduce((s, i) => s + ((i as { balance?: number | null }).balance ?? 0), 0);
	if (saldo > 0) return `saldo de ${f.eurosCorto(saldo)}`;
	return t.items.length > 1 ? `${t.items.length} contratos` : 'declarado por el banco';
}

/** El estado de los siete productos para una entidad en su mes de corte. */
export function estadosProductos(h: Hechos): EstadoProducto[] {
	const { mes, man } = h;
	const acciones = mes.actions ?? [];
	const accion = (p: Palanca) => acciones.find((a) => palanca(a) === p);
	const tiene = (id: ProductoId) => h.tenencia.find((t) => t.product === id);
	const solido = man.bands.find((b) => b.key === 'solid')?.min ?? null;
	const liquidez = mes.pillars.find((p) => p.key === 'liquidity');
	const concentrada = /concentrad/i.test(atributo(h.perfil, 'customer_concentration') ?? '');
	const financiadaPorGrupo = h.heredaLiquidez || /financiada por el grupo|caja barrida/i.test(`${h.papel ?? ''} ${atributo(h.perfil, 'financing_profile') ?? ''}`);

	// Bloqueos generales: hechos del motor.
	const bloqueoGeneral = mes.abstain
		? `El motor se abstiene este mes (${man.glossary.reasons[mes.abstain.reason] ?? mes.abstain.reason}): ${voz('no hay veredicto con el que ofrecer nada', 'sin veredicto no podemos recomendarte nada')}.`
		: !mes.feed_live ? 'Los datos del banco no están al día: el efecto no se puede medir.' : null;

	const salida: EstadoProducto[] = [];
	for (const p of PRODUCTOS) {
		const t = tiene(p.id);
		const base = { id: p.id, tiene: !!t, dato: t ? datoTenencia(t) : undefined } as EstadoProducto;
		let e: EstadoProducto | null = null;
		const palancaDe = (Object.keys(PRODUCTOS_DE_PALANCA) as Palanca[]).find((k) => PRODUCTOS_DE_PALANCA[k].includes(p.id));
		const a = palancaDe ? accion(palancaDe) : undefined;

		if (a) {
			const forma: Forma = t ? (p.id === 'linea_credito' ? 'ampliar' : 'usar_mas') : 'contratar';
			const motivo = forma === 'ampliar'
				? `Ya ${voz('tiene', 'tienes')} ${t ? datoTenencia(t) : 'línea'} y aun así el motor pide: ${minuscula(tituloAccion(a))}.`
				: forma === 'usar_mas'
					? `Ya lo ${voz('tiene', 'tienes')}; el motor pide: ${minuscula(tituloAccion(a))}. Toca pasar más operaciones por él.`
					: `El motor pide: ${minuscula(tituloAccion(a))}.`;
			e = { ...base, estado: t ? 'tiene' : 'encaja', forma, motivo, accion: a };
			if (p.id === 'linea_credito' && h.heredaLiquidez) e = { ...e, estado: t ? 'tiene' : 'bloqueado', bloqueo: `La liquidez la lleva el grupo: se decide en ${voz('su tesorería', 'la tesorería del grupo')}, no en esta empresa.` };
		} else if (p.id === 'seguro_credito' && concentrada) {
			const ev = h.perfil.find((x) => x.key === 'customer_concentration')?.evidence;
			e = { ...base, estado: t ? 'tiene' : 'encaja', forma: t ? undefined : 'contratar', motivo: ev ?? 'Depende de un cliente principal.', sinEfecto: 'No mueve el score: cubre el riesgo del cliente principal.' };
		} else if (p.familia === 'inversion' && solido !== null && liquidez?.score != null && liquidez.score >= solido && !accion('liquidity-buffer')) {
			// Excedente: pilar de liquidez en nivel sólido (umbral de banda del manifiesto) y ninguna acción de colchón.
			const niveles = PRODUCTOS.filter((x) => x.familia === 'inversion');
			const siguiente = niveles.find((x) => !tiene(x.id));
			const esElSiguiente = siguiente?.id === p.id;
			const pensionesPermitidas = p.id !== 'plan_pensiones' || (mes.band === 'solid' && mes.conf.label === 'high');
			if (t) e = { ...base, estado: 'tiene', motivo: voz('Lo tiene: su caja ya rinde.', 'Lo tienes: tu caja ya rinde.') };
			else if (esElSiguiente && pensionesPermitidas) {
				e = { ...base, estado: 'encaja', forma: tiene(niveles[0].id) ? 'siguiente_nivel' : 'contratar',
					motivo: `Liquidez en nivel ${man.bands.find((b) => b.key === 'solid')?.label.toLowerCase()} (${f.score(liquidez.score)} puntos) y ninguna acción de colchón: hay excedente.`,
					sinEfecto: voz('No cambia su rumbo: lo consolida.', 'No cambia tu rumbo: lo consolida.') };
			}
		}
		if (!e && t) e = { ...base, estado: 'tiene', motivo: t.source === 'movimientos' ? voz('Se ve en sus movimientos.', 'Se ve en tus movimientos.') : 'Declarado por el banco.' };
		if (!e) e = { ...base, estado: 'no_consta', motivo: voz('Ni lo tiene según los datos ni el motor pide lo que resuelve.', 'Ni lo tienes según los datos ni el motor pide lo que resuelve.') };
		if (bloqueoGeneral && e.estado === 'encaja') e = { ...e, estado: 'bloqueado', bloqueo: bloqueoGeneral };
		salida.push(e);
	}
	void financiadaPorGrupo;
	return salida;
}

/** Cada acción del motor con los productos que la resuelven y, si no hay producto, su palanca propia. */
export interface Recomendacion {
	accion: AccionM;
	productos: ProductoId[];
	propia: string | null;
	/** En filiales que financia el grupo, la cobertura se decide arriba. */
	delGrupo: boolean;
}

export function recomendaciones(h: Hechos): Recomendacion[] {
	const financiadaPorGrupo = h.heredaLiquidez || /financiada por el grupo|caja barrida|sin actividad operativa/i.test(`${h.papel ?? ''} ${h.perfil.find((x) => x.key === 'financing_profile')?.value ?? ''}`);
	return (h.mes.actions ?? []).map((a) => {
		const p = palanca(a);
		return { accion: a, productos: PRODUCTOS_DE_PALANCA[p] ?? [], propia: PALANCA_PROPIA[p] ?? null, delGrupo: financiadaPorGrupo && p === 'activity-coverage' };
	});
}

const minuscula = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

/** Para la cartera y el filtro «a los que les encaja»: con las acciones del grupo y lo que tienen sus empresas. */
export function encajaAGrupo(acciones: AccionM[] | undefined, tenenciaGrupo: Partial<Record<ProductoId, number>> | undefined, id: ProductoId): boolean {
	const pal = (Object.keys(PRODUCTOS_DE_PALANCA) as Palanca[]).find((k) => PRODUCTOS_DE_PALANCA[k].includes(id));
	if (!pal) return false;
	return (acciones ?? []).some((a) => palanca(a) === pal) && (id === 'linea_credito' || !(tenenciaGrupo?.[id]));
}

export type { ProductosEmpresaM };
