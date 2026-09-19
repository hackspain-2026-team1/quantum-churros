// Las escenas: qué figura compone la arena en cada vista, a partir de la consulta (Contexto).
// Cada grupo es dueño de POR_GRUPO granos, siempre los mismos (constancia del objeto). La reserva
// dibuja ejes, los nombres de las zonas, la regla con sus avisos y el reposo.

import { escenaVacia, TONO, type Escena } from './arena';
import { ajustar, anillo, disco, emparejar, linea, punteado, rect, texto, type Puntos } from './formas';
import { CORTE_SCORE, NOMBRE_ZONA, pasa, type Contexto, type Zona } from '../datos/consulta';
import { tendencia } from '../datos/derivados';
import { PILARES, esDeterioro, esMejora, type Empresa, type Grupo, type Pilar } from '../datos/modelo';
import type { Periodo } from '../datos/periodos';
import { encajaAGrupo } from '../datos/encaje';
import { PRODUCTOS } from '../datos/productos';
import { DOMINIO_SCORE, baseRegla, cajasExpediente, tramo, xScore, yRitmo, type Marco } from '../geometria';

export const POR_GRUPO = 200;
export const RESERVA = 14000;
export const nGranos = (nGrupos: number) => nGrupos * POR_GRUPO + RESERVA;
export const SERIF = "'Newsreader Variable', Newsreader, Georgia, serif";

export interface Posicion { id: string; gi: number; x: number; y: number; r: number; visible: boolean }
export interface Fila { id: string; gi: number; y: number; alto: number }

export interface OpcionesEscena {
	sel: string | null;
	hover: string | null;
	zonaHover: Zona | null;
	/** Origen de la onda: los granos cercanos parten antes. */
	origen?: { x: number; y: number } | null;
	/** Deslizar en lugar de disolver (reloj, vista previa, hover). */
	suave?: boolean;
	/** Lente de la cartera: score (hoy), productos (qué tienen y qué les encaja) u horizonte (dónde estarán en seis meses). */
	lente?: 'score' | 'productos' | 'horizonte';
}

const gauss = () => {
	const u = Math.max(Math.random(), 1e-9);
	return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * Math.random());
};

class Lote {
	p: Puntos = [];
	tono: number[] = [];
	alfa: number[] = [];
	talla: number[] = [];
	add(pts: Puntos, tono: number, alfa: number, talla: number) {
		for (let i = 0; i < pts.length; i += 2) {
			this.p.push(pts[i], pts[i + 1]);
			this.tono.push(tono); this.alfa.push(alfa); this.talla.push(talla);
		}
	}
	get n() { return this.p.length / 2; }
}

function volcar(e: Escena, granos: number[], l: Lote, gx: ArrayLike<number>, gy: ArrayLike<number>, m: Marco) {
	if (l.n !== granos.length) {
		const ajust = ajustar(l.p, granos.length);
		const nuevo = new Lote();
		for (let i = 0; i < granos.length; i++) {
			const k = Math.min(l.n - 1, Math.floor((i * l.n) / granos.length));
			nuevo.p.push(ajust[i * 2], ajust[i * 2 + 1]);
			nuevo.tono.push(l.tono[k] ?? TONO.filete); nuevo.alfa.push(l.alfa[k] ?? 0); nuevo.talla.push(l.talla[k] ?? 1.2);
		}
		l = nuevo;
	}
	const asig = emparejar(gx, gy, granos, l.p, m.W, m.H);
	for (let k = 0; k < granos.length; k++) {
		const i = granos[k], j = asig[k];
		e.x[i] = l.p[j * 2]; e.y[i] = l.p[j * 2 + 1];
		e.tono[i] = l.tono[j]; e.alfa[i] = l.alfa[j]; e.talla[i] = l.talla[j];
	}
}

function reposo(n: number, m: Marco): Lote {
	const l = new Lote();
	const pts: Puntos = [];
	for (let i = 0; i < n; i++) pts.push(m.regla.x + Math.random() * m.regla.w, m.H + 30 + Math.abs(gauss()) * 2);
	l.add(pts, TONO.filete, 0.06, 1.1);
	return l;
}

