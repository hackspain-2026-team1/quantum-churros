// Ofertas de financiación por banco: un ranking determinista de los bancos con
// los que la organización ya trabaja, para que el usuario de Embat elija a quién
// proponerle cada instrumento. Entran todos los bancos conectados: si ya
// financian, se usa su tipo cuando consta; si solo tienen cuentas, la tasa es
// la estimación de mercado marcada. El motor solo aporta el instrumento y el monto.

import type {
  FinanciacionM,
  OtraDeudaM,
  ProductoId,
  TenenciaM,
} from "./contrato";
import { producto } from "./productos";
import { tasaPara, type FuenteTasa } from "./tasas";

export interface OfertaBanco {
  bank: string;
  /** true si el banco ya le da a la entidad un producto de este tipo. */
  tieneProducto: boolean;
  /** Tasa anual en % cuando el dato existe (productos de calendario); si no, null. */
  rate: number | null;
  rate_type: string | null;
  granted: number | null;
  outstanding: number | null;
  /** La tasa de la oferta: la real del banco, o la estimación de mercado marcada. */
  oferta_tasa: number | null;
  oferta_fuente: FuenteTasa | null;
  /** true si solo constan cuentas (depósitos, ahorro) y ningún crédito. */
  soloCuentas: boolean;
}

export interface FuentesBanco {
  tenencias: TenenciaM[];
  otras: OtraDeudaM[];
  /** Los bancos donde constan productos de banco (cuentas, tarjetas…): banco → cuántos. */
  bancos: Record<string, number>;
}

const PRODUCTO_POR_KIND: Partial<Record<FinanciacionM["kind"], ProductoId>> = {
  factoring: "factoring",
  confirming: "confirming",
  line: "linea_credito",
};
/** El instrumento «reestructuración» equivale a un préstamo (loan) entre las otras deudas. */
const ES_PRESTAMO = /loan|préstamo/i;

/** Los productos de crédito: lo que convierte a un banco en un prestamista con evidencia. */
const PRODUCTOS_DE_CREDITO: Set<ProductoId> = new Set([
  "factoring",
  "confirming",
  "linea_credito",
]);

function bancoDe(bank: string | null): string | null {
  return bank && bank.trim() ? bank.trim() : null;
}

/** Los bancos que consta que financian a la entidad: tienen un producto de crédito contratado. */
function bancosPrestamistas(fuentes: FuentesBanco): Set<string> {
  const prestamistas = new Set<string>();
  for (const tenencia of fuentes.tenencias)
    if (PRODUCTOS_DE_CREDITO.has(tenencia.product))
      for (const item of tenencia.items) {
        const b = bancoDe(item.bank);
        if (b) prestamistas.add(b);
      }
  for (const otra of fuentes.otras) {
    const b = bancoDe(otra.bank);
    if (b) prestamistas.add(b);
  }
  return prestamistas;
}

function vacia(bank: string): OfertaBanco {
  return {
    bank,
    tieneProducto: false,
    rate: null,
    rate_type: null,
    granted: null,
    outstanding: null,
    oferta_tasa: null,
    oferta_fuente: null,
    soloCuentas: true,
  };
}

function mejorTasa(
  actual: OfertaBanco,
  rate: number | null,
  granted: number | null,
): boolean {
  if (rate !== null && actual.rate === null) return true;
  if (rate !== null && actual.rate !== null && rate < actual.rate) return true;
  return (
    actual.rate === null &&
    rate === null &&
    (granted ?? 0) > (actual.granted ?? 0)
  );
}

/**
 * Los bancos a los que ofrecer el instrumento: todos los conectados, de mejor
 * a peor. Primero los que ya dan ese producto, después el resto de
 * prestamistas, al final los que solo tienen cuentas (con estimación de
 * mercado). Determinista: empates por nombre.
 */
