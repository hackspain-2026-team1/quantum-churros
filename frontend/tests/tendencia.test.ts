import { describe, expect, test } from "bun:test";
import { pendienteTheilSen, tendencia } from "../src/datos/derivados";
import type { Grupo } from "../src/datos/modelo";

/** Serie en décimas que sube `paso` décimas (paso/10 puntos) cada mes. */
const serieLineal = (n: number, paso = 10) => Array.from({ length: n }, (_, i) => 100 + i * paso);

describe("pendienteTheilSen", () => {
  test("una serie lineal de 1 punto por mes da exactamente 1", () => {
    expect(pendienteTheilSen(serieLineal(12), 11)).toBe(1);
  });

  test("un bache de un mes no arrastra la mediana", () => {
    const s = serieLineal(10);
    s[3] = 900;
    expect(pendienteTheilSen(s, 9)).toBe(1);
  });

  test("con menos de seis meses medibles se calla", () => {
    expect(pendienteTheilSen(serieLineal(5), 4)).toBeNull();
  });

  test("solo mira la ventana hacia atrás desde el corte", () => {
    const s = Array.from({ length: 30 }, (_, i) => (i < 18 ? 100 + i * 50 : 1000));
    // En los últimos doce meses la serie es plana; la historia anterior no cuenta.
    expect(pendienteTheilSen(s, 29)).toBe(0);
  });

  test("los meses sin dato se saltan, no se inventan", () => {
    const s = serieLineal(12);
    s[2] = null;
    s[5] = null;
    expect(pendienteTheilSen(s, 11)).toBe(1);
  });

  test("no mira el futuro: lo que hay después del corte no entra", () => {
    const s = [...serieLineal(12), 9000];
    expect(pendienteTheilSen(s, 11)).toBe(1);
  });

  test("una ventana corta explícita acota los meses que entran", () => {
    const s = serieLineal(12);
    expect(pendienteTheilSen(s, 11, 6)).toBe(1);
  });
});

describe("tendencia", () => {
  const grupo = (meses: (number | null)[], first_month: number): Grupo =>
    ({
      id: "g1",
      n_companies: 1,
      first_month,
      country: null,
      size_band: null,
      industry: null,
      meses: meses.map((shown) => ({ shown, band: null, direction: null, nature: null, conf: null, abstained: null, perimeter_changed: null, base: 0, pillars: [], penalty: 0, cap: 0 })),
      companies: [],
      alerts: [],
    }) as unknown as Grupo;

  test("respeta el primer mes con score de la entidad", () => {
    const g = grupo(serieLineal(12), 6);
    // Del mes 6 al 11 hay seis meses medibles y la pendiente sigue siendo 1.
    expect(tendencia(g, 11)).toBe(1);
  });

  test("devuelve null con historia corta aunque la ventana pida doce", () => {
    const g = grupo(serieLineal(3), 0);
    expect(tendencia(g, 2)).toBeNull();
  });
});
