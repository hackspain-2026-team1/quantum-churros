import { describe, expect, test } from "bun:test";
import { f } from "../src/datos/formato";

describe("f.fecha", () => {
  test("escribe el día en es-ES sin correrlo por UTC", () => {
    expect(f.fecha("2026-06-30")).toBe("30/06/2026");
    expect(f.fecha("2026-01-02T23:00:00.000Z")).toBe("02/01/2026");
  });
});

describe("f.contraparte", () => {
  test("humaniza el identificador del dataset", () => {
    expect(f.contraparte("COUNTERPARTY_519009")).toBe("Contraparte 519009");
    expect(f.contraparte(null)).toBe("—");
  });
});

describe("f.empresa y f.grupo", () => {
  test("quitan el prefijo y el cero a la izquierda", () => {
    expect(f.empresa("COMPANY_06666")).toBe("Empresa 6666");
    expect(f.empresa("COMP_0087")).toBe("Empresa 87");
    expect(f.grupo("GROUP_0153")).toBe("Grupo 153");
  });
});
