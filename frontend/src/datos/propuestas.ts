// El flujo de propuesta al cliente: lo que el usuario de Embat elige en la
// sección Acciones (acciones + banco por instrumento) y las propuestas que
// genera. Todo vive en localStorage con trazabilidad: id, fecha, entidad,
// corte, hash del bundle y lo elegido. El envío real (correo) lo hace el
// navegador del usuario; aquí se guarda qué se propuso y a quién.

import type { FinanciacionM } from "./contrato";
import { fuenteTexto } from "./tasas";

const CLAVE = "rumbo.propuestas.v1";

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
    const crudo = localStorage.getItem(CLAVE);
    if (!crudo) return { generadas: [] };
    const dato = JSON.parse(crudo) as Partial<Almacen>;
    return { generadas: Array.isArray(dato.generadas) ? dato.generadas : [] };
  } catch {
    return { generadas: [] };
  }
}

function escribir(almacen: Almacen): void {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(almacen));
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

export function guardarPropuesta(p: PropuestaGuardada): void {
  const almacen = leer();
  almacen.generadas = [p, ...almacen.generadas.filter((x) => x.id !== p.id)];
  escribir(almacen);
}

export function borrarPropuesta(id: string): void {
  const almacen = leer();
  almacen.generadas = almacen.generadas.filter((x) => x.id !== id);
  escribir(almacen);
}

/** Id corto y estable: fecha-hora local + azar de la sesión. */
export function nuevaPropuestaId(): string {
  const ahora = new Date();
  const sello = `${ahora.getFullYear()}${String(ahora.getMonth() + 1).padStart(2, "0")}${String(ahora.getDate()).padStart(2, "0")}-${String(ahora.getHours()).padStart(2, "0")}${String(ahora.getMinutes()).padStart(2, "0")}`;
  const azar = Math.random().toString(36).slice(2, 6);
  return `${sello}-${azar}`;
}

/** El asunto y el cuerpo del correo que abre el navegador (el envío lo hace el usuario). */
export function correoPropuesta(p: PropuestaGuardada): {
  asunto: string;
  cuerpo: string;
} {
  const lineas: string[] = [];
  lineas.push(
    `Plan de mejora de ${p.entidad} (${p.kind === "company" ? "empresa" : "organización"}) · corte ${p.corte}`,
  );
  lineas.push(
    `Score actual: ${(p.score_actual_tenths / 10).toLocaleString("es-ES")}.`,
  );
  lineas.push("");
  lineas.push("Acciones propuestas:");
  for (const a of p.acciones)
    lineas.push(
      `· ${a.title} (${a.uplift_tenths > 0 ? "+" : ""}${(a.uplift_tenths / 10).toLocaleString("es-ES")} puntos según el motor)`,
    );
  if (p.financiacion.length) {
    lineas.push("");
    lineas.push("Financiación propuesta:");
    for (const f of p.financiacion) {
      const monto =
        f.amount !== null ? ` por ${f.amount.toLocaleString("es-ES")} EUR` : "";
      const banco = f.bank ?? "banco a convenir";
      const tasa =
        f.rate !== null
          ? `, ${f.rate.toLocaleString("es-ES")} % ${f.rate_type === "variable" ? "variable" : "fijo"}${f.rate_fuente ? ` (${fuenteTexto(f.rate_fuente)})` : ""}`
          : "";
      lineas.push(`· ${f.title}${monto}, con ${banco}${tasa}.`);
    }
  }
  lineas.push("");
  lineas.push(
    `Preparado por Embat · bundle ${p.bundle_id.slice(0, 12)} · ${p.fecha.slice(0, 10)}.`,
  );
  return {
    asunto: `Embat · Plan para ${p.entidad} (${p.corte})`,
    cuerpo: lineas.join("\n"),
  };
}
