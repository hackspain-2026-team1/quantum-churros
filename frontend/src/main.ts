import '@fontsource-variable/newsreader/opsz.css';
import '@fontsource-variable/newsreader/opsz-italic.css';
import '@fontsource-variable/schibsted-grotesk';
import './estilos.css';

import { Arena } from './arena/arena';
import { escenaPlano, escenaTapiz, nGranos, ordenarVisibles, reglaPagina, type Fila, type Posicion } from './arena/escenas';
import { CORTE_SCORE, ESCALAS, ZONAS, conEscala, contexto, type Consulta, type Contexto, type Zona } from './datos/consulta';
import { fmt, tendencia } from './datos/derivados';
import type { Cartera } from './datos/modelo';
import { carteraMotor, hayBundle } from './datos/motor';
import { Almacen, SECCIONES, esPagina, type Estado } from './estado';
import { DOMINIO_SCORE, ajustarDominios, alturas, marcasRitmo, marco, scoreEnX, xScore, yRitmo, type Marco } from './geometria';
import { h, vaciar } from './vistas/dom';
import { hayInforme, prepararInforme, quitarInforme } from './vistas/imprimir';
import { crearPaginas, type Paginas } from './vistas/pagina';
import { escenaPlacas } from './arena/placas';
import { crearFrase, guardarVisita, leerVisita } from './vistas/frase';
import { lineaGranos, logotipo, monogramaArena } from './vistas/marca';
import { miniatura } from './vistas/piezas';
import { crearRegla } from './vistas/regla';
import { triaje } from './vistas/triaje';
import { fijarMeses, nombreGrupo, ritmoEnPalabras } from './vistas/voz';

/**
 * La cartera: el bundle real del motor si está servido en /datos (frontend/public/datos), o la
 * sintética si no lo está o si la URL lleva ?datos=sinteticos.
 */
async function cargarCartera(app: HTMLElement): Promise<Cartera> {
	// Los datos sintéticos solo existen si se piden en la URL, y nunca en la versión de producción.
	const pideSinteticos = new URLSearchParams(location.search).get('datos') === 'sinteticos';
	if (pideSinteticos && !import.meta.env.PROD) return (await import('./datos/sintetico')).carteraSintetica();
	if (!(await hayBundle())) throw new Error('sin-bundle');
	const barra = h('span', { class: 'carga-barra' });
	const carga = h('div', { class: 'carga', role: 'status' }, h('p', {}, 'Leyendo la cartera del motor'), h('span', { class: 'carga-pista' }, barra));
	app.append(carga);
	try {
		return await carteraMotor((f) => { barra.style.transform = `scaleX(${f})`; });
	} finally {
		carga.classList.add('fuera');
		setTimeout(() => carga.remove(), 400);
	}
}