function puntoSedimento(m: Marco, x: number): [number, number] {
	return [x + gauss() * 2.2, m.sedimento.y + m.sedimento.h - Math.abs(gauss()) * 4.5 - Math.random() * 1.5];
}

function esperas(e: Escena, px: ArrayLike<number>, py: ArrayLike<number>, o: OpcionesEscena, maxAleatoria: number) {
	for (let i = 0; i < e.espera.length; i++) {
		if (o.suave) { e.espera[i] = 0; continue; }
		const d = o.origen ? Math.hypot(px[i] - o.origen.x, py[i] - o.origen.y) / 1700 : 0;
		e.espera[i] = d + Math.random() * maxAleatoria;
	}
}

function tonoMes(g: Grupo, k: number) {
	const mm = g.meses[k];
	if (!mm) return TONO.tinta;
	if (mm.nature === 'structural') return mm.direction === 'deteriorating' ? TONO.peligro : TONO.exito;
	if (mm.nature === 'shock_pending') return TONO.aviso;
	return TONO.tinta;
}

const reservaDe = (nGrupos: number) => Array.from({ length: RESERVA }, (_, i) => nGrupos * POR_GRUPO + i);

/** Grupos cuyos avisos se posan en la regla: los que pasan el tamiz sin contar los filtros de movimiento. */
export function gruposDeLaRegla(ctx: Contexto) {
	const sinMov = ctx.q.filtros.filter((f) => f.tipo !== 'mov');
	const r: number[] = [];
	ctx.c.groups.forEach((_, gi) => { if (!ctx.sinDatos.has(gi) && pasa(ctx, gi, sinMov)) r.push(gi); });
	return r;
}

/** Cuántos avisos hay en cada periodo (mejoras y deterioros), hasta el corte. `propios`: los avisos
 * de la entidad abierta (índice de mes y si es mejora), en lugar de los de los grupos. */
export function avisosPorPeriodo(ctx: Contexto, grupos: number[], propios?: { month: number; mejora: boolean }[]) {
	const mejoras = new Array(ctx.periodos.length).fill(0), deterioros = new Array(ctx.periodos.length).fill(0);
	const lista: { gi: number; pi: number; kind: string; month: number }[] = [];
	if (propios) {
		for (const a of propios) {
			if (a.month > ctx.corte) continue;
			const pi = ctx.periodos.findIndex((p) => p.meses.includes(a.month));
			if (pi < 0) continue;
			if (a.mejora) mejoras[pi]++; else deterioros[pi]++;
		}
		return { mejoras, deterioros, lista };
	}
	for (const gi of grupos) {
		for (const a of ctx.c.groups[gi].alerts) {
			if (a.state !== 'fired' || a.month > ctx.corte) continue;
			const pi = ctx.periodos.findIndex((p) => p.meses.includes(a.month));
			if (pi < 0) continue;
			if (esMejora(a.kind)) { mejoras[pi]++; lista.push({ gi, pi, kind: a.kind, month: a.month }); }
			else if (esDeterioro(a.kind)) { deterioros[pi]++; lista.push({ gi, pi, kind: a.kind, month: a.month }); }
		}
	}
	return { mejoras, deterioros, lista };
}

// ─────────────────────────────────────────────── la regla (común a todas las vistas)

/** Línea del tiempo, marcas de periodo y los avisos posados como montones: mejoras arriba, deterioros abajo.
 * En las páginas solo hay un tirador (el corte): toda la línea hasta él va en tinta. */
