// Sección IV · Detalles: la trazabilidad completa de una entidad (propuesta 06 §3.4 y 07 §5).
// Traslado de la página de empresa de Bruno (cascada que cuadra al décimo, evidencia por pilar,
// confianza, abstención) a las piezas de Rumbo, más lo que le faltaba: las curvas reales del
// motor con la entidad encima, el veredicto por dentro, la evidencia filtrable, los supuestos y la
// calibración de los horizontes y la huella de cada fichero.

import { carga } from '../datos/carga';
import type { AlertaM, EmpresaM, FilaEvidenciaM, Tabla } from '../datos/contrato';
import { f } from '../datos/formato';
import { importes, nombrePilar } from '../datos/redaccion';
import { h, vaciar } from './dom';
import { desplegable } from './desplegable';
import { primeraMayuscula } from '../datos/formato';
import { hilo, seccion } from './primitivos';
import { triaje } from './triaje';
import { lineaAviso, nudosScore, partitura, type Acciones, type DatosFicha, type FiltroEvidencia } from './ficha';

const NS = 'http://www.w3.org/2000/svg';
const sv = <K extends keyof SVGElementTagNameMap>(tag: K, a: Record<string, string | number>) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(a)) e.setAttribute(k, String(v)); return e; };

export function seccionTecnica(d: DatosFicha, acc: Acciones): HTMLElement {
	const raiz = h('div', { class: 'sec-tecnico' });
	const m = d.mes;
	if (!m) { raiz.append(h('p', { class: 'vacio' }, `Sin datos en ${f.mes(d.corte)}.`)); return raiz; }

	// 1. Qué aporta cada pilar: la lectura pilar a pilar antes de las décimas.
	raiz.append(partitura(d, acc));

	// 2. La cascada, décima a décima.
	const pasos: [string, number, string?][] = [['Punto de partida (referencia ponderada)', m.base]];
	for (const p of m.pillars) pasos.push([nombrePilar(d.man, p.key), p.contrib, p.score === null ? 'sin dato' : `pilar ${f.scoreDec(p.score)} · peso ${f.porcentaje(p.w_eff, 0)}`]);
	pasos.push(['Penalización por el pilar más débil', -m.penalty, d.params ? `λ ${f.numero(d.params.penalty.lam, 2)} · τ ${f.numero(d.params.penalty.tau)}` : undefined]);
	pasos.push(['Tope', -m.cap.amount, m.cap.rule ? d.man.glossary.caps[m.cap.rule] ?? m.cap.rule : m.cap.fired.length ? m.cap.fired.map((x) => d.man.glossary.caps[x] ?? x).join('; ') : 'sin tope']);
	const suma = pasos.reduce((s, x) => s + x[1], 0);
	const escala = Math.max(...pasos.slice(1).map((x) => Math.abs(x[1])), 1);
	let acum = 0;
	const tabla = h('div', { class: 'cascada-t' });
	pasos.forEach(([n, v, det], i) => {
		acum += v;
		const fila = h('div', { class: `ct-fila ${i === 0 ? 'base' : ''}` },
			h('span', { class: 'ct-nombre' }, n, det ? h('span', { class: 'ct-det' }, det) : null),
			h('span', { class: 'ct-barra' }, i === 0 ? null : h('span', { class: `ct-b ${v < 0 ? 'neg' : 'pos'}`, style: { width: `${(Math.abs(v) / escala) * 50}%`, [v < 0 ? 'right' : 'left']: '50%' } })),
			h('span', { class: `ct-v ${v < 0 ? 'neg' : ''}` }, i === 0 ? f.scoreDec(v) : f.delta(v)),
			h('span', { class: 'ct-acum' }, f.scoreDec(acum)));
		// Las filas de pilar se leen como en Scoring: al pasar, el pilar en el horizonte; con clic, su evidencia.
		const pil = i > 0 && i <= m.pillars.length ? m.pillars[i - 1] : null;
		if (pil && pil.score !== null) tocable(fila, pil.key, acc);
		tabla.append(fila);
	});
	tabla.append(h('div', { class: 'ct-fila total' }, h('span', { class: 'ct-nombre' }, 'Score'), h('span', {}), h('span', { class: 'ct-v' }, f.scoreDec(m.shown)), h('span', { class: 'ct-acum' }, suma === m.shown ? 'cuadra al décimo' : `no cuadra: ${f.scoreDec(suma)}`)));
	raiz.append(seccion('La cascada', tabla, h('p', { class: 'nota' }, 'score = base + Σ aportaciones − penalización − tope, en décimas enteras. La confianza no interviene.')));

	// 3. Las curvas del motor con la entidad encima.
	raiz.append(seccion('Dónde cae en cada curva', curvas(d, acc)));

	// 4. El veredicto por dentro.
	const v = m.verdict, t = d.params?.trajectory;
	const umbral = t && v.sigma !== null ? Math.max(t.min_delta_points, t.min_sigma_multiple * (v.sigma / 10)) : null;
	const filasV: [string, string][] = [
		['Dirección y naturaleza', `${v.direction}${v.nature ? ` · ${v.nature}` : ''}${v.available ? '' : ` (sin veredicto: ${v.reason ?? '—'})`}`],
		['Δ3 (cambio en tres meses)', v.delta3 === null ? '—' : `${f.delta(v.delta3)} puntos frente a ${v.compared_to ? f.mes(v.compared_to) : '—'}`],
		['σ propia (cambios mes a mes)', v.sigma === null ? '—' : `${f.scoreDec(v.sigma)} puntos · Δ3/σ ${v.delta3_sigma === null ? '—' : f.numero(v.delta3_sigma, 2)}`],
		['Umbral para moverse', umbral === null ? '—' : `max(${f.numero(t!.min_delta_points)}; ${f.numero(t!.min_sigma_multiple, 1)} × σ) = ${f.numero(umbral, 1)} puntos`],
		['Persistencia', `${f.plural(v.persistence_months, 'mes', 'meses')}${v.detected_since ? ` desde ${f.mes(v.detected_since)}` : ''}`],
		['Pilares que se movieron', v.pillars_moved.length ? v.pillars_moved.map((p) => nombrePilar(d.man, p)).join(', ') : 'ninguno'],
		['Meses observados', f.numero(m.months_observed)],
		['Feed bancario', m.feed_live ? 'vivo' : 'sin actualizar'],
		['Rama de pilares', m.branch.split('+').map((p) => nombrePilar(d.man, p)).join(' + ')],
	];
	if (m.flags.length) filasV.push(['Marcas del mes', m.flags.map((x) => d.man.glossary.flags[x] ?? x).join('; ')]);
	raiz.append(seccion('El veredicto por dentro', dl(filasV)));

	// 5. Confianza y abstención.
	const conf = d.params?.confidence as { label_high_min?: number; label_medium_min?: number } | undefined;
	raiz.append(seccion('Confianza', dl([
		['Historia × cobertura × calidad', `${f.porcentaje(m.conf.history, 0)} × ${f.porcentaje(m.conf.coverage, 0)} × ${f.porcentaje(m.conf.quality, 0)} = ${f.porcentaje(m.conf.value, 0)}`],
		['Etiqueta', `${({ high: 'alta', medium: 'media', low: 'baja' } as Record<string, string>)[m.conf.label]}${conf?.label_high_min ? ` (alta desde ${f.porcentaje(conf.label_high_min, 0)}, media desde ${f.porcentaje(conf.label_medium_min ?? 0, 0)})` : ''}`],
		['Abstención', m.abstain ? `${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason} Qué la levantaría: ${m.abstain.unlock}` : 'no se abstiene'],
	])));

	// 6. El hilo entero.
	raiz.append(seccion('El hilo del score', hilo(nudosScore(d, acc))));

	// 7. Avisos, todos.
	const todos = d.ent.alerts.filter((a) => a.month <= d.corte).sort((a, b) => (a.month < b.month ? 1 : -1));
	const avisos = seccion(`Avisos del motor · ${f.numero(todos.length)}`, bandejaAvisos(d, todos));
	avisos.id = 'bandeja-avisos';
	avisos.tabIndex = -1;
	raiz.append(avisos);

	// 8. Las acciones, con el texto original del motor.
	const accs = m.actions ?? [];
	if (accs.length) raiz.append(seccion('Acciones, tal y como las da el motor', h('ul', { class: 'acciones-motor' }, ...accs.map((a) => {
		const imp = importes(a);
		return h('li', {}, h('b', {}, a.id), ` · pilar ${nombrePilar(d.man, a.pillar).toLowerCase()} de ${f.numero(a.current, 2)} a ${f.numero(a.target, 2)} ${a.unit} · subida ${f.delta(a.uplift_tenths)} → ${f.scoreDec(a.new_score_tenths)} · esfuerzo ${a.effort}`,
			h('p', { class: 'texto-motor' }, `«${a.detail}»`),
			imp.length ? h('p', { class: 'nota' }, `Importe leído del texto del motor (todavía no es un campo): ${imp.map((x) => `${f.euros(x.valor)} ${x.cada === 'una vez' ? '' : `al ${x.cada}`} (${x.sentido})`).join(' o ')}.`) : null);
	})), m.actions_combined ? h('p', { class: 'nota' }, `Todas juntas, según el motor: ${f.scoreDec(m.actions_combined.new_score)} (${f.delta(m.actions_combined.uplift)}).`) : null));

	// 9. Supuestos y calibración de los horizontes.
	raiz.append(seccion('Cómo se calcula el futuro', supuestos(d)));

	// 10. Huella.
	raiz.append(seccion('Huella', huella(d)));
	return raiz;
}

