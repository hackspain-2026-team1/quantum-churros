// La ficha de una entidad (empresa u organización) con sus cuatro secciones (propuesta 06, §3–4):
//   I   Scoring y tendencia: lo observado y lo previsto en una sola línea de tiempo.
//   II  Productos: lo que tiene contratado y lo que le encajaría.
//   III Acciones: avisos, recomendaciones del motor y el horizonte de cada una.
//   IV  Técnico: la trazabilidad completa (ver tecnico.ts).
// Todo sale de los ficheros: el bundle del motor, products/, horizons/ y params.json.

import { TONO } from "../arena/arena";
import type { Futuro, PlacaSerie } from "../arena/placas";
import { carga } from "../datos/carga";
import type {
  AccionM,
  AlertaM,
  EmpresaM,
  EmpresaResumenM,
  EscenarioM,
  EvidenciaM,
  GrupoM,
  HorizonteM,
  Manifiesto,
  MesM,
  ParametrosM,
  ProductosEmpresaM,
  ProductosGrupoM,
  TenenciaM,
} from "../datos/contrato";
import {
  estadosProductos,
  recomendaciones,
  type EstadoProducto,
} from "../datos/encaje";
import { f, primeraMayuscula } from "../datos/formato";
import { senalMonitor } from "../datos/monitor";
import { FAMILIAS, PRODUCTOS, producto } from "../datos/productos";
import {
  ESFUERZO,
  ESTADO_AVISO,
  explicacionAccion,
  lineaAvisoM,
  movimiento,
  nombreBanda,
  nombrePilar,
  tituloAccion,
} from "../datos/redaccion";
import type { Seccion } from "../estado";
import { h, vaciar } from "./dom";
import { iconoProducto } from "./iconos";
import {
  asiento,
  cifraC,
  hilo,
  lineaEstado,
  llamadas,
  marcaBanco,
  seccion,
  sello,
  type Nudo,
} from "./primitivos";
import { placa } from "./registro";
import { seccionTecnica } from "./tecnico";
import { abrirPropuesta } from "./propuesta";
import { triaje } from "./triaje";

/** Filtro con el que se abre la evidencia desde un nudo del hilo. */
export interface FiltroEvidencia {
  pilar?: string | null;
  fichero?: string;
  texto?: string;
}

export interface EmpresaDeGrupo {
  res: EmpresaResumenM;
  ent: EmpresaM | null;
  prod: ProductosEmpresaM | null;
}

export interface DatosFicha {
  kind: "company" | "group";
  id: string;
  grupoId: string;
  ent: EmpresaM | GrupoM;
  corte: string;
  mes: MesM | null;
  man: Manifiesto;
  params: ParametrosM | null;
  evid: EvidenciaM | null;
  prodE: ProductosEmpresaM | null;
  prodG: ProductosGrupoM | null;
  hor: HorizonteM | null;
  /** Score del grupo en el corte (para situar a la empresa). */
  grupoMes: MesM | null;
  empresas: EmpresaDeGrupo[];
  /** Organizaciones del mismo tamaño en el corte (portfolio.json): mediana y cuántas. */
  pares?: { mediana: number; n: number; tamano: string } | null;
}

export async function cargarFicha(
  kind: "company" | "group",
  id: string,
  grupoId: string,
  corte: string,
  man: Manifiesto,
): Promise<DatosFicha | null> {
  const ent =
    kind === "company" ? await carga.empresa(id) : await carga.grupo(id);
  if (!ent) return null;
  const [params, evid, hor, grupo] = await Promise.all([
    carga.parametros(),
    carga.evidencia(id),
    carga.horizonte(id),
    kind === "company" ? carga.grupo(grupoId) : Promise.resolve(ent as GrupoM),
  ]);
  const prodE = kind === "company" ? await carga.productosEmpresa(id) : null;
  const prodG = await carga.productosGrupo(grupoId);
  let empresas: EmpresaDeGrupo[] = [];
  if (kind === "group") {
    const g = ent as GrupoM;
    empresas = await Promise.all(
      g.companies.map(async (res) => ({
        res,
        ent: await carga.empresa(res.id),
        prod: await carga.productosEmpresa(res.id),
      })),
    );
  }
  return {
    kind,
    id,
    grupoId,
    ent,
    corte,
    man,
    params,
    evid,
    hor,
    prodE,
    prodG,
    empresas,
    mes: ent.months.find((m) => m.month === corte) ?? null,
    grupoMes: (grupo as GrupoM).months.find((m) => m.month === corte) ?? null,
  };
}

// ─── Nombres ─────────────────────────────────────────────────
export const nombreEntidad = (kind: "company" | "group", id: string) =>
  kind === "company" ? f.empresa(id) : f.grupo(id);
const atributo = (d: DatosFicha, k: string) =>
  d.ent.profile.find((a) => a.key === k)?.value ?? null;

/** La sombra de productos de una empresa: sus tenencias. */
const tenenciaDe = (d: DatosFicha): TenenciaM[] => d.prodE?.held ?? [];

function estados(d: DatosFicha): EstadoProducto[] {
  if (!d.mes) return [];
  const papel = d.kind === "company" ? (d.ent as EmpresaM).role : null;
  const tenencia: TenenciaM[] =
    d.kind === "company"
      ? tenenciaDe(d)
      : PRODUCTOS.filter((p) => (d.prodG?.counts[p.id] ?? 0) > 0).map(
          (p) =>
            ({
              product: p.id,
              source: "declarado",
              items: [],
              evidence: [],
            }) as TenenciaM,
        );
  return estadosProductos({
    mes: d.mes,
    man: d.man,
    tenencia,
    perfil: d.ent.profile,
    papel,
    heredaLiquidez:
      d.kind === "company" ? (d.ent as EmpresaM).inherits_liquidity : false,
  });
}

// ─── Cabecera ─────────────────────────────────────────────────

export interface Acciones {
  abrirEmpresa(id: string): void;
  abrirGrupo(id: string): void;
  irSeccion(s: Seccion, accion?: string, filtro?: FiltroEvidencia): void;
  irBandeja(): void;
  repintarArena(): void;
}

export function cabecera(
  d: DatosFicha,
  movil: boolean,
  acc: Acciones,
): HTMLElement {
  const nombre = nombreEntidad(d.kind, d.id);
  const numero = h("div", {
    class: "cab-numeral",
    "aria-label": d.mes ? `Score ${f.score(d.mes.shown)}` : "Sin score",
  });
  if (d.mes)
    placa(numero, (c) => ({
      tipo: "numeral",
      x: c.x - 2,
      y: c.y,
      h: c.h,
      texto: f.score(d.mes!.shown),
    }));
  const sub: string[] = [];
  if (d.kind === "company") {
    const e = d.ent as EmpresaM;
    sub.push(`${e.role} · ${f.grupo(d.grupoId)}`);
  } else
    sub.push(
      `${f.plural((d.ent as GrupoM).companies.length, "empresa", "empresas")}`,
    );
  const pais = atributo(d, "country");
  if (pais) sub.push(pais.replace(/\s*\([A-Z]{2}\)/, ""));
  const sector = d.ent.context.industry?.label;
  if (sector) sub.push(sector);
  const tes = atributo(d, "treasury_structure");
  if (tes) sub.push(`tesorería ${tes.charAt(0).toLowerCase()}${tes.slice(1)}`);
  sub.push(`con datos desde ${f.mes(d.ent.first_month)}`);
  const cab = h(
    "header",
    { class: "ficha-cab" },
    numero,
    h(
      "div",
      { class: "cab-texto" },
      h("h1", {}, nombre),
      h("p", { class: "cab-sub" }, sub.join(" · ")),
      d.mes
        ? lineaEstado(d.man, d.mes, notaConflicto(d))
        : h("p", { class: "cab-vacio" }, `Sin datos en ${f.mes(d.corte)}.`),
      d.mes ? h("p", { class: "cab-explica" }, explicacion(d)) : null,
      d.kind === "group"
        ? h(
            "p",
            { class: "cab-aviso" },
            "El score del grupo se calcula sumando los flujos de todas sus empresas; no es la media de sus scores.",
          )
        : null,
    ),
    monitorProactivo(d, acc),
  );
  void movil;
  return cab;
}

