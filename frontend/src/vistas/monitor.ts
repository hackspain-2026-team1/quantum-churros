// El monitor de la portada (propuesta 08). De arriba abajo:
//   · la cabeza: la rosa de los vientos (sus puntas, las zonas del plano; la aguja, hacia donde va la
//     cartera) y el estado del mes, con cada cifra como filtro;
//   · un solo campo: «rumbo de ¿qué organización?» abre una organización; cualquier otra cosa se
//     entiende como una vista (palabras clave al instante, Jev para afinar);
//   · dos columnas: las que piden atención, en orden de gravedad, y los avisos del mes;
//   · la vista: siete formas (ranking, bandas, plano, tapiz, flujo, avisos, horizonte), cada una en
//     arena o en tabla, por organizaciones o por empresas, con su orden y sus filtros en la URL.

import { disponer, margen, type BandaA, type DatosVista, type Disposicion, type EntArena } from '../arena/vistas';
import { carga } from '../datos/carga';
import type { EntidadesM, Manifiesto } from '../datos/contrato';
import { PAISES, type Zona } from '../datos/consulta';
import { f, primeraMayuscula } from '../datos/formato';
import { porJev, porPalabras, aplicar, URL_VISTA, type Campo, type Interpretacion } from '../datos/interpretar';
import type { Cartera } from '../datos/modelo';
import {
	BANDAS, ESTADO_INICIAL, FORMAS, MOVIMIENTOS_M, ORDENES, TIPOS_AVISO, atencion, entidades, escribirEstadoURL, flujo, leerEstadoURL, nombreBandaM, ordenar, pasa,
	piezasFiltro, resumen, vocabulario, type Entidad, type EstadoMonitor, type FiltrosM, type Resumen, type Unidad,
} from '../datos/monitorCartera';
import { producto, PRODUCTOS } from '../datos/productos';
import { claveDeMirada } from '../datos/redaccion';
import { conCifras } from './cifras';
import { cola, h, vaciar } from './dom';
import { desplegable } from './desplegable';
import { logotipo } from './marca';
import { placa } from './registro';
import { triaje } from './triaje';

export interface CtxMonitor {
	c: Cartera;
	man: Manifiesto;
	corte(): string;
	/** El grupo del CFO cuando se mira desde su silla; null cuando lo mira Embat. */
	cfo(): string | null;
	abrirGrupo(id: string): void;
	abrirEmpresa(grupo: string, id: string): void;
	irMapa(v: 'plano' | 'tapiz', est: EstadoMonitor): void;
	repintarArena(): void;
	esMovil(): boolean;
	metodologia(): void;
}

const NOMBRE_ZONA: Record<Zona, string> = { solida: 'sólidas', mejora: 'mejoran', tuerce: 'se tuercen', hunde: 'se hunden' };
const UNIDAD: Record<Unidad, [string, string]> = { organizaciones: ['organización', 'organizaciones'], empresas: ['empresa', 'empresas'] };
const MESES_TAPIZ = 24, MESES_AVISOS = 12;
const CLAVE_VISTAS = () => claveDeMirada('rumbo.vistas.v1');

const leerVistas = (): { nombre: string; estado: EstadoMonitor }[] => { try { return JSON.parse(localStorage.getItem(CLAVE_VISTAS()) ?? '[]'); } catch { return []; } };
const guardarVistas = (v: { nombre: string; estado: EstadoMonitor }[]) => { try { localStorage.setItem(CLAVE_VISTAS(), JSON.stringify(v)); } catch { /* sin almacenamiento: vale para la sesión */ } };

export interface Monitor {
	raiz: HTMLElement;
	/** Lleva a la bandeja de avisos. */
	irAvisos(): void;
	/** La versión para imprimir: el estado, las que piden atención, los avisos y la vista elegida. */
	informe(): HTMLElement;
}

