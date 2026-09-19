import { describe, expect, test } from "bun:test";
import {
  bancosConectados,
  fuentesDe,
  ofertasBanco,
  type FuentesBanco,
} from "../src/datos/ofertas";
import type {
  ItemProductoM,
  OtraDeudaM,
  TenenciaM,
} from "../src/datos/contrato";

function item(bank: string, extra: Partial<ItemProductoM> = {}): ItemProductoM {
  return {
    bank,
    label: null,
    granted: null,
    outstanding: null,
    available: null,
    usage: null,
    since: null,
    rate: null,
    rate_type: null,
    ...extra,
  };
}
function tenencia(
  product: TenenciaM["product"],
  items: ItemProductoM[],
): TenenciaM {
  return { product, source: "declarado", items, evidence: [] };
}
function otra(bank: string, extra: Partial<OtraDeudaM> = {}): OtraDeudaM {
  return {
    type: "loan",
    type_label: "Préstamo",
    bank,
    label: null,
    granted: null,
    outstanding: null,
    rate: null,
    rate_type: null,
    periods: null,
    next_payment: null,
    since: null,
    ...extra,
  };
}

const fuentes = (extra: Partial<FuentesBanco> = {}): FuentesBanco => ({
  tenencias: [
    tenencia("factoring", [
      item("Banco A"),
      item("Banco B", { granted: 500_000 }),
    ]),
    tenencia("linea_credito", [item("Banco C", { granted: 1_000_000 })]),
  ],
  otras: [otra("Banco D", { rate: 3.5, rate_type: "fixed" }), otra("Banco B")],
  bancos: { "Banco E": 2, "Banco A": 4 },
  ...extra,
});

describe("ofertasBanco", () => {
  test("primero los bancos que ya dan el producto, después el resto", () => {
    const ofertas = ofertasBanco("factoring", fuentes());
    expect(ofertas.map((o) => o.bank)).toEqual([
      "Banco B",
      "Banco A",
      "Banco C",
      "Banco D",
    ]);
    expect(ofertas[0].tieneProducto).toBe(true);
    expect(ofertas[2].tieneProducto).toBe(false);
  });

  test("un banco que solo guarda cuentas no se ofrece como prestamista", () => {
    const ofertas = ofertasBanco("factoring", fuentes());
    expect(ofertas.map((o) => o.bank)).not.toContain("Banco E");
    // solo cuentas y ningún crédito: no hay a quién ofrecer
    expect(
      ofertasBanco("line", {
        tenencias: [],
        otras: [],
        bancos: { "Banco Solo": 3 },
      }),
    ).toEqual([]);
  });

  test("a igual producto, ordena por tasa creciente cuando consta", () => {
    const f = fuentes({
      tenencias: [
        tenencia("factoring", [
          item("Alto", { rate: 5 }),
          item("Bajo", { rate: 2.5 }),
        ]),
      ],
      otras: [],
      bancos: {},
    });
    expect(ofertasBanco("factoring", f).map((o) => o.bank)).toEqual([
      "Bajo",
      "Alto",
    ]);
  });

  test("sin tasas, por concedido decreciente y empates por nombre", () => {
    const f = fuentes({
      tenencias: [
        tenencia("factoring", [
          item("Chico", { granted: 100 }),
          item("Grande", { granted: 900 }),
        ]),
      ],
      otras: [],
      bancos: { Zeta: 1 },
    });
    expect(ofertasBanco("factoring", f).map((o) => o.bank)).toEqual([
      "Grande",
      "Chico",
    ]);
  });

  test("reestructuración equipara a los préstamos de otras deudas", () => {
    const f = fuentes({
      tenencias: [],
      otras: [otra("Prestamista", { rate: 7 }), otra("SoloCuenta")],
      bancos: {},
    });
    const ofertas = ofertasBanco("restructure", f);
    expect(ofertas[0].bank).toBe("Prestamista");
    expect(ofertas[0].tieneProducto).toBe(true);
    expect(ofertas[0].rate).toBe(7);
  });

  test("determinista ante los mismos datos", () => {
    expect(ofertasBanco("line", fuentes())).toEqual(
      ofertasBanco("line", fuentes()),
    );
  });
});

describe("bancosConectados", () => {
  test("cuentas por banco y el sello de quién financia", () => {
    const conectados = bancosConectados(fuentes());
    const porNombre = Object.fromEntries(conectados.map((b) => [b.bank, b]));
    expect(porNombre["Banco A"].cuentas).toBe(4);
    expect(porNombre["Banco A"].otorga).toBe(true); // factoring
    expect(porNombre["Banco E"].cuentas).toBe(2);
    expect(porNombre["Banco E"].otorga).toBe(false); // solo cuentas
    expect(porNombre["Banco E"].productos).toEqual([]);
    // los que financian van primero
    expect(conectados[0].otorga).toBe(true);
  });
});

describe("fuentesDe", () => {
  test("para un grupo junta los bancos de sus empresas", () => {
    const juntas = fuentesDe(
      [tenencia("confirming", [item("Matriz Banco")])],
      [],
      { "Matriz Cuenta": 1 },
      [
        {
          tenencias: [tenencia("linea_credito", [item("Filial Banco")])],
          otras: [],
          bancos: { "Filial Cuenta": 2 },
        },
      ],
    );
    expect(juntas.tenencias.length).toBe(2);
    expect(juntas.bancos).toEqual({ "Matriz Cuenta": 1, "Filial Cuenta": 2 });
  });
});