async function iniciar() {
	const app = document.getElementById('app')!;
	let c: Cartera;
	try {
		c = await cargarCartera(app);
	} catch (err) {
		const falta = err instanceof Error && err.message === 'sin-bundle';
		if (!falta) console.error(err);
		app.append(h('div', { class: 'sin-datos' }, h('h1', {}, falta ? 'Rumbo no encuentra los datos' : 'Rumbo no puede leer los datos'),
			falta ? null : h('p', {}, `Error: ${err instanceof Error ? err.message : String(err)}`),
			h('p', {}, 'Falta el bundle del motor en public/datos (y los ficheros de Rumbo en public/rumbo). Rumbo no enseña nada que no salga de los datos, así que no arranca con otros.'),
			h('p', {}, 'Para prepararlos: exportar con el motor (make export), ejecutar scripts/datos/parametros.py y productos.py y generar la previsión con el motor (make forecast). Ver interfaz/DIARIO.md.')));
		return;
	}
	// En producción, un bundle sintético no se enseña nunca.
	if (import.meta.env.PROD && c.manifiesto?.dataset_hash.startsWith('synthetic')) {
		app.append(h('div', { class: 'sin-datos' }, h('h1', {}, 'Bundle sintético'), h('p', {}, 'Este bundle es el de pruebas. Rumbo no lo enseña en producción.')));
		return;
	}
	fijarMeses(c.months);
	{
		const t = c.months.length - 1;
		const scores: number[] = [], ritmos: number[] = [];
		for (const g of c.groups) {
			if (g.meses[t].shown !== null) scores.push(g.meses[t].shown! / 10);
			const r = tendencia(g, t);
			if (r !== null) ritmos.push(r);
		}
		ajustarDominios(scores, ritmos);
	}
	const S = new Almacen(c);
	const lienzo = document.getElementById('arena') as HTMLCanvasElement;
	const visitaAnterior = leerVisita();

	await Promise.all([
		document.fonts.load("600 120px 'Newsreader Variable'"),
		document.fonts.load("500 26px 'Newsreader Variable'"),
		document.fonts.load("500 13px 'Schibsted Grotesk Variable'"),
	]).catch(() => {});

	// ?captura: cada grano va directo a su destino y no hay animaciones (para verificar en headless).
	const captura = new URLSearchParams(location.search).has('captura');
	if (captura) {
		document.documentElement.classList.add('captura');
		Object.assign(lienzo.style, { width: `${innerWidth}px`, height: `${innerHeight}px`, inset: 'auto', left: '0', top: '0' });
	}
	let arena: Arena;
	try {
		arena = new Arena(lienzo, nGranos(c.groups.length));
		if (captura) arena.reducido = true;
	} catch {
		app.append(h('div', { class: 'aviso-webgl' }, 'Este navegador no puede dibujar la arena (le falta WebGL2). Prueba con Chrome, Safari o Firefox actualizados.'));
		return;
	}

	// Contextos en caché: la frase pide muchos (uno por opción que enseña su recuento).
	const cache = new Map<string, Contexto>();
	const ctxDe = (q: Consulta) => {
		const k = JSON.stringify(q);
		let x = cache.get(k);
		if (!x) { x = contexto(c, q); cache.set(k, x); if (cache.size > 80) cache.delete(cache.keys().next().value!); }
		return x;
	};

	// ─── Esqueleto ─────────────────────────────────────────────
	const barra = h('header', { class: 'barra' });
	barra.style.setProperty('--linea-granos', `url(${lineaGranos()})`);
	// La marca: el monograma, hecho de arena, y el logotipo. En la portada no aparece: la portada es la marca.
	const marca = h('button', { class: 'marca', type: 'button', title: 'Volver a la portada', 'aria-label': 'Rumbo, volver a la portada' }, monogramaArena(30), logotipo(21), h('span', { class: 'marca-de' }, 'para Embat'));
	marca.addEventListener('click', () => S.fijar({ vista: 'entrada', sel: null, emp: null }, true));
	const lentes = h('div', { class: 'lentes', role: 'radiogroup', 'aria-label': 'Lente de la cartera' });
	for (const [k, t, d] of [['score', 'Score', 'Nivel y ritmo de hoy'], ['productos', 'Productos', 'Qué tienen contratado y qué les encaja'], ['horizonte', 'Horizonte', 'Dónde estarán en seis meses si nada cambia']] as const) {
		const b = h('button', { type: 'button', class: 'lente', 'data-lente': k, role: 'radio', title: d }, t);
		b.addEventListener('click', () => S.fijar({ lente: k }, true));
		lentes.append(b);
	}
	// La campana: avisos de organización del mes sin revisar (la revisión es la de la bandeja).
	const campana = h('button', { class: 'campana', type: 'button', title: 'Avisos del mes sin revisar' }, h('span', { class: 'campana-grano', 'aria-hidden': 'true' }), h('span', { class: 'campana-n' }));
	const pintarCampana = () => {
		const t = ctxDe(S.e.q).corte;
		const n = c.groups.reduce((s, g) => s + g.alerts.filter((a) => a.month === t && a.state === 'fired' && !triaje.de(a.id)).length, 0);
		campana.querySelector('.campana-n')!.textContent = `${n} ${n === 1 ? 'aviso' : 'avisos'}`;
		campana.classList.toggle('vacia', n === 0);
		campana.setAttribute('aria-label', `${n} avisos del mes sin revisar`);
	};
	campana.addEventListener('click', () => paginas?.irAvisos());
	triaje.oir(pintarCampana);
	const botonMetodo = h('button', { class: 'boton-metodo', type: 'button' }, 'Metodología');
	botonMetodo.addEventListener('click', () => S.fijar({ vista: 'metodologia' }, true));
	const botonFinanciacion = h('button', { class: 'boton-financiacion', type: 'button' }, 'Financiación');
	botonFinanciacion.addEventListener('click', () => S.fijar({ vista: 'financiacion' }, true));
	const selPlano = h('button', { class: 'vista-btn', type: 'button', 'aria-pressed': 'false' });
	const selTapiz = h('button', { class: 'vista-btn', type: 'button', 'aria-pressed': 'false' });
	const selector = h('nav', { class: 'selector', 'aria-label': 'Forma de ver la cartera' }, selPlano, selTapiz);
	const nota = c.origen === 'motor' && c.meta
		? h('span', { class: 'nota-datos real', title: `Bundle ${c.meta.bundle_id} · motor ${c.meta.engine_version} · generado el ${new Date(c.meta.generated_at).toLocaleString('es-ES')}. Datos del reto (dataset ${c.meta.dataset_hash.slice(0, 12)}).` }, `datos reales · motor ${c.meta.engine_version}`)
		: h('span', { class: 'nota-datos', title: 'Cartera sintética con la forma exacta del contrato del motor (xray-export-v1). Se usa cuando no hay bundle servido o con ?datos=sinteticos. Ver frontend/DIARIO.md.' }, 'datos sintéticos');
	const botonAyuda = h('button', { class: 'boton-ayuda', type: 'button', 'aria-label': 'Cómo se usa (?)', title: 'Cómo se usa (?)' }, '?');
const hueco = h('span', { class: 'hueco barra-hueco' });
barra.append(marca, hueco, lentes, selector, nota, campana, botonFinanciacion, botonMetodo, botonAyuda);
	const anot = h('div', { class: 'anot' });
	const capaExp = h('div', { class: 'anot capa-exp' });
	const lazo = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
	lazo.setAttribute('class', 'lazo');
	const lazoPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
	lazo.append(lazoPath);
	const pista = h('div', { class: 'pista', role: 'status' });
	const deshacer = h('button', { class: 'deshacer', type: 'button', title: 'Deshacer (⌘Z)' }, flechaDeshacer(), 'deshacer');
	const ayuda = h('div', { class: 'ayuda', role: 'dialog', 'aria-label': 'Cómo se usa' });
	app.append(anot, capaExp, lazo, barra);

	let reproduciendo = 0;
	let modo: 'avanza' | 'acumula' = 'avanza';
	let M: Marco = marco(innerWidth, innerHeight, 120, false);
	let posiciones: Posicion[] = [];
	let filas: Fila[] = [];
	let origen: { x: number; y: number } | null = null;

	const frase = crearFrase(c, S, ctxDe, () => {}, () => M.movil, { volver: () => volver(), abrirGrupo: (id) => abrir(id, { x: M.W / 2, y: M.zona.y }) , orden: () => ordenarVisibles(ctxDe(S.confirmado.q)).map((gi) => c.groups[gi].id) });
	app.append(frase.raiz, pista, deshacer, ayuda);
	const regla = crearRegla(c, S, alternarPlay, () => { modo = modo === 'avanza' ? 'acumula' : 'avanza'; pintarHtml(S.e); }, () => modo);
	app.append(regla.raiz);
	const paginas: Paginas | null = c.manifiesto ? crearPaginas(app, S, c, c.manifiesto, {
		alCambiarArena: () => { if (esPagina(S.e.vista)) componer(S.e, false); },
		alDesplazar: () => arena.desplazar(paginas!.desplazamiento()),
		irCartera: (v) => S.fijar({ vista: v ?? S.e.cartera }, true),
		esMovil: () => M.movil,
		corte: () => c.months[ctxDe(S.e.q).corte],
		imprimir: () => imprimir(),
		hilo: (hs) => arena.hilos(hs),
	}) : null;
	paginas?.ocultar();
	// La miga de pan de las páginas vive en la cabecera, junto a la marca.
	if (paginas) hueco.before(paginas.miga);

	// Imprimir (o guardar en PDF): el informe de la ficha abierta. También con ⌘P.
	function imprimir() {
		prepararInforme(paginas?.informe() ?? null);
		print();
	}
	addEventListener('beforeprint', () => {
		if (document.querySelector('.panel-propuesta')) {
			document.body.classList.add('imprimir-propuesta');
			return;
		}
		if (!hayInforme()) prepararInforme(paginas?.informe() ?? null);
	});
	addEventListener('afterprint', () => {
		document.body.classList.remove('imprimir-propuesta');
		quitarInforme();
	});
	void capaExp;

	ayuda.append(h('h2', {}, 'Cómo se usa'), h('p', {}, 'La frase de arriba dice lo que ves. Toca cualquier trozo para cambiarlo, o escribe en cualquier parte.'));
	for (const [k, d] of [['1 2 3 4', 'Scoring, productos, acciones y técnico (en una organización o una empresa)'], ['← → en una ficha', 'El mes que se mira'], ['Escribe', '«se tuercen», «T2», «factoring», «42»…'], ['← →', 'Mover el intervalo un periodo'], ['⇧ ← →', 'Mover solo «desde»'], ['[ ]', 'Escala más fina o más gruesa'], ['Espacio', 'Reproducir o parar'], ['↵', 'Abrir el grupo señalado'], ['↑ ↓', 'Grupo anterior o siguiente'], ['Esc', 'Subir un nivel o quitar el último filtro'], ['⌘Z', 'Deshacer'], ['?', 'Esta ayuda']])
		ayuda.append(h('div', { class: 'ayuda-fila' }, h('span', { class: 'ayuda-tecla' }, k), h('span', {}, d)));
	botonAyuda.addEventListener('click', () => ayuda.classList.toggle('ver'));

	// ─── Medidas ───────────────────────────────────────────────
	function medir() {
		arena.redimensionar();
		const { ancho, alto } = arena.dimensiones;
		const A = alturas(ancho);
		const barraAlto = A.barra + A.regla;
		frase.raiz.style.top = `${barraAlto + (ancho < 700 ? 2 : 6)}px`;
		const pad = ancho < 700 ? 16 : ancho < 1100 ? 28 : 44;
		frase.raiz.style.left = `${pad}px`;
		frase.raiz.style.right = `${pad}px`;
		const abajo = frase.raiz.getBoundingClientRect().bottom || barraAlto + 80;
		M = marco(ancho, alto, abajo, false);
		if (paginas) {
			paginas.raiz.style.top = `${barraAlto}px`;
			paginas.raiz.style.bottom = '0px';
		}
	}

	// ─── Composición de la arena ───────────────────────────────
	function componer(e: Estado, suave: boolean) {
		if (esPagina(e.vista) && paginas) {
			const [arriba, abajo] = paginas.franja();
			arena.recortar(arriba, abajo);
			arena.desplazar(paginas.desplazamiento());
			// La regla va también en las fichas: fija arriba, con los avisos de la entidad abierta.
			const ctx = ctxDe(e.q);
			const propios = paginas.avisosPropios()?.map((a) => ({ month: c.months.indexOf(a.month), mejora: a.mejora })).filter((a) => a.month >= 0) ?? null;
			const regla = e.vista === 'organizacion' || e.vista === 'empresa' ? reglaPagina(ctx, M, propios) : undefined;
			// Los granos que sobran reposan debajo de toda la página, no solo del viewport:
			// si no, en la portada queda una franja blanca al final del monitor.
			const cuerpo = paginas.raiz.querySelector('.pagina-cuerpo') as HTMLElement | null;
			const altoPagina = Math.max(M.H, (cuerpo?.getBoundingClientRect().top ?? 0) + (cuerpo?.scrollHeight ?? paginas.raiz.scrollHeight));
			arena.fijar(escenaPlacas(paginas.placas(), arena.n, M.W, altoPagina, M.movil, regla));
			posiciones = []; filas = [];
			return;
		}
		arena.recortar(-1e6, 1e6);
		arena.desplazar(0);
		const ctx = ctxDe(e.q);
		const o = { sel: e.sel, hover: e.hover, zonaHover: e.zonaHover, origen: suave ? null : origen, suave, lente: e.lente };
		if (e.vista === 'plano') { const r = escenaPlano(ctx, M, o, arena.px, arena.py); posiciones = r.posiciones; filas = []; arena.fijar(r.escena); }
		else if (e.vista === 'tapiz') { const r = escenaTapiz(ctx, M, o, arena.px, arena.py); filas = r.filas; posiciones = []; arena.fijar(r.escena); }
		origen = null;
	}

	// ─── Capa HTML de cada vista ───────────────────────────────
	function etiqueta(x: number, y: number, clase: string, ...hijos: (Node | string)[]) {
		const el = h('div', { class: `etq ${clase}` }, ...hijos);
		el.style.left = `${x}px`; el.style.top = `${y}px`;
		anot.append(el);
		return el;
	}

	function pintarAnotaciones(e: Estado, ctx: Contexto) {
		vaciar(anot);
		if (esPagina(e.vista)) return;
		const z = M.zona;
		if (e.vista === 'plano') {
			for (const s of [0, 20, 40, 60, 80, 100].filter((v) => v > DOMINIO_SCORE[0])) etiqueta(xScore(M, s), z.y + z.h + 2, 'eje-x', String(s));
			etiqueta(z.x + z.w, z.y + z.h + 14, 'eje-titulo der', 'score');
			const ticks = marcasRitmo(M.movil);
			for (const v of ticks) etiqueta(z.x - 8, yRitmo(M, v), 'eje-y', v === 0 ? '0' : `${v > 0 ? '+' : '−'}${String(Math.abs(v)).replace('.', ',')}`);
			etiqueta(M.pad, z.y - 18, 'eje-titulo', M.movil ? 'ritmo' : 'ritmo, en puntos al mes');
			if (e.lente !== 'score') etiqueta(z.x + z.w / 2, z.y - 18, 'eje-titulo lente-leyenda', e.lente === 'horizonte'
				? (c.horizontes && c.months[ctx.corte] === c.horizontes.cut ? 'Horizonte: cada organización donde estará en seis meses si nada cambia (mediana de 400 simulaciones); la estela sale de donde está hoy' : `Horizonte: los horizontes se calculan desde ${c.horizontes ? fmt.mesLargo(c.horizontes.cut) : '—'}`)
				: 'Productos: en azul, a las que les encaja alguno según las acciones del motor; en tinta, las que ya tienen y no necesitan más');
		}
		if (e.vista === 'tapiz') {
			for (const f of filas) if (f.id === e.hover || f.id === e.sel) {
				const v = ctx.valor(f.gi, ctx.pHasta);
				const el = etiqueta(M.tiempo.x - 10, f.y, 'fila-etq', `${nombreGrupo(f.id)} · ${fmt.score(v)}`);
				el.style.transform = 'translate(-100%, -50%)';
			}
			if (!M.movil) etiqueta(M.pad, z.y - 18, 'eje-titulo', 'tinta densa, score alto');
		}
		{
			const fuera = ctx.fuera.size;
			if (fuera) {
				const b = h('button', { class: 'sedimento-etq', type: 'button', title: 'Quitar el tamiz' }, `${fuera} fuera del tamiz`, h('span', {}, ' · devolverlos'));
				b.addEventListener('click', () => S.consulta({ ...S.confirmado.q, filtros: [] }));
				b.style.left = `${M.sedimento.x}px`;
				b.style.top = `${M.sedimento.y + M.sedimento.h + 3}px`;
				anot.append(b);
			}
			if (!ctx.visibles.size) {
				const el = etiqueta(z.x + z.w / 2, z.y + z.h / 2, 'vacio', 'Ningún grupo pasa el tamiz en este periodo. ');
				const amp = h('button', { class: 'ampliar', type: 'button' }, 'Ver toda la historia');
				amp.addEventListener('click', () => S.consulta({ ...S.confirmado.q, desde: 0, hasta: ctx.periodos.length - 1 }));
				el.append(amp);
			}
		}
		pintarLineaHover(e, ctx);
	}

	/** La línea junto al cometa señalado: nombre, score y ritmo, sin caja. */
	function pintarLineaHover(e: Estado, ctx: Contexto) {
		anot.querySelector('.linea-hover')?.remove();
		if (e.vista !== 'plano' || !e.hover) return;
		const p = posiciones.find((q) => q.id === e.hover);
		if (!p || !p.visible) return;
		const v = ctx.valor(p.gi, ctx.pHasta);
		const el = h('div', { class: 'linea-hover' }, h('b', {}, nombreGrupo(p.id)), ` · ${fmt.score(v)} · ${ritmoEnPalabras(ctx.ritmo(p.gi))}`, h('span', { class: 'linea-pista' }, M.movil ? ' · toca otra vez para abrir' : ' · clic para abrir'));
		const aLaIzquierda = p.x > M.zona.x + M.zona.w * 0.62;
		el.style.left = `${p.x + (aLaIzquierda ? -p.r - 10 : p.r + 10)}px`;
		el.style.top = `${p.y}px`;
		if (aLaIzquierda) el.style.transform = 'translate(-100%, -50%)';
		anot.append(el);
	}

	function pintarSelector(e: Estado, ctx: Contexto) {
		const vis = [...ctx.visibles].slice(0, 170);
		const plano = vis.map((gi) => ({ x: (ctx.valor(gi, ctx.pHasta)! / 10 - 15) / 85, y: 0.5 - Math.max(-0.5, Math.min(0.5, (ctx.ritmo(gi) ?? 0) / 5)), t: 0 }));
		const orden = ordenarVisibles(ctx).slice(0, 40);
		const tapiz: { x: number; y: number; t: number }[] = [];
		orden.forEach((gi, r) => ctx.periodos.forEach((p, k) => { if (p.i > ctx.pHasta.i) return; const v = ctx.valor(gi, p); if (v !== null) tapiz.push({ x: k / Math.max(1, ctx.periodos.length - 1), y: r / 40, t: Math.max(0, Math.min(1, (v / 10 - 25) / 65)) }); }));
		vaciar(selPlano); vaciar(selTapiz);
		selPlano.append(miniatura('plano', plano), h('span', {}, 'Plano'));
		selTapiz.append(miniatura('tapiz', tapiz), h('span', {}, 'Tapiz'));
		selPlano.setAttribute('aria-pressed', String(e.vista === 'plano'));
		selTapiz.setAttribute('aria-pressed', String(e.vista === 'tapiz'));
		selPlano.title = 'Plano: el nivel y el ritmo de cada grupo';
		selTapiz.title = 'Tapiz: cada grupo, periodo a periodo';
	}
	selPlano.addEventListener('click', () => irA('plano'));
	selTapiz.addEventListener('click', () => irA('tapiz'));

	function pintarHtml(e: Estado) {
		const ctx = ctxDe(e.q);
		frase.pintar(e, ctx);
		pintarAnotaciones(e, ctx);
		regla.pintar(e, ctx, M, visitaAnterior);
		if (esPagina(e.vista) && paginas) paginas.pintar(e); else paginas?.ocultar();
		for (const b of lentes.querySelectorAll<HTMLElement>('.lente')) b.setAttribute('aria-checked', String(b.dataset.lente === e.lente));
		pintarSelector(e, ctx);
		pintarCampana();
		document.body.dataset.vista = e.vista;
		colocarDeshacer();
	}

	// ─── Reacción al estado ────────────────────────────────────
	let temporizadorDeshacer = 0;
	S.oir((e, a) => {
		const vistaCambia = e.vista !== a.vista || (esPagina(e.vista) && (e.sel !== a.sel || e.emp !== a.emp || e.sec !== a.sec || e.finRol !== a.finRol || e.finCaso !== a.finCaso)) || e.lente !== a.lente;
		const qCambia = JSON.stringify(e.q) !== JSON.stringify(a.q);
		const soloTiempo = qCambia && JSON.stringify({ ...e.q, desde: 0, hasta: 0 }) === JSON.stringify({ ...a.q, desde: 0, hasta: 0 });
		const efimero = !vistaCambia && !qCambia;
		// La vista va en el cuerpo antes de medir: cambia el cuerpo de letra de la frase.
		document.body.dataset.vista = e.vista;
		// La arena solo se aparta al paso del cursor en la portada; en reposo, quieta.
		arena.apartar = e.vista === 'entrada';
		arena.respira = e.vista === 'entrada' || e.vista === 'plano' || e.vista === 'tapiz' ? 0.35 : 0;
		if (vistaCambia) arena.hilos([]);
		if (vistaCambia || qCambia) {
			// La frase puede cambiar de altura: se pinta primero y luego se mide el marco.
			frase.pintar(e, ctxDe(e.q));
			if (!e.previa || vistaCambia) medir();
		}
		const suave = !vistaCambia && (e.previa || soloTiempo || e.reproduciendo);
		if (esPagina(e.vista)) {
			// La página pinta su HTML (a veces tras leer ficheros) y luego pide la arena.
			if (vistaCambia || qCambia) pintarHtml(e);
		} else {
			if (vistaCambia || qCambia) componer(e, suave);
			else if (e.hover !== a.hover || e.zonaHover !== a.zonaHover) componer(e, true);
			if (!efimero || e.reproduciendo !== a.reproduciendo) pintarHtml(e);
			else if (e.vista === 'tapiz') pintarAnotaciones(e, ctxDe(e.q));
			else pintarLineaHover(e, ctxDe(e.q));
		}
		if (qCambia && !e.previa && !e.reproduciendo && !a.previa) {
			deshacer.classList.add('ver');
			clearTimeout(temporizadorDeshacer);
			temporizadorDeshacer = window.setTimeout(() => deshacer.classList.remove('ver'), 5000);
		}
	});
	deshacer.addEventListener('click', () => { deshacer.classList.remove('ver'); S.deshacer(); });
	function colocarDeshacer() {
		const r = frase.raiz.querySelector('.frase-linea')?.getBoundingClientRect();
		if (!r) return;
		deshacer.style.top = `${r.bottom + 4}px`;
		deshacer.style.left = `${Math.max(M.pad, Math.min(r.right - 96, innerWidth - 130))}px`;
	}

	// ─── Acciones ──────────────────────────────────────────────
	function abrir(id: string, desde?: { x: number; y: number }) {
		const p = posiciones.find((q) => q.id === id);
		origen = desde ?? (p ? { x: p.x, y: p.y } : { x: M.W / 2, y: M.H / 2 });
		arena.pulsar(origen.x, origen.y, 50, 0.5);
		parar();
		pintarPista(0, 0, null);
		S.fijar({ vista: 'organizacion', sel: id, emp: null, sec: 'scoring', hover: null, zonaHover: null }, true);
	}
	/** Sube un nivel: empresa → organización → entrada; la metodología vuelve a la entrada. */
	function volver() {
		origen = { x: M.pad + 90, y: M.zona.y + 60 };
		if (S.e.vista === 'empresa') S.fijar({ vista: 'organizacion', emp: null }, true);
		else if (S.e.vista === 'organizacion' || S.e.vista === 'metodologia' || S.e.vista === 'financiacion') S.fijar({ vista: 'entrada', sel: null, emp: null }, true);
		else S.fijar({ vista: 'entrada', hover: null }, true);
	}
	function irA(v: 'plano' | 'tapiz') {
		if (S.e.vista === v) return;
		origen = { x: M.W / 2, y: M.zona.y + M.zona.h / 2 };
		S.fijar({ vista: v, hover: null }, true);
	}
	function tamizar(filtroNuevo: Consulta['filtros'][number]) {
		const q = S.confirmado.q;
		const filtros = q.filtros.filter((f) => f.tipo !== filtroNuevo.tipo);
		filtros.push(filtroNuevo);
		S.efimero({ zonaHover: null, hover: null });
		S.consulta({ ...q, filtros });
	}

	// Reproducir: la ventana avanza (o acumula) un periodo cada vez.
	function alternarPlay() { reproduciendo ? parar() : reproducir(); }
	function reproducir() {
		let q = S.confirmado.q;
		const ultimo = ctxDe(q).periodos.length - 1;
		if (q.hasta >= ultimo) {
			const largo = modo === 'avanza' ? q.hasta - q.desde : 0;
			q = { ...q, desde: 0, hasta: largo };
			S.fijar({ q }, true);
		}
		S.efimero({ reproduciendo: true });
		const mesesPorPeriodo = ESCALAS.find((x) => x.id === q.escala)!.meses;
		const paso = Math.round(420 + 180 * Math.log2(mesesPorPeriodo));
		reproduciendo = window.setInterval(() => {
			const q2 = S.confirmado.q;
			const ult = ctxDe(q2).periodos.length - 1;
			if (q2.hasta >= ult) return parar();
			S.fijar({ q: { ...q2, hasta: q2.hasta + 1, desde: modo === 'avanza' ? q2.desde + 1 : q2.desde } }, false);
		}, paso);
	}
	function parar() {
		if (!reproduciendo) return;
		clearInterval(reproduciendo);
		reproduciendo = 0;
		S.efimero({ reproduciendo: false });
	}
	function moverTiempo(d: number, soloDesde: boolean) {
		parar();
		const q = S.confirmado.q;
		const ult = ctxDe(q).periodos.length - 1;
		if (soloDesde) return S.consulta({ ...q, desde: Math.max(0, Math.min(q.hasta, q.desde + d)) });
		const largo = q.hasta - q.desde;
		const hasta = Math.max(largo, Math.min(ult, q.hasta + d));
		if (hasta !== q.hasta) S.consulta({ ...q, desde: hasta - largo, hasta });
	}
	function cambiarEscala(d: number) {
		const orden = ESCALAS.map((x) => x.id);
		const i = orden.indexOf(S.confirmado.q.escala);
		const j = Math.max(0, Math.min(orden.length - 1, i + d));
		if (i !== j) S.consulta(conEscala(c, S.confirmado.q, orden[j]));
	}
	function vecino(d: number) {
		const ctx = ctxDe(S.confirmado.q);
		const orden = ordenarVisibles(ctx).map((gi) => c.groups[gi].id);
		if (!orden.length) return;
		const actual = S.e.vista === 'organizacion' ? S.e.sel : S.e.hover;
		const i = actual ? orden.indexOf(actual) : -1;
		const j = (i + d + orden.length) % orden.length;
		if (S.e.vista === 'organizacion') { origen = { x: M.W / 2, y: M.H / 2 }; S.fijar({ sel: orden[j] }, true); }
		else S.efimero({ hover: orden[j] });
	}

	// ─── Puntero sobre la arena ────────────────────────────────
	function grupoBajo(x: number, y: number): string | null {
		if (S.e.vista === 'plano') {
			let mejor: Posicion | null = null, dm = 1e9;
			for (const p of posiciones) {
				if (!p.visible) continue;
				const d = Math.hypot(p.x - x, p.y - y);
				if (d < Math.max(M.movil ? 16 : 11, p.r + 6) && d < dm) { dm = d; mejor = p; }
			}
			return mejor?.id ?? null;
		}
		if (S.e.vista === 'tapiz') {
			if (x < M.tiempo.x - 4 || x > M.tiempo.x + M.tiempo.w + 4) return null;
			for (const f of filas) if (Math.abs(f.y - y) <= Math.max(2.5, f.alto / 2 + 0.5)) return f.id;
		}
		return null;
	}
	function zonaBajo(x: number, y: number): Zona | null {
		if (S.e.vista !== 'plano') return null;
		const z = M.zona;
		if (x < z.x || x > z.x + z.w || y < z.y || y > z.y + z.h) return null;
		const derecha = scoreEnX(M, x) >= CORTE_SCORE;
		const arriba = y < yRitmo(M, 0);
		return arriba ? (derecha ? 'solida' : 'mejora') : derecha ? 'tuerce' : 'hunde';
	}
	const sobreControl = (t: EventTarget | null) => !!(t as HTMLElement)?.closest?.('button, .frase, .panel, .regla, .barra, .exp-lateral, .ayuda, .exp-cab, .exp-cifras, .sedimento-etq');

	let lazoPuntos: number[] = [];
	let pulsado: { x: number; y: number; tipo: string } | null = null;

	function pintarPista(x: number, y: number, texto: string | null) {
		if (!texto) { pista.classList.remove('ver'); return; }
		pista.textContent = texto;
		pista.classList.add('ver');
		pista.style.left = `${Math.max(8, Math.min(x + 14, innerWidth - pista.offsetWidth - 10))}px`;
		pista.style.top = `${Math.min(y + 18, innerHeight - 40)}px`;
	}

	addEventListener('pointermove', (ev) => {
		if (frase.abierta() || document.body.classList.contains('arrastrando')) return;
		if (esPagina(S.e.vista)) return;
		if (pulsado && S.e.vista === 'plano') {
			const d = Math.hypot(ev.clientX - pulsado.x, ev.clientY - pulsado.y);
			if (d > 8 || lazoPuntos.length) {
				if (!lazoPuntos.length) lazoPuntos.push(pulsado.x, pulsado.y);
				lazoPuntos.push(ev.clientX, ev.clientY);
				lazoPath.setAttribute('d', `M${lazoPuntos[0]},${lazoPuntos[1]} L${lazoPuntos.slice(2).join(' ')} Z`);
				lazo.classList.add('ver');
				const n = gruposEnLazo().length;
				pintarPista(ev.clientX, ev.clientY, n ? `${n} ${n === 1 ? 'grupo' : 'grupos'} dentro · suelta para quedarte con ${n === 1 ? 'él' : 'ellos'}` : 'Rodea los grupos que quieras');
				return;
			}
		}
		if (sobreControl(ev.target) || ev.pointerType === 'touch') {
			if (ev.pointerType !== 'touch' && (S.e.hover || S.e.zonaHover)) S.efimero({ hover: null, zonaHover: null });
			if (ev.pointerType !== 'touch') pintarPista(0, 0, null);
			document.body.style.cursor = '';
			return;
		}
		const id = grupoBajo(ev.clientX, ev.clientY);
		const zona = id ? null : zonaBajo(ev.clientX, ev.clientY);
		if (id !== S.e.hover || zona !== S.e.zonaHover) {
			const p = id ? posiciones.find((q) => q.id === id) : null;
			if (p && id !== S.e.hover) arena.pulsar(p.x, p.y, p.r + 10, 0.18);
			S.efimero({ hover: id, zonaHover: zona });
		}
		document.body.style.cursor = id ? 'pointer' : zona ? 'crosshair' : '';
		if (zona) pintarPista(ev.clientX, ev.clientY, textoZona(zona));
		else pintarPista(0, 0, null);
	});

	function textoZona(zona: Zona) {
		const ctx = ctxDe(S.confirmado.q);
		const n = [...ctx.visibles].filter((gi) => ctx.zona(gi) === zona).length;
		const zz = ZONAS.find((x) => x.id === zona)!;
		return `${n} ${n === 1 ? zz.singular : zz.plural} · clic para quedarte con ${n === 1 ? 'él' : 'ellos'}, o arrastra para rodear`;
	}

	addEventListener('pointerdown', (ev) => {
		if (frase.abierta() || sobreControl(ev.target) || ev.button !== 0) return;
		if (esPagina(S.e.vista)) return;
		pulsado = { x: ev.clientX, y: ev.clientY, tipo: ev.pointerType };
		lazoPuntos = [];
	});

	addEventListener('pointerup', (ev) => {
		const p0 = pulsado;
		pulsado = null;
		if (!p0) return;
		if (lazoPuntos.length > 6) {
			const ids = gruposEnLazo();
			lazo.classList.remove('ver');
			lazoPuntos = [];
			pintarPista(0, 0, null);
			if (ids.length === 1) return abrir(ids[0], { x: ev.clientX, y: ev.clientY });
			if (ids.length) return tamizar({ tipo: 'mano', v: ids });
			return;
		}
		lazo.classList.remove('ver');
		lazoPuntos = [];
		const id = grupoBajo(ev.clientX, ev.clientY);
		if (id) {
			// En pantallas táctiles, el primer toque señala y el segundo abre.
			if (p0.tipo === 'touch' && S.e.hover !== id) { S.efimero({ hover: id, zonaHover: null }); return; }
			return abrir(id, { x: ev.clientX, y: ev.clientY });
		}
		const zona = zonaBajo(ev.clientX, ev.clientY);
		if (zona) {
			if (p0.tipo === 'touch' && S.e.zonaHover !== zona) { S.efimero({ zonaHover: zona, hover: null }); pintarPista(ev.clientX, ev.clientY, textoZona(zona).replace('clic', 'toca otra vez')); return; }
			arena.pulsar(ev.clientX, ev.clientY, 80, 0.3);
			pintarPista(0, 0, null);
			tamizar({ tipo: 'zona', v: zona });
		}
	});

	function gruposEnLazo(): string[] {
		const pts = lazoPuntos;
		const n = pts.length / 2;
		if (n < 3) return [];
		const dentro = (x: number, y: number) => {
			let c2 = false;
			for (let i = 0, j = n - 1; i < n; j = i++) {
				const xi = pts[i * 2], yi = pts[i * 2 + 1], xj = pts[j * 2], yj = pts[j * 2 + 1];
				if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c2 = !c2;
			}
			return c2;
		};
		return posiciones.filter((p) => p.visible && dentro(p.x, p.y)).map((p) => p.id);
	}

	// ─── Teclado ───────────────────────────────────────────────
	addEventListener('keydown', (ev) => {
		const t = ev.target as HTMLElement;
		if (t?.closest?.('input:not([type=checkbox]), textarea')) return;
		if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'z') { ev.preventDefault(); frase.cerrar(); parar(); ev.shiftKey ? S.rehacer() : S.deshacer(); return; }
		// En las páginas, las teclas son de la página: 1–4 cambian de sección, Esc sube un nivel.
		if (esPagina(S.e.vista)) {
			if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
			if (/^[1-5]$/.test(ev.key) && (S.e.vista === 'organizacion' || S.e.vista === 'empresa')) S.fijar({ sec: SECCIONES[Number(ev.key) - 1] }, true);
			else if ((ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') && (S.e.vista === 'organizacion' || S.e.vista === 'empresa') && !t?.closest?.('select')) {
				ev.preventDefault();
				const q = S.confirmado.q, ult = ctxDe(q).periodos.length - 1;
				const hasta = Math.max(0, Math.min(ult, q.hasta + (ev.key === 'ArrowRight' ? 1 : -1)));
				if (hasta !== q.hasta) S.consulta({ ...q, desde: Math.min(q.desde, hasta), hasta });
			}
			else if (ev.key === '?') ayuda.classList.toggle('ver');
			else if (ev.key === 'Escape') { if (ayuda.classList.contains('ver')) ayuda.classList.remove('ver'); else if (S.e.vista !== 'entrada') volver(); }
			return;
		}
		if (frase.tecla(ev)) return;
		if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
		switch (ev.key) {
			case ' ': if (!t?.closest?.('button')) { ev.preventDefault(); alternarPlay(); } break;
			case 'ArrowRight': if (!t?.closest?.('.asa')) { ev.preventDefault(); moverTiempo(1, ev.shiftKey); } break;
			case 'ArrowLeft': if (!t?.closest?.('.asa')) { ev.preventDefault(); moverTiempo(-1, ev.shiftKey); } break;
			case ']': cambiarEscala(1); break;
			case '[': cambiarEscala(-1); break;
			case 'ArrowDown': if (!t?.closest?.('.ficha')) { ev.preventDefault(); vecino(1); } break;
			case 'ArrowUp': if (!t?.closest?.('.ficha')) { ev.preventDefault(); vecino(-1); } break;
			case 'Enter': if (S.e.hover && !esPagina(S.e.vista) && !t?.closest?.('button')) abrir(S.e.hover); break;
			case '1': case '2': case '3': case '4': case '5': if (S.e.vista === 'organizacion' || S.e.vista === 'empresa') S.fijar({ sec: SECCIONES[Number(ev.key) - 1] }, true); break;
			case '?': ayuda.classList.toggle('ver'); break;
			case 'Escape':
				if (ayuda.classList.contains('ver')) ayuda.classList.remove('ver');
				else if (esPagina(S.e.vista) && S.e.vista !== 'entrada') volver();
				else if (S.confirmado.q.filtros.length) S.consulta({ ...S.confirmado.q, filtros: S.confirmado.q.filtros.slice(0, -1) });
				break;
		}
	});

	// ─── Tamaño y visita ───────────────────────────────────────
	let temporizadorResize = 0;
	let primera = true;
	new ResizeObserver(() => {
		if (primera) { primera = false; return; }
		clearTimeout(temporizadorResize);
		temporizadorResize = window.setTimeout(() => { frase.pintar(S.e, ctxDe(S.e.q)); medir(); pintarHtml(S.e); componer(S.e, true); pintarHtml(S.e); }, 80);
	}).observe(document.body);
	const guardar = () => guardarVisita(ctxDe(S.confirmado.q).corte);
	addEventListener('pagehide', guardar);
	document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') guardar(); });

	// ─── Arranque: la arena cae y se posa ──────────────────────
	document.body.dataset.vista = S.e.vista;
	arena.apartar = S.e.vista === 'entrada';
	arena.respira = S.e.vista === 'organizacion' || S.e.vista === 'empresa' || S.e.vista === 'metodologia' ? 0 : 0.35;
	frase.pintar(S.e, ctxDe(S.e.q));
	medir();
	pintarHtml(S.e);
	origen = { x: M.W / 2, y: 0 };
	componer(S.e, false);
	pintarHtml(S.e);
	if (captura) setInterval(() => (document.title = `vp ${innerWidth}x${innerHeight} M ${M.W}x${M.H}`), 300);
	Object.assign(window, { xray: { c, S, arena, ctxDe, get paginas() { return paginas; }, get M() { return M; }, get posiciones() { return posiciones; }, get filas() { return filas; } } });
}

function flechaDeshacer() {
	const ns = 'http://www.w3.org/2000/svg';
	const s = document.createElementNS(ns, 'svg');
	s.setAttribute('width', '16'); s.setAttribute('height', '14'); s.setAttribute('viewBox', '0 0 16 14'); s.setAttribute('aria-hidden', 'true');
	for (let i = 0; i < 9; i++) {
		const a = Math.PI * (0.15 + (i / 8) * 1.1);
		const c = document.createElementNS(ns, 'circle');
		c.setAttribute('cx', String(9 + Math.cos(a) * 5)); c.setAttribute('cy', String(8 - Math.sin(a) * 5)); c.setAttribute('r', '0.9');
		s.append(c);
	}
	const p = document.createElementNS(ns, 'path');
	p.setAttribute('d', 'M2 6.5 L4.3 9.3 L6.8 6.6'); p.setAttribute('fill', 'none'); p.setAttribute('stroke-width', '1.3'); p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round');
	s.append(p);
	return s;
}

iniciar();
