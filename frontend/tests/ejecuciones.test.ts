import { describe, expect, test } from 'bun:test';
import { avanceEjecucion, pasosEjecucion, situacionAccion, type Ejecucion } from '../src/datos/ejecuciones';
const registro = (inicio: number | null, target: number, value?: number | null): Ejecucion => ({
 id: 'test', status: 'completada', version: 1, created_at: '2026-09-20',
 snapshot: { id: 'debt', title: '', detail: '', baseline: inicio, target, unit: '%', corte: '2026-08', uplift_tenths: 8, score_tenths: 690 },
 events: value === undefined ? [] : [{ id: 'observation', actor: 'Motor', kind: 'measurement', created_at: '2026-10-01', payload: { month: '2026-09', value } }],
});
describe('avance observado, separado del estado manual', () => {
 test('completada sin cierre posterior sigue esperando', () => expect(avanceEjecucion(registro(3.1, 2.17), '2026-09').barra).toBeNull());
 test('reducción y aumento usan la dirección del objetivo', () => {
  expect(avanceEjecucion(registro(4, 2, 3), '2026-09').barra).toBe(0.5);
  expect(avanceEjecucion(registro(1, 2, 1.5), '2026-09').barra).toBe(0.5);
 });
 test('superar el objetivo cuenta como alcanzado', () => expect(avanceEjecucion(registro(4, 2, 1), '2026-09').texto).toBe('Objetivo alcanzado'));
 test('retroceso no produce una barra negativa', () => {
  const p = avanceEjecucion(registro(4, 2, 5), '2026-09');
  expect(p.barra).toBe(0); expect(p.texto).toBe('Se aleja del objetivo');
 });
 test('no usa datos futuros, nulos o un punto inicial ausente', () => {
  expect(avanceEjecucion(registro(4, 2, 3), '2026-08').barra).toBeNull();
  expect(avanceEjecucion(registro(4, 2, null), '2026-09').barra).toBeNull();
  expect(avanceEjecucion(registro(null, 2, 3), '2026-09').barra).toBeNull();
 });
});

describe('situación de una acción frente a las decisiones guardadas', () => {
 const decision = (corte: string, status: Ejecucion['status'], extra: Partial<Ejecucion['snapshot']> = {}): Ejecucion => ({ ...registro(4, 2), id: `${corte}-${status}`, status, snapshot: { ...registro(4, 2).snapshot, corte, ...extra } });
 test('sin decisiones, la acción está disponible', () => expect(situacionAccion([], 'debt', '2026-08').estado).toBe('disponible'));
 test('una decisión abierta de un cierre anterior sigue ocupando la acción', () => {
  expect(situacionAccion([decision('2026-07', 'en_curso')], 'debt', '2026-08').estado).toBe('en_curso');
  expect(situacionAccion([decision('2026-07', 'pausada')], 'debt', '2026-08').estado).toBe('pausada');
 });
 test('finalizada cuenta en su cierre y se puede retomar desde el siguiente', () => {
  expect(situacionAccion([decision('2026-08', 'completada')], 'debt', '2026-08').estado).toBe('completada');
  expect(situacionAccion([decision('2026-07', 'completada')], 'debt', '2026-08').estado).toBe('disponible');
 });
 test('la abierta manda sobre una finalizada anterior', () => expect(situacionAccion([decision('2026-06', 'completada'), decision('2026-08', 'en_curso')], 'debt', '2026-08').registro?.id).toBe('2026-08-en_curso'));
 test('ni los ejemplos de demostración ni las decisiones futuras ocupan la acción', () => {
  expect(situacionAccion([decision('2026-08', 'en_curso', { demo: true })], 'debt', '2026-08').estado).toBe('disponible');
  expect(situacionAccion([decision('2026-09', 'en_curso')], 'debt', '2026-08').estado).toBe('disponible');
 });
 test('cada estado ofrece solo sus pasos', () => {
  expect(pasosEjecucion.en_curso.map(p => p.a)).toEqual(['pausada', 'completada']);
  expect(pasosEjecucion.pausada.map(p => p.a)).toEqual(['en_curso', 'completada']);
  expect(pasosEjecucion.completada.map(p => p.a)).toEqual(['en_curso']);
 });
});