export function crearMonitor(ctx: CtxMonitor): Monitor {
	const { c, man } = ctx;
	let est: EstadoMonitor = leerEstadoURL();
	let indice: EntidadesM | null = null;
	const t = () => c.months.indexOf(ctx.corte());
	const cache = new Map<string, Entidad[]>();
	// El CFO mira sus empresas, y solo las suyas: el universo se recorta, no se filtra.
	const cfo = () => ctx.cfo();
	const grupoCFO = () => (cfo() ? c.groups.find((g) => g.id === cfo()) ?? null : null);
	if (cfo()) est = { ...est, unidad: 'empresas', filtros: { ...est.filtros, producto: undefined, sector: undefined, pais: undefined, grupo: undefined } };
	// Un grupo de una o dos empresas no es una cartera: ni rosa, ni buscador, ni siete formas.
	const reducido = () => (grupoCFO()?.n_companies ?? 99) <= 2;
	const FORMAS_POCAS = ['avisos', 'horizonte', 'tapiz'];
	if (reducido() && est.forma === 'ranking') est = { ...est, forma: 'avisos', modo: 'tabla' };
	const todas = (u: Unidad = est.unidad) => {
		const k = `${u}|${t()}|${indice ? 1 : 0}|${cfo() ?? ''}`;
		if (!cache.has(k)) cache.set(k, entidades(c, u, t(), indice, cfo()));
		return cache.get(k)!;
	};
	const visibles = () => ordenar(todas().filter((e) => pasa(c, e, est.filtros, t())), est.orden);
	// Lo que se manda a Jev también se acota: los sectores y países de la cartera son de Embat.
	const vocab = (() => {
		const v = vocabulario(c);
		const g = cfo() ? c.groups.find((x) => x.id === cfo()) : null;
		return g ? { ...v, sectores: [g.industry].filter((x): x is string => !!x), paises: [g.country].filter((x): x is string => !!x) } : v;
	})();
	// En la cartera, una empresa se nombra con su grupo detrás; en su propio grupo, el grupo sobra.
	const nombreEnt = (e: Entidad) => (e.kind === 'company' && !cfo() ? `${e.nombre} · ${f.grupo(e.grupo)}` : e.nombre);
	const abrir = (e: Entidad) => (e.kind === 'group' ? ctx.abrirGrupo(e.id) : ctx.abrirEmpresa(e.grupo, e.id));

	const raiz = h('article', { class: 'entrada portada-monitor' });
	const cabeza = h('div', { class: 'mon-cabeza' });
	const campo = h('div', { class: 'mon-campo' });
	const columnas = h('div', { class: 'mon-columnas' });
	const vistaSec = h('section', { class: 'mon-vista', 'aria-label': 'Las entidades' });
	const pie = h('p', { class: 'entrada-lema' });
	const masAbajo = h('button', { type: 'button', class: 'mon-mas-abajo' }, h('span', {}, ctx.cfo() ? 'Piden atención, avisos y tus empresas' : 'Piden atención, avisos y la cartera'), h('span', { class: 'mon-flecha', 'aria-hidden': 'true' }, '↓'));
	masAbajo.addEventListener('click', () => columnas.scrollIntoView({ behavior: 'smooth', block: 'start' }));
	// Primero el monitor y luego lo que se busca; con un filtro puesto, la cartera sube por encima.
	raiz.append(cabeza, columnas, campo, vistaSec, pie, masAbajo);
	const colocar = () => raiz.insertBefore(columnas, Object.values(est.filtros).some(Boolean) ? pie : campo);
	// La pista se va en cuanto se baja un poco (la página se desplaza dentro de su contenedor).
	requestAnimationFrame(() => {
		const cont = raiz.parentElement;
		const mirar = () => masAbajo.classList.toggle('fuera', !!cont && cont.scrollTop > 60);
		cont?.addEventListener('scroll', mirar, { passive: true });
	});

	// El índice de entidades trae el tamaño de cada empresa; se lee una vez.
	void carga.entidades().then((ix) => { indice = ix; cache.clear(); if (est.unidad === 'empresas') pintarTodo(); });

	function cambiar(parcial: Partial<EstadoMonitor>) {
		const antes = est.unidad;
		const filtro = parcial.filtros !== undefined;
		est = { ...est, ...parcial, filtros: parcial.filtros ?? est.filtros };
		escribirEstadoURL(est);
		pintarCabeza();
		if (est.unidad !== antes) pintarColumnas();
		pintarVista();
		if (filtro) vistaSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
		ctx.repintarArena();
	}
	const filtrar = (fl: FiltrosM) => cambiar({ filtros: { ...est.filtros, ...fl } });

	// ─── Cabeza: la rosa y el estado del mes ───────────────
	let res: Resumen = resumen(todas());
	function pintarCabeza() {
		res = resumen(todas());
		vaciar(cabeza);
		const r = res;
		const rosaCaja = h('div', { class: 'mon-rosa' });
		const rosa = h('div', { class: 'entrada-rosa', 'aria-hidden': 'true' });
		placa(rosa, (cj) => {
			// La aguja: hacia la derecha si la media está por encima del corte de 60, hacia arriba si el ritmo medio sube.
			const x = Math.max(-1, Math.min(1, ((r.media ?? 60) - 60) / 25)), y = Math.max(-1, Math.min(1, (r.ritmoMedio ?? 0) / 1.5));
			return { tipo: 'rosa', cx: cj.x + cj.w / 2, cy: cj.y + cj.h / 2, r: Math.min(cj.w, cj.h) * 0.36, zonas: r.zonas, aguja: Math.atan2(x, y || 0.0001) };
		});
		rosaCaja.append(rosa);
		if (reducido()) rosaCaja.classList.add('sin-rosa');
		for (const [z, clase] of (reducido() ? [] : [['solida', 'ne'], ['tuerce', 'se'], ['hunde', 'so'], ['mejora', 'no']]) as [Zona, string][]) {
			const b = h('button', { type: 'button', class: `rosa-zona ${clase} ${est.filtros.zona === z ? 'activa' : ''}`, title: `Quedarse con las que ${NOMBRE_ZONA[z]}` }, h('b', {}, f.numero(r.zonas[z])), ` ${NOMBRE_ZONA[z]}`);
			b.addEventListener('click', () => filtrar({ zona: est.filtros.zona === z ? undefined : z }));
			rosaCaja.append(b);
		}
		const cifra = (texto: string, fl: FiltrosM | null, titulo?: string) => {
			if (!fl) return h('span', {}, texto);
			const b = h('button', { type: 'button', class: 'mon-cifra', title: titulo ?? 'Quedarse con estas' }, texto);
			b.addEventListener('click', () => filtrar(fl));
			return b;
		};
		const [uno, varias] = UNIDAD[est.unidad];
		const bandas = BANDAS.slice().reverse().filter(() => true);
		const lineaBandas = h('p', { class: 'mon-linea' });
		BANDAS.forEach((b, i) => {
			const d = r.bandas[b];
			if (i) lineaBandas.append(' · ');
			lineaBandas.append(cifra(`${f.numero(d.n)} en ${nombreBandaM(c, b).toLowerCase()}`, { banda: b }));
			if (b === 'critical' && (d.entran || d.salen)) lineaBandas.append(h('span', { class: 'mon-mov' }, ` (${f.numero(d.entran)} ${d.entran === 1 ? 'entra' : 'entran'}, ${f.numero(d.salen)} ${d.salen === 1 ? 'sale' : 'salen'})`));
		});
		void bandas;
		const lineaMes = h('p', { class: 'mon-linea' },
			cifra(`${f.plural(r.cambian, `${uno} cambia`, `${varias} cambian`)} de banda`, { mov: undefined }, 'Ver el flujo entre bandas'), ': ',
			cifra(`${f.numero(r.bajan)} bajan`, { mov: 'baja_banda' }), ' y ', cifra(`${f.numero(r.suben)} suben`, { mov: 'sube_banda' }), ' · ',
			cifra(`${f.numero(r.caen3)} caen tres puntos o más`, { mov: 'cae' }), ' · ',
			cifra(`${f.numero(r.haciaCritico)} van hacia crítico`, { mov: 'hacia_critico' }, 'Con un 50 % o más de probabilidad de estar en crítico dentro de seis meses'), ' · ',
			cifra(`${f.plural(r.avisos, 'aviso', 'avisos')}`, { mov: 'avisos' }),
			r.sinScore ? h('span', { class: 'mon-mov' }, ` · ${f.numero(r.sinScore)} sin score este mes`) : null);
		// «cambian de banda» abre el flujo, no un filtro.
		(lineaMes.firstChild as HTMLElement).addEventListener('click', (ev) => { ev.stopImmediatePropagation(); cambiar({ forma: 'flujo' }); }, true);
		// Los mapas son de la cartera entera: no existen para el CFO.
		const mapas = h('div', { class: 'mon-mapas' });
		if (!cfo()) for (const [v, t2, d2] of [['plano', 'Abrir el plano', 'nivel y ritmo, a pantalla completa'], ['tapiz', 'Abrir el tapiz', 'cada organización, mes a mes']] as const) {
			const b = h('button', { type: 'button', class: 'mapa-btn' }, h('b', {}, t2), h('span', {}, d2));
			b.addEventListener('click', () => ctx.irMapa(v, { ...est, filtros: est.unidad === 'organizaciones' ? est.filtros : {} }));
			mapas.append(b);
		}
		const gr = grupoCFO();
		const estado = h('div', { class: 'mon-estado' },
			gr ? h('h1', { class: 'mon-titulo' }, `${f.grupo(gr.id)} en `, h('span', { class: 'mon-mes' }, f.mes(ctx.corte())))
				: h('h1', { class: 'mon-titulo' }, 'La cartera en ', h('span', { class: 'mon-mes' }, f.mes(ctx.corte()))),
			gr ? cabezaGrupo(gr) : h('p', { class: 'mon-cuantas' }, `${f.plural(r.total, uno, varias)}${est.unidad === 'empresas' ? ` de ${f.plural(c.groups.length, 'organización', 'organizaciones')}` : ''}`),
			lineaBandas, lineaMes, mapas);
		cabeza.append(...(reducido() ? [] : [rosaCaja]), estado);
		cabeza.classList.toggle('mon-cabeza-sola', reducido());
	}

	/** El titular del CFO: dónde está su grupo, cómo se ha movido y dónde estará en seis meses. */
	function cabezaGrupo(g: Cartera['groups'][number]): HTMLElement {
		const tt = t();
		const m = g.meses[tt], m3 = g.meses[tt - 3];
		const d3 = m?.shown != null && m3?.shown != null ? m.shown - m3.shown : null;
		const hz = c.horizontes && c.horizontes.cut === c.months[tt] ? c.horizontes.entities[g.id] : null;
		const abrirFicha = h('button', { type: 'button', class: 'as-enlace' }, 'Ver la ficha del grupo');
		abrirFicha.addEventListener('click', () => ctx.abrirGrupo(g.id));
		return h('p', { class: 'mon-cuantas mon-grupo' },
			h('b', { class: `mon-grupo-score ${m?.band === 'critical' ? 'critico' : ''}` }, m?.shown != null ? f.score(m.shown) : '—'),
			m?.band ? h('span', {}, ` ${nombreBandaM(c, m.band).toLowerCase()}`) : null,
			d3 !== null ? h('span', { class: 'mon-mov' }, ` · ${d3 >= 0 ? '+' : '−'}${f.numero(Math.abs(Math.round(d3 / 10)))} en tres meses`) : null,
			hz?.p50_h6 != null ? h('span', { class: 'mon-mov' }, ` · a seis meses, ${f.score(hz.p50_h6)}`) : null,
			h('span', { class: 'mon-mov' }, ` · ${f.plural(g.n_companies, 'empresa', 'empresas')} `), abrirFicha);
	}

	// ─── El campo: una organización o una vista ─────────────
	const entrada = h('input', { class: 'entrada-buscar', type: 'search', placeholder: cfo() ? '¿qué empresa?' : '¿qué organización?', 'aria-label': cfo() ? 'Buscar una de tus empresas o pedir una vista' : 'Buscar una organización o pedir una vista de la cartera', autocomplete: 'off' }) as HTMLInputElement;
	const resultados = h('ul', { class: 'entrada-resultados', role: 'listbox' });
	const entendido = h('div', { class: 'mon-entendido', role: 'status' });
	let peticion: AbortController | null = null;
	// La segunda línea: «dile qué quieres ver», con su propio campo y ejemplos que se pueden tocar.
	const pedirCampo = h('input', { class: 'mon-pedir-campo', type: 'search', placeholder: 'o dile qué quieres ver…', 'aria-label': cfo() ? 'Dile qué quieres ver de tus empresas' : 'Dile qué quieres ver de la cartera', autocomplete: 'off' }) as HTMLInputElement;
	const pedirBoton = h('button', { type: 'button', class: 'mon-pedir-boton' }, 'Ver');
	const ejemplos = h('p', { class: 'mon-ejemplos' });
	for (const ej of cfo()
		? ['las que se tuercen', 'qué ha cambiado este mes', 'cómo estarán en seis meses', 'las críticas, en tabla']
		: ['las que se hunden en marketing', 'qué ha cambiado este mes', 'cómo estarán en seis meses', 'empresas sin datos del banco, en tabla']) {
		const b = h('button', { type: 'button', class: 'ejemplo' }, ej);
		b.addEventListener('click', () => { pedirCampo.value = ej; void pedir(ej); });
		ejemplos.append(b, ' ');
	}
	const lanzar = () => { const t2 = pedirCampo.value.trim(); if (t2) void pedir(t2); };
	pedirCampo.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') lanzar(); });
	pedirBoton.addEventListener('click', lanzar);
	campo.append(
		h('div', { class: 'entrada-frase' }, h('span', { class: 'entrada-rumbo' }, logotipo(ctx.esMovil() ? 34 : 50, 'Rumbo'), h('span', { class: 'entrada-de' }, 'de')), entrada),
		resultados,
		h('div', { class: 'mon-pedir' }, h('span', { class: 'mon-pedir-grano', 'aria-hidden': 'true' }), pedirCampo, pedirBoton),
		ejemplos, entendido);

	const normal = (x: string) => x.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
	const buscar = () => {
		vaciar(resultados);
		const texto = entrada.value.trim();
		if (!texto) return;
		const q = normal(texto);
		const gr = grupoCFO();
		if (gr) {
			// En su grupo solo se buscan sus empresas: ni un nombre de fuera.
			const numE = Number(q.replace(/^empresa\s*/, ''));
			const suyas = todas('empresas').filter((e) => (Number.isFinite(numE) && numE > 0 && Number(e.id.split('_')[1]) === numE) || (q.length >= 3 && normal(`${e.nombre} empresa ${Number(e.id.split('_')[1])}`).includes(q))).slice(0, 6);
			for (const e of suyas) {
				const li = h('li', { role: 'option', tabindex: '0', class: 'tocable' }, h('b', {}, e.nombre), h('span', { class: 'sub' }, [e.tamano, e.band ? nombreBandaM(c, e.band) : null].filter(Boolean).join(' · ')), h('span', { class: 'res-score' }, f.score(e.shown)));
				li.addEventListener('click', () => abrir(e));
				li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(e); });
				resultados.append(li);
			}
			return;
		}
		const num = Number(q.replace(/^(grupo|organizacion)\s*/, ''));
		const hits = c.groups.filter((g) => (Number.isFinite(num) && num > 0 && Number(g.id.split('_')[1]) === num) || (q.length >= 3 && `${g.industry ?? ''} ${PAISES[g.country ?? ''] ?? ''} ${f.grupo(g.id)} grupo ${Number(g.id.split('_')[1])}`.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(q))).slice(0, 6);
		const tt = t();
		for (const g of hits) {
			const m = g.meses[tt];
			const li = h('li', { role: 'option', tabindex: '0', class: 'tocable' }, h('b', {}, f.grupo(g.id)), h('span', { class: 'sub' }, [`Grupo ${Number(g.id.split('_')[1])}`, g.industry, PAISES[g.country ?? ''] ?? g.country, f.plural(g.n_companies, 'empresa', 'empresas')].filter(Boolean).join(' · ')), h('span', { class: 'res-score' }, m?.shown != null ? f.score(m.shown) : '—'));
			li.addEventListener('click', () => ctx.abrirGrupo(g.id));
			li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ctx.abrirGrupo(g.id); });
			resultados.append(li);
		}
	};
	entrada.addEventListener('input', buscar);
	entrada.addEventListener('keydown', (ev) => {
		if (ev.key !== 'Enter') return;
		const texto = entrada.value.trim();
		if (!texto) return;
		const loc = porPalabras(texto, est);
		if (loc.abrir) return abrirNumero(loc.abrir);
		const primera = resultados.querySelector('li.tocable') as HTMLElement | null;
		// Si no es ninguna organización, se entiende como una vista.
		if (primera) primera.click(); else { pedirCampo.value = texto; entrada.value = ''; void pedir(texto); }
	});

	function abrirNumero(a: NonNullable<Interpretacion['abrir']>) {
		const gr = grupoCFO();
		if (gr) {
			const em = gr.companies.find((x) => Number(x.id.split('_')[1]) === a.numero);
			if (em) return ctx.abrirEmpresa(gr.id, em.id);
			vaciar(entendido);
			entendido.append(h('p', {}, `Ninguna de tus empresas lleva el número ${a.numero}.`));
			return;
		}
		if (a.kind === 'group') {
			const g = c.groups.find((x) => Number(x.id.split('_')[1]) === a.numero);
			if (g) return ctx.abrirGrupo(g.id);
		} else {
			for (const g of c.groups) { const em = g.companies.find((x) => Number(x.id.split('_')[1]) === a.numero); if (em) return ctx.abrirEmpresa(g.id, em.id); }
		}
		vaciar(entendido);
		entendido.append(h('p', {}, `No hay ninguna ${a.kind === 'group' ? 'organización' : 'empresa'} con el número ${a.numero}.`));
	}

	/** Entiende la frase: primero por palabras (al instante) y luego con Jev (afina y pregunta si duda). */
	async function pedir(texto: string) {
		vaciar(resultados);
		const loc = porPalabras(texto, est);
		if (loc.abrir) return abrirNumero(loc.abrir);
		if (loc.fijados.length) aplicarInterpretacion(loc, texto, !!URL_VISTA);
		else if (URL_VISTA) { vaciar(entendido); entendido.append(h('p', { class: 'mon-afinando' }, `Entendiendo «${texto}»…`)); }
		if (!URL_VISTA) { if (!loc.fijados.length) sinEntender(texto); return; }
		peticion?.abort();
		peticion = new AbortController();
		const jev = await porJev(texto, vocab, loc, peticion.signal);
		if (!jev) { if (loc.fijados.length) aplicarInterpretacion(loc, texto, false, 'Jev no responde; entendido por palabras clave.'); else sinEntender(texto); return; }
		if ((jev.relevante ?? 1) < 0.3 && !jev.fijados.length) return sinEntender(texto);
		aplicarInterpretacion(jev, texto, false);
	}

	function sinEntender(texto: string) {
		vaciar(entendido);
		entendido.append(h('p', {}, cfo()
			? `No sé qué vista es «${texto}». Prueba con una banda («las críticas»), un movimiento («las que caen») o una forma («el flujo», «en tabla»).`
			: `No sé qué vista es «${texto}». Prueba con una banda («las críticas»), un movimiento («las que caen»), un sector, un país, un producto o una forma («el flujo», «en tabla»).`));
	}

	function aplicarInterpretacion(i: Interpretacion, texto: string, afinando: boolean, nota?: string) {
		est = i.estado;
		escribirEstadoURL(est);
		pintarTodo();
		ctx.repintarArena();
		vaciar(entendido);
		const fuente = i.fuente === 'jev' ? `Jev, ${f.numero((i.ms ?? 0) / 1000, 1)} s` : 'palabras clave';
		entendido.append(h('p', {}, h('span', { class: 'versalita' }, 'Entendido '), h('span', { class: 'mon-que' }, `«${texto}»: `), descripcion(), h('span', { class: 'mon-fuente' }, ` · ${fuente}${afinando ? ' · afinando con Jev…' : ''}`)));
		if (nota) entendido.append(h('p', { class: 'nota' }, nota));
		for (const d of i.dudas) {
			const p = h('p', { class: 'mon-duda' }, `¿${NOMBRE_CAMPO[d.campo]}? `);
			d.opciones.forEach((o, k) => {
				if (k) p.append(' o ');
				const b = h('button', { type: 'button', class: 'mon-cifra' }, valorLegible(d.campo, o.valor));
				b.addEventListener('click', () => { const e2 = { ...est, filtros: { ...est.filtros } }; aplicar(e2, d.campo, o.valor); est = e2; escribirEstadoURL(est); pintarTodo(); ctx.repintarArena(); p.remove(); });
				p.append(b);
			});
			entendido.append(p);
		}
	}

	const NOMBRE_CAMPO: Record<Campo, string> = { forma: 'Qué forma', modo: 'Arena o tabla', unidad: 'Organizaciones o empresas', orden: 'En qué orden', banda: 'Qué banda', mov: 'Qué movimiento', zona: 'Qué zona', sector: 'Qué sector', pais: 'Qué país', tamano: 'Qué tamaño', producto: 'Qué producto' };
	const valorLegible = (campo: Campo, v: string): string => {
		switch (campo) {
			case 'forma': return FORMAS.find((x) => x.id === v)?.nombre ?? v;
			case 'orden': return ORDENES.find((x) => x.id === v)?.nombre ?? v;
			case 'banda': return nombreBandaM(c, v as BandaA);
			case 'mov': return MOVIMIENTOS_M.find((x) => x.id === v)?.nombre ?? v;
			case 'zona': return primeraMayuscula(NOMBRE_ZONA[v as Zona] ?? v);
			case 'pais': return PAISES[v] ?? v;
			case 'producto': return PRODUCTOS.find((p) => p.id === v)?.nombre ?? v;
			default: return primeraMayuscula(v);
		}
	};

	/** Lo que se ve, en una frase: «Las 7 organizaciones que entran en crítico, por gravedad». */
	function descripcion(): HTMLElement {
		const n = visibles().length;
		const [uno, varias] = UNIDAD[est.unidad];
		const piezas = piezasFiltro(c, est.filtros, (id) => producto(id).nombre);
		const s = h('span', { class: 'mon-descripcion' }, n === 1 ? `La ${uno}` : `Las ${f.numero(n)} ${varias}`);
		for (const p of piezas) {
			s.append(' ');
			const ficha = h('span', { class: 'mon-ficha' }, p.texto);
			const quitar = h('button', { type: 'button', class: 'mon-quitar', 'aria-label': `Quitar «${p.texto}»`, title: 'Quitar' }, '×');
			quitar.addEventListener('click', () => { const fl = { ...est.filtros }; delete fl[p.clave]; cambiar({ filtros: fl }); });
			ficha.append(quitar);
			s.append(ficha);
		}
		s.append(`, ${ORDENES.find((o) => o.id === est.orden)!.nombre}`);
		return s;
	}

	// ─── Columnas: las que piden atención y los avisos ──────
	function pintarColumnas() {
		vaciar(columnas);
		const { piden, suben } = atencion(todas());
		const movil = ctx.esMovil();
		const lista = h('ol', { class: 'atencion mon-lista' });
		const fila = (e: Entidad, i: number | null, motivo: string) => {
			const li = h('li', { class: `tocable nivel-${e.nivel}`, tabindex: '0' },
				h('span', { class: 'mon-puesto' }, i === null ? '' : String(i + 1)),
				h('b', { class: 'mon-nombre' }, nombreEnt(e)),
				h('span', { class: `mon-score ${e.band === 'critical' ? 'critico' : ''}` }, f.score(e.shown)),
				h('span', { class: `mon-delta ${(e.delta1 ?? 0) < 0 ? 'baja' : (e.delta1 ?? 0) > 0 ? 'sube' : ''}` }, e.delta1 === null || Math.round(e.delta1 / 10) === 0 ? '' : `${e.delta1 < 0 ? '▼' : '▲'}${f.deltaEntero(e.delta1)}`),
				h('span', { class: 'at-texto' }, ...conCifras(motivo, { que: `Por qué ${nombreEnt(e)} pide atención`, mes: ctx.corte(), ir: () => abrir(e) })),
				movil ? null : cola(e.serie.slice(-24), 88, 20));
			li.addEventListener('click', () => abrir(e));
			li.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(e); });
			return li;
		};
		piden.slice(0, movil ? 5 : 6).forEach((e, i) => lista.append(fila(e, i, e.motivo)));
		if (!piden.length) lista.append(h('li', { class: 'nota' }, `Ninguna ${UNIDAD[est.unidad][0]} pide atención este mes.`));
		const verTodas = h('button', { type: 'button', class: 'as-enlace' }, piden.length === 1 ? 'Verla en el ranking' : `Ver las ${f.numero(piden.length)} en el ranking`);
		verTodas.addEventListener('click', () => { cambiar({ forma: 'ranking', orden: 'gravedad', filtros: {} }); vistaSec.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
		const listaSuben = h('ol', { class: 'atencion mon-lista suben' });
		suben.slice(0, 3).forEach((e) => listaSuben.append(fila(e, null, e.sube!)));
		const colA = h('section', { class: 'mon-col mon-atencion' },
			h('header', { class: 'mon-col-cab' }, h('h2', { title: 'En orden de gravedad: primero las que entran en crítico, luego las que tienen un deterioro confirmado, las que siguen en crítico y bajan, las que van hacia crítico según los horizontes y los golpes por confirmar.' }, 'Piden atención'), h('span', { class: 'mon-cuenta' }, f.numero(piden.length)), h('span', { class: 'hueco' }), verTodas),
			lista,
			suben.length ? h('h3', { class: 'mon-sub' }, `Suben · ${f.numero(suben.length)}`) : null,
			suben.length ? listaSuben : null);
		// Avisos del mes, con el triaje de siempre.
		const avisosMes = todas().flatMap((e) => e.avisos.filter((a) => a.state === 'fired').map((a) => ({ e, a })));
		// El CFO ve también los avisos de su grupo, que no son de ninguna empresa suya.
		const gAv = grupoCFO();
		if (gAv) {
			const suyos = new Set(avisosMes.map((x) => `${x.a.kind}|${x.a.month}|${x.a.shown}`));
			const eG = todas('organizaciones').find((x) => x.id === gAv.id);
			if (eG) for (const a of eG.avisos.filter((x) => x.state === 'fired')) if (!suyos.has(`${a.kind}|${a.month}|${a.shown}`)) avisosMes.push({ e: eG, a });
		}
		const orden = TIPOS_AVISO.map((x) => x.id);
		avisosMes.sort((x, y) => orden.indexOf(x.a.kind) - orden.indexOf(y.a.kind) || (x.e.shown ?? 0) - (y.e.shown ?? 0));
		const sinRevisar = avisosMes.filter((x) => !triaje.de(x.a.id));
		const listaAv = h('ul', { class: 'avisos mon-avisos-lista' });
		for (const { e, a } of sinRevisar.slice(0, movil ? 5 : 6)) {
			const tipo = TIPOS_AVISO.find((x) => x.id === a.kind)!;
			const li = h('li', { class: `aviso ${tipo.tono === 'sube' ? 'sube' : tipo.tono === 'baja' ? 'baja' : 'neutro'}` },
				h('span', { class: 'av-grano' }), h('button', { type: 'button', class: 'av-ent' }, nombreEnt(e)), h('span', { class: 'av-texto' }, `${tipo.nombre.toLowerCase()} · ${f.score(a.shown)}`),
				h('span', { class: 'av-triaje' }, ...(['visto', 'descartado'] as const).map((v) => { const b = h('button', { type: 'button', class: 'av-boton' }, v === 'visto' ? 'Visto' : 'Descartar'); b.addEventListener('click', (ev) => { ev.stopPropagation(); triaje.fijar(a.id, v); }); return b; })));
			(li.querySelector('.av-ent') as HTMLElement).addEventListener('click', () => abrir(e));
			listaAv.append(li);
		}
		if (!sinRevisar.length) listaAv.append(h('li', { class: 'nota' }, avisosMes.length ? 'Todos los avisos del mes están revisados.' : 'Ningún aviso este mes.'));
		const verAvisos = h('button', { type: 'button', class: 'as-enlace' }, 'Ver todos');
		verAvisos.addEventListener('click', () => { cambiar({ forma: 'avisos', modo: 'tabla', filtros: {} }); vistaSec.scrollIntoView({ behavior: 'smooth', block: 'start' }); });
		const colB = h('section', { class: 'mon-col mon-avisos', id: 'mon-avisos' },
			h('header', { class: 'mon-col-cab' }, h('h2', {}, 'Avisos del mes'), h('span', { class: 'mon-cuenta' }, `${f.numero(sinRevisar.length)} sin revisar`), h('span', { class: 'hueco' }), verAvisos),
			listaAv);
		columnas.append(colA, colB);
	}
	triaje.oir(() => { if (raiz.isConnected) { pintarColumnas(); if (est.forma === 'avisos' && est.modo === 'tabla') pintarVista(); } });

	// ─── La vista ────────────────────────────────────────────
	function barra(): HTMLElement {
		const b = h('div', { class: 'mon-barra' });
		const formas = h('div', { class: 'mon-formas', role: 'radiogroup', 'aria-label': 'Forma' });
		for (const fo of (reducido() ? FORMAS.filter((x) => FORMAS_POCAS.includes(x.id)) : FORMAS)) {
			const x = h('button', { type: 'button', class: `mon-forma ${est.forma === fo.id ? 'activa' : ''}`, role: 'radio', 'aria-checked': String(est.forma === fo.id), title: fo.explica, 'data-forma': fo.id }, fo.nombre);
			x.addEventListener('click', () => cambiar({ forma: fo.id }));
			formas.append(x);
		}
		const conmutador = <T extends string>(clase: string, etiqueta: string, opciones: [T, string][], actual: T, alCambiar: (v: T) => void) => {
			const g = h('div', { class: `mon-conmutador ${clase}`, role: 'radiogroup', 'aria-label': etiqueta });
			for (const [v, texto] of opciones) {
				const x = h('button', { type: 'button', role: 'radio', 'aria-checked': String(actual === v), class: actual === v ? 'activa' : '', 'data-valor': v }, texto);
				x.addEventListener('click', () => alCambiar(v));
				g.append(x);
			}
			return g;
		};
		const orden = desplegable<EstadoMonitor['orden']>({
			etiqueta: 'Orden', valor: est.orden,
			opciones: ORDENES.map((o) => ({ valor: o.id, texto: primeraMayuscula(o.nombre) })),
			alElegir: (v) => cambiar({ orden: v }),
		}).raiz;
		b.append(formas, h('span', { class: 'hueco' }), conmutador('mon-modo', 'Arena o tabla', [['arena', 'Arena'], ['tabla', 'Tabla']], est.modo, (v) => cambiar({ modo: v })));
		const opciones = h('div', { class: 'mon-opciones' },
			cfo() ? null : conmutador('mon-unidad', 'Unidad', [['organizaciones', 'Organizaciones'], ['empresas', 'Empresas']], est.unidad, (v) => cambiar({ unidad: v, filtros: { ...est.filtros, producto: v === 'empresas' ? undefined : est.filtros.producto, grupo: undefined } })),
			orden);
		return h('div', {}, b, opciones);
	}

	function acciones(): HTMLElement {
		const a = h('div', { class: 'mon-acciones' });
		if ((est.forma === 'plano' || est.forma === 'tapiz') && est.unidad === 'organizaciones') {
			const m = h('button', { type: 'button', class: 'as-enlace' }, 'Pantalla completa');
			m.addEventListener('click', () => ctx.irMapa(est.forma as 'plano' | 'tapiz', est));
			a.append(m);
		}
		const guardar = h('button', { type: 'button', class: 'as-enlace' }, 'Guardar la vista');
		guardar.addEventListener('click', () => {
			vaciar(a);
			const nombre = h('input', { class: 'mon-nombre-vista', type: 'text', placeholder: 'Nombre de la vista', 'aria-label': 'Nombre de la vista', maxlength: '40' }) as HTMLInputElement;
			const ok = h('button', { type: 'button', class: 'miga-accion' }, 'Guardar');
			const hecho = () => { const n = nombre.value.trim(); if (!n) return; guardarVistas([...leerVistas().filter((v) => v.nombre !== n), { nombre: n, estado: est }]); pintarVista(); };
			ok.addEventListener('click', hecho);
			nombre.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') hecho(); if (ev.key === 'Escape') pintarVista(); });
			a.append(nombre, ok);
			nombre.focus();
		});
		a.append(guardar);
		return a;
	}

	function misVistas(): HTMLElement | null {
		const vs = leerVistas();
		if (!vs.length) return null;
		const p = h('p', { class: 'mon-mis-vistas' }, h('span', { class: 'versalita' }, 'Mis vistas '));
		for (const v of vs) {
			const b = h('button', { type: 'button', class: 'mon-ficha vista' }, v.nombre);
			b.addEventListener('click', () => { est = { ...ESTADO_INICIAL, ...v.estado, filtros: { ...v.estado.filtros } }; escribirEstadoURL(est); pintarTodo(); ctx.repintarArena(); });
			const x = h('button', { type: 'button', class: 'mon-quitar', 'aria-label': `Borrar la vista «${v.nombre}»`, title: 'Borrar' }, '×');
			x.addEventListener('click', (ev) => { ev.stopPropagation(); guardarVistas(leerVistas().filter((y) => y.nombre !== v.nombre)); pintarVista(); });
			b.append(x);
			p.append(b, ' ');
		}
		return p;
	}

	let lienzoActual: HTMLElement | null = null;
	let observador: ResizeObserver | null = null;
	function pintarVista() {
		colocar();
		vaciar(vistaSec);
		observador?.disconnect();
		lienzoActual = null;
		const vis = visibles();
		vistaSec.append(
			h('header', { class: 'mon-vista-cab' }, h('h2', {}, cfo() ? 'Tus empresas' : 'La cartera')),
			barra(),
			h('div', { class: 'mon-frase-fila' }, h('p', { class: 'mon-frase' }, descripcion()), acciones()),
			misVistas() ?? '',
		);
		if (!vis.length) {
			vistaSec.append(h('p', { class: 'vacio-monitor' }, 'Ninguna pasa estos filtros. Quita alguno tocando su ×.'));
			return;
		}
		const cuerpo = est.modo === 'arena' ? lienzo(vis) : tabla(vis);
		vistaSec.append(cuerpo);
		void vis;
	}

	// ─── En arena ─────────────────────────────────────────
	function datosArena(vis: Entidad[]): DatosVista {
		const tt = t(), movil = ctx.esMovil();
		const puesto = new Map(vis.map((e, i) => [e.id, i]));
		const desde = tt - MESES_TAPIZ + 1, desdeAv = tt - MESES_AVISOS + 1;
		const tiposVis = TIPOS_AVISO.filter((tp) => vis.some((e) => e.historia.some((a) => a.kind === tp.id && a.state === 'fired' && a.month >= desdeAv)));
		const filaTipo = new Map(tiposVis.map((x, i) => [x.id, i]));
		const ents: EntArena[] = [...todas()].sort((a, b) => (a.id < b.id ? -1 : 1)).map((e) => ({
			id: e.id, visible: puesto.has(e.id), puesto: puesto.get(e.id) ?? -1,
			shown: e.shown, prevShown: e.prevShown, band: e.band, prevBand: e.prevBand, ritmo: e.ritmo,
			serie: Array.from({ length: MESES_TAPIZ }, (_, i) => e.serie[desde + i] ?? null),
			bandas: Array.from({ length: MESES_TAPIZ }, (_, i) => e.bandas[desde + i] ?? null),
			p50: e.hz?.p50 ?? null, pCritico: e.hz?.pCritico ?? null,
			avisos: e.historia.filter((a) => a.state === 'fired' && a.month >= desdeAv && filaTipo.has(a.kind)).map((a) => [a.month - desdeAv, filaTipo.get(a.kind)!] as [number, number]),
		}));
		const filas = est.forma === 'ranking' ? Math.min(vis.length, movil ? 14 : 20) : Math.min(vis.length, movil ? 24 : 40);
		return { forma: est.forma, ents, k: est.unidad === 'organizaciones' ? 180 : 36, meses: est.forma === 'avisos' ? MESES_AVISOS : MESES_TAPIZ, tipos: tiposVis.map((x) => ({ tono: x.tono })), filas, movil };
	}

	function altoArena(d: DatosVista): number {
		const movil = !!d.movil;
		switch (d.forma) {
			case 'ranking': return d.filas * (movil ? 22 : 21) + 30;
			case 'bandas': return movil ? 300 : 340;
			case 'plano': return movil ? 320 : 430;
			case 'tapiz': return d.filas * (movil ? 14 : 16) + 50;
			case 'flujo': return movil ? 380 : 440;
			case 'avisos': return Math.max(1, d.tipos.length) * (movil ? 44 : 58) + 34;
			case 'horizonte': return movil ? 380 : 440;
		}
	}

	function lienzo(vis: Entidad[]): HTMLElement {
		const datos = datosArena(vis);
		const alto = altoArena(datos);
		const caja = h('div', { class: `mon-lienzo forma-${est.forma}`, style: { height: `${alto}px` } });
		const arena = h('div', { class: 'mon-lienzo-arena' });
		placa(arena, (cj) => ({ tipo: 'vista', x: cj.x, y: cj.y, w: cj.w, h: cj.h, datos }));
		const rotulos = h('div', { class: 'mon-rotulos' });
		const tip = h('div', { class: 'mon-tip', role: 'tooltip' });
		caja.append(arena, rotulos, tip);
		const porId = new Map(vis.map((e) => [e.id, e]));
		let disp: Disposicion | null = null;
		const rotular = () => {
			const w = caja.clientWidth;
			if (!w) return;
			disp = disponer(datos, w, alto);
			vaciar(rotulos);
			rotularForma(rotulos, disp, datos, vis, w, alto);
		};
		const cerca = (ev: PointerEvent) => {
			if (!disp) return null;
			const r = caja.getBoundingClientRect();
			const x = ev.clientX - r.left, y = ev.clientY - r.top;
			let mejor: string | null = null, dm = Infinity;
			for (const [id, a] of disp.anclas) { const d = Math.hypot(a.x - x, a.y - y); if (d < Math.max(8, a.r + 5) && d < dm) { dm = d; mejor = id; } }
			// En ranking y tapiz vale toda la fila.
			if (!mejor && (est.forma === 'ranking' || est.forma === 'tapiz')) for (const [id, a] of disp.anclas) if (Math.abs(a.y - y) <= a.r) { mejor = id; break; }
			return mejor ? { e: porId.get(mejor)!, x, y } : null;
		};
		caja.addEventListener('pointermove', (ev) => {
			const hit = cerca(ev);
			caja.style.cursor = hit ? 'pointer' : '';
			if (!hit) { tip.classList.remove('ver'); return; }
			tip.textContent = `${nombreEnt(hit.e)} · ${f.score(hit.e.shown)}${hit.e.motivo ? ` · ${hit.e.motivo}` : ''}`;
			tip.style.left = `${Math.min(hit.x + 12, caja.clientWidth - 260)}px`;
			tip.style.top = `${hit.y + 14}px`;
			tip.classList.add('ver');
		});
		caja.addEventListener('pointerleave', () => tip.classList.remove('ver'));
		caja.addEventListener('click', (ev) => { const hit = cerca(ev as PointerEvent); if (hit) abrir(hit.e); });
		lienzoActual = caja;
		requestAnimationFrame(rotular);
		setTimeout(rotular, 0);
		observador = new ResizeObserver(() => { rotular(); ctx.repintarArena(); });
		observador.observe(caja);
		return caja;
	}

	function rotularForma(capa: HTMLElement, d: Disposicion, datos: DatosVista, vis: Entidad[], w: number, alto: number) {
		const g = d.guias;
		const movil = !!datos.movil;
		const m = margen(datos.forma, movil);
		const et = (x: number, y: number, clase: string, ...hijos: (Node | string)[]) => { const e = h('span', { class: `mr ${clase}` }, ...hijos); e.style.left = `${x}px`; e.style.top = `${y}px`; capa.append(e); return e; };
		const tt = t();
		switch (datos.forma) {
			case 'ranking': {
				vis.slice(0, datos.filas).forEach((e, i) => {
					const y = g.y0 + (i + 0.5) * g.fila;
					et(g.x0 - 10, y, 'mr-nombre', movil ? e.nombre.replace(/^(Grupo|Empresa) /, '') : e.nombre);
					et(g.x1 + 10, y, 'mr-dato', h('b', {}, f.score(e.shown)), e.delta1 !== null && Math.round(e.delta1 / 10) !== 0 ? h('span', { class: e.delta1 < 0 ? 'baja' : 'sube' }, ` ${f.deltaEntero(e.delta1)}`) : '');
				});
				// El eje, de 0 a 100, con las fronteras de banda.
				for (const s of [0, 20, 40, 60, 80, 100]) et(g.x0 + (s / 100) * (g.x1 - g.x0), g.y1 + 6, 'mr-eje x', String(s));
				for (const s of [40, 60, 80]) { const ln = h('span', { class: 'mr-linea v tenue' }); ln.style.left = `${g.x0 + (s / 100) * (g.x1 - g.x0)}px`; ln.style.top = `${g.y0}px`; ln.style.height = `${g.y1 - g.y0}px`; capa.append(ln); }
				if (vis.length > datos.filas) et(4, alto - 2, 'mr-mas', `y ${f.numero(vis.length - datos.filas)} más`);
				break;
			}
			case 'bandas': {
				BANDAS.forEach((b, bi) => {
					const lista = vis.filter((e) => e.band === b);
					const entran = lista.filter((e) => e.prevBand && e.prevBand !== b).length;
					const salen = vis.filter((e) => e.prevBand === b && e.band !== b).length;
					const x = g.x0 + (bi + 0.5) * g.colW;
					const b1 = et(x, alto - m.b + 6, 'mr-banda', h('b', {}, `${nombreBandaM(c, b)} · ${f.numero(lista.length)}`), h('span', {}, `${f.numero(entran)} entran · ${f.numero(salen)} salen`));
					b1.addEventListener('click', () => filtrar({ banda: b }));
				});
				break;
			}
			case 'plano': {
				const lineaV = h('span', { class: 'mr-linea v' }); lineaV.style.left = `${g.xCorte}px`; lineaV.style.top = `${g.y0}px`; lineaV.style.height = `${g.y1 - g.y0}px`; capa.append(lineaV);
				const lineaH = h('span', { class: 'mr-linea h' }); lineaH.style.left = `${g.x0}px`; lineaH.style.top = `${g.yCero}px`; lineaH.style.width = `${g.x1 - g.x0}px`; capa.append(lineaH);
				for (const s of [0, 20, 40, 60, 80, 100]) et(g.x0 + (s / 100) * (g.x1 - g.x0), g.y1 + 6, 'mr-eje x', String(s));
				for (const r of [-4, -2, 0, 2, 4]) et(g.x0 - 6, (g.y0 + g.y1) / 2 - (r / 5) * (g.y1 - g.y0) / 2, 'mr-eje y', r === 0 ? '0' : `${r > 0 ? '+' : '−'}${Math.abs(r)}`);
				const zonas: [Zona, number, number, string][] = [['mejora', g.x0 + 8, g.y0 + 4, 'izq'], ['solida', g.x1 - 8, g.y0 + 4, 'der'], ['hunde', g.x0 + 8, g.y1 - 18, 'izq'], ['tuerce', g.x1 - 8, g.y1 - 18, 'der']];
				for (const [z, x, y, lado] of zonas) {
					if (est.filtros.zona && est.filtros.zona !== z) continue;
					const n = vis.filter((e) => e.zona === z).length;
					if (est.filtros.zona && n === 0) continue;
					const b = et(x, y, `mr-zona ${lado}`, `${primeraMayuscula(NOMBRE_ZONA[z])} · ${f.numero(n)}`);
					b.addEventListener('click', () => filtrar({ zona: z }));
				}
				break;
			}
			case 'tapiz': {
				if (g.fila >= 10) vis.slice(0, datos.filas).forEach((e, i) => et(g.x0 - 8, g.y0 + (i + 0.5) * g.fila, 'mr-nombre chica', movil ? e.nombre.replace(/^(Grupo|Empresa) /, '') : e.nombre));
				for (let i = 0; i < datos.meses; i += movil ? 6 : 3) { const iso = c.months[tt - datos.meses + 1 + i]; if (iso) et(g.x0 + (i + 0.5) * g.col, g.y1 + 6, 'mr-eje x', f.mesCorto(iso)); }
				if (vis.length > datos.filas) et(g.x0, alto - 2, 'mr-mas', `y ${f.numero(vis.length - datos.filas)} más`);
				break;
			}
			case 'flujo': {
				const antes = c.months[tt - 1], ahora = c.months[tt];
				if (antes) et(g.x0, 0, 'mr-cab izq', f.mes(antes));
				et(g.x1, 0, 'mr-cab der', f.mes(ahora));
				for (const b of BANDAS) {
					if (g[`in_${b}`]) et(g.x0 - 10, g[`i_${b}`], 'mr-nombre', `${nombreBandaM(c, b)} · ${f.numero(g[`in_${b}`])}`);
					if (g[`dn_${b}`]) et(g.x1 + 10, g[`d_${b}`], 'mr-dato', `${nombreBandaM(c, b)} · ${f.numero(g[`dn_${b}`])}`);
				}
				const cambian = vis.filter((e) => e.band && e.prevBand && e.band !== e.prevBand);
				const bajan = cambian.filter((e) => BANDAS.indexOf(e.band!) < BANDAS.indexOf(e.prevBand!)).length;
				et(g.xm, alto - 4, 'mr-mas centro', `${f.numero(bajan)} bajan · ${f.numero(cambian.length - bajan)} suben · ${f.numero(vis.length - cambian.length)} se quedan`);
				break;
			}
			case 'avisos': {
				const tiposVis = TIPOS_AVISO.filter((tp) => datos.tipos.length && vis.some((e) => e.historia.some((a) => a.kind === tp.id && a.state === 'fired' && a.month >= tt - MESES_AVISOS + 1)));
				tiposVis.forEach((tp, i) => et(g.x0 - 10, g.y0 + (i + 0.5) * g.fila, 'mr-nombre', tp.nombre));
				for (let i = 0; i < datos.meses; i += movil ? 3 : 2) { const iso = c.months[tt - datos.meses + 1 + i]; if (iso) et(g.x0 + (i + 0.5) * g.col, g.y1 + 6, 'mr-eje x', f.mesCorto(iso)); }
				// La cifra de cada celda, encima de su pila.
				const cuenta = new Map<string, number>();
				for (const e of datos.ents) if (e.visible) for (const [cc, ff] of e.avisos) cuenta.set(`${cc}:${ff}`, (cuenta.get(`${cc}:${ff}`) ?? 0) + 1);
				for (const [k, n] of cuenta) { const [cc, ff] = k.split(':').map(Number); et(g.x0 + (cc + 0.5) * g.col, g.y0 + (ff + 1) * g.fila - 2 - n * g.unidad - 13, 'mr-cuenta', f.numero(n)); }
				break;
			}
			case 'horizonte': {
				et(g.x0, 0, 'mr-cab izq', 'hoy');
				et(g.x1, 0, 'mr-cab der', 'dentro de seis meses');
				const ocupado: number[] = [];
				for (const b of BANDAS) {
					if (g[`in_${b}`]) et(g.x0 - 10, g[`i_${b}`], 'mr-nombre', `${nombreBandaM(c, b)} · ${f.numero(g[`in_${b}`])}`);
					if (g[`dn_${b}`]) { et(g.x1 + 10, g[`d_${b}`], 'mr-dato', `${nombreBandaM(c, b)} · ${f.numero(g[`dn_${b}`])}`); ocupado.push(g[`d_${b}`]); }
				}
				// Las que van hacia crítico, con nombre donde acaba su cinta y sin pisar los rótulos de banda.
				const riesgo = vis.filter((e) => e.band !== 'critical' && (e.hz?.pCritico ?? 0) >= 0.5 && g[`fin:${e.id}`] !== undefined).sort((a, b) => (b.hz!.pCritico ?? 0) - (a.hz!.pCritico ?? 0)).slice(0, 10).sort((a, b) => g[`fin:${a.id}`] - g[`fin:${b.id}`]);
				let ultimo = -Infinity;
				for (const e of riesgo) {
					let y = Math.max(g[`fin:${e.id}`], ultimo + 14);
					for (const yb of ocupado) if (Math.abs(y - yb) < 14) y = yb + 14;
					ultimo = y;
					et(g.x1 + 10, y, 'mr-dato riesgo', movil ? e.nombre.replace(/^(Grupo|Empresa) /, '') : `${e.nombre} · ${f.porcentaje(e.hz!.pCritico!, 0)}`);
				}
				const sinHz = vis.filter((e) => e.hz?.p50 == null).length;
				if (sinHz) et(g.x0, alto - 2, 'mr-mas', `${f.numero(sinHz)} sin horizonte (se calcula desde ${c.horizontes ? f.mes(c.horizontes.cut) : '—'})`);
				break;
			}
		}
		void w;
	}

	// ─── En tabla ─────────────────────────────────────────
	let tope = 60;
	function tabla(vis: Entidad[]): HTMLElement {
		const caja = h('div', { class: `mon-tabla forma-${est.forma}` });
		const esEmp = est.unidad === 'empresas';
		const celdaEnt = (e: Entidad) => { const b = h('button', { type: 'button', class: 'enlace-empresa' }, e.nombre, esEmp ? h('span', { class: 'mz-papel' }, f.grupo(e.grupo)) : ''); b.addEventListener('click', () => abrir(e)); return h('td', {}, b); };
		const delta = (v: number | null) => h('td', { class: `num ${v !== null && v < 0 ? 'baja' : v !== null && v > 0 ? 'sube' : ''}` }, v === null ? '—' : f.deltaEntero(v));
		const mas = (n: number) => { if (n <= tope) return null; const b = h('button', { type: 'button', class: 'as-enlace' }, `Ver ${f.numero(Math.min(60, n - tope))} más (de ${f.numero(n)})`); b.addEventListener('click', () => { tope += 60; pintarVista(); }); return b; };
		const ordenable = (texto: string, orden: EstadoMonitor['orden'] | null, clase = '') => {
			if (!orden) return h('th', { class: clase }, texto);
			const b = h('button', { type: 'button', class: `th-orden ${est.orden === orden ? 'activo' : ''}`, title: `Ordenar ${ORDENES.find((o) => o.id === orden)!.nombre}` }, texto);
			b.addEventListener('click', () => cambiar({ orden }));
			return h('th', { class: clase, 'aria-sort': est.orden === orden ? 'ascending' : undefined }, b);
		};
		switch (est.forma) {
			case 'ranking': {
				const tb = h('table', { class: 'tabla-sutil mon-t' },
					h('thead', {}, h('tr', {}, ordenable('#', 'gravedad'), h('th', {}, esEmp ? 'Empresa' : 'Organización'), ordenable('Score', 'score', 'num'), ordenable('Mes', 'cambio', 'num'), ordenable('3 meses', 'cambio3', 'num'), h('th', {}, 'Banda'), h('th', {}, 'Por qué'), ordenable('A 6 meses', 'horizonte', 'num'), ordenable('Avisos', 'avisos', 'num'), ctx.esMovil() ? null : h('th', {}, 'Dos años'))),
					h('tbody', {}, ...vis.slice(0, tope).map((e, i) => h('tr', { class: e.band === 'critical' ? 'fila-critica' : '' },
						h('td', { class: 'num tenue' }, String(i + 1)), celdaEnt(e), h('td', { class: 'num' }, h('b', {}, f.score(e.shown))), delta(e.delta1), delta(e.delta3),
						h('td', {}, e.band ? nombreBandaM(c, e.band).toLowerCase() : '—', e.prevBand && e.band && e.prevBand !== e.band ? h('span', { class: 'sub' }, ` (era ${nombreBandaM(c, e.prevBand).toLowerCase()})`) : ''),
						h('td', { class: 'por-que' }, e.nivel <= 4 ? e.motivo : e.sube ?? ''),
						h('td', { class: 'num' }, e.hz?.p50 != null ? `${f.score(e.hz.p50)}${e.hz.pCritico ? ` · ${f.porcentaje(e.hz.pCritico, 0)}` : ''}` : '—'),
						h('td', { class: 'num' }, String(e.avisos.filter((a) => a.state === 'fired').length || '')),
						ctx.esMovil() ? null : h('td', {}, cola(e.serie.slice(-24), 80, 18))))));
				caja.append(h('div', { class: 'tabla-caja' }, tb), mas(vis.length) ?? '');
				break;
			}
			case 'bandas': case 'plano': {
				const grupos: [string, Entidad[], FiltrosM][] = (est.forma === 'bandas'
					? BANDAS.map((b): [string, Entidad[], FiltrosM] => [nombreBandaM(c, b), vis.filter((e) => e.band === b), { banda: b }])
					: (['hunde', 'tuerce', 'mejora', 'solida'] as Zona[]).map((z): [string, Entidad[], FiltrosM] => [primeraMayuscula(NOMBRE_ZONA[z]), vis.filter((e) => e.zona === z), { zona: z }])
				).filter(([, lista, fl]) => {
					if (est.forma === 'plano' && est.filtros.zona) return fl.zona === est.filtros.zona;
					if (est.forma === 'bandas' && est.filtros.banda) return fl.banda === est.filtros.banda;
					return lista.length > 0 || (!est.filtros.zona && !est.filtros.banda);
				});
				const rejilla = h('div', { class: 'mon-grupos' });
				for (const [nombre, lista, fl] of grupos) {
					const col = h('div', { class: 'mon-grupo' });
					const cab = h('button', { type: 'button', class: 'mon-grupo-cab' }, h('b', {}, nombre), ` · ${f.numero(lista.length)}`);
					cab.addEventListener('click', () => filtrar(fl));
					col.append(cab);
					if (est.forma === 'bandas') {
						const entran = lista.filter((e) => e.prevBand && e.prevBand !== e.band).length;
						col.append(h('p', { class: 'sub' }, `${f.numero(entran)} entran este mes`));
					}
					const ul = h('ul', {});
					for (const e of [...lista].sort((a, b) => Number(!!b.prevBand && b.prevBand !== b.band) - Number(!!a.prevBand && a.prevBand !== a.band) || (a.shown ?? 0) - (b.shown ?? 0)).slice(0, 30)) {
						const entra = est.forma === 'bandas' && e.prevBand && e.prevBand !== e.band;
						const li = h('li', { class: 'tocable' }, h('span', {}, e.nombre), h('span', { class: 'num' }, f.score(e.shown)), entra ? h('span', { class: `mon-entra ${BANDAS.indexOf(e.band!) < BANDAS.indexOf(e.prevBand!) ? 'baja' : 'sube'}` }, 'entra') : '');
						li.addEventListener('click', () => abrir(e));
						ul.append(li);
					}
					if (lista.length > 30) ul.append(h('li', { class: 'nota' }, `y ${f.numero(lista.length - 30)} más`));
					col.append(ul);
					rejilla.append(col);
				}
				caja.append(rejilla);
				break;
			}
			case 'tapiz': {
				const n = ctx.esMovil() ? 6 : 12;
				const meses = c.months.slice(t() - n + 1, t() + 1);
				const tb = h('table', { class: 'tabla-sutil mon-t tapiz-t' },
					h('thead', {}, h('tr', {}, h('th', {}, esEmp ? 'Empresa' : 'Organización'), ...meses.map((m) => h('th', { class: 'num' }, f.mesCorto(m))))),
					h('tbody', {}, ...vis.slice(0, tope).map((e) => h('tr', {}, celdaEnt(e), ...meses.map((_, i) => { const k = t() - n + 1 + i; const v = e.serie[k]; const b = e.bandas[k]; return h('td', { class: `num celda-${b ?? 'nada'}` }, v == null ? '' : f.score(v)); })))));
				caja.append(h('div', { class: 'tabla-caja' }, tb), mas(vis.length) ?? '');
				break;
			}
			case 'flujo': {
				const mz = flujo(vis);
				const antes = c.months[t() - 1];
				const detalle = h('div', { class: 'mon-flujo-detalle' });
				const tb = h('table', { class: 'tabla-sutil mon-t matriz-flujo' },
					h('thead', {}, h('tr', {}, h('th', {}, `${antes ? f.mes(antes) : 'Antes'} ↓ · ${f.mes(ctx.corte())} →`), ...BANDAS.map((b) => h('th', { class: 'num' }, nombreBandaM(c, b))))),
					h('tbody', {}, ...BANDAS.map((a) => h('tr', {}, h('th', {}, nombreBandaM(c, a)), ...BANDAS.map((b) => {
						const l = mz[a][b];
						const tono = a === b ? 'igual' : BANDAS.indexOf(b) < BANDAS.indexOf(a) ? 'baja' : 'sube';
						if (!l.length) return h('td', { class: 'num tenue' }, '·');
						const btn = h('button', { type: 'button', class: `mon-celda ${tono}` }, f.numero(l.length));
						btn.addEventListener('click', () => {
							vaciar(detalle);
							detalle.append(h('p', { class: 'sub' }, `De ${nombreBandaM(c, a).toLowerCase()} a ${nombreBandaM(c, b).toLowerCase()}: ${f.numero(l.length)}`));
							const ul = h('ul', { class: 'mon-flujo-lista' });
							for (const e of l.slice(0, 60)) { const li = h('li', { class: 'tocable' }, e.nombre, h('span', { class: 'num' }, ` ${f.score(e.prevShown)} → ${f.score(e.shown)}`)); li.addEventListener('click', () => abrir(e)); ul.append(li); }
							detalle.append(ul);
						});
						return h('td', { class: 'num' }, btn);
					})))));
				caja.append(h('div', { class: 'tabla-caja' }, tb), h('p', { class: 'nota' }, 'Filas: la banda del mes pasado; columnas: la de este. Toca una cifra para ver quiénes son.'), detalle);
				break;
			}
			case 'avisos': {
				const filas = vis.flatMap((e) => e.avisos.map((a) => ({ e, a })));
				const orden = TIPOS_AVISO.map((x) => x.id);
				filas.sort((x, y) => orden.indexOf(x.a.kind) - orden.indexOf(y.a.kind) || (x.e.shown ?? 0) - (y.e.shown ?? 0));
				const tb = h('table', { class: 'tabla-sutil mon-t' },
					h('thead', {}, h('tr', {}, h('th', {}, esEmp ? 'Empresa' : 'Organización'), h('th', {}, 'Aviso'), h('th', { class: 'num' }, 'Score'), h('th', {}, 'Estado'), h('th', {}, 'Revisión'))),
					h('tbody', {}, ...filas.slice(0, tope).map(({ e, a }) => {
						const tp = TIPOS_AVISO.find((x) => x.id === a.kind)!;
						const rev = triaje.de(a.id);
						const acciones = h('td', { class: 'av-triaje' });
						const boton = (texto: string, v: 'visto' | 'descartado' | null) => { const b = h('button', { type: 'button', class: 'av-boton' }, texto); b.addEventListener('click', () => triaje.fijar(a.id, v)); acciones.append(b); };
						if (rev) boton('Restaurar', null); else { boton('Visto', 'visto'); boton('Descartar', 'descartado'); }
						return h('tr', { class: rev ? `triaje-${rev}` : '' }, celdaEnt(e), h('td', {}, h('span', { class: `av-punto ${tp.tono}` }), tp.nombre), h('td', { class: 'num' }, f.score(a.shown)), h('td', {}, a.state === 'fired' ? 'disparado' : a.state === 'suppressed' ? 'silenciado' : 'sin veredicto'), acciones);
					})));
				caja.append(h('p', { class: 'sub' }, `Avisos de ${f.mes(ctx.corte())}: ${f.numero(filas.length)}.`), h('div', { class: 'tabla-caja' }, tb), mas(filas.length) ?? '');
				break;
			}
			case 'horizonte': {
				const con = vis.filter((e) => e.hz?.p50 != null).sort((a, b) => (b.hz!.pCritico ?? 0) - (a.hz!.pCritico ?? 0) || (a.hz!.p50! - (a.shown ?? 0)) - (b.hz!.p50! - (b.shown ?? 0)));
				const tb = h('table', { class: 'tabla-sutil mon-t' },
					h('thead', {}, h('tr', {}, h('th', {}, esEmp ? 'Empresa' : 'Organización'), h('th', { class: 'num' }, 'Hoy'), h('th', { class: 'num' }, 'A 6 meses'), h('th', { class: 'num' }, 'Cambio'), h('th', { class: 'num' }, 'P(crítico)'), h('th', {}, 'Cruce más probable'))),
					h('tbody', {}, ...con.slice(0, tope).map((e) => h('tr', { class: e.band !== 'critical' && (e.hz!.pCritico ?? 0) >= 0.5 ? 'fila-critica' : '' },
						celdaEnt(e), h('td', { class: 'num' }, f.score(e.shown)), h('td', { class: 'num' }, h('b', {}, f.score(e.hz!.p50))), delta(e.shown !== null ? e.hz!.p50! - e.shown : null),
						h('td', { class: 'num' }, e.hz!.pCritico != null ? f.porcentaje(e.hz!.pCritico, 0) : '—'),
						h('td', {}, e.hz!.cruce ? `a ${nombreBandaM(c, e.hz!.cruce.to).toLowerCase()} hacia ${f.mes(e.hz!.cruce.month)} (${f.porcentaje(e.hz!.cruce.prob, 0)})` : '')))));
				caja.append(h('div', { class: 'tabla-caja' }, tb), mas(con.length) ?? '', con.length < vis.length ? h('p', { class: 'nota' }, `${f.numero(vis.length - con.length)} sin horizonte en este corte.`) : '');
				break;
			}
		}
		return caja;
	}

	function pintarTodo() {
		tope = 60;
		campo.hidden = reducido();
		pintarCabeza();
		pintarColumnas();
		pintarVista();
		vaciar(pie);
		const met = h('button', { type: 'button', class: 'as-enlace' }, 'Cómo se calcula todo esto');
		met.addEventListener('click', () => ctx.metodologia());
		const gp = grupoCFO();
		pie.append(gp
			? `${f.grupo(gp.id)} · ${f.plural(gp.n_companies, 'empresa', 'empresas')}, de ${f.mes(man.months[0])} a ${f.mes(man.months[man.months.length - 1])}. Dónde está cada una, hacia dónde va y qué puede cambiar su rumbo. `
			: `${f.numero(man.counts.groups)} organizaciones y ${f.numero(man.counts.companies)} empresas, de ${f.mes(man.months[0])} a ${f.mes(man.months[man.months.length - 1])}. Dónde está cada una, hacia dónde va y qué puede cambiar su rumbo. `, met);
	}
	pintarTodo();
	// El campo recibe el foco sin desplazar la página: lo primero que se ve es el monitor.
	requestAnimationFrame(() => entrada.focus({ preventScroll: true }));

	return {
		raiz,
		irAvisos: () => { (raiz.querySelector('#mon-avisos') as HTMLElement | null)?.scrollIntoView({ block: 'start' }); },
		informe: () => {
			// El papel: el estado, todas las que piden atención, los avisos y la vista elegida (con la arena cocida).
			const hoja = h('article', { class: 'hoja-ficha informe monitor-informe' });
			const { piden, suben } = atencion(todas());
			hoja.append(cabeza.cloneNode(true));
			(hoja.querySelector('.mon-rosa') as HTMLElement | null)?.remove();
			const tbA = h('table', { class: 'tabla-sutil mon-t' }, h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Entidad'), h('th', { class: 'num' }, 'Score'), h('th', { class: 'num' }, 'Mes'), h('th', {}, 'Por qué'))),
				h('tbody', {}, ...piden.map((e, i) => h('tr', {}, h('td', { class: 'num' }, String(i + 1)), h('td', {}, nombreEnt(e)), h('td', { class: 'num' }, f.score(e.shown)), h('td', { class: 'num' }, e.delta1 === null ? '—' : f.deltaEntero(e.delta1)), h('td', {}, e.motivo)))));
			hoja.append(h('section', { class: 'informe-seccion primera' }, h('h2', { class: 'informe-titulo' }, `Piden atención · ${f.numero(piden.length)}`), tbA,
				suben.length ? h('p', { class: 'nota' }, `Suben: ${suben.slice(0, 12).map((e) => `${nombreEnt(e)} (${e.sube})`).join('; ')}.`) : ''));
			const vistaCopia = h('section', { class: 'informe-seccion' }, h('h2', { class: 'informe-titulo' }, `${cfo() ? 'Tus empresas' : 'La cartera'}, en ${FORMAS.find((x) => x.id === est.forma)!.nombre.toLowerCase()}`), h('p', { class: 'mon-frase' }, descripcion()));
			const vis = visibles();
			if (vis.length) {
				if (est.modo === 'arena') {
					// En papel la arena va quieta y con sus rótulos: se compone con el ancho de la hoja.
					const datos = { ...datosArena(vis), movil: false };
					const alto = altoArena(datos);
					const caja = h('div', { class: `mon-lienzo forma-${est.forma}`, style: { height: `${alto}px` } });
					const arena = h('div', { class: 'mon-lienzo-arena' });
					placa(arena, (cj) => ({ tipo: 'vista', x: cj.x, y: cj.y, w: cj.w, h: cj.h, datos }));
					const rot = h('div', { class: 'mon-rotulos' });
					caja.append(arena, rot);
					vistaCopia.append(caja);
					// Los rótulos se ponen al medir la hoja (imprimir.ts llama a esto tras montar la capa).
					(caja as HTMLElement & { rotular?: () => void }).rotular = () => rotularForma(rot, disponer(datos, caja.clientWidth, alto), datos, vis, caja.clientWidth, alto);
				} else {
					tope = 400;
					vistaCopia.append(tabla(vis));
					tope = 60;
				}
			}
			hoja.append(vistaCopia);
			return hoja;
		},
	};
	// (lienzoActual se guarda para depurar desde la consola.)
	void lienzoActual;
}
