import { describe, expect, test } from 'bun:test';
import type { AlertaM, MesM } from '../src/datos/contrato';
import { senalMonitor } from '../src/datos/monitor';

const alerta = (month: string, state: AlertaM['state'] = 'fired'): AlertaM => ({
	id: `COMP_TEST:${month}:deterioration_structural`,
	entity_kind: 'company',
	entity_id: 'COMP_TEST',
	group_id: 'GROUP_TEST',
	month,
	kind: 'deterioration_structural',
	state,
	title: 'Deterioro estructural',
	detail: 'La trayectoria empeora de forma sostenida.',
	shown: 620,
	suppressed_by: state === 'fired' ? null : { reason: 'perimeter_change', since: month, until: month },
});

const mes = (month: string, nature: MesM['verdict']['nature'] = 'structural'): MesM => ({
	month,
	abstain: null,
	verdict: {
		available: true,
		direction: 'deteriorating',
		nature,
		shock_pending: nature === 'shock_pending',
		detected_since: '2026-04',
	},
} as MesM);

describe('ciclo del monitor proactivo', () => {
	test('distingue el disparo nuevo de una señal que sigue activa', () => {
		const alertas = [alerta('2026-05')];
		expect(senalMonitor(mes('2026-05'), alertas, 'COMP_TEST')?.fase).toBe('nueva');
		expect(senalMonitor(mes('2026-08'), alertas, 'COMP_TEST')?.fase).toBe('activa');
	});

	test('no inventa un envío mientras observa o cuando el motor retiene el aviso', () => {
		expect(senalMonitor(mes('2026-05', 'shock_pending'), [], 'COMP_TEST')).toMatchObject({
			fase: 'observando',
			alerta: null,
		});
		expect(senalMonitor(mes('2026-05'), [alerta('2026-05', 'suppressed')], 'COMP_TEST')).toMatchObject({
			fase: 'pausa',
			alerta: null,
		});
	});

	test('ignora otras entidades y veredictos sin movimiento estructural', () => {
		expect(senalMonitor(mes('2026-05'), [alerta('2026-05')], 'COMP_OTHER')).toBeNull();
		expect(senalMonitor({ ...mes('2026-05'), verdict: { ...mes('2026-05').verdict, direction: 'stable' } }, [], 'COMP_TEST')).toBeNull();
	});
});
