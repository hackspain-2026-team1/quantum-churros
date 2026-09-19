// El flujo de propuesta al cliente (sección Acciones), en tres pasos:
//   1. Tus bancos conectados: la relación real de la entidad, banco por banco.
//   2. Acciones: qué ofrecer, con el efecto que calculó el motor.
//   3. Financiación: por instrumento, qué banco lo otorga, con su tasa (la del
//      banco cuando consta, si no una estimación de mercado siempre marcada).
// Generar propuesta la guarda con trazabilidad (id, fecha, entidad, corte,
// hash del bundle) y abre el informe del cliente: radiografía + plan. Entrega:
// PDF por impresión del navegador o mailto (el envío lo hace el usuario).

import { carga } from "../datos/carga";
import { f } from "../datos/formato";
import {
  bancosConectados,
  fuentesDe,
  ofertasBanco,
  type BancoConectado,
  type FuentesBanco,
} from "../datos/ofertas";
import {
  borrarPropuesta,
  correoPropuesta,
  guardarPropuesta,
  nuevaPropuestaId,
  propuestasDe,
  type PropuestaGuardada,
} from "../datos/propuestas";
import {
  ESFUERZO,
  explicacionAccion,
  nombreBanda,
  nombrePilar,
  tituloAccion,
} from "../datos/redaccion";
import { fuenteTexto } from "../datos/tasas";
import { h, vaciar } from "./dom";
import type { Acciones, DatosFicha } from "./ficha";

const CONFIANZA: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
};

function fuentesDeFicha(d: DatosFicha): FuentesBanco {
  const propias = d.prodE;
  const empresas =
    d.kind === "group"
      ? d.empresas.map((e) => ({
          tenencias: e.prod?.held ?? [],
          otras: e.prod?.other_debt ?? [],
          cuentas: Object.keys(e.prod?.accounts ?? {}),
        }))
      : [];
  return fuentesDe(
    propias?.held ?? [],
    propias?.other_debt ?? [],
    Object.keys(propias?.accounts ?? {}),
    empresas,
  );
}

/** La estimación del plan: cada cifra es del motor; la suma puede solaparse y se marca como tal. */
function estimacionPlan(
  m: NonNullable<DatosFicha["mes"]>,
  acciones: Set<string>,
  bancos: Record<string, string | null>,
): number {
  const deAcciones = (m.actions ?? [])
    .filter((a) => acciones.has(a.id))
    .reduce((t, a) => t + a.uplift_tenths, 0);
  const deFinanciacion = (m.financing ?? [])
    .filter((x) => bancos[x.id])
    .reduce((t, x) => t + x.uplift_tenths, 0);
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
  const lineas = b.productos.length
    ? b.productos.map((p) =>
        h(
          "p",
          { class: "propuesta-banco-producto" },
          p.producto,
          p.granted !== null
            ? h("span", {}, ` · ${f.eurosCorto(p.granted)}`)
            : "",
          p.rate !== null
            ? h(
                "span",
                { class: "propuesta-badge propuesta-badge-banco" },
                `${f.numero(p.rate, 2)} % ${p.rate_type === "variable" ? "variable" : "fijo"} · del banco`,
              )
            : "",
        ),
      )
    : [
        h(
          "p",
          { class: "propuesta-banco-producto" },
          "sin productos contratados",
        ),
      ];
  return h(
    "div",
    { class: "propuesta-banco" },
    h("p", { class: "propuesta-titulo" }, b.bank),
    h(
      "p",
      { class: "propuesta-nota" },
      b.cuentas
        ? `${b.cuentas} ${b.cuentas === 1 ? "cuenta" : "cuentas"} conectadas`
        : "sin cuentas conectadas",
    ),
    ...lineas,
  );
}

type Oferta = ReturnType<typeof ofertasBanco>[number];