function monitorProactivo(d: DatosFicha, acc: Acciones): HTMLElement | null {
  const s = senalMonitor(d.mes, d.ent.alerts, d.id);
  if (!s || !d.mes) return null;
  const mejora = s.direccion === "improving";
  const movimiento = mejora ? "mejora estructural" : "deterioro estructural";
  const titulo =
    s.fase === "nueva"
      ? `Alerta nueva: ${movimiento}`
      : s.fase === "activa"
        ? `Señal activa: ${movimiento}`
        : s.fase === "pausa"
          ? `Aviso en pausa: ${movimiento}`
          : `Movimiento ${mejora ? "positivo" : "negativo"} en observación`;
  const texto =
    s.fase === "nueva" && s.alerta
      ? s.alerta.detail
      : s.fase === "activa"
        ? `El cambio sigue presente desde ${f.mes(s.desde ?? d.corte)} y acumula ${f.plural(d.mes.verdict.persistence_months, "cierre", "cierres")} de persistencia.`
        : s.fase === "pausa"
          ? "El motor reconoce el cambio, pero el aviso está silenciado o en abstención."
          : "Todavía no hay evidencia suficiente para tratar el movimiento como estructural ni avisar por correo.";
  const boton = s.alerta
    ? h("button", { type: "button", class: "as-enlace" }, "Abrir en la bandeja")
    : null;
  boton?.addEventListener("click", () => acc.irBandeja());
  return h(
    "aside",
    {
      class: `monitor ${mejora ? "sube" : "baja"} fase-${s.fase}`,
      "data-monitor-phase": s.fase,
      "aria-live": s.fase === "nueva" ? "polite" : "off",
    },
    h("b", {}, titulo),
    h("p", {}, texto),
    boton,
  );
}

/** La frase del motor cuando la deriva de 12 meses y el horizonte corto se contradicen. */
function notaConflicto(d: DatosFicha): string | null {
  const m = d.evid?.months.find((x) => x.month === d.corte);
  return (
    m?.rows.find(
      (r) => r.pillar === null && r.value === "pendiente de confirmar",
    )?.label ?? null
  );
}

function explicacion(d: DatosFicha): string {
  const m = d.mes!;
  const nombre = nombreEntidad(d.kind, d.id);
  const partes = [
    `${nombre} está en ${nombreBanda(d.man, m.band).toLowerCase()} con ${f.score(m.shown)} puntos.`,
  ];
  const peor = [...m.pillars]
    .filter((p) => p.score !== null)
    .sort((a, b) => a.contrib - b.contrib)[0];
  if (peor && peor.contrib < 0)
    partes.push(
      `Lo que más resta: ${nombrePilar(d.man, peor.key).toLowerCase()} (${f.delta(peor.contrib)}).`,
    );
  if (m.abstain)
    partes.push(
      `El motor se abstiene: ${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason}`,
    );
  else if (m.verdict.nature === "shock_pending")
    partes.push("Se ha movido de golpe y falta confirmar si es un bache.");
  else if (m.verdict.nature === "bump")
    partes.push("El golpe se ha revertido: fue un bache.");
  if (d.pares) {
    // «Pequeña (2-10 M€)» → «pequeñas, de 2 a 10 M€»: sin paréntesis dentro de paréntesis.
    const m = d.pares.tamano.match(/^(\S+)\s*\((.*)\)$/);
    const tramo = m
      ? m[2]
          .replace(/^(\d+)-(\d+)/, "de $1 a $2")
          .replace(/^< /, "menos de ")
          .replace(/^≥ /, "desde ")
      : null;
    const nombre = (m ? m[1] : d.pares.tamano).toLowerCase();
    partes.push(
      `Las ${f.numero(d.pares.n)} ${d.kind === "group" ? "organizaciones" : "empresas"} de su tamaño (${nombre}${tramo ? `, ${tramo}` : ""}) tienen una mediana de ${f.score(d.pares.mediana)}.`,
    );
  }
  if (d.kind === "company" && d.grupoMes) {
    const dif = m.shown - d.grupoMes.shown;
    partes.push(
      Math.abs(dif) < 20
        ? `Su grupo está en ${f.score(d.grupoMes.shown)}, casi igual.`
        : `Su grupo está en ${f.score(d.grupoMes.shown)}: ella ${dif < 0 ? "tira hacia abajo" : "está por encima"}.`,
    );
  }
  return partes.join(" ");
}

// ─── El gráfico de horizonte (I y III) ───────────────────────

export interface OpcionesGrafico {
  escenario: "base" | "drift" | "stress";
  acciones: Set<string>;
  metrica: string; // 'score' o la clave de una serie
  alto: number;
  grande?: boolean;
}

const NOMBRE_ESCENARIO = {
  base: "Si todo sigue igual",
  drift: "Si sigue la deriva",
  stress: "Si se repite su peor trimestre",
} as const;

