// Estado de la interfaz: la consulta confirmada, una vista previa temporal y la URL.
// Cada cambio confirmado es una entrada del historial del navegador: ⌘Z es «atrás» y ⇧⌘Z, «adelante».

import type { Cartera } from './datos/modelo';
import { consultaInicial, type Consulta, type Filtro, type Frente, type Orden, type Zona } from './datos/consulta';
import type { Agregado, Escala } from './datos/periodos';
import { PRODUCTOS, type ProductoId } from './datos/productos';

/** Niveles de Rumbo: la entrada (elegir organización), la cartera como mapa (plano, tapiz),
 * la organización, la empresa y la metodología. */
export type Vista = 'entrada' | 'plano' | 'tapiz' | 'organizacion' | 'empresa' | 'metodologia';
export type Seccion = 'scoring' | 'productos' | 'acciones' | 'tecnico';
export type Lente = 'score' | 'productos' | 'horizonte';
export const SECCIONES: Seccion[] = ['scoring', 'productos', 'acciones', 'tecnico'];
const PAGINAS: Vista[] = ['organizacion', 'empresa', 'metodologia', 'entrada'];
export const esPagina = (v: Vista) => PAGINAS.includes(v);

export interface Estado {
	vista: Vista;
	/** Vista de cartera a la que se vuelve desde una página. */
	cartera: 'plano' | 'tapiz';
	q: Consulta;
	/** Organización (grupo) abierta. */
	sel: string | null;
	/** Empresa abierta. */
	emp: string | null;
	/** Sección de la organización o de la empresa. */
	sec: Seccion;
	/** Lente de la cartera. */
	lente: Lente;
	hover: string | null;
	zonaHover: Zona | null;
	reproduciendo: boolean;
	/** true mientras se enseña una vista previa sin confirmar. */
	previa: boolean;
}

type Oyente = (e: Estado, antes: Estado) => void;

export class Almacen {
	private base: Estado;
	e: Estado;
	private oyentes = new Set<Oyente>();

	constructor(private c: Cartera) {
		this.base = { vista: 'entrada', cartera: 'plano', q: consultaInicial(c), sel: null, emp: null, sec: 'scoring', lente: 'score', hover: null, zonaHover: null, reproduciendo: false, previa: false };
		this.base = { ...this.base, ...this.leerUrl() };
		// Un grupo que no existe en la URL no rompe nada: se vuelve a la cartera.
		if ((this.base.vista === 'organizacion' || this.base.vista === 'empresa') && !c.groups.some((g) => g.id === this.base.sel)) this.base = { ...this.base, vista: 'entrada', sel: null, emp: null };
		if (this.base.vista === 'empresa' && !this.base.emp) this.base = { ...this.base, vista: 'organizacion' };
		this.e = this.base;
		history.replaceState({ xray: 0 }, '', this.url(this.base));
		addEventListener('popstate', () => {
			const antes = this.e;
			this.base = { ...this.base, ...this.leerUrl(), hover: null, previa: false };
			this.e = this.base;
			this.avisar(antes);
		});
	}

	oir(f: Oyente) { this.oyentes.add(f); return () => this.oyentes.delete(f); }
	private avisar(antes: Estado) { for (const f of this.oyentes) f(this.e, antes); }

	/** Cambio confirmado. `historial`: crea una entrada que se deshace con ⌘Z o «atrás». */
	fijar(parcial: Partial<Estado>, historial = false) {
		const antes = this.e;
		this.base = { ...this.base, ...parcial, previa: false };
		if (this.base.vista === 'plano' || this.base.vista === 'tapiz') this.base.cartera = this.base.vista;
		this.e = this.base;
		const url = this.url(this.base);
		if (url !== location.pathname + location.search) {
			const n = (history.state?.xray as number | undefined) ?? 0;
			if (historial) history.pushState({ xray: n + 1 }, '', url);
			else history.replaceState({ xray: n }, '', url);
		}
		this.avisar(antes);
	}

	/** Cambio de la consulta confirmado, siempre con entrada en el historial. */
	consulta(q: Consulta) { this.fijar({ q }, true); }

	/** Vista previa: se enseña sin confirmar; `null` vuelve a lo confirmado. */
	previsualizar(q: Consulta | null) {
		const antes = this.e;
		this.e = q ? { ...this.base, q, previa: true } : this.base;
		this.avisar(antes);
	}

	/** Estado efímero (hover, zona señalada) que no toca la URL. */
	efimero(parcial: Pick<Partial<Estado>, 'hover' | 'zonaHover' | 'reproduciendo'>) {
		const antes = this.e;
		this.base = { ...this.base, ...parcial };
		this.e = { ...this.e, ...parcial };
		this.avisar(antes);
	}

	get confirmado() { return this.base; }

