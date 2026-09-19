// rumbo-vista: traduce una petición en lenguaje natural («las que se hunden en hostelería») a las
// piezas de una vista del monitor de Rumbo, con Jev (TypeSafe). Jev elige entre vocabularios
// cerrados y devuelve probabilidades; la interfaz decide con ellas qué aplica y qué pregunta.
//
// La clave de TypeSafe vive aquí como secreto (TYPESAFE_API_KEY) y nunca llega al navegador. Las
// preguntas también viven aquí: el Worker no reenvía peticiones arbitrarias, solo esta.
// A TypeSafe viaja la frase escrita y los nombres del vocabulario; ningún dato financiero.

interface Env {
	TYPESAFE_API_KEY: string;
	LIMITE?: { limit(o: { key: string }): Promise<{ success: boolean }> };
}

interface Peticion { texto: string; sectores?: string[]; paises?: Record<string, string> }

const MODELO = 'jev-latest';
const MAX_TEXTO = 280;

function preguntas(p: Peticion) {
	const opciones = (lista: string[], ninguno: string) => Object.fromEntries([...lista.map((x) => [x, null] as [string, null]), [ninguno, 'The request does not mention any of these.']]);
	const paises = Object.fromEntries([...Object.entries(p.paises ?? {}).map(([cod, nombre]) => [cod, nombre] as [string, string]), ['ninguno', 'The request does not mention a country.']]);
	return {
		relevante: {
			type: 'noul',
			instructions: 'Is the text a request to see, filter, sort or arrange a portfolio of organizations or companies in a financial-health monitor (scores, health bands, alerts, forecasts, products)?',
			criteria: { true: 'It asks for a view of the portfolio, or part of it.', false: 'It is unrelated small talk or a question about something else.' },
		},
		forma: {
			type: 'choice',
			instructions: 'Which layout does the request ask for? Answer "no_dice" when it only filters or sorts without implying a layout.',
			criteria: {
				ranking: 'A ranked list or leaderboard: the worst, the top N, a list in some order.',
				bandas: 'Grouped by health band (critical, watch, stable, solid): how many in each band, piles per band.',
				plano: 'A scatter or map of level against momentum; quadrants such as improving, sinking or healthy but falling.',
				tapiz: 'Month-by-month history for each entity; evolution over time; a heatmap.',
				flujo: 'What changed since last month: moves between bands, transitions, who went up or down a band.',
				avisos: 'Alerts, warnings or notifications, by month or by type.',
				horizonte: 'The future: forecast, projection, where they will be in six months.',
				no_dice: 'No particular layout is implied.',
			},
		},
		modo: {
			type: 'choice',
			instructions: 'Does the request ask for a visual chart or for a plain table?',
			criteria: { arena: 'A visual, chart, graphic or drawing.', tabla: 'A table, a plain list, numbers, something fixed or printable.', no_dice: 'It does not say.' },
		},
		unidad: {
			type: 'choice',
			instructions: 'Is the request about organizations (business groups) or about individual companies?',
			criteria: { organizaciones: 'Organizations, groups, holdings, clients as groups.', empresas: 'Individual companies, subsidiaries, firms (empresas, filiales).', no_dice: 'It does not say.' },
		},
		orden: {
			type: 'choice',
			instructions: 'In which order should the entities be sorted?',
			criteria: {
				gravedad: 'Most urgent or severe first; priority; what needs attention.',
				score: 'By score, lowest first.',
				cambio: 'By the change this month: biggest drops first.',
				cambio3: 'By the change over the last three months or the quarter.',
				horizonte: 'By the risk of being critical in six months.',
				avisos: 'By number of alerts.',
				tamano: 'By size, biggest first.',
				no_dice: 'No order is requested.',
			},
		},
		banda: {
			type: 'choice',
			instructions: 'Does the request restrict to one health band?',
			criteria: { critical: 'Critical (crítico, críticas, en rojo).', watch: 'Watch (vigilancia, en observación).', stable: 'Stable (estable).', solid: 'Solid (sólido, sanas, las mejores).', ninguna: 'No band restriction.' },
		},
		movimiento: {
			type: 'choice',
			instructions: 'Does the request restrict to entities with a particular movement or event this month?',
			criteria: {
				entra_critico: 'They just entered the critical band this month.',
				baja_banda: 'They moved down a band this month.',
				sube_banda: 'They moved up a band this month.',
				cae: 'Their score dropped three points or more this month; they are falling or getting worse.',
				crece: 'Their score rose three points or more this month; they are improving.',
				deterioro: 'The engine confirmed a structural deterioration.',
				mejora: 'The engine confirmed a structural improvement.',
				hacia_critico: 'The forecast says they are heading to critical.',
				por_confirmar: 'A sudden shock that is not yet confirmed.',
				avisos: 'They have any alert this month.',
				sin_datos: 'Their bank data is stale or not updated.',
				ninguno: 'No movement restriction.',
			},
		},
		zona: {
			type: 'choice',
			instructions: 'Does the request restrict to one zone of the level-versus-momentum map?',
			criteria: { solida: 'High level and stable or rising (sólidas).', mejora: 'Low level but rising (que mejoran).', tuerce: 'Look healthy but are falling (que se tuercen).', hunde: 'Low level and falling (que se hunden).', ninguna: 'No zone restriction.' },
		},
		sector: {
			type: 'choice',
			instructions: 'Which industry sector does the request restrict to? Choose "ninguno" if none is mentioned or implied.',
			criteria: opciones(p.sectores ?? [], 'ninguno'),
		},
		pais: {
			type: 'choice',
			instructions: 'Which country does the request restrict to? Choose "ninguno" if none is mentioned.',
			criteria: paises,
		},
		tamano: {
			type: 'choice',
			instructions: 'Does the request restrict by company size?',
			criteria: { Micro: 'Micro (under 2 M€ revenue).', Pequeña: 'Small (2 to 10 M€).', Mediana: 'Medium (10 to 50 M€).', Grande: 'Large (50 M€ or more).', ninguno: 'No size restriction.' },
		},
		producto: {
			type: 'choice',
			instructions: 'Does the request mention one banking product?',
			criteria: {
				linea_credito: 'Credit line (línea de crédito, póliza).', factoring: 'Factoring.', confirming: 'Confirming (reverse factoring).',
				seguro_credito: 'Credit insurance (seguro de crédito).', cuenta_remunerada: 'Interest-bearing account (cuenta remunerada).',
				depositos: 'Deposits or treasury bills (depósitos, letras).', plan_pensiones: 'Pension plan (plan de pensiones).', ninguno: 'No product is mentioned.',
			},
		},
		producto_modo: {
			type: 'choice',
			instructions: 'If a product is mentioned: do they already have it, or would it fit them (candidates to offer it)?',
			criteria: { tiene: 'They already have or use it.', encaja: 'It would fit them; candidates; could be offered.', no_dice: 'No product, or it does not say.' },
		},
	};
}

