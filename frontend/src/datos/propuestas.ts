// El flujo de propuesta al cliente: lo que el usuario de Embat elige en la
// sección Acciones (acciones + banco por instrumento) y las propuestas que
// genera. Todo vive en localStorage con trazabilidad: id, fecha, entidad,
// corte, hash del bundle y lo elegido. El envío real (correo) lo hace el
// navegador del usuario; aquí se guarda qué se propuso y a quién.

import type { FinanciacionM } from "./contrato";
import { f } from "./formato";
import { claveDeMirada, voz } from "./redaccion";
import { fuenteTexto } from "./tasas";

const CLAVE = () => claveDeMirada("rumbo.propuestas.v1");
const API = "/api/v1/proposals";

export interface FinanciacionElegida {
  id: string;
  kind: FinanciacionM["kind"];
  title: string;
  amount: number | null;
  uplift_tenths: number;
  bank: string | null;
  rate: number | null;
  rate_type: string | null;
  /** De dónde sale la tasa: del banco (dato real) o estimación de mercado. */
  rate_fuente: "banco" | "mercado" | null;
}

export interface AccionElegida {
  id: string;
  pillar: string;
  title: string;
  uplift_tenths: number;
  new_score_tenths: number;
  /** El valor medido del insumo en el corte y al que apunta la acción: para validar después si se cumplió. */
  current?: number | null;
  target?: number | null;
  unit?: "días" | "ratio" | "%" | null;
}

export interface PropuestaGuardada {
  id: string;
  fecha: string; // ISO
  kind: "company" | "group";
  entidad: string;
  grupoId: string;
  corte: string;
  bundle_id: string;
  score_actual_tenths: number;
  acciones: AccionElegida[];
  financiacion: FinanciacionElegida[];
}

interface Almacen {
  generadas: PropuestaGuardada[];
}

function leer(): Almacen {
  try {
    const crudo = localStorage.getItem(CLAVE());
    if (!crudo) return { generadas: [] };
    const dato = JSON.parse(crudo) as Partial<Almacen>;
    return { generadas: Array.isArray(dato.generadas) ? dato.generadas : [] };
  } catch {
    return { generadas: [] };
  }
}

function escribir(almacen: Almacen): void {
  try {
    localStorage.setItem(CLAVE(), JSON.stringify(almacen));
  } catch {
    // sin almacenamiento: la propuesta vive solo en la sesión
  }
}

export function propuestasDe(
  entidad: string,
  corte: string,
): PropuestaGuardada[] {
  return leer()
    .generadas.filter((p) => p.entidad === entidad && p.corte === corte)
    .sort((a, b) => b.fecha.localeCompare(a.fecha));
}

/** Todo el registro de propuestas, de más nueva a más vieja (cualquier entidad y corte). */
export function todasLasPropuestas(): PropuestaGuardada[] {
  return [...leer().generadas].sort((a, b) => b.fecha.localeCompare(a.fecha));
}

/**
 * Instrumentos del mes para el paso 3. Si el motor no propone ninguno en la
 * entidad (pasa en grupos con colchón holgado), se juntan los de sus empresas
 * por tipo: el monto se suma, el texto y el efecto se quedan con el de mayor
 * subida. Ese efecto es de la empresa, no del grupo.
 */
export function instrumentosDelMes(
  propios: readonly FinanciacionM[] | undefined,
  deEmpresas: readonly (readonly FinanciacionM[] | undefined)[],
): FinanciacionM[] {
  if (propios?.length) return [...propios];
  const porKind = new Map<
    FinanciacionM["kind"],
    { item: FinanciacionM; n: number; amount: number | null }
  >();
  for (const lista of deEmpresas)
    for (const x of lista ?? []) {
      const actual = porKind.get(x.kind);
      if (!actual) {
        porKind.set(x.kind, { item: { ...x }, n: 1, amount: x.amount });
        continue;
      }
      actual.n += 1;
      actual.amount =
        actual.amount !== null || x.amount !== null
          ? (actual.amount ?? 0) + (x.amount ?? 0)
          : null;
      if (x.uplift_tenths > actual.item.uplift_tenths) actual.item = { ...x };
    }
  return [...porKind.values()]
    .sort((a, b) => b.item.uplift_tenths - a.item.uplift_tenths)
    .map(({ item, n, amount }) => ({
      ...item,
      amount,
      detail:
        n > 1
          ? `Lo necesitan ${n} empresas del grupo este mes. ${item.detail}`
          : `Lo necesita una empresa del grupo este mes. ${item.detail}`,
    }));
}

