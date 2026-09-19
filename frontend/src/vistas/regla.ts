// La regla del tiempo: calendario, monitor y mando a la vez.
// La arena pinta la línea y los montones de avisos; esta capa pone las etiquetas, las asas, la
// ventana, el reloj de arena y las zonas sensibles de cada periodo.

import { ESCALAS, conEscala, type Consulta, type Contexto, type Filtro } from '../datos/consulta';
import { esMejora, type Cartera } from '../datos/modelo';
import { esPagina, type Almacen, type Estado } from '../estado';
import { avisosPorPeriodo, gruposDeLaRegla } from '../arena/escenas';
import { tramo, type Marco } from '../geometria';
import { h, vaciar } from './dom';
import { relojArena } from './piezas';
import { lineaAviso } from './voz';

export interface Regla {
	raiz: HTMLElement;
	pintar(e: Estado, ctx: Contexto, M: Marco, visita: number | null): void;
}

export function crearRegla(c: Cartera, S: Almacen, alternarPlay: () => void, cambiarModo: () => void, modo: () => 'avanza' | 'acumula'): Regla {
	const raiz = h('div', { class: 'regla', role: 'group', 'aria-label': 'Regla del tiempo' });
	const etiquetas = h('div', { class: 'regla-etiquetas' });
	const zonas = h('div', { class: 'regla-zonas' });
	const ventana = h('div', { class: 'regla-ventana', title: 'Arrastra para mover el intervalo' });
	const asaDesde = h('div', { class: 'asa desde', role: 'slider', tabindex: 0, 'aria-label': 'Desde' }, h('i'), h('i'), h('i'));
	const asaHasta = h('div', { class: 'asa hasta', role: 'slider', tabindex: 0, 'aria-label': 'Hasta' }, h('i'), h('i'), h('i'));
	const nota = h('div', { class: 'regla-nota', role: 'tooltip' });
	const escala = h('div', { class: 'regla-escala' });
	const reproducir = h('button', { class: 'reproducir', type: 'button', 'aria-label': 'Reproducir (espacio)', title: 'Reproducir (espacio)' }, relojArena());
	const modoBtn = h('button', { class: 'modo', type: 'button' });
	const visitaEl = h('button', { class: 'visita', type: 'button', title: 'Ver lo que ha cambiado desde tu última visita' });
	// Mirando un mes pasado, toda la aplicación lo dice, y se vuelve a hoy de un toque.
	const viaje = h('button', { class: 'regla-viaje', type: 'button' });
	raiz.append(zonas, ventana, asaDesde, asaHasta, etiquetas, escala, visitaEl, viaje, nota);
	viaje.addEventListener('click', () => { const q = S.confirmado.q; const ult = actual ? actual.ctx.periodos.length - 1 : q.hasta; S.consulta({ ...q, desde: esPagina(S.e.vista) ? Math.min(q.desde, ult) : Math.max(0, ult - (q.hasta - q.desde)), hasta: ult }); });
	document.getElementById('app')!.append(reproducir, modoBtn);
	reproducir.addEventListener('click', () => alternarPlay());
	modoBtn.addEventListener('click', () => cambiarModo());

	let actual: { e: Estado; ctx: Contexto; M: Marco } | null = null;

	// ─── Pintado ────────────────────────────────────────────
	function pintar(e: Estado, ctx: Contexto, M: Marco, visita: number | null) {
		// La regla manda sobre el intervalo que se lee. En una organización o empresa solo la
		// pestaña de scoring depende de la ventana: en las demás se retira, con sus mandos.
		const sinTiempo = (e.vista === 'organizacion' || e.vista === 'empresa') && e.sec !== 'scoring';
		raiz.hidden = sinTiempo;
		reproducir.hidden = sinTiempo;
		modoBtn.hidden = sinTiempo;
		if (sinTiempo) return;
		actual = { e, ctx, M };
		const R = M.regla;
		Object.assign(raiz.style, { left: `${R.x}px`, top: `${R.y}px`, width: `${R.w}px`, height: `${R.h}px` });
		Object.assign(reproducir.style, { left: `${R.x - 6}px`, top: `${R.y + (M.movil ? 4 : 6)}px` });
		Object.assign(modoBtn.style, { left: `${R.x + 30}px`, top: `${R.y + (M.movil ? 12 : 14)}px` });
		const pagina = esPagina(e.vista);
		raiz.classList.toggle('en-pagina', pagina);
		modoBtn.hidden = pagina || M.movil;
		reproducir.classList.toggle('sonando', e.reproduciendo);
		reproducir.setAttribute('aria-pressed', String(e.reproduciendo));
		modoBtn.textContent = modo() === 'avanza' ? 'la ventana avanza' : 'acumula';
		modoBtn.title = modo() === 'avanza' ? 'Al reproducir, la ventana entera avanza. Clic para acumular.' : 'Al reproducir, «desde» se queda fijo. Clic para que avance la ventana.';
		const x = (px: number) => px - R.x;
		const base = M.movil ? 22 : 24;

		// Etiquetas de los periodos, sin que se pisen.
		vaciar(etiquetas);
		// Primero los periodos del intervalo (siempre visibles); luego el resto, si caben.
		const anchoLetra = M.movil ? 5.8 : 6.4;
		const ocupado: [number, number][] = [];
		const cabe = (a: number, b: number) => ocupado.every(([c0, c1]) => b < c0 - 6 || a > c1 + 6);
		const orden = [...ctx.periodos].sort((a, b) => {
			const da = a.i >= ctx.pDesde.i && a.i <= ctx.pHasta.i ? 0 : 1, db = b.i >= ctx.pDesde.i && b.i <= ctx.pHasta.i ? 0 : 1;
			return da - db || (da ? Math.abs(a.i - ctx.pHasta.i) - Math.abs(b.i - ctx.pHasta.i) : b.i - a.i);
		});
		for (const p of orden) {
			const t = tramo(M, p.meses);
			const w = p.corta.length * anchoLetra;
			const a = x(t.xc) - w / 2, b = x(t.xc) + w / 2;
			if (!cabe(a, b)) continue;
			ocupado.push([a, b]);
			const dentro = p.i >= ctx.pDesde.i && p.i <= ctx.pHasta.i;
			const el = h('span', { class: `regla-etq ${dentro ? 'dentro' : ''} ${p.estado !== 'completo' ? 'incompleto' : ''} ${p.i > ctx.pHasta.i ? 'futuro' : ''}` }, p.corta);
			el.style.left = `${x(t.xc)}px`;
			el.style.top = `${base + 14}px`;
			etiquetas.append(el);
		}

		// Eje temporal: raya y año donde empieza cada año, la convención estándar de un eje x.
		let ano = '';
		for (const p of ctx.periodos) {
			const mes0 = c.months[Math.min(...p.meses)] ?? '';
			const este = mes0.slice(0, 4);
			if (!este || este === ano) continue;
			ano = este;
			const t = tramo(M, p.meses);
			const raya = h('span', { class: 'regla-ano-raya', 'aria-hidden': 'true' });
			raya.style.left = `${x(t.x0)}px`;
			raya.style.top = `${base + (M.movil ? 40 : 44)}px`;
			const marca = h('span', { class: 'regla-ano', 'aria-hidden': 'true' }, este);
			marca.style.left = `${x(t.x0) + 4}px`;
			marca.style.top = `${base + (M.movil ? 38 : 42)}px`;
			etiquetas.append(raya, marca);
		}

		// Zonas sensibles por periodo: arriba mejoras, abajo deterioros.
		vaciar(zonas);
		const giSel = (e.vista === 'organizacion' || e.vista === 'empresa') && e.sel ? c.groups.findIndex((g) => g.id === e.sel) : -1;
		// Desde la silla del CFO, la regla cuenta su historia, no la de la cartera.
		const giCFO = e.modo === 'cfo' && e.cfo ? c.groups.findIndex((g) => g.id === e.cfo) : -1;
		const grupos = giSel >= 0 ? [giSel] : giCFO >= 0 ? [giCFO] : gruposDeLaRegla(ctx);
		const { mejoras, deterioros, lista } = avisosPorPeriodo(ctx, grupos);
		for (const p of ctx.periodos) {
			const t = tramo(M, p.meses);
			const z = h('div', { class: `regla-zona ${p.i > ctx.pHasta.i ? 'futuro' : ''}` });
			Object.assign(z.style, { left: `${x(t.x0)}px`, width: `${t.w}px`, top: '0px', height: `${R.h}px` });
			z.addEventListener('pointermove', (ev) => mostrarNota(ev, p.i, mejoras[p.i], deterioros[p.i], lista));
			z.addEventListener('pointerleave', () => nota.classList.remove('ver'));
			z.addEventListener('click', (ev) => clicPeriodo(ev, p.i, ev.offsetY < base ? 'mejora' : 'deterioro', mejoras[p.i], deterioros[p.i]));
			zonas.append(z);
		}

		// La ventana y sus asas.
		const tA = tramo(M, ctx.pDesde.meses), tB = tramo(M, ctx.pHasta.meses);
		Object.assign(ventana.style, { left: `${x(tA.x0)}px`, width: `${tB.x1 - tA.x0}px`, top: `${base - 9}px`, height: '18px' });
		ventana.hidden = pagina;
		asaDesde.hidden = pagina;
		asaHasta.title = pagina ? 'Hoy: arrastra para ver la ficha en otro mes' : '';
		asaHasta.setAttribute('aria-label', pagina ? 'Mes que se mira' : 'Hasta');
		const ult = ctx.periodos.length - 1;
		viaje.hidden = ctx.pHasta.i >= ult;
		viaje.textContent = `Viendo ${ctx.pHasta.larga} · volver a hoy`;
		document.body.dataset.viaje = ctx.pHasta.i < ult ? '1' : '';
		Object.assign(asaDesde.style, { left: `${x(tA.x0)}px`, top: `${base - 16}px` });
		Object.assign(asaHasta.style, { left: `${x(tB.x1)}px`, top: `${base - 16}px` });
		asaDesde.setAttribute('aria-valuetext', ctx.pDesde.larga);
		asaHasta.setAttribute('aria-valuetext', ctx.pHasta.larga);
		asaDesde.classList.toggle('juntas', ctx.pDesde.i === ctx.pHasta.i);

		// Escala: con su nombre y pista de zoom.
		vaciar(escala);
		escala.append(h('span', { class: 'regla-escala-nombre' }, ESCALAS.find((x) => x.id === ctx.q.escala)!.nombre));
		escala.title = 'Rueda o pellizco sobre la regla para cambiar de escala';

		// Última visita.
		if (visita !== null && visita < ctx.corte) {
			const t = tramo(M, [visita]);
			visitaEl.hidden = false;
			visitaEl.textContent = 'tu última visita';
			visitaEl.dataset.mes = String(visita);
			Object.assign(visitaEl.style, { left: `${x(t.xc)}px`, top: `${base - 30}px` });
		} else visitaEl.hidden = true;
	}

	function mostrarNota(ev: PointerEvent, pi: number, nMej: number, nDet: number, lista: { gi: number; pi: number; kind: string; month: number }[]) {
		if (!actual) return;
		const { ctx } = actual;
		const p = ctx.periodos[pi];
		vaciar(nota);
		const deEste = lista.filter((x) => x.pi === pi);
		nota.append(h('div', { class: 'nota-cab' }, p.larga.charAt(0).toUpperCase() + p.larga.slice(1)));
		if (esPagina(actual.e.vista)) { nota.append(h('div', { class: 'nota-pie' }, 'Clic para ver la ficha en este mes.')); }
		else if (!deEste.length) nota.append(h('div', { class: 'nota-linea tenue' }, pi > ctx.pHasta.i ? 'Todavía no ha pasado.' : 'Sin movimientos confirmados.'));
		for (const a of deEste.slice(0, 7)) nota.append(h('div', { class: `nota-linea ${esMejora(a.kind as never) ? 'sube' : 'baja'}` }, lineaAviso(c.groups[a.gi], a as never)));
		if (deEste.length > 7) nota.append(h('div', { class: 'nota-linea tenue' }, `y ${deEste.length - 7} más`));
		if (esPagina(actual.e.vista)) { /* ya dicho */ }
		else if (nMej || nDet) nota.append(h('div', { class: 'nota-pie' }, `Clic arriba para las ${nMej} mejoras, abajo para los ${nDet} deterioros.`));
		else nota.append(h('div', { class: 'nota-pie' }, 'Clic para ver este periodo.'));
		const r = raiz.getBoundingClientRect();
		nota.classList.add('ver');
		const ancho = nota.offsetWidth;
		const xx = Math.max(0, Math.min(ev.clientX - r.left - ancho / 2, r.width - ancho));
		Object.assign(nota.style, { left: `${xx}px`, top: `${r.height + 4}px` });
	}

	function clicPeriodo(ev: MouseEvent, pi: number, lado: 'mejora' | 'deterioro', nMej: number, nDet: number) {
		if (!actual) return;
		const q = S.confirmado.q;
		if (pi > actual.ctx.periodos.length - 1) return;
		if (ev.shiftKey) {
			// Mayúsculas: extiende el intervalo hasta ese periodo.
			S.consulta({ ...q, desde: Math.min(q.desde, pi), hasta: Math.max(q.hasta, pi) });
			return;
		}
		// En una ficha, la regla solo mueve el mes que se mira.
		if (esPagina(actual.e.vista)) { S.consulta({ ...q, desde: Math.min(q.desde, pi), hasta: pi }); return; }
		const n = lado === 'mejora' ? nMej : nDet;
		const filtros: Filtro[] = q.filtros.filter((f) => f.tipo !== 'mov');
		if (n) filtros.push({ tipo: 'mov', v: lado });
		S.consulta({ ...q, desde: pi, hasta: pi, filtros });
	}

	// ─── Arrastre de asas y ventana ────────────────────────
	function periodoEnX(clientX: number): number {
		if (!actual) return 0;
		const { ctx, M } = actual;
		let mejor = 0, dm = 1e9;
		for (const p of ctx.periodos) {
			const t = tramo(M, p.meses);
			const d = Math.abs(clientX - t.xc);
			if (d < dm) { dm = d; mejor = p.i; }
		}
		return mejor;
	}

	function arrastrar(el: HTMLElement, mover: (pi: number, inicio: Consulta, dxPeriodos: number) => Consulta) {
		let inicio: Consulta | null = null;
		let piInicio = 0;
		el.addEventListener('pointerdown', (ev) => {
			ev.preventDefault(); ev.stopPropagation();
			el.setPointerCapture(ev.pointerId);
			inicio = S.confirmado.q;
			piInicio = periodoEnX(ev.clientX);
			el.classList.add('agarrada');
			document.body.classList.add('arrastrando');
		});
		el.addEventListener('pointermove', (ev) => {
			if (!inicio) return;
			const pi = periodoEnX(ev.clientX);
			const q = mover(pi, inicio, pi - piInicio);
			if (q.desde !== S.e.q.desde || q.hasta !== S.e.q.hasta) S.previsualizar(q);
		});
		const soltar = () => {
			if (!inicio) return;
			const q = S.e.q;
			inicio = null;
			el.classList.remove('agarrada');
			document.body.classList.remove('arrastrando');
			if (q.desde !== S.confirmado.q.desde || q.hasta !== S.confirmado.q.hasta) S.consulta(q);
			else S.previsualizar(null);
		};
		el.addEventListener('pointerup', soltar);
		el.addEventListener('pointercancel', soltar);
	}
	const ultimoP = () => (actual ? actual.ctx.periodos.length - 1 : 0);
	arrastrar(asaDesde, (pi, q) => ({ ...q, desde: Math.min(pi, q.hasta) }));
	arrastrar(asaHasta, (pi, q) => (actual && esPagina(actual.e.vista) ? { ...q, desde: Math.min(q.desde, pi), hasta: pi } : { ...q, hasta: Math.max(pi, q.desde) }));
	arrastrar(ventana, (_pi, q, d) => {
		const largo = q.hasta - q.desde;
		const hasta = Math.max(largo, Math.min(ultimoP(), q.hasta + d));
		return { ...q, desde: hasta - largo, hasta };
	});

	// Teclado en las asas.
	for (const [asa, cual] of [[asaDesde, 'desde'], [asaHasta, 'hasta']] as const) {
		asa.addEventListener('keydown', (ev) => {
			if (ev.key !== 'ArrowLeft' && ev.key !== 'ArrowRight') return;
			ev.preventDefault(); ev.stopPropagation();
			const q = S.confirmado.q;
			const d = ev.key === 'ArrowRight' ? 1 : -1;
			if (cual === 'desde') S.consulta({ ...q, desde: Math.max(0, Math.min(q.hasta, q.desde + d)) });
			else S.consulta({ ...q, hasta: Math.max(q.desde, Math.min(ultimoP(), q.hasta + d)) });
		});
	}

	// Zoom de escala con la rueda o el pellizco.
	let acumulado = 0;
	let bloqueo = 0;
	raiz.addEventListener('wheel', (ev) => {
		ev.preventDefault();
		if (performance.now() < bloqueo) return;
		acumulado += ev.ctrlKey ? -ev.deltaY * 3 : ev.deltaY;
		if (Math.abs(acumulado) < 60) return;
		const orden = ESCALAS.map((x) => x.id);
		const i = orden.indexOf(S.confirmado.q.escala);
		const j = Math.max(0, Math.min(orden.length - 1, i + (acumulado > 0 ? 1 : -1)));
		acumulado = 0;
		bloqueo = performance.now() + 260;
		if (j !== i) S.consulta(conEscala(c, S.confirmado.q, orden[j]));
	}, { passive: false });

	visitaEl.addEventListener('click', () => {
		if (!actual) return;
		const v = Number(visitaEl.dataset.mes ?? -1);
		const pv = actual.ctx.periodos.findIndex((p) => p.meses.includes(v));
		if (pv >= 0) S.consulta({ ...S.confirmado.q, desde: pv, hasta: actual.ctx.periodos.length - 1 });
	});

	return { raiz, pintar };
}
