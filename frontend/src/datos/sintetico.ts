// Cartera SINTÉTICA para desarrollar la interfaz mientras el motor v2 no exporta (build_panel y
// export_bundle siguen sin implementar en feat/engine-v2). Reproduce las reglas documentadas en
// docs/engine/ENGINE.md para que la interfaz se comporte igual que con los datos reales:
//   · 250 grupos, 1.286 empresas, ventana 2024-09 … 2026-08 (24 meses).
//   · Cinco pilares con pesos 0,30/0,20/0,15/0,20/0,15; un pilar no medible reparte su peso.
//   · shown = base + Σcontrib − penalty − cap, en décimas enteras (cuadra exacto).
//   · Penalización 0,5 × (45 − pilar mínimo), tope 22,5; tope de liquidez negativa en 40.
//   · Dirección: Δ3 = score(t) − score(t−3) frente a max(6, 1,5σ propia); mínimo 6 meses.
//   · Naturaleza: primer mes «shock_pending», si aguanta «structural», si revierte «bump».
//   · Abstención con menos de 4 meses; alertas solo en el primer mes de cada racha.
// Nada de esto se despliega como dato real: la fuente lo marca como `origen: 'sintetico'`.

import {
	PILARES,
	bandaDe,
	type Alerta,
	type Cartera,
	type Confianza,
	type Direccion,
	type Empresa,
	type Grupo,
	type MesEntidad,
	type Naturaleza,
	type Pilar,
	type PilarMes,
} from './modelo';

const N_MESES = 24;
const PREVIO = 6;
const PESOS: Record<Pilar, number> = { liquidity: 0.3, payments: 0.2, collections: 0.15, activity: 0.2, debt: 0.15 };
const RETRASO: Record<Pilar, number> = { payments: 0, collections: 1, debt: 2, liquidity: 3, activity: 3 };
const BASE = 600;
const REFERENCIA = 55; // mediana de referencia de cada pilar, en puntos

function crearRng(semilla: number) {
	let a = semilla >>> 0;
	const r = () => {
		a = (a + 0x6d2b79f5) >>> 0;
		let t = a;
		t = Math.imul(t ^ (t >>> 15), t | 1);
		t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
		return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
	};
	return {
		u: r,
		entre: (lo: number, hi: number) => lo + (hi - lo) * r(),
		entero: (lo: number, hi: number) => Math.floor(lo + (hi - lo + 1) * r()),
		normal: () => {
			const u = Math.max(r(), 1e-9);
			return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r());
		},
		elegir: <T>(xs: T[]) => xs[Math.floor(r() * xs.length)],
		ponderado: <T>(pares: [T, number][]) => {
			let x = r() * pares.reduce((s, p) => s + p[1], 0);
			for (const [v, p] of pares) if ((x -= p) <= 0) return v;
			return pares[pares.length - 1][0];
		},
	};
}
type Rng = ReturnType<typeof crearRng>;

const lim = (x: number, a: number, b: number) => Math.max(a, Math.min(b, x));

type Arquetipo = 'solida' | 'media' | 'mejora' | 'deterioro' | 'bache' | 'caida' | 'volatil' | 'recupera' | 'deriva_baja' | 'deriva_alta';