function reglaArena(l: Lote, ctx: Contexto, m: Marco, grupos: number[], propios?: { month: number; mejora: boolean }[], pagina = false) {
	const base = baseRegla(m);
	const { periodos, pDesde, pHasta, corte } = ctx;
	const xCorte = tramo(m, [corte]).x1;
	const tIni = pagina ? m.tiempo.x : tramo(m, pDesde.meses).x0;
	const xFin = tramo(m, [ctx.c.months.length - 1]).x1;
	l.add(punteado(m.tiempo.x, base, Math.min(tIni, xCorte), base, 3.2), TONO.filete, 0.9, 1.3);
	l.add(punteado(tIni, base, xCorte, base, 2.2), TONO.tinta, 0.6, 1.35);
	if (xCorte < xFin - 2) l.add(punteado(xCorte, base, xFin, base, 3.2), TONO.filete, 0.9, 1.3);
	for (const p of periodos) {
		const t = tramo(m, p.meses);
		l.add(punteado(t.x0, base - 3, t.x0, base + 3, 2), TONO.filete, 0.9, 1.2);
	}
	const { mejoras, deterioros } = avisosPorPeriodo(ctx, grupos, propios);
	const maxN = Math.max(1, ...mejoras, ...deterioros);
	periodos.forEach((p, pi) => {
		const t = tramo(m, p.meses);
		if (t.x0 > xCorte) return;
		const dentro = pagina || (pi >= pDesde.i && pi <= pHasta.i);
		const ancho = Math.min(t.w * 0.42, 22);
		const monton = (n: number, arriba: boolean, tono: number) => {
			if (!n) return;
			const alto = 2 + (arriba ? (m.movil ? 9 : 12) : (m.movil ? 6 : 8)) * Math.sqrt(n / maxN);
			const granos = Math.round(14 + 110 * Math.sqrt(n / maxN));
			const pts: Puntos = [];
			for (let i = 0; i < granos; i++) {
				const hh = Math.pow(Math.random(), 0.8);
				const w = (1 - hh) * ancho;
				pts.push(t.xc + (Math.random() - 0.5) * 2 * w, base + (arriba ? -1 : 1) * (4 + hh * alto));
			}
			l.add(pts, tono, dentro ? 0.95 : 0.45, 1.5);
		};
		monton(mejoras[pi], true, TONO.exito);
		monton(deterioros[pi], false, TONO.peligro);
	});
}

/** La regla sola, para las páginas: sus granos se añaden a la escena de placas (fijos). */
export function reglaPagina(ctx: Contexto, m: Marco, propios: { month: number; mejora: boolean }[] | null) {
	const l = new Lote();
	reglaArena(l, ctx, m, [], propios ?? [], true);
	return l;
}

// ─────────────────────────────────────────────── plano