function filaOferta(
  x: { id: string },
  oferta: Oferta,
  elegido: string | null,
  alElegir: (bank: string) => void,
): HTMLElement {
  const marca = h("input", {
    type: "radio",
    name: x.id,
    checked: elegido === oferta.bank,
  }) as HTMLInputElement;
  marca.addEventListener("change", () => alElegir(oferta.bank));
  return h(
    "label",
    { class: "propuesta-oferta" },
    h("span", { class: "propuesta-oferta-marca" }, marca),
    h(
      "span",
      { class: "propuesta-oferta-banco" },
      h("span", { class: "propuesta-titulo" }, oferta.bank),
      h(
        "span",
        { class: "propuesta-nota" },
        oferta.tieneProducto
          ? "Ya le da este producto a la entidad"
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
            `${f.numero(oferta.oferta_tasa, 2)} %`,
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

export function abrirPropuesta(
  d: DatosFicha,
  sel: Set<string>,
  acc: Acciones,
): void {
  document.querySelectorAll(".panel-propuesta").forEach((n) => n.remove());
  const bancos: Record<string, string | null> = {};
  const fuentes = fuentesDeFicha(d);
  const fondo = h("div", { class: "panel-propuesta" });
  const caja = h("div", { class: "panel-propuesta-caja" });
  fondo.append(caja);
  fondo.addEventListener("click", (ev) => {
    if (ev.target === fondo) fondo.remove();
  });

  const m = d.mes;
  caja.append(
    h(
      "header",
      { class: "propuesta-cabecera" },
      h(
        "div",
        {},
        h("p", { class: "versalita" }, "Propuesta al cliente"),
        h("h2", {}, `${d.id} · ${m ? f.mes(m.month) : f.mes(d.corte)}`),
      ),
      h(
        "button",
        {
          type: "button",
          class: "boton-sutil",
          "aria-label": "Cerrar la propuesta",
        },
        "Cerrar",
      ),
    ),
  );
  (caja.querySelector("button") as HTMLElement).addEventListener("click", () =>
    fondo.remove(),
  );

  if (!m) {
    caja.append(
      h(
        "p",
        { class: "vacio" },
        `Sin datos de ${d.id} en ${f.mes(d.corte)}: no hay propuesta que armar.`,
      ),
    );
    (document.querySelector("#app") ?? document.body).append(fondo);
    return;
  }

  // — Paso 1 · Tus bancos conectados.
  const conectados = bancosConectados(fuentes);
  caja.append(
    paso(
      1,
      "Tus bancos conectados",
      "Con estos bancos trabaja la organización: cuentas y productos contratados, con su tasa cuando consta.",
      h(
        "div",
        { class: "propuesta-bancos" },
        ...(conectados.length
          ? conectados.map(tarjetaBanco)
          : [
              h(
                "p",
                { class: "vacio" },
                "El fichero no declara bancos para esta entidad.",
              ),
            ]),
      ),
    ),
  );

  // — Paso 2 · Acciones.
  const cajaAcciones = h("div", { class: "propuesta-acciones" });
  caja.append(
    paso(
      2,
      "Acciones que le ofreces",
      "Cada cifra la calcula el motor: la acción aplicada al mes, re-puntuado entero.",
      cajaAcciones,
    ),
  );
  const zonaResumen = h("div", { class: "propuesta-resumen" });
  caja.append(zonaResumen);
  const repintarResumen = () => {
    const total = estimacionPlan(m, sel, bancos);
    vaciar(zonaResumen);
    zonaResumen.append(
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
  const repintarAcciones = () => {
    vaciar(cajaAcciones);
    for (const [i, a] of (m.actions ?? []).entries()) {
      const marca = h("input", {
        type: "checkbox",
        checked: sel.has(a.id),
      }) as HTMLInputElement;
      marca.addEventListener("change", () => {
        if (marca.checked) sel.add(a.id);
        else sel.delete(a.id);
        acc.repintarArena();
        repintarResumen();
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
              `${explicacionAccion(a)} · esfuerzo ${ESFUERZO[a.effort]}`,
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
  caja.append(
    paso(
      3,
      "Financiación: el banco que la otorga",
      "Solo los instrumentos que el motor recomienda este mes, con el monto calculado y la tasa ofrecida (del banco, o estimación de mercado marcada).",
      cajaFinanciacion,
    ),
  );
  const repintarFinanciacion = () => {
    vaciar(cajaFinanciacion);
    for (const x of m.financing ?? []) {
      if (!(x.id in bancos)) {
        const primeras = ofertasBanco(x.kind, fuentes);
        bancos[x.id] = primeras.length ? primeras[0].bank : null; // la mejor opción ya viene marcada
      }
      const ofertas = ofertasBanco(x.kind, fuentes);
      const ninguna = h("input", {
        type: "radio",
        name: x.id,
        checked: bancos[x.id] === null,
      }) as HTMLInputElement;
      ninguna.addEventListener("change", () => {
        bancos[x.id] = null;
        repintarResumen();
      });
      const filas: HTMLElement[] = [
        h(
          "label",
          { class: "propuesta-oferta" },
          h("span", { class: "propuesta-oferta-marca" }, ninguna),
          h(
            "span",
            { class: "propuesta-oferta-banco" },
            h(
              "span",
              { class: "propuesta-titulo" },
              "Ninguno de tus bancos lo ofrece: Embat lo licita",
            ),
          ),
          h("span", { class: "propuesta-oferta-tasa" }, ""),
        ),
      ];
      for (const o of ofertas)
        filas.push(
          filaOferta(x, o, bancos[x.id], (bank) => {
            bancos[x.id] = bank;
            repintarResumen();
          }),
        );
      if (!ofertas.length)
        filas[0].replaceWith(
          h(
            "p",
            { class: "propuesta-nota" },
            "La entidad no tiene bancos en el fichero: Embat lo licita.",
          ),
        );
      cajaFinanciacion.append(
        h(
          "div",
          { class: "propuesta-instrumento" },
          h(
            "p",
            { class: "propuesta-titulo" },
            `${x.title}${x.amount !== null ? ` · ${f.eurosCorto(x.amount)}` : ""} · ${f.delta(x.uplift_tenths)}`,
          ),
          h("p", { class: "propuesta-nota" }, x.detail),
          ...filas,
        ),
      );
    }
    if (!(m.financing ?? []).length)
      cajaFinanciacion.append(
        h(
          "p",
          { class: "vacio" },
          "Este mes el motor no encuentra financiación que ofrecer.",
        ),
      );
  };

  // — Vista previa del informe, entrega y lista de propuestas.
  const zonaInforme = h("div", { class: "propuesta-informe" });
  caja.append(zonaInforme);
  const listaPropuestas = h("div", { class: "propuesta-grupo" });
  caja.append(listaPropuestas);
  const repintarPropuestas = () => {
    vaciar(listaPropuestas);
    listaPropuestas.append(h("h3", {}, "Propuestas de este corte"));
    const hechas = propuestasDe(d.id, d.corte);
    if (!hechas.length) {
      listaPropuestas.append(
        h(
          "p",
          { class: "vacio" },
          "Todavía ninguna. Generá la primera con el botón de abajo.",
        ),
      );
      return;
    }
    for (const p of hechas) {
      const fila = h(
        "div",
        { class: "propuesta-fila propuesta-hecha" },
        h(
          "div",
          {},
          h(
            "p",
            { class: "propuesta-titulo" },
            `${f.mes(p.corte)} · ${p.acciones.length} acción${p.acciones.length === 1 ? "" : "es"}${p.financiacion.length ? ` · ${p.financiacion.length} financiación` : ""}`,
          ),
          h(
            "p",
            { class: "propuesta-nota" },
            `${p.fecha.slice(0, 16).replace("T", " ")} · bundle ${p.bundle_id.slice(0, 12)}`,
          ),
        ),
        h(
          "button",
          { type: "button", class: "boton-sutil", "data-ver": p.id },
          "Ver",
        ),
        h(
          "button",
          { type: "button", class: "boton-sutil", "data-borrar": p.id },
          "Borrar",
        ),
      );
      fila.querySelector("[data-ver]")!.addEventListener("click", () => {
        void mostrarInforme(p);
      });
      fila.querySelector("[data-borrar]")!.addEventListener("click", () => {
        borrarPropuesta(p.id);
        repintarPropuestas();
      });
      listaPropuestas.append(fila);
    }
  };

  const mostrarInforme = async (p: PropuestaGuardada) => {
    const informe = await construirInforme(d, p);
    vaciar(zonaInforme);
    zonaInforme.append(
      h(
        "div",
        { class: "propuesta-entrega" },
        h("button", { type: "button", "data-pdf": "" }, "Descargar PDF"),
        h("button", { type: "button", "data-mail": "" }, "Enviar por mail"),
        h(
          "button",
          { type: "button", class: "boton-sutil", "data-cerrar": "" },
          "Cerrar vista",
        ),
      ),
      informe,
    );
    zonaInforme
      .querySelector("[data-pdf]")!
      .addEventListener("click", () => window.print());
    zonaInforme.querySelector("[data-mail]")!.addEventListener("click", () => {
      const { asunto, cuerpo } = correoPropuesta(p);
      window.location.href = `mailto:?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(cuerpo)}`;
    });
    zonaInforme
      .querySelector("[data-cerrar]")!
      .addEventListener("click", () => vaciar(zonaInforme));
    zonaInforme.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const generar = async () => {
    const elegidas = (m.actions ?? [])
      .filter((a) => sel.has(a.id))
      .map((a) => ({
        id: a.id,
        pillar: a.pillar,
        title: tituloAccion(a),
        uplift_tenths: a.uplift_tenths,
        new_score_tenths: a.new_score_tenths,
      }));
    const financiacion = (m.financing ?? [])
      .filter((x) => bancos[x.id])
      .map((x) => {
        const oferta =
          ofertasBanco(x.kind, fuentes).find((o) => o.bank === bancos[x.id]) ??
          null;
        return {
          id: x.id,
          kind: x.kind,
          title: x.title,
          amount: x.amount,
          uplift_tenths: x.uplift_tenths,
          bank: bancos[x.id],
          rate: oferta?.oferta_tasa ?? null,
          rate_type: oferta?.rate_type ?? null,
          rate_fuente: oferta?.oferta_fuente ?? null,
        };
      });
    if (!elegidas.length && !financiacion.length) return;
    const p: PropuestaGuardada = {
      id: nuevaPropuestaId(),
      fecha: new Date().toISOString(),
      kind: d.kind,
      entidad: d.id,
      grupoId: d.grupoId,
      corte: d.corte,
      bundle_id: d.man.bundle_id,
      score_actual_tenths: m.shown,
      acciones: elegidas,
      financiacion,
    };
    guardarPropuesta(p);
    repintarPropuestas();
    await mostrarInforme(p);
  };

  caja.append(
    h(
      "div",
      { class: "propuesta-botones" },
      h("button", { type: "button", "data-generar": "" }, "Generar propuesta"),
    ),
  );
  caja.querySelector("[data-generar]")!.addEventListener("click", () => {
    void generar();
  });

  repintarAcciones();
  repintarFinanciacion();
  repintarResumen();
  repintarPropuestas();
  (document.querySelector("#app") ?? document.body).append(fondo);
}

/** La hoja del informe tal como la ve el cliente: radiografía + plan + trazabilidad. */
async function construirInforme(
  d: DatosFicha,
  p: PropuestaGuardada,
): Promise<HTMLElement> {
  const m = d.mes;
  const informe = h("article", { class: "informe" });
  if (!m) return informe;

  informe.append(
    h(
      "header",
      { class: "informe-cabecera" },
      h("p", { class: "versalita" }, "Rumbo · Embat · informe al cliente"),
      h("h1", {}, `Plan de mejora de ${d.id}`),
      h(
        "p",
        { class: "informe-sub" },
        `${d.kind === "company" ? "Empresa" : "Organización"} · corte ${f.mes(p.corte)} · preparado el ${p.fecha.slice(0, 10)}`,
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
        h("p", { class: "informe-cifra" }, f.score(m.shown)),
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

  const alertas = (await carga.alertas()).alerts.filter(
    (a) => a.entity_id === d.id && a.month === p.corte && a.state === "fired",
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
      ...p.acciones.map((a) =>
        h(
          "p",
          { class: "informe-item" },
          h("b", {}, a.title),
          ` · ${f.delta(a.uplift_tenths)} según el motor (score ${f.score(a.new_score_tenths)})`,
        ),
      ),
      ...p.financiacion.map((x) =>
        h(
          "p",
          { class: "informe-item" },
          h("b", {}, x.title),
          x.bank ? ` · con ${x.bank}` : "",
          x.amount !== null ? ` · ${f.eurosCorto(x.amount)}` : "",
          x.rate !== null
            ? ` · ${f.numero(x.rate, 2)} % ${x.rate_fuente ? `(${fuenteTexto(x.rate_fuente)})` : ""}`
            : "",
        ),
      ),
      h(
        "p",
        { class: "informe-nota" },
        "Las tasas marcadas como estimación de mercado no son ofertas del banco: son referencias para la conversación. Este informe es una propuesta, no una oferta vinculante.",
      ),
    ),
  );

  informe.append(
    h(
      "footer",
      { class: "informe-pie" },
      h(
        "p",
        {},
        `Id de propuesta ${p.id} · bundle ${p.bundle_id.slice(0, 12)} · parámetros ${(d.params?.sha256 ?? "").slice(0, 12)} · motor ${d.man.engine_version}.`,
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