/** Salud latente en puntos, de t = −PREVIO a t = 23. */
function latente(rng: Rng, arq: Arquetipo): number[] {
	const n = N_MESES + PREVIO;
	const f = (k: number) => k - PREVIO;
	const H: number[] = [];
	let ruido = 1.4;
	let base = 60;
	for (let k = 0; k < n; k++) H.push(0);
	switch (arq) {
		case 'solida': {
			base = rng.entre(72, 90);
			const d = rng.entre(-0.08, 0.15);
			for (let k = 0; k < n; k++) H[k] = base + d * f(k);
			break;
		}
		case 'media': {
			base = rng.entre(45, 68);
			const d = rng.entre(-0.12, 0.12);
			for (let k = 0; k < n; k++) H[k] = base + d * f(k);
			break;
		}
		case 'mejora': {
			base = rng.entre(30, 52);
			const ini = rng.entre(-2, 12), v = rng.entre(1.2, 2.4), tope = rng.entre(16, 30);
			for (let k = 0; k < n; k++) H[k] = base + lim((f(k) - ini) * v, 0, tope);
			break;
		}
		case 'deterioro': {
			base = rng.entre(62, 86);
			const ini = rng.entre(3, 16), v = rng.entre(1.4, 2.8), tope = rng.entre(16, 34);
			for (let k = 0; k < n; k++) H[k] = base - lim((f(k) - ini) * v, 0, tope);
			break;
		}
		case 'bache': {
			base = rng.entre(55, 84);
			const m = rng.entero(6, 20), prof = rng.entre(12, 20);
			for (let k = 0; k < n; k++) {
				const t = f(k);
				H[k] = base - (t === m ? prof : t === m + 1 ? prof * 0.35 : 0);
			}
			break;
		}
		case 'caida': {
			base = rng.entre(56, 80);
			const ini = rng.entre(9, 19), v = rng.entre(4, 6), tope = rng.entre(26, 40);
			for (let k = 0; k < n; k++) H[k] = base - lim((f(k) - ini) * v, 0, tope);
			break;
		}
		case 'volatil': {
			base = rng.entre(40, 66);
			ruido = 4;
			for (let k = 0; k < n; k++) H[k] = base;
			break;
		}
		case 'recupera': {
			base = rng.entre(55, 76);
			const ini = rng.entre(0, 6), prof = rng.entre(16, 24);
			for (let k = 0; k < n; k++) {
				const t = f(k) - ini;
				H[k] = base - (t <= 0 ? 0 : t <= 5 ? prof * (t / 5) : prof * Math.max(0, 1 - (t - 5) / 10));
			}
			break;
		}
		// Las derivas lentas del propio reto (82 → 68 y 45 → 65): nunca superan 6 puntos en 3 meses.
		case 'deriva_baja': {
			for (let k = 0; k < n; k++) H[k] = 84 - 0.85 * Math.max(0, f(k) - 3);
			ruido = 0.55;
			break;
		}
		case 'deriva_alta': {
			for (let k = 0; k < n; k++) H[k] = 43 + 0.82 * Math.max(0, f(k) + 1);
			ruido = 0.55;
			break;
		}
	}
	let e = 0;
	for (let k = 0; k < n; k++) {
		e = 0.5 * e + ruido * rng.normal();
		H[k] = lim(H[k] + e, 4, 97);
	}
	return H;
}

/** Descompone un mes en pilares y cuadra shown = base + Σcontrib − penalty − cap. */
function componerMes(
	H: number[],
	t: number,
	disponibles: Set<Pilar>,
	sesgo: Record<Pilar, number>,
	rng: Rng,
): Pick<MesEntidad, 'shown' | 'base' | 'pillars' | 'penalty' | 'cap'> {
	const pesoTotal = PILARES.filter((p) => disponibles.has(p)).reduce((s, p) => s + PESOS[p], 0);
	const pillars: PilarMes[] = [];
	let minimo = 100;
	let suma = 0;
	for (const key of PILARES) {
		if (!disponibles.has(key)) {
			pillars.push({ key, score: null, contrib: 0 });
			continue;
		}
		const puntos = lim(H[t + PREVIO - RETRASO[key]] + sesgo[key] + 2.2 * rng.normal(), 2, 99);
		const contrib = Math.round((PESOS[key] / pesoTotal) * (puntos - REFERENCIA) * 10);
		pillars.push({ key, score: Math.round(puntos * 10), contrib });
		minimo = Math.min(minimo, puntos);
		suma += contrib;
	}
	const penalty = minimo < 45 ? Math.min(225, Math.round(5 * (45 - minimo))) : 0;
	let bruto = BASE + suma - penalty;
	const liq = pillars[0].score;
	let cap = liq !== null && liq < 200 && bruto > 400 ? bruto - 400 : 0;
	bruto -= cap;
	// Mantener el rango 0–1000 absorbiendo el exceso en el tope.
	if (bruto > 1000) { cap += bruto - 1000; bruto = 1000; }
	if (bruto < 0) bruto = 0;
	return { shown: bruto, base: BASE, pillars, penalty, cap };
}