export function escenaPlano(ctx: Contexto, m: Marco, o: OpcionesEscena, px: Float32Array, py: Float32Array) {
	const c = ctx.c;
	const N = nGranos(c.groups.length);
	const e = escenaVacia(N);
	const posiciones: Posicion[] = [];

	c.groups.forEach((g, gi) => {
		const i0 = gi * POR_GRUPO;
		if (ctx.sinDatos.has(gi)) {
			for (let k = 0; k < POR_GRUPO; k++) { e.x[i0 + k] = m.zona.x + Math.random() * 30; e.y[i0 + k] = m.H - 3; e.alfa[i0 + k] = 0; e.talla[i0 + k] = 1; e.tono[i0 + k] = TONO.filete; }
			posiciones.push({ id: g.id, gi, x: -1e4, y: -1e4, r: 0, visible: false });
			return;
		}
		const hoyV = ctx.valor(gi, ctx.pHasta)! / 10;
		// Lente de horizonte: la mediana a seis meses de los horizontes (si hay y el corte es el suyo).
		const hz = o.lente === 'horizonte' && c.horizontes && c.months[ctx.corte] === c.horizontes.cut ? c.horizontes.entities[g.id] : undefined;
		const v = hz?.p50_h6 != null ? hz.p50_h6 / 10 : hoyV;
		const x = xScore(m, v), y = yRitmo(m, ctx.ritmo(gi) ?? 0);
		const visible = ctx.visibles.has(gi);
		const r = (m.movil ? 2.2 : 2.8) + (m.movil ? 1.05 : 1.35) * Math.sqrt(g.n_companies);
		posiciones.push({ id: g.id, gi, x, y, r, visible });

		if (!visible) {
			for (let k = 0; k < POR_GRUPO; k++) {
				const [sx, sy] = puntoSedimento(m, x);
				e.x[i0 + k] = sx; e.y[i0 + k] = sy; e.tono[i0 + k] = TONO.apagado; e.alfa[i0 + k] = 0.3; e.talla[i0 + k] = 1.25;
			}
			return;
		}

		const destacado = g.id === o.sel || g.id === o.hover;
		const mesCorte = g.meses[ctx.corte];
		// Lente de productos: azul si le encaja alguno según las acciones del motor, tinta si ya tiene y nada más le encaja.
		const encaja = o.lente === 'productos' && PRODUCTOS.some((p) => encajaAGrupo(mesCorte.acciones, g.tenencia, p.id));
		const tiene = o.lente === 'productos' && Object.values(g.tenencia ?? {}).some((n) => (n ?? 0) > 0);
		const tono = destacado ? TONO.info : o.lente === 'productos' ? (encaja ? TONO.info : tiene ? TONO.tinta : TONO.apagado) : tonoMes(g, ctx.corte);
		const nDisco = 124;
		const hueco = mesCorte.nature === 'shock_pending' || mesCorte.abstained;
		const cuerpo = hueco ? anillo(x, y, r + 1, nDisco, 1.3) : disco(x, y, r, nDisco);
		for (let k = 0; k < nDisco; k++) {
			e.x[i0 + k] = cuerpo[k * 2]; e.y[i0 + k] = cuerpo[k * 2 + 1];
			e.tono[i0 + k] = mesCorte.abstained && !destacado ? TONO.apagado : tono;
			e.alfa[i0 + k] = destacado ? 1 : o.lente === 'productos' && !encaja && !tiene ? 0.35 : o.lente === 'horizonte' && !hz?.p50_h6 ? 0.3 : 0.9;
			e.talla[i0 + k] = destacado ? 2.1 : 1.6;
		}

		// El cuerpo de la flecha: de la posición de origen (desde o comparación) a la actual.
		// El grupo señalado enseña su historia entera, mes a mes, en azul.
		const camino: Puntos = [x, y];
		if (destacado) {
			for (let k = ctx.corte - 1; k >= g.first_month; k--) {
				const s = g.meses[k].shown;
				if (s === null) break;
				camino.push(xScore(m, s / 10), yRitmo(m, tendencia(g, k) ?? 0));
			}
		} else if (hz?.p50_h6 != null) {
			camino.push(xScore(m, hoyV), y);
		} else {
			const po = ctx.origen(gi);
			if (po) {
				const vo = ctx.valor(gi, po)! / 10;
				const ro = tendencia(g, po.meses[po.meses.length - 1]) ?? 0;
				camino.push(xScore(m, vo), yRitmo(m, ro));
			}
		}
		const nCola = POR_GRUPO - nDisco;
		const conCola = camino.length >= 4 && Math.hypot(camino[camino.length - 2] - x, camino[camino.length - 1] - y) > r * 1.2;
		const cola = conCola ? linea(camino, nCola, destacado ? 1 : 1.4, (u) => Math.pow(u, destacado ? 1.3 : 1.6)) : disco(x, y, r * 0.6, nCola);
		for (let k = 0; k < nCola; k++) {
			const i = i0 + nDisco + k;
			const u = k / nCola;
			e.x[i] = cola[k * 2]; e.y[i] = cola[k * 2 + 1];
			e.tono[i] = destacado ? TONO.info : tono === TONO.aviso ? TONO.tinta : tono;
			e.alfa[i] = conCola ? (destacado ? 0.85 : 0.5) * (1 - u * 0.8) : 0.6;
			e.talla[i] = destacado ? 1.35 : 1.2;
		}
	});

	// Reserva: ejes, zonas escritas en arena, contorno de la zona señalada, regla y reposo.
	const l = new Lote();
	const z = m.zona;
	const y0 = yRitmo(m, 0), xc = xScore(m, CORTE_SCORE);
	l.add(punteado(z.x, y0, z.x + z.w, y0, 3.4), TONO.filete, 0.95, 1.3);
	l.add(punteado(xc, z.y, xc, z.y + z.h, 3.4), TONO.filete, 0.95, 1.3);
	for (const s of [20, 40, 80, 100]) { const x = xScore(m, s); l.add(punteado(x, z.y + z.h - 5, x, z.y + z.h, 1.6), TONO.filete, 0.9, 1.2); }
	l.add(punteado(z.x, m.sedimento.y + m.sedimento.h + 1, z.x + z.w, m.sedimento.y + m.sedimento.h + 1, 4), TONO.filete, 0.6, 1.1);
	const cuerpoZona = m.movil ? 17 : 26;
	const zonas: [Zona, number, number, 'izq' | 'der'][] = [
		['mejora', z.x + 12, z.y + 8, 'izq'], ['solida', z.x + z.w - 12, z.y + 8, 'der'],
		['hunde', z.x + 12, z.y + z.h - cuerpoZona - 8, 'izq'], ['tuerce', z.x + z.w - 12, z.y + z.h - cuerpoZona - 8, 'der'],
	];
	for (const [zz, x, y, lado] of zonas) {
		const t = texto(NOMBRE_ZONA[zz], cuerpoZona, 500, m.movil ? 1.5 : 1.8, SERIF);
		const pts: Puntos = [];
		const dx = lado === 'izq' ? x : x - t.ancho;
		for (let i = 0; i < t.puntos.length; i += 2) pts.push(dx + t.puntos[i], y + t.puntos[i + 1]);
		const activa = o.zonaHover === zz;
		l.add(pts, activa ? TONO.info : TONO.tinta, activa ? 0.95 : 0.36, activa ? 1.4 : 1.3);
	}
	if (o.zonaHover) {
		const izq = o.zonaHover === 'mejora' || o.zonaHover === 'hunde';
		const arriba = o.zonaHover === 'mejora' || o.zonaHover === 'solida';
		const xa = izq ? z.x : xc, xb = izq ? xc : z.x + z.w;
		const ya = arriba ? z.y : y0, yb = arriba ? y0 : z.y + z.h;
		for (const [ax, ay, bx, by] of [[xa, ya, xb, ya], [xb, ya, xb, yb], [xb, yb, xa, yb], [xa, yb, xa, ya]] as const)
			l.add(punteado(ax, ay, bx, by, 3), TONO.info, 0.8, 1.45);
	}
	reglaArena(l, ctx, m, gruposDeLaRegla(ctx));
	const resto = reposo(RESERVA - l.n, m);
	l.add(resto.p, TONO.filete, 0.06, 1.1);
	volcar(e, reservaDe(c.groups.length), l, px, py, m);

	esperas(e, px, py, o, 0.22);
	e.turbulencia = o.suave ? 0.05 : 0.5;
	e.rigidez = o.suave ? 6.5 : 7.5;
	return { escena: e, posiciones };
}