/** La conciliación: la evidencia fila a fila —de dónde salió cada cifra—, filtrable y buscable. */
export function seccionConciliacion(d: DatosFicha, filtro: FiltroEvidencia | null = null): HTMLElement {
	const raiz = h('div', { class: 'sec-conciliacion' });
	if (!d.mes) { raiz.append(h('p', { class: 'vacio' }, `Sin datos en ${f.mes(d.corte)}.`)); return raiz; }
	const ev = seccion('Conciliación', evidencia(d, filtro));
	if (filtro) ev.classList.add('evidencia-filtrada');
	raiz.append(ev);
	return raiz;
}

/** La bandeja de avisos: por estado del motor y por clasificación propia (sin revisar, vistos, descartados). */
function bandejaAvisos(d: DatosFicha, todos: AlertaM[]): HTMLElement {
	const caja = h('div', { class: 'bandeja' });
	const umbral = d.params?.alerts.critical_score ?? null;
	let filtro: 'todos' | 'sin' | 'vistos' | 'descartados' = 'todos';
	const pestanas = h('div', { class: 'escenarios', role: 'radiogroup', 'aria-label': 'Qué avisos' });
	const lista = h('ul', { class: 'avisos completo' });
	const pintar = () => {
		vaciar(pestanas); vaciar(lista);
		const cuenta = { todos: todos.filter((a) => triaje.de(a.id) !== 'descartado').length, sin: todos.filter((a) => !triaje.de(a.id)).length, vistos: todos.filter((a) => triaje.de(a.id) === 'visto').length, descartados: todos.filter((a) => triaje.de(a.id) === 'descartado').length };
		for (const [k, t] of [['todos', 'Todos'], ['sin', 'Sin revisar'], ['vistos', 'Vistos'], ['descartados', 'Descartados']] as const) {
			const b = h('button', { type: 'button', class: `esc ${filtro === k ? 'activo' : ''}`, role: 'radio', 'aria-checked': String(filtro === k) }, `${t} · ${f.numero(cuenta[k])}`);
			b.addEventListener('click', () => { filtro = k; pintar(); });
			pestanas.append(b);
		}
		const ver = todos.filter((a) => { const t = triaje.de(a.id); return filtro === 'todos' ? t !== 'descartado' : filtro === 'sin' ? !t : filtro === 'vistos' ? t === 'visto' : t === 'descartado'; });
		for (const a of ver) lista.append(lineaAviso(a, d.man, umbral, true));
		if (!ver.length) lista.append(h('li', { class: 'nota' }, 'Ningún aviso en esta bandeja.'));
	};
	triaje.oir(() => { if (caja.isConnected) pintar(); });
	pintar();
	caja.append(pestanas, lista);
	return caja;
}

