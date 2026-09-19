// El flujo de propuesta al cliente (sección Acciones), en pantalla completa:
//   izquierda · el documento: vista previa en vivo de lo que se elige a la
//     derecha, o el historial de propuestas con su validación de cumplimiento
//     (lo medido en el corte contra lo medido en los meses posteriores);
//   derecha · los tres pasos: bancos conectados, acciones, financiación por
//     banco (tasa del banco cuando consta, si no estimación de mercado marcada).
// Enviar reporte por mail la guarda con trazabilidad (id, fecha, entidad,
// corte, hash del bundle), abre el correo del usuario y deja el informe
// final. El PDF es la misma hoja por impresión del navegador.

import { carga } from "../datos/carga";
import { f } from "../datos/formato";
import type {
  FacturaVencidaM,
  FinanciacionM,
  InvoicesDueM,
  SerieM,
} from "../datos/contrato";
import {
  bancosConectados,
  fuentesDe,
  ofertasBanco,
  type BancoConectado,
  type FuentesBanco,
} from "../datos/ofertas";
import {
  borrarPropuesta,
  enviarPropuestaPorMail,
  instrumentosDelMes,
  nuevaPropuestaId,
  sincronizarPropuestas,
  todasLasPropuestas,
  type AccionElegida,
  type FinanciacionElegida,
  type PropuestaGuardada,
} from "../datos/propuestas";
import {
  ESFUERZO,
  explicacionAccion,
  voz,
  nombreBanda,
  nombrePilar,
  tituloAccion,
  tituloFinanciacion,
} from "../datos/redaccion";
import {
  validarPropuesta,
  valorSerieEn,
  type EstadoAccion,
} from "../datos/seguimiento";
import { fuenteTexto } from "../datos/tasas";
import { h, vaciar } from "./dom";
import type { Acciones, DatosFicha } from "./ficha";
import { marcaBanco } from "./primitivos";

const nombreDe = (kind: "company" | "group", id: string) =>
  kind === "company" ? f.empresa(id) : f.grupo(id);

const CONFIANZA: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
};

/** Las medidas reales que el informe muestra en «la foto de este mes». */
const SERIES_FOTO: string[] = [
  "buffer_days",
  "cash_month_end",
  "headroom",
  "debt_burden",
  "ar_days_beyond_terms",
  "ap_days_beyond_terms",
];

const ESTADO_TEXTO: Record<EstadoAccion, string> = {
  cumplida: "cumplida",
  "en camino": "en camino",
  pendiente: "pendiente",
  "sin datos": "sin datos",
};

function fuentesDeFicha(d: DatosFicha): FuentesBanco {
  const propias = d.prodE;
  const empresas =
    d.kind === "group"
      ? d.empresas.map((e) => ({
          tenencias: e.prod?.held ?? [],
          otras: e.prod?.other_debt ?? [],
          bancos: e.prod?.banks ?? {},
        }))
      : [];
  return fuentesDe(
    propias?.held ?? [],
    propias?.other_debt ?? [],
    propias?.banks ?? {},
    empresas,
  );
}

function accionesDe(
  m: NonNullable<DatosFicha["mes"]>,
  sel: Set<string>,
): AccionElegida[] {
  return (m.actions ?? [])
    .filter((a) => sel.has(a.id))
    .map((a) => ({
      id: a.id,
      pillar: a.pillar,
      title: tituloAccion(a),
      uplift_tenths: a.uplift_tenths,
      new_score_tenths: a.new_score_tenths,
      current: a.current,
      target: a.target,
      unit: a.unit,
    }));
}

function financiacionDe(
  instrumentos: readonly FinanciacionM[],
  bancos: Record<string, string[]>,
  fuentes: FuentesBanco,
): FinanciacionElegida[] {
  const filas: FinanciacionElegida[] = [];
  for (const x of instrumentos) {
    const elegidos = bancos[x.id] ?? [];
    if (!elegidos.length) continue;
    const ofertas = ofertasBanco(x.kind, fuentes);
    for (const bank of elegidos) {
      const oferta = ofertas.find((o) => o.bank === bank) ?? null;
      filas.push({
        id: x.id,
        kind: x.kind,
        title: tituloFinanciacion(x),
        amount: x.amount,
        uplift_tenths: x.uplift_tenths,
        bank,
        rate: oferta?.oferta_tasa ?? null,
        rate_type: oferta?.rate_type ?? null,
        rate_fuente: oferta?.oferta_fuente ?? null,
      });
    }
  }
  return filas;
}