// ─────────────────────────────────────────────── tapiz

export function ordenarVisibles(ctx: Contexto): number[] {
	const g = ctx.c.groups;
	const vis = [...ctx.visibles];
	const primerAviso = (gi: number) => {
		const a = g[gi].alerts.find((x) => x.state === 'fired' && x.month <= ctx.corte && (esMejora(x.kind) || (esDeterioro(x.kind) && x.kind !== 'level_critical')));
		return a ? a.month : 99;
	};
	const clave = (gi: number) => {
		switch (ctx.q.orden) {
			case 'score': return -(ctx.valor(gi, ctx.pHasta) ?? 0);
			case 'ritmo': return ctx.ritmo(gi) ?? 0;
			case 'alerta': return primerAviso(gi);
			case 'tamano': return -g[gi].n_companies;
		}
	};
	return vis.sort((a, b) => clave(a) - clave(b) || a - b);
}

export function escenaTapiz(ctx: Contexto, m: Marco, o: OpcionesEscena, px: Float32Array, py: Float32Array) {
	const c = ctx.c;
	const N = nGranos(c.groups.length);
	const e = escenaVacia(N);
	const orden = ordenarVisibles(ctx);
	const filas: Fila[] = [];
	const paso = Math.min(12, m.zona.h / Math.max(orden.length, 1));
	const alto = Math.max(0.9, paso * 0.74);
	const periodos = ctx.periodos.filter((p) => p.i <= ctx.pHasta.i);

	orden.forEach((gi, r) => {
		const g = c.groups[gi];
		const y0 = m.zona.y + r * paso;
		filas.push({ id: g.id, gi, y: y0 + paso / 2, alto: paso });
		const i0 = gi * POR_GRUPO;
		const celdas = periodos.map((p) => ({ p, v: ctx.valor(gi, p), mes: Math.min(p.meses[p.meses.length - 1], ctx.corte) })).filter((x) => x.v !== null);
		const destacado = g.id === o.sel || g.id === o.hover;
		// Reparto de los granos entre las celdas, proporcional a los meses de cada periodo.
		const cortes: number[] = [];
		let acum = 0;
		const total = celdas.reduce((s, x) => s + x.p.meses.length, 0) || 1;
		for (const x of celdas) { acum += x.p.meses.length / total; cortes.push(acum); }
		let ci = 0;
		for (let q = 0; q < POR_GRUPO; q++) {
			const i = i0 + q;
			if (!celdas.length) { e.x[i] = m.tiempo.x; e.y[i] = m.H - 3; e.alfa[i] = 0; e.talla[i] = 1; continue; }
			const u = (q + 0.5) / POR_GRUPO;
			while (ci < celdas.length - 1 && u > cortes[ci]) ci++;
			const celda = celdas[ci];
			const t = tramo(m, celda.p.meses);
			const dentro = celda.p.i >= ctx.pDesde.i && celda.p.i <= ctx.pHasta.i;
			const nivel = Math.max(0, Math.min(1, (celda.v! / 10 - DOMINIO_SCORE[0] - 10) / (90 - DOMINIO_SCORE[0])));
			const tm = tonoMes(g, celda.mes);
			e.x[i] = t.x0 + t.w * (0.03 + 0.94 * Math.random());
			e.y[i] = y0 + (paso - alto) / 2 + Math.random() * alto;
			e.tono[i] = destacado ? TONO.info : tm === TONO.aviso ? TONO.tinta : tm;
			e.alfa[i] = destacado ? 1 : (0.14 + 0.86 * Math.pow(nivel, 1.15)) * (dentro ? 1 : 0.55);
			e.talla[i] = destacado ? 1.9 : Math.max(1.4, Math.min(2.8, alto * 0.34 + 0.4 + nivel * 0.8));
		}
	});

	c.groups.forEach((_, gi) => {
		if (ctx.visibles.has(gi)) return;
		const i0 = gi * POR_GRUPO;
		const v = ctx.valor(gi, ctx.pHasta);
		for (let k = 0; k < POR_GRUPO; k++) {
			if (v === null) { e.x[i0 + k] = m.tiempo.x; e.y[i0 + k] = m.H - 3; e.alfa[i0 + k] = 0; e.talla[i0 + k] = 1; continue; }
			const [sx, sy] = puntoSedimento(m, xScore(m, v / 10));
			e.x[i0 + k] = sx; e.y[i0 + k] = sy; e.tono[i0 + k] = TONO.apagado; e.alfa[i0 + k] = 0.28; e.talla[i0 + k] = 1.2;
		}
	});

	const l = new Lote();
	const t0 = tramo(m, ctx.pDesde.meses), t1 = tramo(m, ctx.pHasta.meses);
	const fondo = m.zona.y + Math.max(40, orden.length * paso) + 4;
	l.add(punteado(t0.x0, m.zona.y - 6, t0.x0, fondo, 3), TONO.info, 0.45, 1.3);
	l.add(punteado(t1.x1, m.zona.y - 6, t1.x1, fondo, 3), TONO.info, 0.45, 1.3);
	reglaArena(l, ctx, m, gruposDeLaRegla(ctx));
	const resto = reposo(RESERVA - l.n, m);
	l.add(resto.p, TONO.filete, 0.06, 1.1);
	volcar(e, reservaDe(c.groups.length), l, px, py, m);

	esperas(e, px, py, o, 0.16);
	if (!o.suave && !o.origen) for (let i = 0; i < N; i++) e.espera[i] = ((e.y[i] - m.zona.y) / m.zona.h) * 0.28 + Math.random() * 0.1;
	e.turbulencia = o.suave ? 0.04 : 0.45;
	e.rigidez = o.suave ? 6.5 : 7;
	return { escena: e, filas, paso };
}

