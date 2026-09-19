import { describe, expect, test } from "bun:test";
import {
  correoPropuesta,
  instrumentosDelMes,
  type PropuestaGuardada,
} from "../src/datos/propuestas";
import type { FinanciacionM } from "../src/datos/contrato";

const p: PropuestaGuardada = {
  id: "20260919-1200-abcd",
  fecha: "2026-09-19T10:00:00.000Z",
  kind: "company",
  entidad: "COMP_0087",
  grupoId: "GROUP_0010",
  corte: "2026-08",
  bundle_id: "aabbccddeeff001122334455",
  score_actual_tenths: 280,
  acciones: [
    {
      id: "a1",
      pillar: "collections",
      title: "Cobrar 4 días antes",
      uplift_tenths: 27,
      new_score_tenths: 307,
    },
  ],
  financiacion: [
    {
      id: "f1",
      kind: "factoring",
      title: "Anticipar facturas",
      amount: 160_000,
      uplift_tenths: 115,
      bank: "Santander",
      rate: 6,
      rate_type: "variable",
      rate_fuente: "mercado",
    },
  ],
};

describe("correoPropuesta", () => {
  test("el asunto y el cuerpo usan el formato de Rumbo", () => {
    const { asunto, cuerpo } = correoPropuesta(p);
    expect(asunto).toBe("Embat · Plan para Empresa 87 (agosto de 2026)");
    expect(cuerpo).toContain("Plan de mejora de Empresa 87");
    expect(cuerpo).toContain("Score actual: 28.");
    expect(cuerpo).toContain("Cobrar 4 días antes (+2,7 puntos según el motor)");
    expect(cuerpo).toContain("por 160.000");
    expect(cuerpo).toContain("variable (estimación de mercado)");
    expect(cuerpo).toContain("19/09/2026");
    expect(cuerpo).not.toContain("COMP_0087");
  });
});

const confirming = (over: Partial<FinanciacionM> = {}): FinanciacionM => ({
  id: "confirming",
  kind: "confirming",
  title: "Financia pagos",
  detail: "detalle confirming",
  amount: 100,
  uplift_tenths: 10,
  new_score_tenths: 300,
  ...over,
});

const factoring = (over: Partial<FinanciacionM> = {}): FinanciacionM => ({
  id: "factoring",
  kind: "factoring",
  title: "Anticipa facturas",
  detail: "detalle factoring",
  amount: 50,
  uplift_tenths: 8,
  new_score_tenths: 280,
  ...over,
});

describe("instrumentosDelMes", () => {
  test("si el motor propone en la entidad, no mira las empresas", () => {
    const propios = [confirming()];
    const out = instrumentosDelMes(propios, [[factoring()]]);
    expect(out).toEqual(propios);
  });

  test("si el grupo viene vacío, junta las de las empresas por tipo", () => {
    const out = instrumentosDelMes([], [
      [confirming({ amount: 100, uplift_tenths: 10 })],
      [confirming({ amount: 40, uplift_tenths: 30, title: "mejor" }), factoring()],
    ]);
    expect(out.map((x) => x.kind)).toEqual(["confirming", "factoring"]);
    expect(out[0].title).toBe("mejor");
    expect(out[0].amount).toBe(140);
    expect(out[0].uplift_tenths).toBe(30);
    expect(out[0].detail).toContain("2 empresas");
    expect(out[1].amount).toBe(50);
    expect(out[1].detail).toContain("una empresa");
  });

  test("sin propios y sin empresas no inventa instrumentos", () => {
    expect(instrumentosDelMes([], [undefined, []])).toEqual([]);
    expect(instrumentosDelMes(undefined, [])).toEqual([]);
  });
});