/** La estimación del plan: cada cifra es del motor; la suma puede solaparse y se marca como tal. */
function estimacionPlan(
  m: NonNullable<DatosFicha["mes"]>,
  acciones: AccionElegida[],
  financiacion: FinanciacionElegida[],
): number {
  const deAcciones = acciones.reduce((t, a) => t + a.uplift_tenths, 0);
  const nativos = new Set((m.financing ?? []).map((x) => x.id));
  const vistos = new Set<string>();
  const deFinanciacion = financiacion.reduce((t, x) => {
    if (!nativos.has(x.id) || vistos.has(x.id)) return t;
    vistos.add(x.id);
    return t + x.uplift_tenths;
  }, 0);
  return Math.min(1000, m.shown + deAcciones + deFinanciacion);
}

function paso(
  n: number,
  titulo: string,
  nota: string,
  cuerpo: HTMLElement,
): HTMLElement {
  return h(
    "section",
    { class: "propuesta-paso" },
    h(
      "div",
      { class: "propuesta-paso-cabeza" },
      h("span", { class: "propuesta-paso-n" }, String(n)),
      h(
        "div",
        {},
        h("h3", {}, titulo),
        h("p", { class: "propuesta-nota" }, nota),
      ),
    ),
    cuerpo,
  );
}

function tarjetaBanco(b: BancoConectado): HTMLElement {
  const creditos = b.productos.filter((p) => p.credito);
  const resumen = creditos.length
    ? creditos
        .slice(0, 2)
        .map((p) =>
          p.rate !== null
            ? `${p.producto} ${f.puntosPorcentaje(p.rate, 2)}`
            : p.producto,
        )
        .join(" · ")
    : b.productos.length
      ? b.productos[0].producto
      : "sin productos contratados";
  return h(
    "div",
    { class: "propuesta-banco" },
    h(
      "div",
      { class: "propuesta-banco-cabeza" },
      marcaBanco(b.bank, 18),
      h("p", { class: "propuesta-titulo" }, b.bank),
      b.otorga
        ? h(
            "span",
            { class: "propuesta-badge propuesta-badge-banco" },
            "ya te financia",
          )
        : "",
    ),
    h(
      "p",
      { class: "propuesta-nota" },
      b.cuentas
        ? f.plural(b.cuentas, "cuenta conectada", "cuentas conectadas")
        : "sin cuentas conectadas",
      creditos.length > 2 ? ` · ${resumen} · +${creditos.length - 2}` : ` · ${resumen}`,
    ),
  );
}

type Oferta = ReturnType<typeof ofertasBanco>[number];

function filaOferta(
  x: { id: string },
  oferta: Oferta,
  elegidos: string[],
  alElegir: (bank: string, on: boolean) => void,
): HTMLElement {
  const marca = h("input", {
    type: "checkbox",
    name: x.id,
    checked: elegidos.includes(oferta.bank),
  }) as HTMLInputElement;
  marca.addEventListener("change", () => alElegir(oferta.bank, marca.checked));
  return h(
    "label",
    {
      class: `propuesta-oferta${elegidos.includes(oferta.bank) ? " elegida" : ""}`,
    },
    h("span", { class: "propuesta-oferta-marca" }, marca),
    h(
      "span",
      { class: "propuesta-oferta-banco" },
      h(
        "span",
        { class: "propuesta-oferta-entidad" },
        marcaBanco(oferta.bank, 18),
        h("span", { class: "propuesta-titulo" }, oferta.bank),
      ),
      h(
        "span",
        { class: "propuesta-nota" },
        oferta.tieneProducto
          ? "Ya le da este producto a la entidad"
          : oferta.soloCuentas
            ? "Solo tiene cuentas: se ofrece con estimación de mercado"
            : "Trabaja con la entidad",
      ),
    ),
    h(
      "span",
      { class: "propuesta-oferta-tasa" },
      oferta.oferta_tasa !== null
        ? h(
            "span",
            { class: "propuesta-titulo" },
            f.puntosPorcentaje(oferta.oferta_tasa, 2),
          )
        : h("span", { class: "propuesta-titulo" }, "—"),
      oferta.oferta_fuente
        ? h(
            "span",
            {
              class: `propuesta-badge ${oferta.oferta_fuente === "banco" ? "propuesta-badge-banco" : "propuesta-badge-mercado"}`,
            },
            fuenteTexto(oferta.oferta_fuente),
          )
        : "",
    ),
  );
}

// ─── El documento (izquierda) ─────────────────────────────────

/** Lo que el informe necesita del plan: las elecciones del momento o lo guardado. */
interface PlanInforme {
  corte: string;
  score_actual_tenths: number;
  acciones: AccionElegida[];
  financiacion: FinanciacionElegida[];
}

function formatoSerie(s: SerieM, v: number | null): string {
  if (v === null) return "—";
  if (s.unit === "EUR") return f.eurosCorto(v);
  if (s.unit === "días") return `${f.numero(v, 1)} días`;
  if (s.unit === "ratio") return `${f.numero(v, 2)}×`;
  return `${f.numero(v, 1)}${s.unit === "%" ? " %" : ""}`;
}