export function ofertasBanco(
  kind: FinanciacionM["kind"],
  fuentes: FuentesBanco,
): OfertaBanco[] {
  const producto = PRODUCTO_POR_KIND[kind];
  const prestamistas = bancosPrestamistas(fuentes);
  const porBanco = new Map<string, OfertaBanco>();
  const visto = (bank: string): OfertaBanco => {
    if (!porBanco.has(bank)) porBanco.set(bank, vacia(bank));
    return porBanco.get(bank)!;
  };

  for (const nombre of Object.keys(fuentes.bancos)) {
    const b = bancoDe(nombre);
    if (b) visto(b);
  }
  for (const tenencia of fuentes.tenencias) {
    const es = tenencia.product === producto;
    const credito = PRODUCTOS_DE_CREDITO.has(tenencia.product);
    for (const item of tenencia.items) {
      const b = bancoDe(item.bank);
      if (!b) continue;
      const o = visto(b);
      if (credito) o.soloCuentas = false;
      if (
        es &&
        mejorTasa(o, item.rate, item.granted)
      ) {
        o.tieneProducto = true;
        o.soloCuentas = false;
        o.rate = item.rate;
        o.rate_type = item.rate_type;
        o.granted = item.granted;
        o.outstanding = item.outstanding;
      }
    }
  }
  for (const otra of fuentes.otras) {
    const b = bancoDe(otra.bank);
    if (!b) continue;
    const o = visto(b);
    o.soloCuentas = false;
    if (
      kind === "restructure" &&
      ES_PRESTAMO.test(`${otra.type} ${otra.type_label}`) &&
      mejorTasa(o, otra.rate, otra.granted)
    ) {
      o.tieneProducto = true;
      o.rate = otra.rate;
      o.rate_type = otra.rate_type;
      o.granted = otra.granted;
      o.outstanding = otra.outstanding;
    }
  }
  for (const bank of prestamistas) visto(bank).soloCuentas = false;

  return [...porBanco.values()]
    .map((o) => {
      const oferta = tasaPara(kind, o.rate, o.rate_type);
      return {
        ...o,
        oferta_tasa: oferta?.tasa ?? null,
        oferta_fuente: oferta?.fuente ?? null,
      };
    })
    .sort((a, b) => {
      if (a.tieneProducto !== b.tieneProducto) return a.tieneProducto ? -1 : 1;
      if (a.soloCuentas !== b.soloCuentas) return a.soloCuentas ? 1 : -1;
      const pesoFuente = (o: OfertaBanco) =>
        o.oferta_fuente === "banco" ? 0 : o.oferta_fuente === "mercado" ? 1 : 2;
      if (pesoFuente(a) !== pesoFuente(b)) return pesoFuente(a) - pesoFuente(b);
      if ((a.oferta_tasa ?? 1e9) !== (b.oferta_tasa ?? 1e9))
        return (a.oferta_tasa ?? 1e9) - (b.oferta_tasa ?? 1e9);
      if ((b.granted ?? 0) !== (a.granted ?? 0))
        return (b.granted ?? 0) - (a.granted ?? 0);
      return a.bank.localeCompare(b.bank, "es");
    });
}

/** Los bancos de la entidad con lo que tiene en cada uno: para «Tus bancos conectados». */
export interface BancoConectado {
  bank: string;
  /** Cuántos productos de banco (cuentas, tarjetas…) tiene ahí. */
  cuentas: number;
  /** true si consta que el banco ya financia a la entidad (un producto de crédito). */
  otorga: boolean;
  productos: {
    producto: string;
    granted: number | null;
    rate: number | null;
    rate_type: string | null;
    /** true si es un producto de crédito (no una cuenta). */
    credito: boolean;
  }[];
}

export function bancosConectados(fuentes: FuentesBanco): BancoConectado[] {
  const porBanco = new Map<string, BancoConectado>();
  const visto = (bank: string): BancoConectado => {
    if (!porBanco.has(bank))
      porBanco.set(bank, { bank, cuentas: 0, otorga: false, productos: [] });
    return porBanco.get(bank)!;
  };
  for (const [banco, n] of Object.entries(fuentes.bancos)) {
    if (!banco.trim()) continue;
    visto(banco.trim()).cuentas += n;
  }
  for (const t of fuentes.tenencias) {
    const credito = PRODUCTOS_DE_CREDITO.has(t.product);
    for (const item of t.items) {
      const b = item.bank?.trim();
      if (!b) continue;
      const banco = visto(b);
      banco.productos.push({
        producto: producto(t.product).nombre,
        granted: item.granted,
        rate: item.rate,
        rate_type: item.rate_type,
        credito,
      });
      if (credito) banco.otorga = true;
    }
  }
  for (const o of fuentes.otras) {
    const b = o.bank?.trim();
    if (!b) continue;
    const banco = visto(b);
    banco.productos.push({
      producto: o.type_label,
      granted: o.granted,
      rate: o.rate,
      rate_type: o.rate_type,
      credito: true,
    });
    banco.otorga = true;
  }
  return [...porBanco.values()].sort((a, b) => {
    const peso = (x: BancoConectado) =>
      (x.otorga ? 2 : 0) + Math.min(x.cuentas, 9);
    if (peso(a) !== peso(b)) return peso(b) - peso(a);
    return a.bank.localeCompare(b.bank, "es");
  });
}

/** Las fuentes de la ficha de una entidad (empresa: las suyas; grupo: las de sus empresas). */
export function fuentesDe(
  tenencias: TenenciaM[],
  otras: OtraDeudaM[],
  bancos: Record<string, number>,
  empresas: {
    tenencias: TenenciaM[];
    otras: OtraDeudaM[];
    bancos: Record<string, number>;
  }[],
): FuentesBanco {
  if (!empresas.length) return { tenencias, otras, bancos };
  const juntos: Record<string, number> = { ...bancos };
  for (const e of empresas)
    for (const [banco, n] of Object.entries(e.bancos))
      juntos[banco] = (juntos[banco] ?? 0) + n;
  return {
    tenencias: [...tenencias, ...empresas.flatMap((e) => e.tenencias)],
    otras: [...otras, ...empresas.flatMap((e) => e.otras)],
    bancos: juntos,
  };
}
