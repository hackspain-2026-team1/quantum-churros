// La fuente de precios de las ofertas. En producción este contrato lo llenan
// las APIs de los bancos; en la demo se llena con lo que el dataset trae
// (tasa real de los préstamos) y, donde no hay dato, con una estimación de
// mercado SIEMPRE marcada como tal. Nada se presenta como real sin serlo.

import type { FinanciacionM } from "./contrato";

export type FuenteTasa = "banco" | "mercado";

export interface TasaOfrecida {
  tasa: number; // % anual (factoring/confirming: comisión sobre el anticipo)
  fuente: FuenteTasa;
}

/** Estimaciones deterministas de mercado por instrumento, para la demo. */
export const ESTIMACIONES: Record<
  Exclude<FinanciacionM["kind"], "sweep">,
  number
> = {
  factoring: 6.0, // comisión habitual sobre el anticipo: 4-8 %
  confirming: 3.0, // 2-4 %
  line: 4.5, // Euribor + ~2-3
  restructure: 6.5, // préstamo a plazo renegociado, si no consta el dato
};

/** La tasa que se ofrece para el instrumento: la real del banco si consta, si no la estimación de mercado. */
export function tasaPara(
  kind: FinanciacionM["kind"],
  rate: number | null,
  _rate_type: string | null,
): TasaOfrecida | null {
  if (kind === "sweep") return null; // mover caja del grupo no tiene tasa
  if (rate !== null && rate !== undefined)
    return { tasa: rate, fuente: "banco" };
  return {
    tasa: ESTIMACIONES[kind as keyof typeof ESTIMACIONES],
    fuente: "mercado",
  };
}

export function fuenteTexto(fuente: FuenteTasa): string {
  return fuente === "banco" ? "tasa del banco" : "estimación de mercado";
}