/** «La foto de este mes»: las medidas reales del motor en el corte del informe. */
function bloqueFoto(
  d: DatosFicha,
  corte: string,
  cabecera: string,
): HTMLElement {
  const celdas: HTMLElement[] = [];
  for (const clave of SERIES_FOTO) {
    const s = d.ent.series.find((x) => x.key === clave);
    if (!s) continue;
    const v = valorSerieEn(d.ent, clave, corte);
    celdas.push(
      h(
        "div",
        { class: "informe-metrica" },
        h("span", { class: "informe-metrica-valor" }, formatoSerie(s, v)),
        h("span", { class: "informe-metrica-nombre" }, s.label),
      ),
    );
  }
  return h(
    "section",
    { class: "informe-bloque" },
    h("h2", {}, cabecera),
    h("div", { class: "informe-metricas" }, ...celdas),
  );
}

/** Las facturas vencidas abiertas del lado pedido, las más grandes que exporta el motor. */
function facturasDe(
  due: InvoicesDueM,
  d: DatosFicha,
  lado: "ar" | "ap",
): FacturaVencidaM[] {
  const mapa =
    d.kind === "company" ? due.rows[lado].companies : due.rows[lado].groups;
  return mapa[d.id] ?? [];
}

function bloqueFacturas(
  titulo: string,
  filas: FacturaVencidaM[],
  sinDatos: string,
): HTMLElement {
  if (!filas.length)
    return h(
      "section",
      { class: "informe-bloque" },
      h("h2", {}, titulo),
      h("p", { class: "informe-nota" }, sinDatos),
    );
  const tabla = h(
    "table",
    { class: "tabla-sutil" },
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "Contraparte"),
        h("th", {}, "Vencida el"),
        h("th", { class: "num" }, "Atraso"),
        h("th", { class: "num" }, "Importe"),
      ),
    ),
  );
  const cuerpo = h("tbody");
  for (const x of filas.slice(0, 8))
    cuerpo.append(
      h(
        "tr",
        {},
        h("td", {}, f.contraparte(x.counterparty_id)),
        h("td", {}, f.fecha(x.due_date)),
        h("td", { class: "num" }, f.dias(x.days_overdue)),
        h("td", { class: "num" }, f.eurosCorto(x.amount)),
      ),
    );
  tabla.append(cuerpo);
  return h(
    "section",
    { class: "informe-bloque" },
    h("h2", {}, titulo),
    tabla,
    h(
      "p",
      { class: "informe-nota" },
      "Solo las facturas vencidas y abiertas más grandes que exporta el motor; el total puede ser mayor.",
    ),
  );
}

/** El bloque de seguimiento de una propuesta guardada: lo prometido contra lo medido después. */
function bloqueSeguimiento(d: DatosFicha, p: PropuestaGuardada): HTMLElement {
  const seg = validarPropuesta(p, d.ent, d.mes);
  const filas: HTMLElement[] = [];
  const chip = (estado: EstadoAccion) =>
    h(
      "span",
      { class: `informe-chip estado-${estado.replace(/ /g, "-")}` },
      ESTADO_TEXTO[estado],
    );
  for (const v of seg.acciones)
    filas.push(
      h(
        "div",
        { class: "informe-seg" },
        chip(v.estado),
        h(
          "div",
          {},
          h("p", { class: "informe-item" }, h("b", {}, v.accion.title)),
          h(
            "p",
            { class: "informe-nota" },
            `${v.etiqueta} · apuntaba a ${v.accion.target !== null && v.accion.target !== undefined ? f.numero(v.accion.target, 1) : "—"} ${v.accion.unit === "ratio" ? "×" : (v.accion.unit ?? "")}`,
          ),
        ),
      ),
    );
  return h(
    "section",
    { class: "informe-bloque" },
    h("h2", {}, "Seguimiento: ¿se cumplió?"),
    h(
      "div",
      { class: "informe-seg-score" },
      h(
        "p",
        {},
        h("b", {}, "Score: "),
        `${f.score(seg.scoreAntes)} en ${f.mes(p.corte)} → ${seg.scoreAhora !== null ? f.score(seg.scoreAhora) : "—"} en ${f.mes(d.corte)}`,
      ),
      seg.scoreAhora !== null && seg.scoreAhora !== seg.scoreAntes
        ? h(
            "p",
            { class: "informe-nota" },
            f.delta(seg.scoreAhora - seg.scoreAntes),
          )
        : null,
    ),
    ...(seg.conMeses
      ? filas
      : [
          h(
            "p",
            { class: "informe-nota" },
            "Sin meses posteriores en el fichero: todavía no hay nada que validar.",
          ),
        ]),
  );
}