export function graficoHorizonte(
  d: DatosFicha,
  o: OpcionesGrafico,
  empresasHilo = false,
): HTMLElement {
  const caja = h("div", {
    class: `grafico ${o.grande ? "grande" : ""}`,
    style: { height: `${o.alto}px` },
  });
  const meses = d.ent.months.filter((m) => m.month <= d.corte);
  const pasado = meses.slice(-24);
  const escenarios = d.hor?.scenarios;
  const conFuturo =
    o.metrica === "score" && !!escenarios && d.hor!.cut === d.corte;
  // Los escenarios mejor/común/peor que calcula el motor (bundle del mes del corte): abanico a t+horizonte.
  const abanico =
    o.metrica === "score" && d.mes?.outlook ? d.mes.outlook : null;
  const nF = conFuturo ? d.hor!.months.length : 0;
  const columnas =
    pasado.length + Math.max(nF, abanico ? abanico.horizon_months : 0);
  const hoy = pasado.length - 1;
  const col = (iso: string) => pasado.findIndex((m) => m.month === iso);

  let valores: [number, number | null, number?][];
  let unidad = "puntos";
  if (o.metrica === "score")
    valores = pasado.map((m, i) => [
      i,
      m.shown / 10,
      m.band === "critical" ? TONO.peligro : TONO.tinta,
    ]);
  else {
    const s = d.ent.series.find((x) => x.key === o.metrica);
    unidad = s?.unit ?? "";
    // Las series traen los últimos meses de la entidad: se alinean por el final.
    const ultimo = d.ent.months[d.ent.months.length - 1].month;
    const desplaz =
      d.ent.months.findIndex((m) => m.month === ultimo) -
      d.ent.months.findIndex((m) => m.month === d.corte);
    const vals = s
      ? s.values.slice(0, s.values.length - Math.max(0, desplaz))
      : [];
    valores = pasado.map((_, i) => {
      const k = vals.length - (pasado.length - i);
      return [i, k >= 0 ? (vals[k] ?? null) : null];
    });
  }
  const futuros: Futuro[] = [];
  const marcas: [number, number][] = [];
  let lo = Infinity,
    hi = -Infinity;
  for (const v of valores)
    if (v[1] !== null) {
      lo = Math.min(lo, v[1]);
      hi = Math.max(hi, v[1]);
    }
  if (abanico)
    for (const v of [abanico.best, abanico.common, abanico.worst]) {
      lo = Math.min(lo, v / 10);
      hi = Math.max(hi, v / 10);
    }
  if (conFuturo) {
    const esc: EscenarioM | undefined =
      escenarios![o.escenario] ?? escenarios!.base;
    const accs = (d.hor!.actions ?? []).filter((a) => o.acciones.has(a.id));
    futuros.push({
      granos: esc.grains,
      tono: TONO.apagado,
      alfa: accs.length ? 0.3 : 0.62,
      mediana: accs.length ? undefined : esc.q.p50,
    });
    for (const a of accs)
      futuros.push({
        granos: a.grains,
        tono: TONO.info,
        alfa: 0.7,
        mediana: a.q.p50,
      });
    const todas = [esc, ...accs];
    for (const e of todas)
      for (const k of ["p10", "p90"] as const)
        for (const v of e.q[k]) {
          lo = Math.min(lo, v / 10);
          hi = Math.max(hi, v / 10);
        }
    if (accs.length) {
      const lag = Math.max(...accs.map((a) => a.lag_months));
      const ids = accs.map((a) => a.id).sort();
      const cifra =
        accs.length === 1
          ? accs[0].engine_new_score
          : d.hor!.combos?.find((c) => [...c.ids].sort().join() === ids.join())
              ?.new_score;
      if (cifra !== undefined) marcas.push([hoy + lag, cifra / 10]);
    }
  }
  if (!Number.isFinite(lo)) {
    lo = 0;
    hi = 100;
  }
  const margen = Math.max(3, (hi - lo) * 0.08);
  if (o.metrica === "score") {
    lo = Math.max(0, Math.floor((lo - margen) / 5) * 5);
    hi = Math.min(100, Math.ceil((hi + margen) / 5) * 5);
  } else {
    lo = lo - margen;
    hi = hi + margen;
  }
  if (hi - lo < 10 && o.metrica === "score") {
    hi = Math.min(100, lo + 10);
  }
  const bandas =
    o.metrica === "score"
      ? d.man.bands.filter((b) => b.min > 0).map((b) => b.min / 10)
      : [];

  // En el grupo, las estelas finas de sus empresas (alineadas con los meses del fichero del grupo).
  const hilos: [number, number | null][][] = [];
  if (empresasHilo && d.kind === "group" && o.metrica === "score") {
    const g = d.ent as GrupoM;
    const primero = g.months.findIndex((m) => m.month === pasado[0]?.month);
    for (const em of g.companies)
      hilos.push(
        pasado.map((_, i) => {
          const v = em.shown[primero + i];
          return [i, v === null || v === undefined ? null : v / 10];
        }),
      );
    for (const hl of hilos)
      for (const [, v] of hl)
        if (v !== null) {
          lo = Math.min(lo, Math.max(0, v - 2));
          hi = Math.max(hi, Math.min(100, v + 2));
        }
  }
  const hueco = h("div", { class: "grafico-arena" });
  placa(hueco, (c): PlacaSerie => ({
    tipo: "serie",
    x: c.x,
    y: c.y,
    w: c.w,
    h: c.h,
    lo,
    hi,
    columnas: Math.max(columnas, 2),
    hoy,
    pasado: valores,
    hilos,
    futuros,
    bandas,
    marcas,
    abanico: abanico
      ? {
          mejor: abanico.best,
          comun: abanico.common,
          peor: abanico.worst,
          mes: abanico.horizon_months,
        }
      : undefined,
  }));
  caja.append(hueco);

  // Etiquetas HTML con el mismo mapeo (porcentajes de la caja).
  const X = (c: number) => `${((c + 0.5) / Math.max(columnas, 2)) * 100}%`;
  const Y = (v: number) => `${(1 - (v - lo) / (hi - lo)) * 100}%`;
  const eti = (clase: string, texto: string, x: string, y: string) => {
    const e = h("span", { class: `g-etq ${clase}` }, texto);
    e.style.left = x;
    e.style.top = y;
    caja.append(e);
    return e;
  };
  const fmtV = (v: number) =>
    o.metrica === "score"
      ? f.numero(v)
      : unidad === "EUR"
        ? f.eurosCorto(v)
        : unidad === "ratio"
          ? f.ratio(v)
          : `${f.numero(v, 1)}${unidad === "días" ? " días" : ""}`;
  eti("eje-v", fmtV(hi), "0", "0%");
  eti("eje-v", fmtV(lo), "0", "100%");
  for (const b of d.man.bands.filter((x) => x.min > 0))
    if (o.metrica === "score" && b.min / 10 > lo && b.min / 10 < hi)
      eti("eje-banda", `${b.label} · ${f.score(b.min)}`, "100%", Y(b.min / 10));
  pasado.forEach((m, i) => {
    if (
      i === hoy ||
      (pasado.length - 1 - i) % (pasado.length > 14 ? 6 : 3) === 0
    )
      eti(
        `eje-m ${i === hoy ? "hoy" : ""}`,
        i === hoy ? `hoy · ${f.mesCorto(m.month)}` : f.mesCorto(m.month),
        X(i),
        "100%",
      );
  });
  if (conFuturo) {
    const esc = escenarios![o.escenario] ?? escenarios!.base;
    for (const hz of [3, 6, 12] as const) {
      const k = hz - 1;
      if (k >= nF) continue;
      const b = esc.bands[`h${hz}` as "h3" | "h6" | "h12"];
      const q = esc.q;
      const txt = `${hz === 12 ? "un año" : `${hz} meses`}: ${f.score(q.p10[k])}–${f.score(q.p90[k])}`;
      const boya = eti(
        `boya ${hz === 12 ? "fin" : ""}`,
        txt,
        X(hoy + hz),
        "100%",
      );
      if (b)
        boya.title = d.man.bands
          .map((x) => `${x.label} ${f.porcentaje(b[x.key] ?? 0, 0)}`)
          .join(" · ");
    }
    eti(
      "eje-m futuro",
      o.acciones.size ? "previsto, con acciones" : "previsto",
      X(hoy + Math.min(6, nF)),
      "0%",
    );
  }
  if (abanico) {
    const xa = X(hoy + abanico.horizon_months);
    eti(
      "g-etq abanico mejor",
      `Mejor ${f.score(abanico.best)}`,
      xa,
      Y(abanico.best / 10),
    );
    eti(
      "g-etq abanico comun",
      `Común ${f.score(abanico.common)}`,
      xa,
      Y(abanico.common / 10),
    );
    eti(
      "g-etq abanico peor",
      `Peor ${f.score(abanico.worst)}`,
      xa,
      Y(abanico.worst / 10),
    );
    if (!conFuturo)
      eti("g-etq abanico mes", `+${abanico.horizon_months} meses`, xa, "100%");
  }
  void empresasHilo;
  void col;
  return caja;
}

// ─── Sección I · Scoring y tendencia ──────────────────────────

