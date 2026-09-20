import { f } from './formato';

export type EstadoEjecucion = 'en_curso' | 'pausada' | 'completada';
export const estadosEjecucion: Record<EstadoEjecucion, string> = { en_curso: 'En curso', pausada: 'En pausa', completada: 'Finalizada' };
export interface EleccionFinanciacion { entity_id: string; id: string; banks: string[] }
export interface AmbitoEjecucion { entity_id: string; group_id: string; kind: 'company' | 'group' }
export interface Ejecucion {
 id: string; status: EstadoEjecucion; version: number; created_at: string;
 snapshot: { id: string; title: string; detail: string; baseline: number | null; target: number | null; unit: string; corte: string; uplift_tenths: number; score_tenths: number | null; demo?: boolean; banks?: string[]; financing?: boolean; source_entity_id?: string };
 events: { id: string; actor: string; kind: 'decision' | 'measurement'; created_at: string; payload: { status?: EstadoEjecucion; previous_status?: EstadoEjecucion; note?: string; month?: string; value?: number | null; score_tenths?: number | null } }[];
}
/** El fallo de la API con su código: un 409 pide recargar, no reintentar. */
export class ErrorEjecuciones extends Error {
 constructor(mensaje: string, readonly estado: number | null) { super(mensaje); }
}
const base = '/api/v1/action-executions';
async function api<T>(path: string, method: string, body?: unknown): Promise<T> {
 let res: Response;
 try { res = await fetch(base + path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); }
 catch { throw new ErrorEjecuciones('No se pudo conectar. No damos el cambio por guardado; vuelve a intentarlo.', null); }
 if (!res.ok) {
  const error = await res.json().catch(() => null);
  throw new ErrorEjecuciones(typeof error?.detail === 'string' ? error.detail : 'No se pudo guardar o consultar el seguimiento. Vuelve a intentarlo.', res.status);
 }
 return res.json();
}
export const ejecuciones = {
 listar: (a: AmbitoEjecucion) => api<Ejecucion[]>(`?entity_id=${encodeURIComponent(a.entity_id)}&group_id=${encodeURIComponent(a.group_id)}`, 'GET'),
 actualizarMedidas: (a: AmbitoEjecucion) => api<Ejecucion[]>('/refresh', 'POST', a),
 iniciar: (a: AmbitoEjecucion, corte: string, bundle_id: string, action_ids: string[], actor: string, financing: EleccionFinanciacion[] = []) => api<Ejecucion[]>('', 'POST', { ...a, corte, bundle_id, action_ids, actor, financing }),
 guardar: (e: Ejecucion, group_id: string, status: EstadoEjecucion, note: string, actor: string) => api<Ejecucion>(`/${encodeURIComponent(e.id)}`, 'PATCH', { group_id, status, note, actor, version: e.version }),
};
export function avanceEjecucion(e: Ejecucion, corte: string) {
 const medidas = e.events.filter(v => v.kind === 'measurement' && v.payload.month! <= corte)
  .sort((a, b) => a.payload.month!.localeCompare(b.payload.month!) || a.created_at.localeCompare(b.created_at));
 const ultima = medidas.at(-1)?.payload;
 const inicio = e.snapshot.baseline, objetivo = e.snapshot.target, actual = ultima?.value ?? null;
 const fraccion = inicio !== null && objetivo !== null && actual !== null && objetivo !== inicio ? (actual - inicio) / (objetivo - inicio) : null;
 return { actual, mes: ultima?.month, fraccion, barra: fraccion === null ? null : Math.max(0, Math.min(1, fraccion)),
  texto: !ultima ? 'A la espera del próximo cierre' : fraccion === null ? 'Sin datos comparables en este cierre' : fraccion >= 1 ? 'Objetivo alcanzado' : fraccion < 0 ? 'Se aleja del objetivo' : 'Avance hacia el objetivo' };
}
/** Igual que la palanca de la acción (`palancaDeAccion`): la medida tiene que leerse con sus mismas unidades. */
export const valorEjecucion = (v: number | null, unit: string) => v === null ? 'Sin dato' : unit === '%' ? f.puntosPorcentaje(v) : unit === 'ratio' ? `${f.ratio(v)} ×` : f.valorUnidad(v, unit);

/** Dónde está una acción del motor respecto a las decisiones guardadas. */
export type SituacionAccion = { estado: 'disponible'; registro: null } | { estado: EstadoEjecucion; registro: Ejecucion };
/**
 * El motor repite la palanca cada mes mientras no se cumple, con el mismo id. Una decisión abierta
 * de un cierre anterior sigue siendo esa acción; una ya finalizada solo cuenta en su propio cierre,
 * porque desde el siguiente se puede retomar. Los ejemplos de demostración no ocupan la acción.
 */
export function situacionAccion(registros: readonly Ejecucion[], id: string, corte: string): SituacionAccion {
 const suyos = registros.filter(e => e.snapshot.id === id && !e.snapshot.demo && e.snapshot.corte <= corte)
  .sort((a, b) => b.snapshot.corte.localeCompare(a.snapshot.corte));
 const registro = suyos.find(e => e.status !== 'completada') ?? suyos.find(e => e.snapshot.corte === corte) ?? null;
 return registro ? { estado: registro.status, registro } : { estado: 'disponible', registro: null };
}
/** Los cambios de estado que se ofrecen desde cada uno, con el verbo que lleva el botón. */
export const pasosEjecucion: Record<EstadoEjecucion, { a: EstadoEjecucion; verbo: string }[]> = {
 en_curso: [{ a: 'pausada', verbo: 'Pausar' }, { a: 'completada', verbo: 'Finalizar' }],
 pausada: [{ a: 'en_curso', verbo: 'Reanudar' }, { a: 'completada', verbo: 'Finalizar' }],
 completada: [{ a: 'en_curso', verbo: 'Reabrir' }],
};
