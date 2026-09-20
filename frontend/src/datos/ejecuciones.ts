import { f } from './formato';

export type EstadoEjecucion = 'en_curso' | 'pausada' | 'completada';
export const estadosEjecucion: Record<EstadoEjecucion, string> = { en_curso: 'En curso', pausada: 'Pausada', completada: 'Completada' };
export interface EleccionFinanciacion { entity_id: string; id: string; banks: string[] }
export interface AmbitoEjecucion { entity_id: string; group_id: string; kind: 'company' | 'group' }
export interface Ejecucion {
 id: string; status: EstadoEjecucion; version: number; created_at: string;
 snapshot: { id: string; title: string; detail: string; baseline: number | null; target: number | null; unit: string; corte: string; uplift_tenths: number; score_tenths: number | null; demo?: boolean; banks?: string[]; financing?: boolean; source_entity_id?: string };
 events: { id: string; actor: string; kind: 'decision' | 'measurement'; created_at: string; payload: { status?: EstadoEjecucion; note?: string; month?: string; value?: number | null; score_tenths?: number | null } }[];
}
const base = '/api/v1/action-executions';
async function api<T>(path: string, method: string, body?: unknown): Promise<T> {
 let res: Response;
 try { res = await fetch(base + path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); }
 catch { throw new Error('No se pudo conectar. No damos el cambio por guardado; vuelve a intentarlo.'); }
 if (!res.ok) {
  const error = await res.json().catch(() => null);
  throw new Error(typeof error?.detail === 'string' ? error.detail : 'No se pudo guardar o consultar el seguimiento. Vuelve a intentarlo.');
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
export const valorEjecucion = (v: number | null, unit: string) => v === null ? 'Sin dato' : unit === '%' ? f.puntosPorcentaje(v) : f.valorUnidad(v, unit);
