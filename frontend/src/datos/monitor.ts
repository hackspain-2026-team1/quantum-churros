import type { AlertaM, MesM } from './contrato';

export type FaseMonitor = 'nueva' | 'activa' | 'observando' | 'pausa';
export interface SenalMonitor {
	fase: FaseMonitor;
	direccion: 'improving' | 'deteriorating';
	alerta: AlertaM | null;
	desde: string | null;
}

/** Presenta el ciclo de una señal; solo el motor decide si existe y si se dispara. */
export function senalMonitor(mes: MesM | null, alertas: readonly AlertaM[], entidad: string): SenalMonitor | null {
	if (!mes || mes.abstain || !mes.verdict.available) return null;
	const clase = mes.verdict.direction === 'improving'
		? 'improvement_structural'
		: mes.verdict.direction === 'deteriorating'
			? 'deterioration_structural'
			: null;
	if (!clase) return null;
	const relacionadas = alertas
		.filter((a) => a.entity_id === entidad && a.kind === clase && a.month <= mes.month && (!mes.verdict.detected_since || a.month >= mes.verdict.detected_since))
		.sort((a, b) => b.month.localeCompare(a.month));
	const disparada = relacionadas.find((a) => a.state === 'fired') ?? null;
	const retenida = relacionadas.find((a) => a.state !== 'fired') ?? null;
	const base = { direccion: mes.verdict.direction as SenalMonitor['direccion'], alerta: disparada, desde: mes.verdict.detected_since };
	if (disparada?.month === mes.month) return { ...base, fase: 'nueva' };
	if (mes.verdict.nature === 'structural' && disparada) return { ...base, fase: 'activa' };
	if (mes.verdict.nature === 'structural' && retenida) return { ...base, alerta: null, fase: 'pausa' };
	if (mes.verdict.shock_pending || mes.verdict.nature === 'shock_pending') return { ...base, alerta: null, fase: 'observando' };
	return null;
}
