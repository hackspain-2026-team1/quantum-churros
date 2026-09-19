import { describe, expect, test } from 'bun:test';
import { avanceEjecucion, type Ejecucion } from '../src/datos/ejecuciones';
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