export function seccionScoring(
  d: DatosFicha,
  estado: { escenario: OpcionesGrafico["escenario"]; metrica: string },
  acc: Acciones,
  movil: boolean,
): HTMLElement {
  const raiz = h("div", { class: "sec-scoring" });
  const m = d.mes;
  if (!m) {
    raiz.append(
      h(
        "p",
        { class: "vacio" },
        `${nombreEntidad(d.kind, d.id)} no tiene datos en ${f.mes(d.corte)}. Su primer mes es ${f.mes(d.ent.first_month)}.`,
      ),
    );
    return raiz;
  }

  // Controles del gráfico: métrica y escenario.
  const metricas: [string, string][] = [
    ["score", "Score"],
    ...d.ent.series
      .filter((s) =>
        [
          "buffer_days",
          "cash_month_end",
          "headroom",
          "ar_days_beyond_terms",
          "ap_days_beyond_terms",
          "activity_coverage",
          "debt_burden",
          "op_inflow_1m",
          "op_outflow_1m",
        ].includes(s.key),
      )
      .map((s) => [s.key, s.label] as [string, string]),
  ];
  const selM = h(
    "select",
    { class: "sel-sutil", "aria-label": "Qué se dibuja" },
    ...metricas.map(([k, n]) =>
      h("option", { value: k, selected: k === estado.metrica }, n),
    ),
  );
  selM.addEventListener("change", () => {
    estado.metrica = selM.value;
    repintar();
  });
  const esc = h("div", {
    class: "escenarios",
    role: "radiogroup",
    "aria-label": "Escenario",
  });
  for (const k of ["base", "drift", "stress"] as const) {
    const b = h(
      "button",
      {
        type: "button",
        class: `esc ${estado.escenario === k ? "activo" : ""}`,
        role: "radio",
        "aria-checked": String(estado.escenario === k),
        title:
          k === "drift"
            ? "Qué pasaría si: en la prueba hacia atrás, este escenario predice peor que el básico."
            : undefined,
      },
      NOMBRE_ESCENARIO[k],
    );
    b.addEventListener("click", () => {
      estado.escenario = k;
      repintar();
    });
    esc.append(b);
  }
  const zona = h("div", { class: "zona-grafico" });
  const pie = h("p", { class: "grafico-pie" });
  const repintar = () => {
    vaciar(zona);
    zona.append(
      graficoHorizonte(
        d,
        {
          escenario: estado.escenario,
          acciones: new Set(),
          metrica: estado.metrica,
          alto: movil ? 220 : 300,
        },
        true,
      ),
    );
    for (const b of esc.querySelectorAll("button"))
      b.classList.toggle(
        "activo",
        b.textContent === NOMBRE_ESCENARIO[estado.escenario],
      );
    pie.textContent = pieGrafico(d, estado.escenario, estado.metrica);
    esc.hidden = estado.metrica !== "score" || !d.hor?.scenarios;
    acc.repintarArena();
  };
  raiz.append(h("div", { class: "controles-grafico" }, selM, esc), zona, pie);
  repintar();

  // Cinco cifras con contexto.
  const v = m.verdict;
  const deriva = d.evid?.months
    .find((x) => x.month === d.corte)
    ?.rows.find((r) => r.pillar === null && /deriva acumulada/i.test(r.label));
  const esc6 = d.hor?.scenarios?.base;
  const conSims = !!esc6 && d.hor!.cut === d.corte;
  const ol = d.mes?.outlook ?? null;
  const cifras = h(
    "div",
    { class: "cifras-c" },
    cifraC(
      f.score(m.shown),
      "score",
      v.compared_to && v.delta3 !== null
        ? `${f.delta(v.delta3)} frente a ${f.mesCorto(v.compared_to)}`
        : null,
      v.delta3 === null
        ? ""
        : v.delta3 < -5
          ? "baja"
          : v.delta3 > 5
            ? "sube"
            : "",
    ),
    cifraC(
      f.porcentaje(m.conf.value, 0),
      `confianza ${({ high: "alta", medium: "media", low: "baja" } as Record<string, string>)[m.conf.label]}`,
      `historia ${f.porcentaje(m.conf.history, 0)} · cobertura ${f.porcentaje(m.conf.coverage, 0)} · calidad ${f.porcentaje(m.conf.quality, 0)}`,
    ),
    cifraC(
      v.persistence_months
        ? f.plural(v.persistence_months, "mes", "meses")
        : "—",
      "persistencia",
      v.detected_since ? `${movimiento(m)}` : "sin movimiento confirmado",
      v.available
        ? v.direction === "improving"
          ? "sube"
          : v.direction === "deteriorating"
            ? "baja"
            : ""
        : "",
    ),
    cifraC(
      deriva && typeof deriva.value === "number"
        ? f.signo(deriva.value, 1)
        : "—",
      "deriva de 12 meses",
      deriva
        ? `${f.periodo(deriva.period)}, según el motor`
        : "el motor no la calcula este mes",
      deriva && typeof deriva.value === "number"
        ? deriva.value < -3
          ? "baja"
          : deriva.value > 3
            ? "sube"
            : ""
        : "",
    ),
    cifraC(
      conSims
        ? `${f.score(esc6!.q.p10[5])}–${f.score(esc6!.q.p90[5])}`
        : ol
          ? `${f.score(ol.worst)}–${f.score(ol.best)}`
          : "—",
      "previsto a seis meses",
      conSims
        ? `lo más probable, ${f.score(esc6!.q.p50[5])}${esc6!.cross ? ` · ${f.porcentaje(esc6!.cross.prob, 0)} de pasar a ${nombreBanda(d.man, esc6!.cross.to).toLowerCase()}` : ""}`
        : ol
          ? `escenario común, ${f.score(ol.common)}: lo calcula el motor, sin simulación`
          : (d.hor?.reason ?? "sin horizonte en este mes"),
    ),
  );
  raiz.append(cifras);

  // La partitura de pilares.
  raiz.append(partitura(d, acc));
  // El hilo, en corto.
  raiz.append(
    seccion(
      "De dónde sale",
      hilo(nudosScore(d, acc).slice(0, 3), true),
      (() => {
        const b = h(
          "button",
          { type: "button", class: "as-enlace" },
          "Ver el hilo entero en Detalles",
        );
        b.addEventListener("click", () => acc.irSeccion("tecnico"));
        return b;
      })(),
    ),
  );
  return raiz;
}

function pieGrafico(
  d: DatosFicha,
  esc: OpcionesGrafico["escenario"],
  metrica: string,
): string {
  if (metrica !== "score")
    return "Serie mensual del motor. La previsión se dibuja solo para el score.";
  const ol = d.mes?.outlook ?? null;
  const abanicoTxt = ol
    ? ` Los escenarios mejor, común y peor a ${ol.horizon_months} meses los calcula el motor con la deriva y la volatilidad medidas: no son simulaciones.`
    : "";
  if (!d.hor?.scenarios) {
    if (ol)
      return `Sin simulación de horizonte para esta entidad.${abanicoTxt}`;
    return d.hor?.reason
      ? `Sin horizonte: ${d.hor.reason}`
      : "Sin horizonte para esta entidad.";
  }
  if (d.hor.cut !== d.corte)
    return `Los horizontes se calculan desde ${f.mes(d.hor.cut)}: mueve la regla a ese mes para verlos.${abanicoTxt}`;
  const base =
    "Cada grano del futuro es una de 400 simulaciones puntuadas con el propio motor; donde se amontonan, es más probable.";
  return (
    (esc === "drift"
      ? `${base} Este escenario prolonga la deriva de 12 meses: es un «qué pasaría si», no una predicción (en la prueba hacia atrás acierta menos que el básico).`
      : esc === "stress"
        ? `${base} Los tres primeros meses repiten su peor trimestre observado.`
        : base) + abanicoTxt
  );
}

function partitura(d: DatosFicha, acc: Acciones): HTMLElement {
  const m = d.mes!;
  const filas = h("div", { class: "partitura" });
  const textosNota: string[] = [];
  for (const p of m.pillars) {
    const ref = d.man.pillars.find((x) => x.key === p.key)?.baseline ?? null;
    const gates = p.gates.map((g) => d.man.glossary.gates[g] ?? g);
    const marcas: HTMLElement[] = [];
    for (const g of gates) {
      textosNota.push(g);
      marcas.push(
        h(
          "sup",
          { class: "llamada" },
          "¹²³⁴⁵⁶⁷⁸⁹"[textosNota.length - 1] ?? String(textosNota.length),
        ),
      );
    }
    const barra = h(
      "div",
      {
        class: "pt-barra",
        title:
          ref !== null ? `Referencia del motor: ${f.score(ref)}` : undefined,
      },
      h("span", {
        class: "pt-lleno",
        style: { width: `${p.score === null ? 0 : p.score / 10}%` },
      }),
      ref !== null
        ? h("span", { class: "pt-ref", style: { left: `${ref / 10}%` } })
        : null,
    );
    const fila = h(
      "div",
      {
        class: `pt-fila tocable ${p.score === null ? "nulo" : ""}`,
        tabindex: "0",
        title: "Ver de dónde sale, en Detalles",
      },
      h(
        "div",
        { class: "pt-nombre" },
        nombrePilar(d.man, p.key),
        ...marcas,
        h("span", { class: "pt-peso" }, ` ${f.porcentaje(p.w_eff, 0)}`),
      ),
      h(
        "div",
        { class: "pt-score" },
        p.score === null ? "sin dato" : f.score(p.score),
      ),
      barra,
      h(
        "div",
        {
          class: `pt-aporta ${p.contrib < 0 ? "neg" : p.contrib > 0 ? "pos" : ""}`,
        },
        p.score === null ? "" : f.delta(p.contrib),
      ),
      h("p", { class: "pt-nota" }, p.note ?? ""),
    );
    const ir = () => acc.irSeccion("tecnico", undefined, { pilar: p.key });
    fila.addEventListener("click", ir);
    fila.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") ir();
    });
    filas.append(fila);
  }
  const { notas } = llamadas(textosNota);
  return seccion("Qué aporta cada pilar", filas, notas);
}

