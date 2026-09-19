// Validación de cumplimiento de las propuestas guardadas: compara el insumo
// que cada acción apuntaba en su corte con la métrica real de los meses
// posteriores del fichero. Nada se predice: solo se mira si la métrica medida
// se movió hacia el objetivo (o llegó). Sin meses posteriores, no hay juicio.

import type { EntidadM, MesM } from "./contrato";
import { f } from "./formato";
import type { AccionElegida, PropuestaGuardada } from "./propuestas";

/** La serie del motor donde se ve el insumo que cada pilar mueve. */
const SERIE_POR_PILAR: Record<string, string> = {
  liquidity: "buffer_days",
  payments: "ap_days_beyond_terms",
  collections: "ar_days_beyond_terms",
  activity: "activity_coverage",
  debt: "debt_burden",
};

export const serieDePilar = (pillar: string): string | null =>
  SERIE_POR_PILAR[pillar] ?? null;

/** El valor de una serie en un mes: las series van alineadas por el final con los meses. */
export function valorSerieEn(
  ent: EntidadM,
  clave: string,
  mes: string,
): number | null {
  const meses = ent.months.map((m) => m.month);
  const i = meses.indexOf(mes);
  if (i < 0) return null;
  const s = ent.series.find((x) => x.key === clave);
  if (!s) return null;
  return s.values[i + (s.values.length - meses.length)] ?? null;
}

export type EstadoAccion = "cumplida" | "en camino" | "pendiente" | "sin datos";

export interface AccionValidada {
  accion: AccionElegida;
  estado: EstadoAccion;
  antes: number | null;
  ahora: number | null;
  /** «de 19 a 15 días»: lo medido en el corte y lo medido hoy. */
  etiqueta: string;
}

const NOMBRE_UNIDAD: Record<string, string> = {
  días: "días",
  ratio: "veces",
  "%": "%",
};

function formatoValor(v: number | null, unit: string): string {
  if (v === null) return "—";
  const u = NOMBRE_UNIDAD[unit] ?? "";
  return u === "días"
    ? `${f.numero(v, 1)} días`
    : u === "veces"
      ? `${f.numero(v, 2)}×`
      : u === "%"
        ? `${f.numero(v, 1)} %`
        : f.numero(v, 1);
}

/** El juicio de una acción guardada frente a lo medido antes y después. */
export function validarAccion(
  a: AccionElegida,
  antes: number | null,
  ahora: number | null,
): AccionValidada {
  const unit = a.unit ?? "";
  if (
    antes === null ||
    ahora === null ||
    a.target === null ||
    a.target === undefined ||
    a.current === null ||
    a.current === undefined
  )
    return {
      accion: a,
      estado: "sin datos",
      antes,
      ahora,
      etiqueta: `${formatoValor(antes, unit)} → ${formatoValor(ahora, unit)}`,
    };
  const brecha = antes - a.target;
  const tol = Math.abs(brecha) * 0.1;
  const estado: EstadoAccion =
    Math.abs(ahora - a.target) <= tol + 1e-9 || Math.abs(brecha) < 1e-9
      ? "cumplida"
      : (antes - ahora) / brecha >= 0.5
        ? "en camino"
        : "pendiente";
  return {
    accion: a,
    estado,
    antes,
    ahora,
    etiqueta: `${formatoValor(antes, unit)} → ${formatoValor(ahora, unit)}`,
  };
}

export interface SeguimientoM {
  /** Score del corte de la propuesta y del mes más reciente. */
  scoreAntes: number;
  scoreAhora: number | null;
  acciones: AccionValidada[];
  /** true si hay al menos un mes de datos posterior al corte de la propuesta. */
  conMeses: boolean;
}

/** Lo que pasó desde que se guardó la propuesta hasta el último mes del fichero. */
export function validarPropuesta(
  p: PropuestaGuardada,
  ent: EntidadM,
  mesActual: MesM | null,
): SeguimientoM {
  const conMeses = !!mesActual && mesActual.month > p.corte;
  const acciones: AccionValidada[] = [];
  if (conMeses && mesActual) {
    for (const a of p.acciones) {
      const clave = serieDePilar(a.pillar);
      acciones.push(
        validarAccion(
          a,
          clave ? valorSerieEn(ent, clave, p.corte) : null,
          clave ? valorSerieEn(ent, clave, mesActual.month) : null,
        ),
      );
    }
  }
  return {
    scoreAntes: p.score_actual_tenths,
    scoreAhora: mesActual?.shown ?? null,
    acciones,
    conMeses,
  };
}