/** La hoja del informe tal como la ve el cliente: radiografía + foto real + plan + trazabilidad. */
async function construirInforme(
  d: DatosFicha,
  plan: PlanInforme,
  p: PropuestaGuardada | null,
): Promise<HTMLElement> {
  const m = d.mes;
  const informe = h("article", { class: "informe" });
  if (!m) return informe;
  const due = await carga.facturasVencidas();
  const ap = due ? facturasDe(due, d, "ap") : [];
  const ar = due ? facturasDe(due, d, "ar") : [];

  informe.append(
    h(
      "header",
      { class: "informe-cabecera" },
      h("p", { class: "versalita" }, voz("Rumbo · Embat · informe al cliente", "Rumbo · plan para el banco")),
      h("h1", {}, `Plan de mejora de ${nombreDe(d.kind, d.id)}`),
      h(
        "p",
        { class: "informe-sub" },
        `${d.kind === "company" ? "Empresa" : "Organización"} · corte ${f.mes(plan.corte)} · ${
          p
            ? `${voz("propuesta", "plan")} ${p.id} del ${f.fecha(p.fecha)}`
            : "borrador, aún sin enviar"
        }`,
      ),
    ),
  );

  const cascada = m.pillars.map((pi) =>
    h(
      "div",
      {},
      h("span", {}, nombrePilar(d.man, pi.key)),
      h(
        "span",
        { class: pi.contrib < 0 ? "neg" : "pos" },
        pi.score !== null
          ? `${f.score(pi.score)} (${f.delta(pi.contrib)})`
          : "no observable",
      ),
    ),
  );
  informe.append(
    h(
      "section",
      { class: "informe-bloque" },
      h("h2", {}, "La radiografía"),
      h(
        "div",
        { class: "informe-score" },
        h("p", { class: "informe-cifra" }, f.score(plan.score_actual_tenths)),
        h(
          "div",
          {},
          h("p", {}, nombreBanda(d.man, m.band)),
          h(
            "p",
            { class: "informe-nota" },
            `Confianza ${CONFIANZA[m.conf.label] ?? m.conf.label}.`,
          ),
        ),
      ),
      h("div", { class: "cascada" }, ...cascada),
    ),
  );

  informe.append(bloqueFoto(d, plan.corte, "La foto de este mes"));
  informe.append(
    bloqueFacturas(
      "Proveedores que esperan cobro",
      ap,
      "Ninguna factura de proveedor vencida y abierta consta este mes.",
    ),
  );
  informe.append(
    bloqueFacturas(
      "Clientes que te deben",
      ar,
      "Ninguna factura de cliente vencida y abierta consta este mes.",
    ),
  );

  const alertas = (await carga.alertas()).alerts.filter(
    (a) =>
      a.entity_id === d.id && a.month === plan.corte && a.state === "fired",
  );
  if (alertas.length)
    informe.append(
      h(
        "section",
        { class: "informe-bloque" },
        h("h2", {}, "Avisos activos"),
        ...alertas.map((a) =>
          h(
            "p",
            { class: "informe-aviso" },
            h("b", {}, a.title),
            " — ",
            a.detail,
          ),
        ),
      ),
    );

  informe.append(
    h(
      "section",
      { class: "informe-bloque" },
      h("h2", {}, "El plan"),
      ...(plan.acciones.length
        ? plan.acciones.map((a) =>
            h(
              "p",
              { class: "informe-item" },
              h("b", {}, a.title),
              ` · ${f.delta(a.uplift_tenths)} según el motor (score ${f.score(a.new_score_tenths)})`,
            ),
          )
        : [
            h(
              "p",
              { class: "informe-nota" },
              "Sin acciones elegidas todavía: márcalas en el panel de la derecha.",
            ),
          ]),
      ...plan.financiacion.map((x) =>
        h(
          "p",
          { class: "informe-item" },
          h("b", {}, x.title),
          x.bank ? ` · con ${x.bank}` : " · banco a convenir",
          x.amount !== null ? ` · ${f.eurosCorto(x.amount)}` : "",
          x.rate !== null
            ? ` · ${f.puntosPorcentaje(x.rate, 2)} ${x.rate_type === "variable" ? "variable" : "fijo"}`
            : "",
          x.rate_fuente
            ? h(
                "span",
                {
                  class: `propuesta-badge ${x.rate_fuente === "banco" ? "propuesta-badge-banco" : "propuesta-badge-mercado"}`,
                },
                fuenteTexto(x.rate_fuente),
              )
            : "",
        ),
      ),
      h(
        "p",
        { class: "informe-nota" },
        voz("Las tasas marcadas como estimación de mercado no son ofertas del banco: son referencias para la conversación. Este informe es una propuesta, no una oferta vinculante.", "Las tasas marcadas como estimación de mercado no son ofertas de tu banco: son referencias para la conversación. Este plan no es una solicitud firmada ni una oferta vinculante."),
      ),
    ),
  );

  if (p) informe.append(bloqueSeguimiento(d, p));

  informe.append(
    h(
      "footer",
      { class: "informe-pie" },
      h(
        "p",
        {},
        p
          ? `Id de ${voz("propuesta", "plan")} ${p.id} · bundle ${p.bundle_id.slice(0, 12)} · parámetros ${(d.params?.sha256 ?? "").slice(0, 12)} · motor ${d.man.engine_version}.`
          : `Borrador · bundle ${d.man.bundle_id.slice(0, 12)} · motor ${d.man.engine_version}.`,
      ),
      h(
        "p",
        {},
        "Cada cifra la calcula el motor determinista sobre los datos de la entidad; ninguna promesa se estima a mano.",
      ),
    ),
  );
  return informe;
}