/** Un elemento que señala un pilar: al pasar lo dibuja en el horizonte y con clic filtra su evidencia. */
function tocable(el: HTMLElement, pilar: string, acc: Acciones) {
	el.classList.add('tocable');
	el.tabIndex = 0;
	el.title = 'Pasa por encima para verlo en el horizonte; clic para su evidencia';
	const ir = () => acc.irSeccion('conciliacion', undefined, { pilar });
	el.addEventListener('click', ir);
	el.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') ir(); });
	el.addEventListener('pointerenter', () => acc.horizonte.pilar(pilar));
	el.addEventListener('pointerleave', () => acc.horizonte.pilar(null));
	el.addEventListener('focus', () => acc.horizonte.pilar(pilar));
	el.addEventListener('blur', () => acc.horizonte.pilar(null));
}

function dl(filas: [string, string][]): HTMLElement {
	return h('dl', { class: 'dl-tecnica' }, ...filas.flatMap(([k, v]) => [h('dt', {}, k), h('dd', {}, v)]));
}

// ─── Curvas ────────────────────────────────────────────────────

const TAMANO: Record<string, string> = { micro: 'micro', pequeña: 'small', mediana: 'medium', grande: 'large' };

function curvas(d: DatosFicha, acc: Acciones): HTMLElement {
	const caja = h('div', { class: 'curvas' });
	const P = d.params;
	if (!P) { caja.append(h('p', { class: 'aviso-datos' }, 'Falta rumbo/params.json: ejecuta scripts/datos/parametros.py.')); return caja; }
	const m = d.mes!;
	const serie = (k: string) => {
		const s = d.ent.series.find((x) => x.key === k);
		if (!s) return null;
		const ultimo = d.ent.months.length - 1, corte = d.ent.months.findIndex((x) => x.month === d.corte);
		const idx = s.values.length - 1 - (ultimo - corte);
		return idx >= 0 ? s.values[idx] : null;
	};
	const tam = (d.ent.profile.find((a) => a.key === 'size_band')?.value ?? '').split(' ')[0].toLowerCase();
	const bandaLiq = TAMANO[tam];
	const tablaLiq = bandaLiq && (P.liquidity as { segmented?: boolean }).segmented !== false ? P.liquidity.band_anchors[bandaLiq] : P.anchors.liquidity_absolute ?? P.anchors.liquidity;
	const def: { pilar: string; titulo: string; tabla: Tabla | undefined; x: number | null; unidad: string; x2?: number | null; nota?: string }[] = [
		{ pilar: 'liquidity', titulo: `Liquidez · días de colchón${bandaLiq ? ` (escala de las empresas ${tam === 'pequeña' ? 'pequeñas' : tam === 'mediana' ? 'medianas' : tam === 'grande' ? 'grandes' : 'micro'})` : ''}`, tabla: tablaLiq, x: serie('buffer_days'), unidad: 'días', nota: `El pilar mezcla ${f.porcentaje(P.liquidity.month_end_weight, 0)} del colchón a fin de mes y ${f.porcentaje(P.liquidity.intra_min_weight, 0)} del peor día.` },
		{ pilar: 'payments', titulo: 'Pagos · días sobre el vencimiento', tabla: P.anchors.payments, x: serie('ap_days_beyond_terms'), unidad: 'días' },
		{ pilar: 'collections', titulo: 'Cobros · días sobre el vencimiento', tabla: P.anchors.collections, x: serie('ar_days_beyond_terms'), unidad: 'días' },
		{ pilar: 'activity', titulo: 'Actividad · cobertura de pagos', tabla: P.anchors.activity_coverage, x: serie('activity_coverage'), unidad: 'veces', nota: 'El pilar es la media de la cobertura y el impulso.' },
		{ pilar: 'activity', titulo: 'Actividad · impulso de cobros', tabla: P.anchors.activity_momentum, x: serie('activity_momentum'), unidad: 'veces' },
		{ pilar: 'debt', titulo: 'Deuda · servicio sobre cobros', tabla: P.anchors.debt_burden, x: serie('debt_burden'), unidad: '%' },
	];
	for (const c of def) {
		if (!c.tabla) continue;
		const pil = m.pillars.find((p) => p.key === c.pilar);
		const fig = curva(c.titulo, c.tabla, c.x, c.unidad, pil?.score ?? null, c.nota);
		if (pil && pil.score !== null) tocable(fig, c.pilar, acc);
		caja.append(fig);
	}
	const heredada = d.kind === 'company' && (d.ent as EmpresaM).inherits_liquidity;
	caja.append(h('p', { class: 'nota' }, `Curvas de params/reference_v1.json (huella ${P.sha256.slice(0, 12)}, la misma del bundle). ${heredada ? 'Esta empresa hereda la liquidez del grupo: su pilar de liquidez es el del grupo.' : ''} Topes: liquidez negativa en ${f.numero(P.caps.negative_liquidity_min_months)} de ${f.numero(P.caps.negative_liquidity_window_months)} meses → como mucho ${f.numero(P.caps.negative_liquidity_ceiling)}; pagos por debajo de ${f.numero(P.caps.weak_payments_threshold)} → como mucho ${f.numero(P.caps.weak_payments_ceiling)}.`));
	return caja;
}