const CORS = {
	'Access-Control-Allow-Origin': '*',
	'Access-Control-Allow-Methods': 'POST, OPTIONS',
	'Access-Control-Allow-Headers': 'Content-Type',
	'Access-Control-Max-Age': '86400',
};

const json = (datos: unknown, estado = 200) => new Response(JSON.stringify(datos), { status: estado, headers: { 'Content-Type': 'application/json; charset=utf-8', ...CORS } });

function valida(x: unknown): Peticion | string {
	if (!x || typeof x !== 'object') return 'Cuerpo JSON no válido.';
	const p = x as Record<string, unknown>;
	if (typeof p.texto !== 'string' || !p.texto.trim()) return 'Falta el texto.';
	if (p.texto.length > MAX_TEXTO) return `El texto pasa de ${MAX_TEXTO} caracteres.`;
	const sectores = Array.isArray(p.sectores) ? p.sectores.filter((s): s is string => typeof s === 'string' && s.length <= 60).slice(0, 30) : [];
	const paises: Record<string, string> = {};
	if (p.paises && typeof p.paises === 'object') for (const [k, v] of Object.entries(p.paises as Record<string, unknown>).slice(0, 40)) if (/^[A-Z]{2}$/.test(k) && typeof v === 'string' && v.length <= 60) paises[k] = v;
	return { texto: p.texto.trim(), sectores, paises };
}

export default {
	async fetch(req: Request, env: Env): Promise<Response> {
		if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
		const url = new URL(req.url);
		if (req.method === 'GET' && url.pathname === '/') return json({ servicio: 'rumbo-vista', modelo: MODELO, uso: 'POST {texto, sectores, paises}' });
		if (req.method !== 'POST' || url.pathname !== '/vista') return json({ error: 'No encontrado.' }, 404);
		if (!env.TYPESAFE_API_KEY) return json({ error: 'Falta la clave de TypeSafe en el Worker.' }, 503);
		if (env.LIMITE) {
			const ip = req.headers.get('CF-Connecting-IP') ?? 'anonimo';
			const { success } = await env.LIMITE.limit({ key: ip });
			if (!success) return json({ error: 'Demasiadas peticiones; espera un momento.' }, 429);
		}
		let cuerpo: unknown;
		try { cuerpo = await req.json(); } catch { return json({ error: 'Cuerpo JSON no válido.' }, 400); }
		const p = valida(cuerpo);
		if (typeof p === 'string') return json({ error: p }, 400);

		const t0 = Date.now();
		const peticion = JSON.stringify({ model: MODELO, state: { peticion: p.texto }, questions: preguntas(p) });
		let r: Response | null = null;
		for (let intento = 0; intento < 3; intento++) {
			r = await fetch('https://api.typesafe.ai/v1/systemone', { method: 'POST', headers: { Authorization: `Bearer ${env.TYPESAFE_API_KEY}`, 'Content-Type': 'application/json' }, body: peticion });
			if (r.status !== 429 && r.status !== 529) break;
			await new Promise((ok) => setTimeout(ok, 300 * 2 ** intento));
		}
		if (!r || !r.ok) return json({ error: `TypeSafe respondió ${r?.status ?? 'sin respuesta'}.` }, 502);
		const datos = (await r.json()) as { model: string; answers: Record<string, unknown>; usage?: unknown };
		return json({ modelo: datos.model, respuestas: datos.answers, uso: datos.usage, ms: Date.now() - t0 });
	},
};
