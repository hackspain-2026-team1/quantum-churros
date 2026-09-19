// Lectura de los ficheros de datos, con caché. Dos raíces:
//   bundle → el bundle del motor (xray-export-v1): manifest, portfolio, groups, companies, evidence, alerts, receipt.
//   rumbo  → lo que generan los procesos de Rumbo desde los mismos datos: products, horizons y params.
// En desarrollo son public/datos y public/rumbo; en el despliegue, VITE_DATOS=/data/v1/ y
// VITE_RUMBO=/data/rumbo/ (carpetas montadas en el contenedor web, fuera de la imagen).
// Si un fichero de Rumbo falta, la función devuelve null y la interfaz lo dice; nunca rellena con otra cosa.

import type {
	AlertaM, EmpresaM, IndiceEmpresasM, EvidenciaM, GrupoM, HorizonteM, HorizontesIndiceM, HorizontesPasadosM, Manifiesto, ParametrosM,
	ProductosEmpresaM, ProductosGrupoM, ProductosIndiceM, ReciboM,
} from './contrato';

const BASE = import.meta.env.BASE_URL;
const conBarra = (r: string) => (r.endsWith("/") ? r : `${r}/`);
export const RAIZ_BUNDLE = conBarra(
  import.meta.env.VITE_DATOS || `${BASE}datos/`,
);
export const RAIZ_RUMBO = conBarra(
  import.meta.env.VITE_RUMBO || `${BASE}rumbo/`,
);

const cache = new Map<string, Promise<unknown>>();

async function pedir<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return (await r.json()) as T;
}

/** Lee y guarda en caché. `opcional` devuelve null si el fichero no existe. */
function leer<T>(url: string, opcional: true): Promise<T | null>;
function leer<T>(url: string, opcional?: false): Promise<T>;
function leer<T>(url: string, opcional = false): Promise<T | null> {
  if (!cache.has(url))
    cache.set(url, opcional ? pedir<T>(url).catch(() => null) : pedir<T>(url));
  return cache.get(url) as Promise<T | null>;
}

export const carga = {
	manifiesto: () => leer<Manifiesto>(`${RAIZ_BUNDLE}manifest.json`),
	grupo: (id: string) => leer<GrupoM>(`${RAIZ_BUNDLE}groups/${id}.json`),
	empresa: (id: string) => leer<EmpresaM>(`${RAIZ_BUNDLE}companies/${id}.json`, true),
	evidencia: (id: string) => leer<EvidenciaM>(`${RAIZ_BUNDLE}evidence/${id}.json`, true),
	alertas: () => leer<{ alerts: AlertaM[] }>(`${RAIZ_BUNDLE}alerts.json`),
	recibo: () => leer<ReciboM>(`${RAIZ_BUNDLE}receipt.json`, true),
	productosEmpresa: (id: string) => leer<ProductosEmpresaM>(`${RAIZ_RUMBO}products/${id}.json`, true),
	productosGrupo: (id: string) => leer<ProductosGrupoM>(`${RAIZ_RUMBO}products/${id}.json`, true),
	productosIndice: () => leer<ProductosIndiceM>(`${RAIZ_RUMBO}products/index.json`, true),
	horizonte: (id: string) => leer<HorizonteM>(`${RAIZ_RUMBO}horizons/${id}.json`, true),
	horizontePasado: (id: string) => leer<HorizontesPasadosM>(`${RAIZ_RUMBO}horizons/pasados/${id}.json`, true),
	horizontesIndice: () => leer<HorizontesIndiceM>(`${RAIZ_RUMBO}horizons/index.json`, true),
	parametros: () => leer<ParametrosM>(`${RAIZ_RUMBO}params.json`, true),
	indiceEmpresas: () => leer<IndiceEmpresasM>(`${RAIZ_RUMBO}indice-empresas.json`, true),
};

/** Lo que se ha cargado ya, sin esperar (para pintar a la primera si está en caché). */
export async function yaCargado<T>(p: Promise<T>): Promise<T> {
  return p;
}

/** Los datos de Rumbo tienen que ser del mismo bundle que el motor: si no, se avisa. */
export function mismaHuella(
  bundleId: string,
  otro: { bundle_id?: string } | null,
) {
  return !otro || !otro.bundle_id || otro.bundle_id === bundleId;
}
