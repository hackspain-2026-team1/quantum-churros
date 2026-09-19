import { describe, expect, test } from "bun:test";
import { ESTIMACIONES, fuenteTexto, tasaPara } from "../src/datos/tasas";

describe("tasas", () => {
  test("usa la tasa real del banco cuando consta", () => {
    expect(tasaPara("restructure", 3.2, "fixed")).toEqual({
      tasa: 3.2,
      fuente: "banco",
    });
  });
  test("sin dato real, usa la estimación de mercado marcada", () => {
    const oferta = tasaPara("factoring", null, null);
    expect(oferta).toEqual({ tasa: ESTIMACIONES.factoring, fuente: "mercado" });
  });
  test("el barrido intragrupo no tiene tasa", () => {
    expect(tasaPara("sweep", null, null)).toBeNull();
  });
  test("la fuente se cuenta en palabras", () => {
    expect(fuenteTexto("banco")).toBe("tasa del banco");
    expect(fuenteTexto("mercado")).toBe("estimación de mercado");
  });
});