// ─────────────────────────────────────────────── expediente

export interface PuntoSerie { p: Periodo; v: number | null; disp: number; mes: number }

/** Serie de un grupo o de una empresa por periodos (al cierre o de media), hasta el periodo «hasta». */
export function seriePeriodos(shown: (number | null)[], periodos: Periodo[], hasta: number, agregado: 'cierre' | 'media'): PuntoSerie[] {
	return periodos.filter((p) => p.i <= hasta).map((p) => {
		const vals = p.meses.map((k) => shown[k]).filter((v): v is number => v !== null && v !== undefined);
		if (!vals.length) return { p, v: null, disp: 0, mes: p.meses[p.meses.length - 1] };
		const media = vals.reduce((a, b) => a + b, 0) / vals.length;
		const disp = vals.length > 1 ? Math.sqrt(vals.reduce((s, x) => s + (x - media) ** 2, 0) / (vals.length - 1)) / 10 : 0;
		let ult = p.meses[0];
		for (const k of p.meses) if (shown[k] !== null && shown[k] !== undefined) ult = k;
		return { p, v: agregado === 'cierre' ? shown[ult]! : Math.round(media), disp, mes: ult };
	});
}

/** Aportación de un pilar en un periodo: la del mes de cierre o la media del periodo. */
export function aportacionPeriodo(g: Grupo, p: Periodo, pilar: number, agregado: 'cierre' | 'media', mesCierre: number) {
	if (agregado === 'cierre') return g.meses[mesCierre]?.pillars[pilar] ?? null;
	const ps = p.meses.map((k) => g.meses[k]?.pillars[pilar]).filter((x) => x && x.score !== null);
	if (!ps.length) return null;
	return { key: PILARES[pilar] as Pilar, score: 0, contrib: Math.round(ps.reduce((s, x) => s + x!.contrib, 0) / ps.length) };
}