function desviacion(xs: number[]) {
	if (xs.length < 2) return 0;
	const m = xs.reduce((a, b) => a + b, 0) / xs.length;
	return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / (xs.length - 1));
}

const INDUSTRIAS = ['Hostelería', 'Distribución', 'Industria', 'Construcción', 'Tecnología', 'Transporte y logística', 'Salud', 'Servicios profesionales', 'Energía', 'Alimentación'];
const PAISES: [string | null, number][] = [['ES', 0.62], ['PT', 0.05], ['FR', 0.06], ['DE', 0.04], ['IT', 0.04], ['GB', 0.05], [null, 0.14]];
const ARQUETIPOS: [Arquetipo, number][] = [
	['solida', 0.26], ['media', 0.24], ['mejora', 0.11], ['deterioro', 0.11], ['bache', 0.1],
	['caida', 0.04], ['volatil', 0.08], ['recupera', 0.06],
];

export function carteraSintetica(semilla = 20260919): Cartera {
	const rng = crearRng(semilla);
	const months = Array.from({ length: N_MESES }, (_, i) => {
		const d = new Date(2024, 8 + i, 1);
		return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
	});

	// Tamaños de grupo: mediana 2, máximo 24, suma 1.286.
	const N = 250;
	const tam = Array.from({ length: N }, () => lim(Math.round(Math.exp(0.7 + 1.05 * rng.normal())), 1, 24));
	let total = tam.reduce((a, b) => a + b, 0);
	while (total < 1286) { const i = rng.entero(0, N - 1); if (tam[i] > 1 && tam[i] < 24) { tam[i]++; total++; } }
	while (total > 1286) { const i = rng.entero(0, N - 1); if (tam[i] > 1) { tam[i]--; total--; } }

	// Alta en la plataforma: 95 grupos desde el principio, unos 80 con 10 meses o menos.
	const inicios = Array.from({ length: N }, (_, i) => (i < 95 ? 0 : i < 170 ? rng.entero(1, 13) : rng.entero(14, 21)));
	for (let i = N - 1; i > 0; i--) { const j = rng.entero(0, i); [inicios[i], inicios[j]] = [inicios[j], inicios[i]]; }

	const groups: Grupo[] = [];
	let idEmpresa = 1;
	for (let g = 0; g < N; g++) {
		const id = `GROUP_${String(g + 1).padStart(4, '0')}`;
		let arq = rng.ponderado(ARQUETIPOS);
		if (g === 41) arq = 'deriva_baja';
		if (g === 112) arq = 'deriva_alta';
		const first = g === 41 || g === 112 ? 0 : inicios[g];
		const H = latente(rng, arq);

		const disponibles = new Set<Pilar>(['liquidity', 'activity', 'debt']);
		if (rng.u() < 0.5) disponibles.add('payments');
		if (rng.u() < 0.4) disponibles.add('collections');
		if (g === 41 || g === 112) { disponibles.add('payments'); disponibles.add('collections'); }
		const sesgo = Object.fromEntries(PILARES.map((p) => [p, 7 * rng.normal()])) as Record<Pilar, number>;

		const meses: MesEntidad[] = [];
		const cambioPerimetro = tam[g] > 2 && rng.u() < 0.3 ? rng.entero(first + 4, 23) : -1;
		for (let t = 0; t < N_MESES; t++) {
			if (t < first) {
				meses.push({
					shown: null, band: null, direction: null, nature: null, conf: null, abstained: null,
					perimeter_changed: null, base: BASE, pillars: PILARES.map((key) => ({ key, score: null, contrib: 0 })), penalty: 0, cap: 0,
				});
				continue;
			}
			const m = componerMes(H, t, disponibles, sesgo, rng);
			const observados = t - first + 1;
			const conf: Confianza = observados < 6 ? 'low' : observados < 12 || disponibles.size < 4 ? 'medium' : 'high';
			meses.push({
				...m,
				band: bandaDe(m.shown!),
				direction: null,
				nature: null,
				conf,
				abstained: observados < 4,
				perimeter_changed: t === cambioPerimetro,
			});
		}

		// Dirección y naturaleza, causales: cada mes solo mira hacia atrás.
		const d3: number[] = [];
		for (let t = first; t < N_MESES; t++) {
			const mes = meses[t];
			if (t - first + 1 < 6 || t - 3 < first) continue;
			const delta = mes.shown! - meses[t - 3].shown!;
			const umbral = Math.max(60, 1.5 * desviacion(d3));
			d3.push(delta);
			let dir: Direccion = delta >= umbral ? 'improving' : delta <= -umbral ? 'deteriorating' : 'stable';
			if (mes.perimeter_changed) dir = 'perimeter_shift';
			mes.direction = dir;
			const prev = meses[t - 1];
			let nat: Naturaleza | null = null;
			if (dir === 'improving' || dir === 'deteriorating') nat = prev.direction === dir ? 'structural' : 'shock_pending';
			else if (prev.nature === 'shock_pending') nat = 'bump';
			mes.nature = nat;
		}

		// Alertas: el primer mes de cada racha.
		const alerts: Alerta[] = [];
		for (let t = first + 1; t < N_MESES; t++) {
			const a = meses[t], b = meses[t - 1];
			const estado = a.abstained ? 'abstained' : a.perimeter_changed ? 'suppressed' : 'fired';
			const alta = (kind: Alerta['kind']) =>
				alerts.push({ id: `${id}:${months[t]}:${kind}`, entity_id: id, group_id: id, month: t, kind, state: estado, shown: a.shown! });
			if (a.nature === 'structural' && b.nature !== 'structural') alta(a.direction === 'improving' ? 'improvement_structural' : 'deterioration_structural');
			if (a.shown! < 350 && (b.shown ?? 1000) >= 350) alta('level_critical');
			if (a.cap > 0 && b.cap === 0) alta('cap_fired');
		}

		// Empresas del grupo: la matriz sigue al grupo; las filiales, con su propio carácter.
		const companies: Empresa[] = [];
		for (let c = 0; c < tam[g]; c++) {
			const cid = `COMP_${String(idEmpresa++).padStart(4, '0')}`;
			const alta = c === 0 ? first : lim(first + (rng.u() < 0.3 ? rng.entero(0, 10) : 0), first, 22);
			const desvio = c === 0 ? 0 : 60 * rng.normal();
			let e = 0;
			const shown = meses.map((m, t) => {
				if (m.shown === null || t < alta) return null;
				e = 0.6 * e + 18 * rng.normal();
				return Math.round(lim(m.shown + desvio + e, 0, 1000));
			});
			companies.push({ id: cid, first_month: alta, shown, band: shown.map((s) => (s === null ? null : bandaDe(s))) });
		}

		// Huella sintética por pilar: ficheros reales del dataset y un número de filas plausible.
		const escalaFilas = tam[g] * (N_MESES - first);
		const huella = {
			liquidity: { fichero: 'transactions.csv', filas: Math.round(escalaFilas * rng.entre(40, 90)), detalle: `movimientos de ${rng.entero(2, 6)} cuentas` },
			payments: { fichero: 'invoices.csv', filas: Math.round(escalaFilas * rng.entre(6, 18)), detalle: 'facturas recibidas' },
			collections: { fichero: 'invoices.csv', filas: Math.round(escalaFilas * rng.entre(5, 16)), detalle: 'facturas emitidas' },
			activity: { fichero: 'transactions.csv', filas: Math.round(escalaFilas * rng.entre(12, 35)), detalle: 'cobros de clientes' },
			debt: { fichero: 'debt_products.csv', filas: rng.entero(1, 3 + tam[g]), detalle: 'productos de deuda' },
		};
		const pais = rng.ponderado(PAISES);
		groups.push({
			id,
			n_companies: tam[g],
			first_month: first,
			country: pais,
			size_band: tam[g] >= 8 ? 'Grande' : tam[g] >= 3 ? 'Mediana' : 'Pequeña',
			industry: rng.u() < 0.9 ? rng.elegir(INDUSTRIAS) : null,
			meses,
			companies,
			alerts,
			huella,
		});
	}

	return {
		origen: 'sintetico',
		months,
		pillars: PILARES.map((key) => ({
			key,
			label: { liquidity: 'Liquidez', payments: 'Pagos', collections: 'Cobros', activity: 'Actividad', debt: 'Deuda' }[key],
			weight: PESOS[key],
		})),
		groups,
	};
}