/** Nudos del hilo del score: score → pilar que más resta → sus medidas → ficheros. */
export function nudosScore(d: DatosFicha, acc: Acciones): Nudo[] {
  const m = d.mes!;
  const nudos: Nudo[] = [
    {
      valor: f.score(m.shown),
      texto: "score",
      detalle: `base ${f.scoreDec(m.base)} · pilares ${f.delta(m.pillars.reduce((s, p) => s + p.contrib, 0))} · penalización ${f.delta(-m.penalty)} · tope ${f.delta(-m.cap.amount)}`,
    },
  ];
  const peor = [...m.pillars]
    .filter((p) => p.score !== null)
    .sort((a, b) => a.contrib - b.contrib)[0];
  if (!peor) return nudos;
  nudos.push({
    valor: f.delta(peor.contrib),
    texto: `${nombrePilar(d.man, peor.key).toLowerCase()} ${peor.contrib < 0 ? "resta" : "aporta"}`,
    detalle: peor.note ?? undefined,
    accion: () => acc.irSeccion("tecnico", undefined, { pilar: peor.key }),
  });
  const filas =
    d.evid?.months
      .find((x) => x.month === d.corte)
      ?.rows.filter((r) => r.pillar === peor.key) ?? [];
  for (const r of filas.slice(0, 3))
    nudos.push({
      valor: f.valorUnidad(r.value, r.unit),
      texto: r.label.charAt(0).toLowerCase() + r.label.slice(1),
      detalle: f.periodo(r.period),
      accion: () =>
        acc.irSeccion("tecnico", undefined, {
          pilar: peor.key,
          texto: r.label,
        }),
    });
  const ficheros = [...new Set(filas.map((r) => r.source_file))];
  if (ficheros.length)
    nudos.push({
      valor: f.plural(ficheros.length, "fichero", "ficheros"),
      texto: ficheros.join(" · "),
      detalle: filas.some((r) => r.n_rows)
        ? `${f.numero(Math.max(...filas.map((r) => r.n_rows ?? 0)))} filas en la ventana`
        : "medidas derivadas",
      accion: () =>
        acc.irSeccion("tecnico", undefined, {
          pilar: peor.key,
          fichero: ficheros[0],
        }),
    });
  return nudos;
}

// ─── Sección II · Productos ───────────────────────────────────

