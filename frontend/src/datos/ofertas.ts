// Ofertas de financiación por banco: un ranking determinista de los bancos con
// los que la organización ya trabaja, para que el usuario de Embat elija a quién
// proponerle cada instrumento. Nada se inventa: la tasa sale de los datos cuando
// consta (casi siempre solo para préstamos) y si no, la oferta dice «sin tasa
// publicada». El motor solo aporta el instrumento y el monto; el banco es una
// relación real de la entidad (cuentas o productos contratados).

import type {
  FinanciacionM,
  OtraDeudaM,
  ProductoId,
  TenenciaM,
} from "./contrato";

export interface OfertaBanco {
  bank: string;
  /** true si el banco ya le da a la entidad un producto de este tipo. */
  tieneProducto: boolean;
  /** Tasa anual en % cuando el dato existe (productos de calendario); si no, null. */
  rate: number | null;
  rate_type: string | null;
  granted: number | null;
  outstanding: number | null;
}

export interface FuentesBanco {
  tenencias: TenenciaM[];
  otras: OtraDeudaM[];
  /** Bancos de las cuentas (claves de accounts). */
  cuentas: string[];
}

const PRODUCTO_POR_KIND: Partial<Record<FinanciacionM["kind"], ProductoId>> = {
  factoring: "factoring",
  confirming: "confirming",
  line: "linea_credito",
};
/** El instrumento «reestructuración» equivale a un préstamo (loan) entre las otras deudas. */
const ES_PRESTAMO = /loan|préstamo/i;

function bancoDe(bank: string | null): string | null {
  return bank && bank.trim() ? bank.trim() : null;
}

/**
 * Los bancos con los que la entidad trabaja, de mejor a peor opción para el
 * instrumento: primero los que ya le dan ese producto (por tasa creciente
 * cuando consta, y concedido decreciente), después los que tienen cualquier
 * otro producto o cuenta. Determinista: los empates por nombre.
 */
export function ofertasBanco(
  kind: FinanciacionM["kind"],
  fuentes: FuentesBanco,
): OfertaBanco[] {
  const producto = PRODUCTO_POR_KIND[kind];
  const exactos = new Map<string, OfertaBanco>();
  const conocidos = new Set<string>();

  const anotar = (
    mapa: Map<string, OfertaBanco>,
    bank: string,
    rate: number | null,
    rate_type: string | null,
    granted: number | null,
    outstanding: number | null,
  ) => {
    const anterior = mapa.get(bank);
    if (
      !anterior ||
      (rate !== null && anterior.rate === null) ||
      (rate !== null && anterior.rate !== null && rate < anterior.rate) ||
      (anterior.rate === null &&
        rate === null &&
        (granted ?? 0) > (anterior.granted ?? 0))
    ) {
      mapa.set(bank, {
        bank,
        tieneProducto: true,
        rate,
        rate_type,
        granted,
        outstanding,
      });
    }
  };

  for (const tenencia of fuentes.tenencias) {
    const es = tenencia.product === producto;
    for (const item of tenencia.items) {
      const b = bancoDe(item.bank);
      if (!b) continue;
      conocidos.add(b);
      if (es)
        anotar(
          exactos,
          b,
          item.rate,
          item.rate_type,
          item.granted,
          item.outstanding,
        );
    }
  }
  for (const otra of fuentes.otras) {
    const b = bancoDe(otra.bank);
    if (!b) continue;
    conocidos.add(b);
    if (
      kind === "restructure" &&
      ES_PRESTAMO.test(`${otra.type} ${otra.type_label}`)
    ) {
      anotar(
        exactos,
        b,
        otra.rate,
        otra.rate_type,
        otra.granted,
        otra.outstanding,
      );
    }
  }
  for (const cuenta of fuentes.cuentas) conocidos.add(cuenta);

  const resto = [...conocidos]
    .filter((b) => !exactos.has(b))
    .map((bank) => ({
      bank,
      tieneProducto: false,
      rate: null,
      rate_type: null,
      granted: null,
      outstanding: null,
    }));
  return [...exactos.values(), ...resto].sort((a, b) => {
    if (a.tieneProducto !== b.tieneProducto) return a.tieneProducto ? -1 : 1;
    if ((a.rate ?? 1e9) !== (b.rate ?? 1e9))
      return (a.rate ?? 1e9) - (b.rate ?? 1e9);
    if ((b.granted ?? 0) !== (a.granted ?? 0))
      return (b.granted ?? 0) - (a.granted ?? 0);
    return a.bank.localeCompare(b.bank, "es");
  });
}

/** Las fuentes de la ficha de una entidad (empresa: las suyas; grupo: las de sus empresas). */
export function fuentesDe(
  tenencias: TenenciaM[],
  otras: OtraDeudaM[],
  cuentas: string[],
  empresas: {
    tenencias: TenenciaM[];
    otras: OtraDeudaM[];
    cuentas: string[];
  }[],
): FuentesBanco {
  if (!empresas.length) return { tenencias, otras, cuentas };
  return {
    tenencias: [...tenencias, ...empresas.flatMap((e) => e.tenencias)],
    otras: [...otras, ...empresas.flatMap((e) => e.otras)],
    cuentas: [...new Set([...cuentas, ...empresas.flatMap((e) => e.cuentas)])],
  };
}