	/** ⌘Z nunca sale de la aplicación: solo retrocede por los pasos propios del historial. */
	deshacer() { if (((history.state?.xray as number | undefined) ?? 0) > 0) history.back(); }
	rehacer() { history.forward(); }
	get puedeDeshacer() { return ((history.state?.xray as number | undefined) ?? 0) > 0; }

	// ─── URL ───────────────────────────────────────────────
	private url(e: Estado) {
		const q = new URLSearchParams(location.search);
		for (const k of ['v', 'c', 'g', 'emp', 'sec', 'lente', 'e', 'a', 'd', 'h', 'f', 'o', 'z', 'mv', 's', 'p', 't', 'mano', 'gr', 'pr']) q.delete(k);
		q.set('v', e.vista);
		if (e.vista === 'organizacion' || e.vista === 'empresa') {
			q.set('c', e.cartera);
			if (e.sel) q.set('g', e.sel);
			if (e.vista === 'empresa' && e.emp) q.set('emp', e.emp);
			if (e.sec !== 'scoring') q.set('sec', e.sec);
		}
		if ((e.vista === 'plano' || e.vista === 'tapiz') && e.lente !== 'score') q.set('lente', e.lente);
		q.set('e', e.q.escala);
		if (e.q.agregado !== 'cierre') q.set('a', e.q.agregado);
		q.set('d', String(e.q.desde));
		q.set('h', String(e.q.hasta));
		if (e.q.frente !== 'nada') q.set('f', e.q.frente);
		if (e.q.orden !== 'score') q.set('o', e.q.orden);
		for (const f of e.q.filtros) {
			if (f.tipo === 'zona') q.append('z', f.v);
			if (f.tipo === 'mov') q.append('mv', f.v);
			if (f.tipo === 'sector') q.append('s', f.v);
			if (f.tipo === 'pais') q.append('p', f.v);
			if (f.tipo === 'tamano') q.append('t', f.v);
			if (f.tipo === 'mano') q.append('mano', f.v.join(','));
			if (f.tipo === 'grupo') q.append('gr', f.v);
			if (f.tipo === 'producto') q.append('pr', f.modo === 'tiene' ? `${f.v}:tiene` : f.v);
		}
		return `${location.pathname}?${q}`;
	}

	private leerUrl(): Partial<Estado> {
		const q = new URLSearchParams(location.search);
		if (!q.has('v')) return {};
		const ini = consultaInicial(this.c);
		const filtros: Filtro[] = [];
		q.getAll('z').forEach((v) => filtros.push({ tipo: 'zona', v: v as Zona }));
		q.getAll('mv').forEach((v) => filtros.push({ tipo: 'mov', v: v as never }));
		q.getAll('s').forEach((v) => filtros.push({ tipo: 'sector', v }));
		q.getAll('p').forEach((v) => filtros.push({ tipo: 'pais', v }));
		q.getAll('t').forEach((v) => filtros.push({ tipo: 'tamano', v }));
		q.getAll('mano').forEach((v) => filtros.push({ tipo: 'mano', v: v.split(',') }));
		q.getAll('gr').forEach((v) => filtros.push({ tipo: 'grupo', v }));
		q.getAll('pr').forEach((x) => { const [v, modo] = x.split(':'); if (PRODUCTOS.some((p) => p.id === v)) filtros.push({ tipo: 'producto', v: v as ProductoId, modo: modo === 'tiene' ? 'tiene' : 'encaja' }); });
		let vista = (q.get('v') as string) ?? 'entrada';
		if (vista === 'expediente') vista = 'organizacion'; // enlaces de la versión anterior
		const sel = q.get('g');
		const emp = q.get('emp');
		const sec = q.get('sec') as Seccion | null;
		const lente = q.get('lente') as Lente | null;
		const num = (k: string, def: number) => (q.has(k) && !Number.isNaN(Number(q.get(k))) ? Number(q.get(k)) : def);
		const escala = (q.get('e') as Escala) ?? ini.escala;
		return {
			vista: (vista === 'organizacion' || vista === 'empresa') && !sel ? 'entrada' : vista === 'empresa' && !emp ? 'organizacion' : (['entrada', 'plano', 'tapiz', 'organizacion', 'empresa', 'metodologia'].includes(vista) ? vista : 'entrada') as Vista,
			cartera: q.get('c') === 'tapiz' || vista === 'tapiz' ? 'tapiz' : 'plano',
			sel,
			emp,
			sec: sec && SECCIONES.includes(sec) ? sec : 'scoring',
			lente: lente === 'productos' || lente === 'horizonte' ? lente : 'score',
			q: {
				filtros,
				escala,
				agregado: (q.get('a') as Agregado) ?? 'cierre',
				desde: num('d', ini.desde),
				hasta: num('h', ini.hasta),
				frente: (q.get('f') as Frente) ?? 'nada',
				orden: (q.get('o') as Orden) ?? 'score',
			},
		};
	}
}
