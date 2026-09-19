import { describe, expect, test } from "bun:test";
import type { EntidadM, MesM } from "../src/datos/contrato";
import type { AccionElegida, PropuestaGuardada } from "../src/datos/propuestas";
import {
  validarAccion,
  validarPropuesta,
  valorSerieEn,
} from "../src/datos/seguimiento";

const accion = (extra: Partial<AccionElegida> = {}): AccionElegida => ({
  id: "collections-collect_earlier",
  pillar: "collections",
  title: "Cobrar 4 días antes",
  uplift_tenths: 118,
  new_score_tenths: 620,
  current: 19,
  target: 15,
  unit: "días",
  ...extra,
});

describe("validarAccion", () => {
  test("cumplida si el insumo llegó al objetivo", () => {
    expect(validarAccion(accion(), 19, 15).estado).toBe("cumplida");
    expect(validarAccion(accion(), 19, 14.6).estado).toBe("cumplida");
  });

  test("en camino si avanzó al menos la mitad de la brecha", () => {
    // brecha 19→15; a 17 queda la mitad exacta, a 16 más
    expect(validarAccion(accion(), 19, 17).estado).toBe("en camino");
    expect(validarAccion(accion(), 19, 16).estado).toBe("en camino");
  });

  test("pendiente si no avanzó o se alejó", () => {
    expect(validarAccion(accion(), 19, 19).estado).toBe("pendiente");
    expect(validarAccion(accion(), 19, 20).estado).toBe("pendiente");
  });

  test("sin datos si falta el insumo", () => {
    expect(validarAccion(accion(), null, 15).estado).toBe("sin datos");
    expect(validarAccion(accion({ current: null }), 19, 15).estado).toBe(
      "sin datos",
    );
  });

  test("el objetivo puede ir hacia arriba (más ingresos)", () => {
    const a = accion({ unit: "ratio", current: 1.2, target: 1.4 });
    expect(validarAccion(a, 1.2, 1.4).estado).toBe("cumplida");
    expect(validarAccion(a, 1.2, 1.1).estado).toBe("pendiente");
    expect(validarAccion(a, 1.2, 1.3).estado).toBe("en camino");
  });
});

describe("valorSerieEn", () => {
  const meses = ["2026-03", "2026-04", "2026-05", "2026-06"];
  const ent = {
    months: meses.map((month) => ({ month })),
    series: [{ key: "ar_days_beyond_terms", values: [10, 12, 14, 16] }],
  } as unknown as EntidadM;

  test("las series van alineadas por el final con los meses", () => {
    // la serie trae solo los últimos 2 meses (mayo, junio)
    const corta = {
      months: meses.map((month) => ({ month })),
      series: [{ key: "ar_days_beyond_terms", values: [14, 16] }],
    } as unknown as EntidadM;
    expect(valorSerieEn(ent, "ar_days_beyond_terms", "2026-06")).toBe(16);
    expect(valorSerieEn(corta, "ar_days_beyond_terms", "2026-05")).toBe(14);
    expect(valorSerieEn(corta, "ar_days_beyond_terms", "2026-03")).toBeNull();
  });

  test("mes o serie inexistentes dan null", () => {
    expect(valorSerieEn(ent, "ar_days_beyond_terms", "2025-01")).toBeNull();
    expect(valorSerieEn(ent, "buffer_days", "2026-06")).toBeNull();
  });
});

describe("validarPropuesta", () => {
  const ent = {
    months: ["2026-07", "2026-08"].map((month) => ({ month })),
    series: [{ key: "ar_days_beyond_terms", values: [19, 15] }],
  } as unknown as EntidadM;
  const mesActual = { month: "2026-08", shown: 640 } as unknown as MesM;
  const p = {
    id: "x",
    fecha: "2026-08-01T10:00:00Z",
    kind: "company",
    entidad: "COMP_0001",
    grupoId: "G",
    corte: "2026-07",
    bundle_id: "b",
    score_actual_tenths: 610,
    acciones: [accion()],
    financiacion: [],
  } as PropuestaGuardada;

  test("con meses posteriores juzga cada acción y el score", () => {
    const seg = validarPropuesta(p, ent, mesActual);
    expect(seg.conMeses).toBe(true);
    expect(seg.scoreAhora).toBe(640);
    expect(seg.acciones[0].estado).toBe("cumplida");
    expect(seg.acciones[0].antes).toBe(19);
    expect(seg.acciones[0].ahora).toBe(15);
  });

  test("sin meses posteriores no hay juicio", () => {
    const mismoCorte = validarPropuesta(
      { ...p, corte: "2026-08" },
      ent,
      mesActual,
    );
    expect(mismoCorte.conMeses).toBe(false);
    expect(mismoCorte.acciones).toEqual([]);
  });
});