export function seccionProductos(d: DatosFicha, acc: Acciones): HTMLElement {
  const raiz = h("div", { class: "sec-productos" });
  if (!d.mes) {
    raiz.append(h("p", { class: "vacio" }, `Sin datos en ${f.mes(d.corte)}.`));
    return raiz;
  }
  if (d.kind === "group") return productosGrupo(d, acc);
  const es = estados(d);
  if (!d.prodE)
    raiz.append(
      h(
        "p",
        { class: "aviso-datos" },
        "Falta products/ para esta empresa: ejecuta scripts/datos/productos.py.",
      ),
    );
  raiz.append(inventario(d, es, acc));

  // Lo que tiene.
  const tiene = h("div", { class: "col-tiene" });
  for (const t of tenenciaDe(d)) {
    const p = producto(t.product);
    const e = es.find((x) => x.id === t.product)!;
    const hechos: (string | Node)[] = [];
    for (const it of t.items.slice(0, 4)) {
      const partes = [it.bank ?? "Entidad sin nombre"];
      if (it.inconsistent)
        partes.push("límite y dispuesto incoherentes en el origen");
      else {
        if (it.granted !== null)
          partes.push(`límite ${f.eurosCorto(it.granted)}`);
        if (it.outstanding !== null && it.granted !== null)
          partes.push(
            `dispuesto ${f.eurosCorto(it.outstanding)}${it.usage !== null ? ` (${f.porcentaje(it.usage, 0)})` : ""}`,
          );
        if (it.balance) partes.push(`saldo ${f.eurosCorto(it.balance)}`);
      }
      if (it.rate !== null)
        partes.push(`${f.numero(it.rate, 2)} % ${it.rate_type ?? ""}`.trim());
      if (it.since) partes.push(`conectado en ${f.mes(it.since)}`);
      hechos.push(partes.join(", "));
    }
    const ev = (Array.isArray(t.evidence) ? t.evidence : [t.evidence]).find(
      (x) => x.file === "transactions.csv",
    );
    if (ev)
      hechos.push(
        `${f.plural(ev.rows ?? 0, "movimiento", "movimientos")} de ${ev.first ? f.mesCorto(ev.first) : "—"} a ${ev.last ? f.mesCorto(ev.last) : "—"}${ev.amount_12m ? `, ${f.eurosCorto(ev.amount_12m)} en 12 meses` : ""}${ev.examples.length ? ` («${ev.examples[0]}»)` : ""}`,
      );
    tiene.append(
      asiento({
        icono: iconoProducto(t.product, { tam: 48, estado: "tiene" }),
        titulo: p.nombre,
        estado:
          t.source === "declarado"
            ? "contratado"
            : "deducido de sus movimientos",
        hechos,
        color: p.color,
        texto: e.forma ? e.motivo : undefined,
        sello: sello(t.items[0]?.bank ?? null, t.source),
        enlace: e.accion
          ? {
              texto: "Ver su horizonte",
              accion: () => acc.irSeccion("acciones", e.accion!.id),
            }
          : undefined,
      }),
    );
  }
  if (!tenenciaDe(d).length)
    tiene.append(
      h(
        "p",
        { class: "nota" },
        "Ninguno de los siete productos consta en sus datos.",
      ),
    );
  const otras = d.prodE?.other_debt.filter((x) => !x.closed) ?? [];
  // La unidad que se repite entre las filas sube a la cabecera y las celdas quedan limpias;
  // el cero no lastra la unidad (0 € = 0 k€). Si se mezclan, cada fila lleva la suya (docs/DESIGN_UX.mdx).
  const unidadDe = (v: number | null) =>
    v === null || v === 0 ? null : Math.abs(v) >= 1e6 ? "M€" : Math.abs(v) >= 1e3 ? "k€" : "€";
  const unidadComun = (vs: (number | null)[]) => {
    const us = new Set(vs.filter((v) => v !== null && v !== 0).map(unidadDe));
    return us.size === 1 ? [...us][0]! : null;
  };
  const importe = (v: number | null, u: "€" | "k€" | "M€" | null) =>
    v === null ? "—" : u ? f.eurosEn(v, u) : f.eurosCorto(v);
  // La tabla se reconstruye por filtro y las unidades se vuelven a medir sobre las filas
  // visibles: filtrar a un solo tipo puede cambiar la unidad común de una columna (docs/DESIGN_UX.mdx).
  const tablaOtras = (visibles: typeof otras) => {
    const uc = unidadComun(visibles.map((x) => x.granted));
    const up = unidadComun(visibles.map((x) => x.outstanding));
    return h(
      "table",
      { class: "tabla-sutil" },
      h(
        "thead",
        {},
        h(
          "tr",
          {},
          h("th", {}, "Tipo"),
          h("th", {}, "Entidad"),
          h("th", { class: "num" }, uc ? `Concedido (${uc})` : "Concedido"),
          h("th", { class: "num" }, up ? `Pendiente (${up})` : "Pendiente"),
          h("th", { class: "num" }, "Interés (%)"),
          h("th", {}, "Próxima cuota"),
        ),
      ),
      h(
        "tbody",
        {},
        ...visibles.map((x) =>
          h(
            "tr",
            {},
            h("td", {}, x.type_label),
            h(
              "td",
              {},
              x.bank
                ? h("span", { class: "banco" }, marcaBanco(x.bank), x.bank)
                : "—",
            ),
            h("td", { class: "num" }, importe(x.granted, uc)),
            h("td", { class: "num" }, importe(x.outstanding, up)),
            h("td", { class: "num" }, x.rate === null ? "—" : f.numero(x.rate, 2)),
            h("td", {}, x.next_payment ? f.mes(x.next_payment.slice(0, 7)) : "—"),
          ),
        ),
      ),
    );
  };
  const tipos = [...new Set(otras.map((x) => x.type_label))];
  let filtro: string | null = null;
  const tabla = h("div");
  const pinta = () => {
    vaciar(tabla);
    tabla.append(tablaOtras(filtro === null ? otras : otras.filter((x) => x.type_label === filtro)));
  };
  const botonesFiltro =
    tipos.length > 1
      ? [null, ...tipos].map((t) =>
          h(
            "button",
            {
              type: "button",
              class: "filtro-opcion",
              "aria-pressed": String(filtro === t),
              "data-tipo": String(t),
            },
            t === null ? "Todos" : t,
          ),
        )
      : null;
  if (botonesFiltro)
    for (const b of botonesFiltro)
      b.addEventListener("click", () => {
        filtro =
          b.dataset.tipo === "null" || b.dataset.tipo === undefined
            ? null
            : b.dataset.tipo;
        for (const x of botonesFiltro)
          x.setAttribute("aria-pressed", String(x === b));
        pinta();
      });
  const otrasEl = otras.length
    ? seccion(
        "Otras deudas",
        ...(botonesFiltro
          ? [
              h(
                "div",
                {
                  class: "filtro-tipo",
                  role: "group",
                  "aria-label": "Filtrar otras deudas por tipo",
                },
                ...botonesFiltro,
              ),
            ]
          : []),
        tabla,
        h(
          "p",
          { class: "nota" },
          "No son de los siete productos, pero pesan en el pilar de deuda.",
        ),
      )
    : null;

  // Lo que le encajaría: ordenado por el efecto del motor.
  const encaja = h("div", { class: "col-encaja" });
  const candidatos = es
    .filter(
      (e) =>
        e.estado === "encaja" ||
        e.estado === "bloqueado" ||
        (e.estado === "tiene" && e.forma),
    )
    .sort(
      (a, b) =>
        (b.accion?.uplift_tenths ?? -1) - (a.accion?.uplift_tenths ?? -1),
    );
  for (const e of candidatos) {
    const p = producto(e.id);
    const efecto = efectoAccion(d, e.accion);
    encaja.append(
      asiento({
        icono: iconoProducto(e.id, {
          tam: 48,
          estado: e.estado === "bloqueado" ? "bloqueado" : "encaja",
        }),
        titulo:
          e.forma === "ampliar"
            ? `Ampliar ${p.articulo.replace(/^una? /, "la ")}`
            : e.forma === "usar_mas"
              ? `Usar más ${p.articulo}`
              : e.forma === "siguiente_nivel"
                ? `Dar el paso a ${p.articulo}`
                : primeraMayuscula(p.articulo),
        estado:
          e.estado === "bloqueado"
            ? "hoy no"
            : e.accion
              ? `encaje ${e.accion.effort === "bajo" ? "fácil" : "con esfuerzo " + e.accion.effort}`
              : "le encaja",
        texto: e.bloqueo ?? e.motivo,
        hechos: [
          efecto ?? e.sinEfecto ?? "",
          FAMILIAS[p.familia].nombre + (p.nivel ? ` · nivel ${p.nivel}` : ""),
        ].filter(Boolean),
        color: p.color,
        clase: e.estado === "bloqueado" ? "bloqueado" : "",
        enlace:
          e.accion && e.estado !== "bloqueado"
            ? {
                texto: "Ver su horizonte",
                accion: () => acc.irSeccion("acciones", e.accion!.id),
              }
            : undefined,
      }),
    );
  }
  if (!candidatos.length)
    encaja.append(
      h(
        "p",
        { class: "nota" },
        "Con lo que dice el motor este mes, ningún producto encaja con claridad.",
      ),
    );
  raiz.append(
    h(
      "div",
      { class: "dos-columnas" },
      seccion("Lo que tiene", tiene, otrasEl),
      seccion("Lo que le encajaría", encaja),
    ),
  );
  raiz.append(
    h(
      "p",
      { class: "nota pie" },
      "Lo contratado sale de debt_products, banking_products y los movimientos de los últimos 12 meses (reglas en products/index.json). Lo que encaja sale de las acciones del motor; el efecto es el que calcula el motor para esa acción.",
    ),
  );
  return raiz;
}

/** El efecto de una acción: la cifra del motor y la mediana a seis meses con y sin ella. */
function efectoAccion(d: DatosFicha, a?: AccionM): string | null {
  if (!a) return null;
  const partes = [`${f.delta(a.uplift_tenths)} puntos según el motor`];
  const ha = d.hor?.actions?.find((x) => x.id === a.id);
  const hb = d.hor?.scenarios?.base;
  if (ha && hb && d.hor!.cut === d.corte)
    partes.push(
      `a seis meses, ${f.score(ha.q.p50[5])} en vez de ${f.score(hb.q.p50[5])}`,
    );
  return partes.join(" · ");
}

function inventario(
  d: DatosFicha,
  es: EstadoProducto[],
  acc: Acciones,
): HTMLElement {
  const fila = h("div", { class: "inventario", role: "list" });
  let familia = "";
  for (const e of es) {
    const p = producto(e.id);
    if (p.familia !== familia) {
      familia = p.familia;
      fila.append(
        h(
          "span",
          { class: "inv-familia versalita" },
          FAMILIAS[p.familia].nombre,
        ),
      );
    }
    const texto =
      e.estado === "tiene"
        ? (e.dato ?? "lo tiene")
        : e.estado === "encaja"
          ? e.accion
            ? `${f.delta(e.accion.uplift_tenths)} puntos`
            : "le encaja"
          : e.estado === "bloqueado"
            ? "hoy no"
            : "no consta";
    const b = h(
      "button",
      {
        type: "button",
        class: `inv-item estado-${e.estado}`,
        role: "listitem",
        title: `${p.nombre}: ${e.bloqueo ?? e.motivo}`,
      },
      iconoProducto(e.id, {
        tam: 44,
        estado: e.estado === "tiene" && e.forma ? "tiene" : e.estado,
        titulo: false,
      }),
      h("span", { class: "inv-nombre" }, p.nombre),
      h("span", { class: "inv-dato" }, texto),
    );
    if (e.accion)
      b.addEventListener("click", () =>
        acc.irSeccion("acciones", e.accion!.id),
      );
    fila.append(b);
  }
  void d;
  return fila;
}