export function dominioTrayectoria(serie: { v: number | null }[]): [number, number] {
	const vs = serie.map((x) => x.v).filter((v): v is number => v !== null).map((v) => v / 10);
	if (!vs.length) return [DOMINIO_SCORE[0], DOMINIO_SCORE[1]];
	const lo = Math.min(...vs), hi = Math.max(...vs);
	const medio = (lo + hi) / 2, mitad = Math.max(12, (hi - lo) / 2 + 5);
	return [Math.max(0, medio - mitad), Math.min(100, medio + mitad)];
}

export function escenaExpediente(ctx: Contexto, gi: number, m: Marco, o: OpcionesEscena, px: Float32Array, py: Float32Array) {
	const c = ctx.c;
	const N = nGranos(c.groups.length);
	const e = escenaVacia(N);
	const g = c.groups[gi];
	const cj = cajasExpediente(m);
	const l = new Lote();
	const agregado = ctx.q.agregado;
	const serie = seriePeriodos(g.meses.map((x) => x.shown), ctx.periodos, ctx.pHasta.i, agregado);
	const actual = serie[serie.length - 1];

	// El número, acuñado en arena.
	const cadena = !actual || actual.v === null ? '—' : String(Math.round(actual.v / 10));
	const num = texto(cadena, cj.numeral.h, 600, m.movil ? 1.35 : 1.55, SERIF);
	const numPts: Puntos = [];
	for (let i = 0; i < num.puntos.length; i += 2) numPts.push(cj.numeral.x - 4 + num.puntos[i], cj.numeral.y + num.puntos[i + 1]);
	l.add(numPts.length / 2 > 13000 ? ajustar(numPts, 13000) : numPts, TONO.tinta, 1, m.movil ? 1.5 : 1.9);

	// La trayectoria por periodos; el grosor es la agitación dentro de cada periodo.
	const T = cj.tray;
	const [lo, hi] = dominioTrayectoria(serie);
	const yS = (v: number) => T.y + T.h - Math.max(0, Math.min(1, (v / 10 - lo) / (hi - lo))) * T.h;
	for (const s of [40, 60, 80]) if (s > lo && s < hi) l.add(punteado(T.x, yS(s * 10), T.x + T.w, yS(s * 10), 5), TONO.filete, 0.85, 1.2);
	const puntos = serie.filter((x) => x.v !== null).map((x) => ({ x: tramo(m, x.p.meses).xc, y: yS(x.v!), disp: x.disp, s: x }));
	for (let i = 1; i < puntos.length; i++) {
		const a = puntos[i - 1], b = puntos[i];
		const n = Math.round(Math.hypot(b.x - a.x, b.y - a.y) * 1.6);
		l.add(linea([a.x, a.y, b.x, b.y], n, 1 + Math.min(6, (a.disp + b.disp) * 1.2)), TONO.tinta, 0.88, 1.5);
	}
	const origenP = ctx.origen(gi);
	for (const pt of puntos) {
		const mm = g.meses[pt.s.mes];
		const tono = tonoMes(g, pt.s.mes);
		const esHoy = pt.s.p.i === ctx.pHasta.i;
		l.add(mm?.nature === 'shock_pending' ? anillo(pt.x, pt.y, 3.8, 22, 0.8) : disco(pt.x, pt.y, esHoy ? 4.6 : 2.8, esHoy ? 36 : 16), tono, 1, 1.65);
		if (origenP && pt.s.p.i === origenP.i) l.add(anillo(pt.x, pt.y, 8, 44, 0.9), TONO.info, 0.9, 1.5);
	}
	const tA = tramo(m, ctx.pDesde.meses), tB = tramo(m, ctx.pHasta.meses);
	if (ctx.pDesde.i !== ctx.pHasta.i) {
		l.add(punteado(tA.x0, T.y - 6, tA.x0, cj.empresas.y + cj.empresas.h, 4), TONO.info, 0.35, 1.2);
		l.add(punteado(tB.x1, T.y - 6, tB.x1, cj.empresas.y + cj.empresas.h, 4), TONO.info, 0.35, 1.2);
	}

	// La partitura: qué aporta cada pilar en cada periodo, con el mismo eje de tiempo.
	let maxAbs = 30;
	const aportaciones = PILARES.map((_, r) => serie.map((x) => (x.v === null ? null : aportacionPeriodo(g, x.p, r, agregado, x.mes))));
	for (const fila of aportaciones) for (const a of fila) if (a && a.score !== null) maxAbs = Math.max(maxAbs, Math.abs(a.contrib));
	for (let r = 0; r < 5; r++) {
		const base = cj.part.y + r * cj.fila + cj.fila / 2;
		const medible = g.meses[ctx.corte].pillars[r].score !== null;
		l.add(punteado(m.tiempo.x, base, m.tiempo.x + m.tiempo.w, base, medible ? 6 : 3), TONO.filete, medible ? 0.8 : 0.45, 1.2);
		if (!medible) continue;
		serie.forEach((x, k) => {
			const a = aportaciones[r][k];
			if (!a || a.score === null) return;
			const t = tramo(m, x.p.meses);
			const cw = Math.max(3, Math.min(t.w * 0.55, 30));
			const h = (Math.abs(a.contrib) / maxAbs) * (cj.fila / 2 - 3);
			const n = Math.round(4 + h * cw * 1.25);
			l.add(rect(t.xc - cw / 2, a.contrib >= 0 ? base - h : base, cw, Math.max(0.8, h), n), a.contrib >= 0 ? TONO.tinta : TONO.peligro, x.p.i === ctx.pHasta.i ? 1 : 0.8, 1.4);
		});
	}

	// Las empresas del grupo, como crestas pequeñas por periodo.
	const E = cj.empresas;
	const emp: Empresa[] = g.companies.slice(0, m.movil ? 6 : 12);
	const pasoE = E.h / Math.max(emp.length, 1);
	emp.forEach((em, r) => {
		const base = E.y + (r + 1) * pasoE;
		const s = seriePeriodos(em.shown, ctx.periodos, ctx.pHasta.i, agregado).filter((x) => x.v !== null);
		const pts: Puntos = [];
		for (const x of s) pts.push(tramo(m, x.p.meses).xc, base - Math.max(0, (x.v! / 10 - 15) / 85) * Math.min(20, pasoE * 3));
		if (pts.length >= 4) l.add(linea(pts, 260, 0.8), TONO.tinta, 0.7, 1.2);
	});

	reglaArena(l, ctx, m, [gi]);
	const todos = Array.from({ length: N }, (_, i) => i);
	if (l.n < N) { const resto = reposo(N - l.n, m); l.add(resto.p, TONO.filete, 0.06, 1.1); }
	volcar(e, todos, l, px, py, m);

	esperas(e, px, py, o, 0.07);
	e.turbulencia = o.suave ? 0.04 : 0.6;
	e.rigidez = o.suave ? 6.5 : 7.2;
	return { escena: e, cajas: cj, dominio: [lo, hi] as [number, number], serie, aportaciones, maxAbs };
}
