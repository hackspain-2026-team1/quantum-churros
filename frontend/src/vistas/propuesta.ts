// Confirmación de acciones y financiación con los bancos conectados, sin documento PDF.
import { f } from '../datos/formato';
import type { FinanciacionM } from '../datos/contrato';
import { bancosConectados, fuentesDe, ofertasBanco, type BancoConectado, type FuentesBanco } from '../datos/ofertas';
import { instrumentosDelMes, type AccionElegida, type FinanciacionElegida } from '../datos/propuestas';
import { ESFUERZO, explicacionAccion, tituloAccion, tituloFinanciacion } from '../datos/redaccion';
import { fuenteTexto } from '../datos/tasas';
import { h } from './dom';
import type { DatosFicha } from './ficha';
import { marcaBanco } from './primitivos';
const nombreDe = (kind: 'company' | 'group', id: string) => kind === 'company' ? f.empresa(id) : f.grupo(id);

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

/** Confirmation keeps the existing banking workflow; there is no document preview. */
export function abrirConfirmacionAcciones(
  d: DatosFicha,
  elegidas: Set<string>,
  existentes: Set<string>,
  confirmar: (ids: string[], financiacion: import('../datos/ejecuciones').EleccionFinanciacion[]) => Promise<void>,
): void {
  if (!d.mes || document.querySelector('.confirmacion-acciones')) return;
  const m = d.mes, sel = new Set(elegidas), bancos: Record<string, string[]> = {};
  const activas = new Set<string>();
  const fuentes = fuentesDeFicha(d);
  const instrumentos = instrumentosDelMes(m.financing, d.kind === 'group' ? d.empresas.map(e => e.ent?.months.find(x => x.month === d.corte)?.financing) : []);
  const origen = document.activeElement as HTMLElement | null;
  const fondo = h('div', { class: 'panel-propuesta confirmacion-acciones', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'confirmacion-titulo' });
  const cerrar = h('button', { type: 'button', class: 'propuesta-cerrar', 'aria-label': 'Cerrar confirmación' }, 'Cancelar');
  const guardar = h('button', { type: 'button', class: 'boton-propuesta' }, 'Confirmar y ejecutar');
  const error = h('p', { role: 'alert', class: 'ejecuciones-error' });
  const resumen = h('div', { class: 'confirmacion-resumen', 'aria-live': 'polite' });
  const pasos = h('div', { class: 'propuesta-pasos' });
  let guardando = false;
  const salir = () => { if (guardando) return; fondo.remove(); origen?.focus(); };
  cerrar.addEventListener('click', salir);
  const ids = () => [...sel].filter(id => !existentes.has(id));
  const finElegida = (): import('../datos/ejecuciones').EleccionFinanciacion[] => {
    const resultado: import('../datos/ejecuciones').EleccionFinanciacion[] = [];
    for (const x of instrumentos.filter(x => activas.has(x.id))) {
      const propias = (m.financing ?? []).some(p => p.id === x.id);
      const destinos = propias ? [{ entity_id: d.id, id: x.id }] : d.empresas.flatMap(e => (e.ent?.months.find(p => p.month === d.corte)?.financing ?? []).filter(p => p.kind === x.kind).map(p => ({ entity_id: e.res.id, id: p.id })));
      for (const destino of destinos) if (!existentes.has(`financing:${destino.entity_id}:${destino.id}`)) resultado.push({ ...destino, banks: bancos[x.id] ?? [] });
    }
    return resultado;
  };
  const actualizar = () => {
    const acciones = accionesDe(m, new Set(ids()));
    const fin = financiacionDe(instrumentos.filter(x => activas.has(x.id)), bancos, fuentes);
    resumen.replaceChildren(h('b', {}, `${f.plural(acciones.length, 'acción', 'acciones')} · ${f.plural(activas.size, 'gestión de financiación', 'gestiones de financiación')}`), h('p', { class: 'propuesta-nota' }, 'Al confirmar se guardan tus decisiones y los bancos elegidos. No se envían solicitudes ni se ordenan pagos.'));
    if (acciones.length && !activas.size) resumen.append(h('p', { class: 'propuesta-nota' }, `Efecto estimado: ${f.score(m.shown)} → ${f.score(estimacionPlan(m, acciones, fin))} puntos. Las acciones pueden solaparse.`));
    guardar.disabled = guardando || (!acciones.length && !finElegida().length);
  };
  const conectados = bancosConectados(fuentes);
  pasos.append(paso(1, 'Tus bancos conectados', 'Los bancos con los que ya trabajas y los productos que tienes contratados.', conectados.length ? h('div', { class: 'propuesta-bancos' }, ...conectados.map(tarjetaBanco)) : h('p', { class: 'propuesta-nota' }, 'No constan bancos conectados en los datos de esta entidad.')));
  const cajaAcciones = h('div', { class: 'propuesta-acciones' });
  for (const a of m.actions ?? []) {
    const existente = existentes.has(a.id);
    const marca = h('input', { type: 'checkbox', checked: sel.has(a.id) || existente, disabled: existente, 'aria-label': tituloAccion(a) });
    const fila = h('label', { class: `propuesta-accion ${marca.checked ? 'elegida' : ''}` }, h('span', { class: 'propuesta-accion-marca' }, marca), h('span', { class: 'propuesta-accion-cuerpo' }, h('span', { class: 'propuesta-titulo' }, tituloAccion(a)), h('span', { class: 'propuesta-nota' }, existente ? 'Ya registrada en el seguimiento de este mes' : `${explicacionAccion(a)} · ${ESFUERZO[a.effort]}`)), h('span', { class: 'propuesta-accion-efecto' }, f.delta(a.uplift_tenths)));
    marca.addEventListener('change', () => { if (marca.checked) sel.add(a.id); else sel.delete(a.id); fila.classList.toggle('elegida', marca.checked); actualizar(); });
    cajaAcciones.append(fila);
  }
  if (!cajaAcciones.childElementCount) cajaAcciones.append(h('p', { class: 'propuesta-nota' }, 'El motor no propone nuevas acciones este mes.'));
  pasos.append(paso(2, 'Acciones que vas a poner en marcha', 'Revisa tu selección antes de confirmar. Cada acción conservará su objetivo y su punto de partida.', cajaAcciones));
  const cajaFin = h('div', { class: 'propuesta-financiacion' });
  for (const x of instrumentos) {
    const yaIniciada = existentes.has(`financing:${d.id}:${x.id}`);
    const incluir = h('input', { type: 'checkbox', disabled: yaIniciada });
    const ofertas = ofertasBanco(x.kind, fuentes);
    const lista = h('div', { class: 'propuesta-ofertas', hidden: true });
    const buscar = h('input', { type: 'checkbox', checked: true });
    const pintarBancos = () => {
      lista.replaceChildren(h('label', { class: 'propuesta-oferta' }, buscar, h('span', { class: 'propuesta-titulo' }, 'Buscar ofertas con Embat')));
      buscar.checked = !(bancos[x.id]?.length);
      for (const o of ofertas) lista.append(filaOferta(x, o, bancos[x.id] ?? [], (bank, on) => {
        const nuevos = new Set(bancos[x.id] ?? []); if (on) nuevos.add(bank); else nuevos.delete(bank); bancos[x.id] = [...nuevos]; pintarBancos(); actualizar();
      }));
    };
    buscar.addEventListener('change', () => { bancos[x.id] = []; pintarBancos(); actualizar(); });
    incluir.addEventListener('change', () => { if (incluir.checked) activas.add(x.id); else activas.delete(x.id); lista.hidden = !incluir.checked; actualizar(); });
    pintarBancos();
    cajaFin.append(h('div', { class: 'propuesta-instrumento' }, h('label', { class: 'confirmacion-instrumento' }, incluir, h('span', { class: 'propuesta-titulo' }, `${tituloFinanciacion(x)}${x.amount !== null ? ` · ${f.eurosCorto(x.amount)}` : ''}`)), h('p', { class: 'propuesta-nota' }, yaIniciada ? 'Esta gestión ya está registrada en el seguimiento.' : x.detail), lista));
  }
  if (!instrumentos.length) cajaFin.append(h('p', { class: 'propuesta-nota' }, 'Este mes el motor no ve financiación que recomendarte. Tus bancos siguen disponibles como referencia.'));
  pasos.append(paso(3, 'Financiación: con qué bancos avanzar', 'Incluye las gestiones que quieras iniciar y elige uno o varios bancos. Se indica si la tasa consta en tus datos o es una estimación.', cajaFin));
  const hoja = h('div', { class: 'propuesta-hoja' }, h('header', { class: 'propuesta-cabecera' }, h('div', {}, h('p', { class: 'versalita' }, 'Confirmar decisiones'), h('h2', { id: 'confirmacion-titulo' }, `${nombreDe(d.kind, d.id)} · ${f.mes(d.corte)}`)), cerrar), pasos, h('footer', { class: 'propuesta-resumen' }, h('div', {}, resumen, error), guardar));
  fondo.append(hoja);
  (document.querySelector('#app') ?? document.body).append(fondo);
  guardar.addEventListener('click', async () => {
    if (guardando) return;
    guardando = true; actualizar(); cerrar.disabled = true; error.textContent = ''; guardar.textContent = 'Guardando decisiones…';
    pasos.inert = true;
    try { await confirmar(ids(), finElegida()); guardando = false; salir(); }
    catch (e) { error.textContent = (e as Error).message; }
    finally { guardando = false; pasos.inert = false; cerrar.disabled = false; guardar.textContent = 'Confirmar y ejecutar'; actualizar(); }
  });
  fondo.addEventListener('keydown', ev => {
    ev.stopPropagation();
    if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); salir(); return; }
    if (ev.key !== 'Tab') return;
    const controles = [...fondo.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex="0"]')].filter(el => el.getClientRects().length && !el.closest('[inert]'));
    const primero = controles[0], ultimo = controles.at(-1);
    if (ev.shiftKey && document.activeElement === primero) { ev.preventDefault(); ultimo?.focus(); }
    else if (!ev.shiftKey && document.activeElement === ultimo) { ev.preventDefault(); primero?.focus(); }
  });
  actualizar(); cerrar.focus();
}