function productosGrupo(d: DatosFicha, acc: Acciones): HTMLElement {
  const raiz = h("div", { class: "sec-productos grupo" });
  raiz.append(inventario(d, estados(d), acc));
  // Matriz empresas × siete productos, con el mismo estado que en la empresa.
  const tabla = h("table", { class: "matriz" });
  tabla.append(
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Empresa"),
        ...PRODUCTOS.map((p) =>
          h(
            "th",
            { title: p.nombre },
            iconoProducto(p.id, { tam: 26, titulo: false, sinFilete: true }),
            h("span", { class: "mz-nombre" }, p.nombre),
          ),
        ),
      ),
    ),
  );
  const cuerpo = h("tbody");
  for (const em of d.empresas) {
    const mes = em.ent?.months.find((m) => m.month === d.corte) ?? null;
    const es =
      mes && em.ent
        ? estadosProductos({
            mes,
            man: d.man,
            tenencia: em.prod?.held ?? [],
            perfil: em.ent.profile,
            papel: em.ent.role,
            heredaLiquidez: em.ent.inherits_liquidity,
          })
        : [];
    const fila = h(
      "tr",
      {},
      h(
        "td",
        {},
        (() => {
          const b = h(
            "button",
            { type: "button", class: "enlace-empresa" },
            f.empresa(em.res.id),
            h("span", { class: "mz-papel" }, em.res.role),
          );
          b.addEventListener("click", () => acc.abrirEmpresa(em.res.id));
          return b;
        })(),
      ),
    );
    for (const p of PRODUCTOS) {
      const e = es.find((x) => x.id === p.id);
      const estado = e?.estado ?? "no_consta";
      fila.append(
        h(
          "td",
          {
            class: `mz-celda estado-${estado}`,
            title: e
              ? `${p.nombre}: ${e.bloqueo ?? e.motivo}`
              : "Sin datos este mes",
          },
          iconoProducto(p.id, {
            tam: 24,
            estado,
            titulo: false,
            sinFilete: true,
          }),
        ),
      );
    }
    cuerpo.append(fila);
  }
  tabla.append(cuerpo);
  raiz.append(
    seccion(
      "Qué tiene cada empresa y qué le encaja",
      h("div", { class: "matriz-caja" }, tabla),
      h(
        "p",
        { class: "nota" },
        "Tinta entera: lo tiene. Contorno con granos: le encaja según las acciones del motor. Tachado: hoy no. Casi invisible: no consta.",
      ),
    ),
  );
  return raiz;
}

// ─── Sección III · Acciones ───────────────────────────────────

export function seccionAcciones(
  d: DatosFicha,
  sel: Set<string>,
  acc: Acciones,
  movil: boolean,
): HTMLElement {
  const raiz = h("div", { class: "sec-acciones" });
  const m = d.mes;
  if (!m) {
    raiz.append(h("p", { class: "vacio" }, `Sin datos en ${f.mes(d.corte)}.`));
    return raiz;
  }
  const recs = recomendaciones({
    mes: m,
    man: d.man,
    tenencia: tenenciaDe(d),
    perfil: d.ent.profile,
    papel: d.kind === "company" ? (d.ent as EmpresaM).role : null,
    heredaLiquidez:
      d.kind === "company" ? (d.ent as EmpresaM).inherits_liquidity : false,
  });

  // El horizonte en grande, con las acciones elegidas.
  const zona = h("div", { class: "zona-grafico" });
  const frase = h("p", { class: "frase-horizonte" });
  const repintar = () => {
    vaciar(zona);
    zona.append(
      graficoHorizonte(d, {
        escenario: "base",
        acciones: sel,
        metrica: "score",
        alto: movil ? 240 : 340,
        grande: true,
      }),
    );
    frase.textContent = fraseHorizonte(d, sel);
    acc.repintarArena();
  };

  // Recomendaciones del motor + «no hacer nada».
  const lista = h("ol", { class: "recomendaciones" });
  recs.forEach((r, i) => {
    const a = r.accion;
    const marca = h("input", {
      type: "checkbox",
      checked: sel.has(a.id),
      "aria-label": `Ver en el horizonte: ${tituloAccion(a)}`,
    }) as HTMLInputElement;
    marca.addEventListener("change", () => {
      if (marca.checked) sel.add(a.id);
      else sel.delete(a.id);
      li.classList.toggle("elegida", marca.checked);
      repintar();
    });
    const efecto = efectoAccion(d, a);
    const prods = r.productos.map((p) =>
      iconoProducto(p, {
        tam: 24,
        titulo: true,
        sinFilete: true,
        estado: tenenciaDe(d).some((t) => t.product === p) ? "tiene" : "encaja",
      }),
    );
    const li = h(
      "li",
      {
        class: `rec ${sel.has(a.id) ? "elegida" : ""}`,
      },
      h(
        "label",
        { class: "rec-marca" },
        marca,
        h("span", { class: "rec-n" }, String(i + 1)),
      ),
      h(
        "div",
        { class: "rec-cuerpo" },
        h("div", { class: "rec-titulo" }, tituloAccion(a)),
        h(
          "p",
          { class: "rec-texto" },
          r.delGrupo
            ? `${explicacionAccion(a)} En una filial que financia el grupo, esto se decide en el grupo.`
            : explicacionAccion(a),
        ),
        h(
          "p",
          { class: "rec-hechos" },
          efecto ?? "",
          " · ",
          ESFUERZO[a.effort],
          " · ",
          `pilar de ${nombrePilar(d.man, a.pillar).toLowerCase()}`,
        ),
        prods.length
          ? h(
              "p",
              { class: "rec-productos" },
              h("span", { class: "versalita" }, "con "),
              ...prods,
              " ",
              r.productos
                .map((p) => producto(p).nombre.toLowerCase())
                .join(" o "),
            )
          : r.propia
            ? h("p", { class: "rec-productos propia" }, r.propia)
            : null,
      ),
    );
    lista.append(li);
  });
  const base = d.hor?.scenarios?.base;
  if (base && d.hor!.cut === d.corte) {
    const peor =
      base.cross &&
      base.cross.to &&
      d.man.bands.findIndex((b) => b.key === base.cross!.to) <
        d.man.bands.findIndex((b) => b.key === m.band);
    lista.append(
      h(
        "li",
        { class: "rec nada" },
        h("span", { class: "rec-marca" }, h("span", { class: "rec-n" }, "—")),
        h(
          "div",
          { class: "rec-cuerpo" },
          h("div", { class: "rec-titulo" }, "No hacer nada"),
          h(
            "p",
            { class: "rec-hechos" },
            `a seis meses, entre ${f.score(base.q.p10[5])} y ${f.score(base.q.p90[5])}; lo más probable, ${f.score(base.q.p50[5])}`,
            peor
              ? ` · ${f.porcentaje(base.cross!.prob, 0)} de pasar a ${nombreBanda(d.man, base.cross!.to).toLowerCase()} hacia ${f.mes(base.cross!.month)}`
              : "",
          ),
        ),
      ),
    );
  }
  if (!recs.length)
    lista.prepend(
      h(
        "li",
        { class: "rec vacia" },
        h(
          "p",
          {},
          m.abstain
            ? `El motor se abstiene este mes y no propone acciones: ${d.man.glossary.reasons[m.abstain.reason] ?? m.abstain.reason}`
            : !m.feed_live
              ? "Sin datos del banco al día, el motor no propone acciones."
              : "El motor no encuentra este mes ninguna palanca que suba el score al menos medio punto.",
        ),
      ),
    );

  raiz.append(seccion("Avisos", avisos(d)));
  if (d.kind === "group")
    raiz.append(
      seccion("Lo que proponen sus empresas", accionesEmpresas(d, acc)),
    );
  const cabeceraAcciones = h(
    "div",
    { class: "sec-acciones-cabecera" },
    h(
      "p",
      { class: "nota" },
      "Las acciones y su efecto las calcula el motor: cada una sube un pilar hasta el siguiente escalón de su curva y vuelve a puntuar. Marca una o varias para verlas en el horizonte.",
    ),
    h(
      "button",
      { type: "button", class: "boton-propuesta" },
      "Armar propuesta al cliente",
    ),
  );
  cabeceraAcciones
    .querySelector("button")!
    .addEventListener("click", () => abrirPropuesta(d, sel, acc));
  raiz.append(seccion("Qué hacer", cabeceraAcciones, lista));
  raiz.append(seccion("El horizonte", zona, frase));
  repintar();
  return raiz;
}