function curva(titulo: string, tabla: Tabla, x: number | null, unidad: string, pilar: number | null, nota?: string): HTMLElement {
	const W = 280, H = 128, pad = 24;
	const xs = tabla.map((p) => p[0]);
	let x0 = Math.min(...xs), x1 = Math.max(...xs);
	if (x !== null) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); }
	// Tablas muy asimétricas (colchón de 0 a 600 días): escala raíz para que se lea el tramo útil.
	const raiz = x1 - x0 > 150 && x0 >= 0;
	const tx = (v: number) => (raiz ? Math.sqrt(Math.max(0, v - x0)) / Math.sqrt(x1 - x0) : (v - x0) / (x1 - x0 || 1));
	const X = (v: number) => pad + tx(v) * (W - pad - 8);
	const Y = (s: number) => H - 18 - (s / 100) * (H - 34);
	const s = document.createElementNS(NS, 'svg');
	s.setAttribute('viewBox', `0 0 ${W} ${H}`); s.setAttribute('class', 'curva'); s.setAttribute('role', 'img');
	s.setAttribute('aria-label', `${titulo}: curva de puntuación del motor`);
	s.append(sv('line', { x1: pad, y1: Y(0), x2: W - 8, y2: Y(0), class: 'cv-eje' }), sv('line', { x1: pad, y1: Y(0), x2: pad, y2: Y(100), class: 'cv-eje' }));
	const puntos = [[x0, tabla[0][1]] as [number, number], ...tabla, [x1, tabla[tabla.length - 1][1]] as [number, number]].filter((p, i, a) => i === 0 || p[0] >= a[i - 1][0]);
	s.append(sv('polyline', { points: puntos.map((p) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(' '), class: 'cv-linea' }));
	for (const p of tabla) s.append(sv('circle', { cx: X(p[0]), cy: Y(p[1]), r: 1.8, class: 'cv-ancla' }));
	const et = (tx_: number, ty: number, t: string, cl = 'cv-etq') => { const e = sv('text', { x: tx_, y: ty, class: cl }); e.textContent = t; s.append(e); };
	for (const v of [0, 50, 100]) { et(pad - 4, Y(v) + 3, String(v), 'cv-etq der'); if (v === 50) s.append(sv('line', { x1: pad, y1: Y(v), x2: W - 8, y2: Y(v), class: 'cv-rejilla' })); }
	const medio = raiz ? x0 + (x1 - x0) / 4 : (x0 + x1) / 2;
	for (const [v, cl] of [[x0, 'cv-etq'], [medio, 'cv-etq'], [x1, 'cv-etq fin']] as const) { et(X(v), H - 4, f.numero(v, Math.abs(v) < 10 ? 1 : 0), cl); s.append(sv('line', { x1: X(v), y1: Y(0), x2: X(v), y2: Y(0) + 3, class: 'cv-eje' })); }
	et(pad + 2, Y(100) - 2, 'pilar', 'cv-etq titulo'); et(W - 8, H - 14, unidad, 'cv-etq fin titulo');
	if (x !== null) {
		const sc = interp(tabla, x);
		s.append(sv('line', { x1: X(x), y1: Y(0), x2: X(x), y2: Y(sc), class: 'cv-guia' }), sv('circle', { cx: X(x), cy: Y(sc), r: 4, class: 'cv-aqui' }));
		et(Math.min(W - 60, X(x) + 6), Math.max(12, Y(sc) - 6), `${f.numero(x, unidad === '%' ? 3 : 1)} → ${f.numero(sc, 0)}`, 'cv-etq aqui');
	}
	// Leer la curva: al pasar, una guía cae hasta ella y dice cuánto puntúa ese valor.
	const guia = sv('line', { class: 'cv-guia-lee' }), pto = sv('circle', { r: 3.4, class: 'cv-pto-lee' }), lee = sv('text', { class: 'cv-etq lee' });
	const zona = sv('rect', { x: pad, y: Y(100) - 6, width: W - pad - 8, height: Y(0) - Y(100) + 12, class: 'cv-zona' });
	s.append(guia, pto, lee, zona);
	const inversa = (px: number) => { const u = Math.max(0, Math.min(1, (px - pad) / (W - pad - 8))); return raiz ? x0 + u * u * (x1 - x0) : x0 + u * (x1 - x0); };
	zona.addEventListener('pointermove', (ev) => {
		const r = s.getBoundingClientRect();
		const px = ((ev.clientX - r.left) / r.width) * W;
		// Cerca de un ancla de la tabla, se engancha a ella: son los valores exactos del motor.
		const ancla = tabla.find((p) => Math.abs(X(p[0]) - px) < 5);
		const v = ancla ? ancla[0] : inversa(px);
		const sc = interp(tabla, v);
		for (const [k, val] of Object.entries({ x1: X(v), y1: Y(0), x2: X(v), y2: Y(sc) })) guia.setAttribute(k, String(val));
		pto.setAttribute('cx', String(X(v))); pto.setAttribute('cy', String(Y(sc)));
		const derecha = X(v) > W - 90;
		lee.setAttribute('x', String(X(v) + (derecha ? -7 : 7))); lee.setAttribute('y', String(Math.max(10, Y(sc) - 7)));
		lee.classList.toggle('der', derecha);
		lee.textContent = `${f.numero(v, unidad === '%' ? 3 : Math.abs(v) < 10 ? 1 : 0)} ${unidad} → ${f.numero(sc, 0)}`;
		s.classList.add('leyendo');
	});
	zona.addEventListener('pointerleave', () => s.classList.remove('leyendo'));
	return h('figure', { class: 'fig-curva' }, s, h('figcaption', {}, h('b', {}, titulo), pilar !== null ? ` · pilar ${f.scoreDec(pilar)}` : ' · sin dato este mes', nota ? h('span', { class: 'cv-nota' }, nota) : null));
}