function mezclar(remotas: PropuestaGuardada[]): void {
  const local = leer().generadas;
  const porId = new Map<string, PropuestaGuardada>();
  for (const p of [...remotas, ...local]) porId.set(p.id, p);
  escribir({
    generadas: [...porId.values()].sort((a, b) => b.fecha.localeCompare(a.fecha)),
  });
}

/** Trae el histórico del API y lo junta con lo del navegador. Si el API no está, no toca nada. */
export async function sincronizarPropuestas(entidad?: string): Promise<void> {
  try {
    const q = entidad ? `?entity_id=${encodeURIComponent(entidad)}` : "";
    const r = await fetch(`${API}${q}`);
    if (!r.ok) return;
    const dato = (await r.json()) as PropuestaGuardada[];
    if (Array.isArray(dato)) mezclar(dato);
  } catch {
    /* sin API: el historial vive en el navegador */
  }
}

export function guardarPropuesta(p: PropuestaGuardada): void {
  const almacen = leer();
  almacen.generadas = [p, ...almacen.generadas.filter((x) => x.id !== p.id)];
  escribir(almacen);
  void fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  }).catch(() => {
    /* sin API: queda el rastro local */
  });
}

export function borrarPropuesta(id: string): void {
  const almacen = leer();
  almacen.generadas = almacen.generadas.filter((x) => x.id !== id);
  escribir(almacen);
  void fetch(`${API}/${encodeURIComponent(id)}`, { method: "DELETE" }).catch(
    () => {
      /* sin API: ya se borró en el navegador */
    },
  );
}

/** Id corto y estable: fecha-hora local + azar de la sesión. */
export function nuevaPropuestaId(): string {
  const ahora = new Date();
  const sello = `${ahora.getFullYear()}${String(ahora.getMonth() + 1).padStart(2, "0")}${String(ahora.getDate()).padStart(2, "0")}-${String(ahora.getHours()).padStart(2, "0")}${String(ahora.getMinutes()).padStart(2, "0")}`;
  const azar = Math.random().toString(36).slice(2, 6);
  return `${sello}-${azar}`;
}

function nombreEntidad(kind: PropuestaGuardada["kind"], id: string): string {
  return kind === "company" ? f.empresa(id) : f.grupo(id);
}

function abrirMailto(asunto: string, cuerpo: string): void {
  window.location.href = `mailto:?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(cuerpo)}`;
}

/** El asunto y el cuerpo del correo que abre el navegador (el envío lo hace el usuario). */
export function correoPropuesta(p: PropuestaGuardada): {
  asunto: string;
  cuerpo: string;
} {
  const quien = nombreEntidad(p.kind, p.entidad);
  const lineas: string[] = [];
  lineas.push(
    `Plan de mejora de ${quien} (${p.kind === "company" ? "empresa" : "organización"}) · corte ${f.mes(p.corte)}`,
  );
  lineas.push(`Score actual: ${f.score(p.score_actual_tenths)}.`);
  lineas.push("");
  lineas.push(voz("Acciones propuestas:", "Acciones que vamos a hacer:"));
  if (p.acciones.length)
    for (const a of p.acciones)
      lineas.push(`· ${a.title} (${f.delta(a.uplift_tenths)} puntos según el motor)`);
  else lineas.push("· Ninguna acción de gestión este mes.");
  if (p.financiacion.length) {
    lineas.push("");
    lineas.push(voz("Financiación propuesta:", "Financiación que solicitamos:"));
    for (const x of p.financiacion) {
      const monto = x.amount !== null ? ` por ${f.euros(x.amount)}` : "";
      const banco = x.bank ?? "banco a convenir";
      const tasa =
        x.rate !== null
          ? `, ${f.puntosPorcentaje(x.rate, 2)} ${x.rate_type === "variable" ? "variable" : "fijo"}${x.rate_fuente ? ` (${fuenteTexto(x.rate_fuente)})` : ""}`
          : "";
      lineas.push(`· ${x.title}${monto}, con ${banco}${tasa}.`);
    }
  }
  lineas.push("");
  lineas.push(
    `${voz("Preparado por Embat", "Preparado con Rumbo (Embat)")} · bundle ${p.bundle_id.slice(0, 12)} · ${f.fecha(p.fecha)}.`,
  );
  return {
    asunto: voz(`Embat · Plan para ${quien} (${f.mes(p.corte)})`, `Plan de ${quien} · ${f.mes(p.corte)}`),
    cuerpo: lineas.join("\n"),
  };
}

/** Guarda el rastro y abre el cliente de correo del usuario. */
export function enviarPropuestaPorMail(p: PropuestaGuardada): void {
  guardarPropuesta(p);
  const { asunto, cuerpo } = correoPropuesta(p);
  abrirMailto(asunto, cuerpo);
}