/** En la organización: las acciones de todas sus empresas, ordenadas por lo que suben según el motor. */
function accionesEmpresas(d: DatosFicha, acc: Acciones): HTMLElement {
  const filas = d.empresas.flatMap((em) =>
    (em.ent?.months.find((m) => m.month === d.corte)?.actions ?? []).map(
      (a) => ({ em, a }),
    ),
  );
  filas.sort((x, y) => y.a.uplift_tenths - x.a.uplift_tenths);
  const lista = h("ul", { class: "acciones-empresas" });
  for (const { em, a } of filas.slice(0, 12)) {
    const li = h(
      "li",
      { class: "tocable", tabindex: "0" },
      h("b", {}, f.empresa(em.res.id)),
      h("span", { class: "ae-titulo" }, tituloAccion(a)),
      h(
        "span",
        { class: "ae-efecto" },
        `${f.delta(a.uplift_tenths)} · ${ESFUERZO[a.effort]}`,
      ),
    );
    const ir = () => acc.abrirEmpresa(em.res.id);
    li.addEventListener("click", ir);
    li.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") ir();
    });
    lista.append(li);
  }
  if (!filas.length)
    lista.append(
      h(
        "li",
        { class: "nota" },
        "Ninguna de sus empresas tiene acciones este mes.",
      ),
    );
  else if (filas.length > 12)
    lista.append(
      h(
        "li",
        { class: "nota" },
        `Y ${f.numero(filas.length - 12)} más en las fichas de cada empresa.`,
      ),
    );
  return h(
    "div",
    {},
    lista,
    h(
      "p",
      { class: "nota" },
      "El efecto es el que el motor calcula para cada empresa; en el grupo, lo que cuenta es la suma de sus flujos, así que no se suman.",
    ),
  );
}

function fraseHorizonte(d: DatosFicha, sel: Set<string>): string {
  const hb = d.hor?.scenarios?.base;
  if (!hb)
    return d.hor?.reason
      ? `Sin horizonte: ${d.hor.reason}`
      : "Sin horizonte para esta entidad.";
  if (d.hor!.cut !== d.corte)
    return `Los horizontes se calculan desde ${f.mes(d.hor!.cut)}.`;
  const partes = [
    `Si no hace nada, dentro de seis meses estará entre ${f.score(hb.q.p10[5])} y ${f.score(hb.q.p90[5])}.`,
  ];
  const accs = (d.hor!.actions ?? []).filter((a) => sel.has(a.id));
  if (accs.length === 1)
    partes.push(
      `Con esta acción, entre ${f.score(accs[0].q.p10[5])} y ${f.score(accs[0].q.p90[5])}; el motor la sitúa en ${f.score(accs[0].engine_new_score)} cuando se nota del todo (${f.plural(accs[0].lag_months, "mes", "meses")}).`,
    );
  else if (accs.length > 1) {
    const ids = accs
      .map((a) => a.id)
      .sort()
      .join();
    const combo = d.hor!.combos?.find((c) => [...c.ids].sort().join() === ids);
    partes.push(
      combo
        ? `Con las ${accs.length} juntas, el motor da ${f.score(combo.new_score)} cuando se notan del todo. Los abanicos azules son los de cada una por separado.`
        : `El motor no trae la cifra de estas ${accs.length} juntas; se ven los abanicos de cada una.`,
    );
  }
  return partes.join(" ");
}

function avisos(d: DatosFicha): HTMLElement {
  const caja = h("div", {});
  const pintar = () => {
    caja.replaceChildren(listaAvisos(d));
  };
  triaje.oir(() => {
    if (caja.isConnected) pintar();
  });
  pintar();
  return caja;
}

function listaAvisos(d: DatosFicha): HTMLElement {
  const lista = h("ul", { class: "avisos" });
  const umbral = d.params?.alerts.critical_score ?? null;
  const deEntidad = d.ent.alerts
    .filter((a) => a.month <= d.corte)
    .sort((a, b) => (a.month < b.month ? 1 : -1));
  const base = d.hor?.scenarios?.base;
  if (base?.cross && d.hor!.cut === d.corte && d.mes) {
    const baja =
      d.man.bands.findIndex((b) => b.key === base.cross!.to) <
      d.man.bands.findIndex((b) => b.key === d.mes!.band);
    lista.append(
      h(
        "li",
        { class: `aviso previsto ${baja ? "baja" : "sube"}` },
        h("span", { class: "av-grano hueco" }),
        h("span", { class: "av-mes" }, f.mesCorto(base.cross.month)),
        h(
          "span",
          { class: "av-texto" },
          `Previsto: si nada cambia, ${baja ? "baja" : "sube"} a ${nombreBanda(d.man, base.cross.to).toLowerCase()} (probabilidad ${f.porcentaje(base.cross.prob, 0)})`,
        ),
        h("span", { class: "av-estado" }, "horizonte"),
      ),
    );
  }
  const vivos = deEntidad.filter((a) => triaje.de(a.id) !== "descartado");
  for (const a of vivos.slice(0, 8))
    lista.append(lineaAviso(a, d.man, umbral, true));
  if (!lista.children.length)
    lista.append(h("li", { class: "nota" }, "Ningún aviso hasta este mes."));
  const descartados = deEntidad.length - vivos.length;
  const sinRevisar = vivos.filter((a) => !triaje.de(a.id)).length;
  lista.append(
    h(
      "li",
      { class: "nota" },
      [
        `${f.plural(sinRevisar, "aviso sin revisar", "avisos sin revisar")}`,
        descartados
          ? `${f.plural(descartados, "descartado", "descartados")} (se ven en Detalles)`
          : "",
        vivos.length > 8
          ? `${f.numero(vivos.length - 8)} más en Detalles`
          : "",
      ]
        .filter(Boolean)
        .join(" · ") + ". La clasificación se guarda en este navegador.",
    ),
  );
  return lista;
}

export function lineaAviso(
  a: AlertaM,
  man: Manifiesto,
  umbral: number | null,
  conTriaje = false,
): HTMLElement {
  const mejora =
    a.kind === "improvement_structural" || a.kind === "improvement_drift";
  const t = triaje.de(a.id);
  const li = h(
    "li",
    {
      class: `aviso ${mejora ? "sube" : "baja"} ${a.state} ${t ? `triaje-${t}` : ""}`,
    },
    h("span", { class: "av-grano" }),
    h("span", { class: "av-mes" }, f.mesCorto(a.month)),
    h(
      "span",
      { class: "av-texto", title: a.detail },
      lineaAvisoM(a, man, umbral),
    ),
    h(
      "span",
      {
        class: "av-estado",
        title: a.suppressed_by
          ? (man.glossary.reasons[a.suppressed_by.reason] ??
            a.suppressed_by.reason)
          : undefined,
      },
      t === "visto"
        ? `${ESTADO_AVISO[a.state]} · visto`
        : ESTADO_AVISO[a.state],
    ),
  );
  if (conTriaje) {
    const acciones = h("span", { class: "av-triaje" });
    const boton = (texto: string, valor: "visto" | "descartado" | null) => {
      const b = h("button", { type: "button", class: "av-boton" }, texto);
      b.addEventListener("click", (ev) => {
        ev.stopPropagation();
        triaje.fijar(a.id, valor);
      });
      acciones.append(b);
    };
    if (t) boton("Restaurar", null);
    else {
      boton("Marcar como visto", "visto");
      boton("Descartar", "descartado");
    }
    li.append(acciones);
  }
  return li;
}

// ─── Todo junto ───────────────────────────────────────────────

export function contenidoSeccion(
  d: DatosFicha,
  sec: Seccion,
  estadoUI: {
    escenario: OpcionesGrafico["escenario"];
    metrica: string;
    acciones: Set<string>;
    filtro?: FiltroEvidencia | null;
  },
  acc: Acciones,
  movil: boolean,
): HTMLElement {
  switch (sec) {
    case "scoring":
      return seccionScoring(d, estadoUI, acc, movil);
    case "productos":
      return seccionProductos(d, acc);
    case "acciones":
      return seccionAcciones(d, estadoUI.acciones, acc, movil);
    case "tecnico":
      return seccionTecnica(d, acc, estadoUI.filtro ?? null);
  }
}