// ─── La vista completa ────────────────────────────────────────

type Pestaña = "documento" | "historial";
/** Qué muestra el documento: el borrador en vivo o una propuesta guardada. */
type ModoDoc = { tipo: "borrador" } | { tipo: "final"; p: PropuestaGuardada };

export function abrirPropuesta(
  d: DatosFicha,
  sel: Set<string>,
  acc: Acciones,
): void {
  document.querySelectorAll(".panel-propuesta").forEach((n) => n.remove());
  const bancos: Record<string, string[]> = {};
  const fuentes = fuentesDeFicha(d);
  void sincronizarPropuestas(d.id);
  const fondo = h("div", { class: "panel-propuesta" });
  (document.querySelector("#app") ?? document.body).append(fondo);

  const m = d.mes;
  const instrumentos = m
    ? instrumentosDelMes(
        m.financing,
        d.kind === "group"
          ? d.empresas.map(
              (e) => e.ent?.months.find((x) => x.month === d.corte)?.financing,
            )
          : [],
      )
    : [];
  let pestaña: Pestaña = "documento";
  let modo: ModoDoc = { tipo: "borrador" };

  // — Barra superior: PDF siempre, mail vive en el pie del editor.
  const botonPdf = h(
    "button",
    { type: "button", class: "boton-propuesta", "data-pdf": "" },
    "Descargar PDF",
  );
  const cabecera = h(
    "header",
    { class: "propuesta-cabecera" },
    h(
      "div",
      {},
      h("p", { class: "versalita" }, voz("Propuesta al cliente", "Tu plan")),
      h(
        "h2",
        {},
        `${nombreDe(d.kind, d.id)} · ${m ? f.mes(m.month) : f.mes(d.corte)}`,
      ),
    ),
    h("div", { class: "propuesta-cabecera-acciones propuesta-entrega" }, botonPdf),
  );
  const cerrar = h(
    "button",
    {
      type: "button",
      class: "propuesta-cerrar",
      "aria-label": voz("Cerrar la propuesta", "Cerrar el plan"),
    },
    "Cerrar",
  );
  cerrar.addEventListener("click", () => fondo.remove());
  cabecera.append(cerrar);

  // — Izquierda: pestañas documento / historial.
  const pestañas = h("div", { class: "propuesta-pestanas", role: "tablist" });
  const botonPestaña = (clave: Pestaña, texto: string) => {
    const b = h(
      "button",
      {
        type: "button",
        role: "tab",
        class: `propuesta-pestana ${pestaña === clave ? "activa" : ""}`,
        "aria-selected": String(pestaña === clave),
      },
      texto,
    );
    b.addEventListener("click", () => {
      pestaña = clave;
      pintar();
    });
    pestañas.append(b);
  };
  botonPestaña("documento", "Documento");
  botonPestaña("historial", voz("Historial", "Planes enviados"));
  const zonaDoc = h("div", { class: "propuesta-doc" });
  const colDoc = h(
    "div",
    { class: "propuesta-col propuesta-col-doc" },
    pestañas,
    zonaDoc,
  );

  // — Derecha: los tres pasos + resumen + envío.
  const colEdit = h("div", { class: "propuesta-col propuesta-col-editor" });
  const zonaResumen = h("div", { class: "propuesta-resumen" });
  const listaPropuestas = h("div", { class: "propuesta-grupo" });

  // Cuerpo del editor (pasos), rellenable cuando hay mes.
  const cajaPasos = h("div", { class: "propuesta-pasos" });

  const pintar = () => {
    for (const b of pestañas.querySelectorAll("button")) {
      const activa =
        b.textContent === (pestaña === "documento" ? "Documento" : "Historial");
      b.classList.toggle("activa", activa);
      b.setAttribute("aria-selected", String(activa));
    }
    if (pestaña === "historial") {
      pintarHistorial();
      return;
    }
    if (modo.tipo === "final") {
      void pintarDocumento(modo.p);
    } else {
      void pintarDocumento(null);
    }
  };

  const pintarDocumento = async (p: PropuestaGuardada | null) => {
    if (!m) return;
    zonaDoc.replaceChildren(
      h("p", { class: "propuesta-nota" }, "Preparando el documento…"),
    );
    const plan: PlanInforme = p
      ? {
          corte: p.corte,
          score_actual_tenths: p.score_actual_tenths,
          acciones: p.acciones,
          financiacion: p.financiacion,
        }
      : {
          corte: d.corte,
          score_actual_tenths: m.shown,
          acciones: accionesDe(m, sel),
          financiacion: financiacionDe(instrumentos, bancos, fuentes),
        };
    zonaDoc.replaceChildren(await construirInforme(d, plan, p));
  };

  const pintarHistorial = () => {
    void sincronizarPropuestas(d.id).then(() => {
      if (pestaña !== "historial") return;
      dibujarHistorial();
    });
    dibujarHistorial();
  };

  const dibujarHistorial = () => {
    vaciar(zonaDoc);
    const hechas = todasLasPropuestas().filter((p) => p.entidad === d.id);
    const zona = h("div", { class: "propuesta-historial" });
    if (!hechas.length) {
      zona.append(
        h(
          "p",
          { class: "vacio" },
          voz("Todavía no se ha enviado ninguna propuesta para esta entidad. Elige acciones a la derecha y envía la primera por correo.", "Todavía no has enviado ningún plan. Elige acciones a la derecha y envía el primero a tu banco."),
        ),
      );
      zonaDoc.append(zona);
      return;
    }
    for (const p of hechas) {
      const seg = validarPropuesta(p, d.ent, d.mes);
      const fichas = seg.acciones
        .filter((v) => v.estado !== "sin datos")
        .map((v) => v.estado);
      const resumenEstado =
        fichas.length === 0
          ? seg.conMeses
            ? "sin métricas para validar"
            : "del corte actual"
          : `${f.plural(fichas.filter((e) => e === "cumplida").length, "cumplida", "cumplidas")} · ${f.plural(fichas.filter((e) => e !== "cumplida").length, "pendiente", "pendientes")}`;
      const fila = h(
        "div",
        { class: "propuesta-fila propuesta-hecha" },
        h(
          "div",
          { class: "propuesta-hecha-info" },
          h(
            "p",
            { class: "propuesta-titulo" },
            `${f.mes(p.corte)} · ${p.acciones.length} acción${p.acciones.length === 1 ? "" : "es"}${p.financiacion.length ? ` · ${p.financiacion.length} financiación` : ""}`,
          ),
          h(
            "p",
            { class: "propuesta-nota" },
            `${f.fecha(p.fecha)} · ${resumenEstado}`,
          ),
          seg.conMeses && seg.scoreAhora !== null
            ? h(
                "p",
                { class: "propuesta-nota seguimiento-score" },
                `score ${f.score(seg.scoreAntes)} → ${f.score(seg.scoreAhora)} (${f.delta(seg.scoreAhora - seg.scoreAntes)})`,
              )
            : "",
        ),
        h(
          "div",
          { class: "propuesta-hecha-botones" },
          h(
            "button",
            { type: "button", class: "boton-propuesta", "data-ver": p.id },
            "Ver",
          ),
          h(
            "button",
            { type: "button", class: "boton-peligro", "data-borrar": p.id },
            "Borrar",
          ),
        ),
      );
      fila.querySelector("[data-ver]")!.addEventListener("click", () => {
        modo = { tipo: "final", p };
        pestaña = "documento";
        pintar();
      });
      fila.querySelector("[data-borrar]")!.addEventListener("click", () => {
        borrarPropuesta(p.id);
        pintarHistorial();
      });
      zona.append(fila);
    }
    zonaDoc.append(zona);
  };

  // — Resumen con cifras + enviar por mail.
  const zonaCifras = h("div", { class: "propuesta-resumen-cifras-zona" });
  const avisoPie = h("p", { class: "propuesta-aviso", hidden: "true" });
  const botonMail = h(
    "button",
    { type: "button", class: "boton-propuesta", "data-mail": "" },
    voz("Enviar reporte por mail", "Enviar el plan a mi banco"),
  );
  botonMail.addEventListener("click", () => enviar());
  zonaResumen.append(
    zonaCifras,
    avisoPie,
    h("div", { class: "propuesta-botones" }, botonMail),
  );
  const planActual = () => {
    if (!m) return { acciones: [] as AccionElegida[], financiacion: [] as FinanciacionElegida[] };
    return {
      acciones: accionesDe(m, sel),
      financiacion: financiacionDe(instrumentos, bancos, fuentes),
    };
  };
  const repintarResumen = () => {
    if (!m) return;
    const { acciones, financiacion } = planActual();
    const hayPlan = acciones.length + financiacion.length > 0;
    botonMail.disabled = !hayPlan;
    avisoPie.hidden = hayPlan;
    avisoPie.textContent = hayPlan
      ? ""
      : voz("Marca al menos una acción o una financiación para enviar el reporte.", "Marca al menos una acción o una financiación para enviar el plan.");
    vaciar(zonaCifras);
    if (!hayPlan) {
      zonaCifras.append(
        h(
          "div",
          { class: "propuesta-resumen-cifras" },
          h("span", { class: "propuesta-resumen-score" }, f.score(m.shown)),
        ),
        h(
          "p",
          { class: "propuesta-nota" },
          "Score de este mes. El efecto del plan aparece cuando eliges acciones o un banco.",
        ),
      );
      return;
    }
    const total = estimacionPlan(m, acciones, financiacion);
    zonaCifras.append(
      h(
        "div",
        { class: "propuesta-resumen-cifras" },
        h("span", { class: "propuesta-resumen-score" }, f.score(m.shown)),
        h("span", { class: "propuesta-resumen-flecha" }, "→"),
        h(
          "span",
          { class: "propuesta-resumen-score propuesta-resumen-nueva" },
          f.score(total),
        ),
        h(
          "span",
          { class: "propuesta-resumen-delta" },
          `(${f.delta(total - m.shown)})`,
        ),
      ),
      h(
        "p",
        { class: "propuesta-nota" },
        "Estimación: cada cifra es del motor; la suma de varias acciones puede solaparse.",
      ),
    );
  };

  const enviar = () => {
    if (!m) return;
    const { acciones, financiacion } = planActual();
    if (!acciones.length && !financiacion.length) {
      avisoPie.hidden = false;
      avisoPie.textContent =
        voz("Marca al menos una acción o una financiación para enviar el reporte.", "Marca al menos una acción o una financiación para enviar el plan.");
      return;
    }
    const p: PropuestaGuardada = {
      id: nuevaPropuestaId(),
      fecha: new Date().toISOString(),
      kind: d.kind,
      entidad: d.id,
      grupoId: d.grupoId,
      corte: d.corte,
      bundle_id: d.man.bundle_id,
      score_actual_tenths: m.shown,
      acciones,
      financiacion,
    };
    enviarPropuestaPorMail(p);
    modo = { tipo: "final", p };
    pestaña = "documento";
    pintar();
  };

  botonPdf.addEventListener("click", () => {
    document.body.classList.add("imprimir-propuesta");
    window.print();
  });

  // — Montaje.
  fondo.append(
    h(
      "div",
      { class: "propuesta-hoja" },
      cabecera,
      h("div", { class: "propuesta-cuerpo" }, colDoc, colEdit),
    ),
  );

  if (!m) {
    colEdit.append(
      h(
        "p",
        { class: "vacio" },
        `Sin datos de ${nombreDe(d.kind, d.id)} en ${f.mes(d.corte)}: no hay plan que preparar.`,
      ),
    );
    pintar();
    return;
  }

  // — Paso 1 · Tus bancos conectados.
  const conectados = bancosConectados(fuentes);
  cajaPasos.append(
    paso(
      1,
      "Tus bancos conectados",
      conectados.length
        ? `${f.plural(conectados.length, "banco conectado", "bancos conectados")}. El sello «ya te financia» marca a los que ya ${voz("le dan", "te dan")} crédito.`
        : voz("El fichero no declara bancos para esta entidad.", "No hay bancos declarados en tus datos."),
      conectados.length
        ? h("div", { class: "propuesta-bancos" }, ...conectados.map(tarjetaBanco))
        : h("div", {}),
    ),
  );

  // — Paso 2 · Acciones.
  const cajaAcciones = h("div", { class: "propuesta-acciones" });
  cajaPasos.append(
    paso(
      2,
      voz("Acciones que le ofreces", "Acciones que vas a hacer"),
      "Cada cifra la calcula el motor: la acción aplicada al mes, re-puntuado entero.",
      cajaAcciones,
    ),
  );
  const repintarAcciones = () => {
    vaciar(cajaAcciones);
    for (const [i, a] of (m.actions ?? []).entries()) {
      const marca = h("input", {
        type: "checkbox",
        checked: sel.has(a.id),
      }) as HTMLInputElement;
      marca.addEventListener("change", () => {
        acc.horizonte.alternar(a.id, marca.checked);
        acc.repintarArena();
        repintarResumen();
        // tocar la elección vuelve el documento al borrador en vivo
        modo = { tipo: "borrador" };
        if (pestaña === "documento") void pintarDocumento(null);
      });
      cajaAcciones.append(
        h(
          "label",
          { class: `propuesta-accion ${sel.has(a.id) ? "elegida" : ""}` },
          h("span", { class: "propuesta-accion-marca" }, marca),
          h(
            "span",
            { class: "propuesta-accion-cuerpo" },
            h(
              "span",
              { class: "propuesta-titulo" },
              `${i + 1}. ${tituloAccion(a)}`,
            ),
            h(
              "span",
              { class: "propuesta-nota" },
              `${explicacionAccion(a)} · ${ESFUERZO[a.effort]}`,
            ),
          ),
          h(
            "span",
            { class: "propuesta-accion-efecto" },
            f.delta(a.uplift_tenths),
          ),
        ),
      );
    }
    if (!(m.actions ?? []).length)
      cajaAcciones.append(
        h("p", { class: "vacio" }, "El motor no propone acciones este mes."),
      );
  };

  // — Paso 3 · Financiación por banco.
  const cajaFinanciacion = h("div", { class: "propuesta-financiacion" });
  cajaPasos.append(
    paso(
      3,
      voz("Financiación: el banco que la otorga", "Financiación: a quién se la pides"),
      "Cada instrumento del motor, con tus bancos conectados. Marca uno o varios; la tasa es la del banco o una estimación de mercado.",
      cajaFinanciacion,
    ),
  );
  const nativos = new Set((m.financing ?? []).map((x) => x.id));
  const repintarFinanciacion = () => {
    vaciar(cajaFinanciacion);
    for (const x of instrumentos) {
      if (!(x.id in bancos)) bancos[x.id] = [];
      const ofertas = ofertasBanco(x.kind, fuentes);
      const elegidos = bancos[x.id] ?? [];
      const alCambiar = () => {
        repintarResumen();
        modo = { tipo: "borrador" };
        if (pestaña === "documento") void pintarDocumento(null);
      };
      const lista = h("div", { class: "propuesta-ofertas" });
      const ninguna = h("input", {
        type: "checkbox",
        name: `${x.id}-ninguno`,
        checked: elegidos.length === 0,
      }) as HTMLInputElement;
      ninguna.addEventListener("change", () => {
        bancos[x.id] = [];
        vaciar(lista);
        pintarFilas();
        alCambiar();
      });
      const pintarFilas = () => {
        const actual = bancos[x.id] ?? [];
        ninguna.checked = actual.length === 0;
        vaciar(lista);
        lista.append(
          h(
            "label",
            {
              class: `propuesta-oferta${actual.length === 0 ? " elegida" : ""}`,
            },
            h("span", { class: "propuesta-oferta-marca" }, ninguna),
            h(
              "span",
              { class: "propuesta-oferta-banco" },
              h(
                "span",
                { class: "propuesta-titulo" },
                voz("Ninguno de tus bancos: Embat lo licita", "Ninguno de tus bancos: que Embat busque ofertas"),
              ),
            ),
            h("span", { class: "propuesta-oferta-tasa" }, ""),
          ),
        );
        for (const o of ofertas)
          lista.append(
            filaOferta(x, o, actual, (bank, on) => {
              const set = new Set(bancos[x.id] ?? []);
              if (on) set.add(bank);
              else set.delete(bank);
              bancos[x.id] = [...set];
              pintarFilas();
              alCambiar();
            }),
          );
        if (!ofertas.length) {
          vaciar(lista);
          lista.append(
            h(
              "p",
              { class: "propuesta-nota" },
              voz("La entidad no tiene bancos en el fichero: Embat lo licita.", "No tienes bancos declarados: que Embat busque ofertas."),
            ),
          );
        }
      };
      pintarFilas();
      cajaFinanciacion.append(
        h(
          "div",
          { class: "propuesta-instrumento" },
          h(
            "p",
            { class: "propuesta-titulo" },
            `${tituloFinanciacion(x)}${x.amount !== null ? ` · ${f.eurosCorto(x.amount)}` : ""}${nativos.has(x.id) ? ` · ${f.delta(x.uplift_tenths)}` : " · efecto en las empresas"}`,
          ),
          h("p", { class: "propuesta-nota" }, x.detail),
          lista,
        ),
      );
    }
    if (!instrumentos.length)
      cajaFinanciacion.append(
        h(
          "p",
          { class: "vacio" },
          voz("Este mes el motor no encuentra financiación que ofrecer.", "Este mes el motor no ve financiación que recomendarte."),
        ),
      );
  };

  colEdit.append(cajaPasos, zonaResumen);
  void listaPropuestas; // el historial vive en la pestaña de la izquierda

  repintarAcciones();
  repintarFinanciacion();
  repintarResumen();
  pintar();
}
