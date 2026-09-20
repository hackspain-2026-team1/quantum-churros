import { ejecuciones, avanceEjecucion, estadosEjecucion, valorEjecucion, type Ejecucion } from '../datos/ejecuciones';
import { f } from '../datos/formato';
import { voz } from '../datos/redaccion';
import type { DatosFicha } from './ficha';
import { h } from './dom';
import { seccion } from './primitivos';
import './ejecuciones.css';
import { abrirConfirmacionAcciones } from './propuesta';

/** Selection is a simulation; only an acknowledged API write starts execution. */
export function seguimientoAcciones(d: DatosFicha, seleccion: () => Set<string>) {
 const ambito = { entity_id: d.id, group_id: d.grupoId, kind: d.kind };
 const actor = voz('Embat', 'CFO');
 const lista = h('div', { class: 'ejecuciones-lista' });
 const aviso = h('p', { class: 'nota', role: 'status', 'aria-live': 'polite' });
 const error = h('p', { class: 'ejecuciones-error', role: 'alert' });
 const refrescar = h('button', { type: 'button', class: 'miga-accion' }, 'Actualizar seguimiento');
 const raiz = seccion('Acciones en marcha', h('div', { class: 'ejecuciones-cabecera' }, h('p', { class: 'nota' }, 'Qué estás llevando a cabo y cómo evoluciona frente al objetivo que elegiste.'), refrescar), aviso, error, lista);
 raiz.classList.add('ejecuciones');
 const boton = h('button', { type: 'button', class: 'boton-propuesta' }, 'Ejecutar acciones');
 const mensaje = h('p', { class: 'nota', role: 'status', 'aria-live': 'polite' });
 let registros: Ejecucion[] = [], cargado = false, ocupado = false;
 const ids = () => [...seleccion()].filter(id => d.mes?.actions?.some(a => a.id === id) && !registros.some(e => e.snapshot.id === id && e.snapshot.corte === d.corte));
 const actualizarBoton = () => {
  const n = ids().length;
  boton.disabled = ocupado || !cargado || d.corte !== d.ent.months.at(-1)?.month;
  boton.textContent = ocupado ? 'Guardando…' : n ? `Ejecutar ${f.plural(n, 'acción', 'acciones')}` : 'Ejecutar acciones';
  if (d.corte !== d.ent.months.at(-1)?.month) mensaje.textContent = 'Vuelve al último cierre para poner acciones en marcha.';
 };
 function pintar() {
  lista.replaceChildren();
  const activas = registros.filter(e => e.status === 'en_curso');
  const anteriores = registros.filter(e => e.status !== 'en_curso');
  aviso.textContent = activas.length ? f.plural(activas.length, 'acción en curso', 'acciones en curso') : 'No hay acciones en curso. Puedes elegir una nueva acción o consultar las decisiones anteriores.';
  const enCurso = h('div', { class: 'ejecuciones-activas', 'aria-label': 'Acciones en curso' });
  const archivo = h('details', { class: 'ejecuciones-archivo' }, h('summary', {}, `Historial · ${f.plural(anteriores.length, 'decisión anterior', 'decisiones anteriores')}`));
  const historialFilas = h('div', {}); archivo.append(historialFilas);
  lista.append(enCurso);
  if (anteriores.length) lista.append(archivo);
  for (const e of registros) {
   const s = e.snapshot, avance = avanceEjecucion(e, d.corte);
   const nota = h('textarea', { rows: 2, maxlength: 2000, placeholder: 'Qué avanzó y cuál es el próximo paso', 'aria-label': `Nota de seguimiento: ${s.title}` });
   const guardar = h('button', { type: 'button', class: 'miga-accion' }, 'Guardar actualización');
   const terminar = h('button', { type: 'button', class: 'miga-accion' }, e.status === 'en_curso' ? 'Dar por finalizada' : 'Volver a poner en curso');
   const respuesta = h('p', { class: 'nota', role: 'status' });
   const historial = h('ol', { class: 'ejecucion-historial' });
   for (const ev of e.events.filter(v => v.kind === 'decision')) historial.append(h('li', {}, `${f.fecha(ev.created_at)} · ${ev.actor} · ${estadosEjecucion[ev.payload.status!]}`, ev.payload.note ? h('p', {}, ev.payload.note) : null));
   const medidas = h('ul', { class: 'ejecucion-medidas' });
   for (const ev of e.events.filter(v => v.kind === 'measurement' && v.payload.month! <= d.corte)) medidas.append(h('li', {}, `${f.mesCorto(ev.payload.month!)} · ${valorEjecucion(ev.payload.value ?? null, s.unit)} · observado el ${f.fecha(ev.created_at)}`));
   const abrir = h('button', { type: 'button', class: 'ejecucion-abrir' }, e.status === 'en_curso' ? 'Actualizar avance' : 'Ver decisión', h('span', { 'aria-hidden': 'true' }, ' ↗'));
   const ficha = h('article', { class: `ejecucion ${e.status === 'en_curso' ? '' : 'anterior'}`, 'data-ejecucion': e.id },
    h('header', {}, h('h4', { title: s.title }, s.title)),
    h('p', { class: 'ejecucion-fecha' }, `Desde ${f.mesCorto(s.corte)}${e.status !== 'en_curso' ? ` · ${estadosEjecucion[e.status]}` : ''}`),
    s.financing ? h('div', { class: 'ejecucion-cifras ejecucion-bancos' }, h('span', {}, 'Bancos elegidos'), h('b', {}, s.banks?.length ? s.banks.join(' · ') : 'Buscar ofertas con Embat')) :
    h('div', { class: 'ejecucion-cifras' },
     h('p', {}, h('span', {}, 'Inicio'), h('b', {}, valorEjecucion(s.baseline, s.unit))),
     h('p', {}, h('span', {}, avance.mes ? f.mesCorto(avance.mes) : 'Nuevo cierre'), h('b', {}, avance.mes ? valorEjecucion(avance.actual, s.unit) : 'Pendiente')),
     h('p', {}, h('span', {}, 'Objetivo'), h('b', {}, valorEjecucion(s.target, s.unit)))),
    h('div', { class: 'ejecucion-progreso' }, h('p', { class: 'ejecucion-avance' }, s.financing ? 'Gestión con los bancos' : avance.texto,
     avance.barra !== null ? h('b', { class: 'num' }, f.porcentaje(avance.barra, 0)) : null),
     avance.barra !== null ? h('progress', { max: 1, value: avance.barra, 'aria-label': `Avance medido de ${s.title}` }) : h('span', { class: 'ejecucion-sin-medida', 'aria-hidden': 'true' })),
    h('p', { class: 'ejecucion-demo' }, s.demo ? 'Demo · cifras históricas del motor' : ''), abrir);
   let dialogo: HTMLDialogElement | null = null;
   abrir.addEventListener('click', () => {
    dialogo = h('dialog', { class: 'ejecucion-dialogo', 'aria-label': s.title });
    const cerrar = h('button', { type: 'button', class: 'miga-accion' }, 'Cerrar');
    cerrar.addEventListener('click', () => dialogo?.close());
    dialogo.addEventListener('close', () => { dialogo?.remove(); abrir.focus(); });
    dialogo.addEventListener('keydown', ev => ev.stopPropagation());
    dialogo.append(h('header', {}, h('h2', {}, s.title), cerrar),
     h('p', { class: 'nota' }, `Registrada el ${f.fecha(e.created_at)}${s.demo ? ' · Ejemplo de demostración' : ''}`),
     h('div', { class: 'ejecucion-edicion' }, nota, h('div', { class: 'ejecucion-controles' }, guardar, terminar)), respuesta,
     h('p', { class: 'nota' }, 'Finalizar retira la acción de tu seguimiento activo. El resultado medido y el historial se conservan.'),
     h('h3', {}, 'Historial de decisiones'), historial,
     h('div', {}, medidas.childElementCount ? h('h3', {}, 'Cierres observados') : null, medidas));
    document.body.append(dialogo); dialogo.showModal();
   });
   const actualizar = async (estado: Ejecucion['status']) => {
    guardar.disabled = true; terminar.disabled = true; respuesta.textContent = 'Guardando…';
    try {
     const actualizado = await ejecuciones.guardar(e, d.grupoId, estado, nota.value, actor);
     dialogo?.close();
     registros = registros.map(v => v.id === e.id ? actualizado : v); pintar();
     aviso.textContent = 'Actualización guardada en el historial.';
     refrescar.focus();
    } catch (err) { respuesta.textContent = (err as Error).message; guardar.disabled = false; terminar.disabled = false; }
   };
   guardar.addEventListener('click', () => void actualizar(e.status));
   terminar.addEventListener('click', () => void actualizar(e.status === 'en_curso' ? 'completada' : 'en_curso'));
   (e.status === 'en_curso' ? enCurso : historialFilas).append(ficha);
  }
  actualizarBoton();
 }
 async function cargar() {
  cargado = false; actualizarBoton();
  refrescar.disabled = true; error.textContent = ''; aviso.textContent = 'Consultando decisiones guardadas…';
  try {
   registros = await ejecuciones.listar(ambito);
   try { registros = await ejecuciones.actualizarMedidas(ambito); }
   catch (err) { error.textContent = `Se muestran las decisiones guardadas. ${(err as Error).message}`; }
   cargado = true; pintar();
  } catch (err) { error.textContent = (err as Error).message; aviso.textContent = ''; }
  finally { refrescar.disabled = false; actualizarBoton(); }
 }
 refrescar.addEventListener('click', () => void cargar());
 boton.addEventListener('click', () => {
  abrirConfirmacionAcciones(d, seleccion(), new Set(registros.filter(e => !e.snapshot.demo && e.snapshot.corte === d.corte).map(e => e.snapshot.id)), async (elegidas, financiacion) => {
   registros = await ejecuciones.iniciar(ambito, d.corte, d.man.bundle_id, elegidas, actor, financiacion); pintar();
   mensaje.textContent = 'Decisiones confirmadas. Ya puedes seguir su evolución.';
   raiz.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
 });
 void cargar(); actualizarBoton();
 return { raiz, boton, mensaje, actualizarBoton };
}
