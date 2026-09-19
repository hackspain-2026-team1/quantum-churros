// El flujo de propuesta al cliente (sección Acciones): el usuario de Embat
// elige qué acciones ofrecer y con qué banco cada instrumento de financiación,
// genera una propuesta con trazabilidad (id, fecha, entidad, corte, hash del
// bundle) y la entrega como vista previa, PDF (impresión del navegador) o
// correo (mailto, el envío lo hace el navegador del usuario).
// Todo lo que se muestra sale del bundle y de products/: nada se inventa.

import { carga } from "../datos/carga";
import { f } from "../datos/formato";
import { fuentesDe, ofertasBanco, type FuentesBanco } from "../datos/ofertas";
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
  nombreBanda,
  nombrePilar,
  tituloAccion,
  explicacionAccion,
} from "../datos/redaccion";
import { h, vaciar } from "./dom";
import type { Acciones, DatosFicha } from "./ficha";

const CONFIANZA: Record<string, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
};

/** Bancos con los que la entidad trabaja: los suyos, o los de sus empresas si es grupo. */
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
    .filter((x) => bancos[x.id] !== null && bancos[x.id] !== undefined)
    .reduce((t, x) => t + x.uplift_tenths, 0);
  return Math.min(1000, m.shown + deAcciones + deFinanciacion);
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

  // — Acciones: checkboxes sincronizados con la selección del horizonte.
  const cajaAcciones = h("div", { class: "propuesta-grupo" });
  caja.append(cajaAcciones);
  const repintarAcciones = () => {
    vaciar(cajaAcciones);
    cajaAcciones.append(h("h3", {}, "Acciones que le ofreces"));
    for (const a of m.actions ?? []) {
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
          { class: "propuesta-fila" },
          marca,
          h(
            "div",
            {},
            h("p", { class: "propuesta-titulo" }, tituloAccion(a)),
            h(
              "p",
              { class: "propuesta-nota" },
              `${f.delta(a.uplift_tenths)} · esfuerzo ${ESFUERZO[a.effort]} · ${explicacionAccion(a)}`,
            ),
          ),
        ),
      );
    }
    if (!(m.actions ?? []).length)
      cajaAcciones.append(
        h("p", { class: "vacio" }, "El motor no propone acciones este mes."),
      );
  };

  // — Financiación: por instrumento, el banco de la organización.
  const cajaFinanciacion = h("div", { class: "propuesta-grupo" });
  caja.append(cajaFinanciacion);
  const repintarFinanciacion = () => {
    vaciar(cajaFinanciacion);
    cajaFinanciacion.append(h("h3", {}, "Financiación: elige el banco"));
    for (const x of m.financing ?? []) {
      if (!(x.id in bancos)) bancos[x.id] = null;
      const ofertas = ofertasBanco(x.kind, fuentes);
      const radios = [
        h(
          "label",
          { class: "propuesta-fila" },
          h("input", {
            type: "radio",
            name: x.id,
            checked: bancos[x.id] === null,
          }) as HTMLInputElement,
          h(
            "div",
            {},
            h(
              "p",
              { class: "propuesta-titulo" },
              "No ofrecer este instrumento",
            ),
          ),
        ),
      ];
      for (const o of ofertas) {
        const marca = h("input", {
          type: "radio",
          name: x.id,
          checked: bancos[x.id] === o.bank,
        }) as HTMLInputElement;
        marca.addEventListener("change", () => {
          bancos[x.id] = o.bank;
          repintarResumen();
        });
        radios.push(
          h(
            "label",
            { class: "propuesta-fila" },
            marca,
            h(
              "div",
              {},
              h("p", { class: "propuesta-titulo" }, o.bank),
              h(
                "p",
                { class: "propuesta-nota" },
                o.tieneProducto
                  ? "Ya le da este producto"
                  : "Trabaja con la entidad",
                o.rate !== null
                  ? ` · ${f.numero(o.rate, 2)} % ${o.rate_type === "variable" ? "variable" : "fijo"}`
                  : " · sin tasa publicada",
                o.granted !== null
                  ? ` · concedido ${f.eurosCorto(o.granted)}`
                  : "",
              ),
            ),
          ),
        );
      }
      radios[0].querySelector("input")!.addEventListener("change", () => {
        bancos[x.id] = null;
        repintarResumen();
      });
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
          ...radios,
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

  // — Resumen y botones.
  const zonaResumen = h("div", { class: "propuesta-resumen" });
  caja.append(zonaResumen);
  const repintarResumen = () => {
    const total = estimacionPlan(m, sel, bancos);
    vaciar(zonaResumen);
    zonaResumen.append(
      h(
        "p",
        { class: "propuesta-titulo" },
        `Score actual ${f.score(m.shown)} → con el plan ${f.score(total)} (${f.delta(total - m.shown)})`,
      ),
      h(
        "p",
        { class: "propuesta-nota" },
        "Estimación: cada cifra es del motor; la suma de varias acciones puede solaparse.",
      ),
    );
  };

  // — Vista previa del informe y entrega.
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
          rate: oferta?.rate ?? null,
          rate_type: oferta?.rate_type ?? null,
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

  // Radiografía: score, banda, confianza y pilares.
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

  // Avisos del corte.
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

  // El plan elegido.
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
          x.rate !== null ? ` · ${f.numero(x.rate, 2)} %` : "",
        ),
      ),
    ),
  );

  // Pie con trazabilidad.
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
        "Cada cifra la calcula el motor determinista sobre los datos de la entidad; ninguna promesa se estima a mano. Este informe no sustituye una oferta vinculante.",
      ),
    ),
  );
  return informe;
}