function interp(t: Tabla, x: number) {
	if (x <= t[0][0]) return t[0][1];
	for (let i = 1; i < t.length; i++) if (x <= t[i][0]) { const [a, ya] = t[i - 1], [b, yb] = t[i]; return ya + ((yb - ya) * (x - a)) / (b - a || 1); }
	return t[t.length - 1][1];
}

// ─── Evidencia filtrable ─────────────────────────────────────

function evidencia(d: DatosFicha, filtro: FiltroEvidencia | null): HTMLElement {
	const caja = h('div', { class: 'evidencia' });
	if (!d.evid) { caja.append(h('p', { class: 'nota' }, 'El bundle no trae evidencia de esta entidad.')); return caja; }
	const meses = d.evid.months.map((x) => x.month).filter((x) => x <= d.corte);
	const selMes = desplegable({
		etiqueta: 'Mes', valor: d.corte, alElegir: () => pintar(),
		opciones: [{ valor: '*', texto: 'Todos los meses' }, ...[...meses].reverse().map((x) => ({ valor: x, texto: primeraMayuscula(f.mes(x)) }))],
	});
	const pilares = [...new Set(d.evid.months.flatMap((x) => x.rows.map((r) => r.pillar ?? '·')))];
	const selPil = desplegable({
		etiqueta: 'Pilar', valor: '*', alElegir: () => pintar(),
		opciones: [{ valor: '*', texto: 'Todos los pilares' }, ...pilares.map((p) => ({ valor: p, texto: p === '·' ? 'Toda la entidad' : nombrePilar(d.man, p) }))],
	});
	const ficheros = [...new Set(d.evid.months.flatMap((x) => x.rows.map((r) => r.source_file)))];
	const selFic = desplegable({
		etiqueta: 'Fichero', valor: '*', alElegir: () => pintar(),
		opciones: [{ valor: '*', texto: 'Todos los ficheros' }, ...ficheros.map((x) => ({ valor: x, texto: x }))],
	});
	const buscar = h('input', { class: 'buscar-sutil', type: 'search', placeholder: 'Buscar en la evidencia', 'aria-label': 'Buscar en la evidencia' }) as HTMLInputElement;
	const cuerpo = h('tbody');
	const cuenta = h('p', { class: 'nota' });
	const pintar = () => {
		vaciar(cuerpo);
		const q = buscar.value.trim().toLowerCase();
		const filas: [string, FilaEvidenciaM][] = [];
		for (const mm of d.evid!.months) {
			if (mm.month > d.corte || (selMes.valor !== '*' && mm.month !== selMes.valor)) continue;
			for (const r of mm.rows) {
				if (selPil.valor !== '*' && (r.pillar ?? '·') !== selPil.valor) continue;
				if (selFic.valor !== '*' && r.source_file !== selFic.valor) continue;
				if (q && !`${r.label} ${r.source_file}`.toLowerCase().includes(q)) continue;
				filas.push([mm.month, r]);
			}
		}
		for (const [mes, r] of filas.slice(0, 300)) cuerpo.append(h('tr', {}, h('td', {}, f.mesCorto(mes)), h('td', {}, r.pillar ? nombrePilar(d.man, r.pillar) : 'Entidad'), h('td', {}, r.label), h('td', { class: 'num' }, f.valorUnidad(r.value, r.unit)), h('td', {}, f.periodo(r.period)), h('td', {}, r.source_file), h('td', { class: 'num' }, r.n_rows === null ? 'derivado' : f.numero(r.n_rows))));
		cuenta.textContent = `${f.plural(filas.length, 'fila', 'filas')}${filas.length > 300 ? ' (se enseñan 300)' : ''}. Son agregados, nunca movimientos sueltos.`;
	};
	// Desde un nudo del hilo, la evidencia llega ya filtrada en ese dato.
	if (filtro) {
		if (filtro.pilar !== undefined) selPil.fijar(filtro.pilar ?? '·');
		if (filtro.fichero) selFic.fijar(filtro.fichero);
		if (filtro.texto) buscar.value = filtro.texto;
	}
	buscar.addEventListener('input', pintar);
	caja.append(h('div', { class: 'filtros' }, selMes.raiz, selPil.raiz, selFic.raiz, buscar),
		h('div', { class: 'tabla-caja' }, h('table', { class: 'tabla-sutil' }, h('thead', {}, h('tr', {}, h('th', {}, 'Mes'), h('th', {}, 'Pilar'), h('th', {}, 'Dato'), h('th', { class: 'num' }, 'Valor'), h('th', {}, 'Periodo'), h('th', {}, 'Fichero'), h('th', { class: 'num' }, 'Filas'))), cuerpo)), cuenta);
	pintar();
	return caja;
}

// ─── Horizontes y huella ────────────────────────────────────

function supuestos(d: DatosFicha): HTMLElement {
	const caja = h('div', { class: 'supuestos' });
	const hz = d.hor;
	if (!hz) { caja.append(h('p', { class: 'aviso-datos' }, 'Falta rumbo/horizons/ para esta entidad: el motor la genera con xray-score forecast.')); return caja; }
	if (!hz.scenarios) { caja.append(h('p', {}, `Sin previsión: ${d.man.glossary.reasons[hz.reason_code ?? ''] ?? 'la entidad no tiene score vivo en el corte'}.`)); return caja; }
	caja.append(dl([
		['Modelo', `${hz.model?.version ?? '—'}, entrenado con la historia de la cartera hasta ${f.mes(hz.model?.trained_until ?? hz.cut)}`],
		['Qué predice', 'el cambio del score a 1–12 meses, con su franja (cuantiles 10, 25, 50, 75 y 90); un modelo por horizonte'],
		['Validado hasta', `${f.plural(d.validado, 'mes', 'meses')}, fuera de muestra`],
		['Bundle de origen', `${hz.bundle_id.slice(0, 12)}${hz.bundle_id === d.man.bundle_id ? ' (el mismo que se ve)' : ' · distinto del que se ve: vuelve a generar la previsión'}`],
	]));
	if (hz.explain_h6?.length) caja.append(h('p', {}, h('b', {}, 'Qué empuja su previsión a seis meses'), ' (puntos): ', hz.explain_h6.map((x) => `${x.variable} ${f.delta(Math.round(x.points * 10))}`).join(' · ')));
	const indice = h('div', { class: 'calibracion' }, h('p', { class: 'nota' }, 'Cargando la validación…'));
	caja.append(indice);
	void carga.horizontesIndice().then((ix) => {
		vaciar(indice);
		const r = ix?.validation?.corte_de_referencia;
		if (!ix || !r) return;
		indice.append(dl([
			[`Desde ${f.mes(r.corte)}, a 3 y 6 meses`, `se equivoca ${f.numero(r.error_mediana, 1)} puntos de media, frente a ${f.numero(r.error_sin_cambio, 1)} de suponer que no cambia nada; la franja del 80 % acierta el ${f.porcentaje(r.acierta_80, 0)} (${f.numero(r.n)} casos)`],
			['Comprobaciones', Object.entries(ix.checks ?? {}).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')],
		]));
	});
	return caja;
}

function huella(d: DatosFicha): HTMLElement {
	const caja = h('div', {});
	const filas: [string, string][] = [
		['Bundle del motor', `${d.man.bundle_id.slice(0, 16)} · ${d.man.engine_version} · generado el ${new Date(d.man.generated_at).toLocaleDateString('es-ES')}`],
		['Parámetros', `${d.man.params_hash.slice(0, 16)}${d.params ? (d.params.sha256 === d.man.params_hash ? ' · verificados contra el bundle' : ' · no coinciden') : ''}`],
		['Datos del reto', d.man.dataset_hash.slice(0, 16)],
		['Productos', d.prodE || d.prodG ? `products/ con corte ${f.mes((d.prodE ?? d.prodG)!.cut)}` : 'sin fichero'],
		['Horizontes', d.hor ? `horizons/ desde ${f.mes(d.hor.cut)}, bundle ${d.hor.bundle_id.slice(0, 12)}` : 'sin fichero'],
	];
	caja.append(dl(filas));
	return caja;
}
