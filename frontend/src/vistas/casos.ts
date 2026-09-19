import type { ExpedienteFinanciacion, RolFinanciacion } from '../datos/financiacion';
import { f } from '../datos/formato';
import { h } from './dom';
import { preferenciasEmpresa } from './preferencias';

const ESTADOS: Record<string, string> = { in_review: 'En revisión', authorized: 'Autorizado', published: 'Ofertas abiertas', shortlisted: 'Preselección', accepted: 'Oferta aceptada', closed: 'Cerrado' };

export function vistaCaso(expediente: ExpedienteFinanciacion, rol: RolFinanciacion, acciones: { autorizar(scope: Record<string, unknown>): void; publicar(): void; revocar(): void }): HTMLElement {
	const caso = expediente.case;
	const necesidad = expediente.need;
	const drivers = Object.entries(necesidad.drivers_json);
	const desde = necesidad.detected_since ? fecha(necesidad.detected_since) : 'este corte';
	const raiz = h('div', { class: 'fin-caso' },
		h('header', { class: 'fin-caso-cab' },
			h('div', {}, h('span', { class: `fin-estado ${caso.status}` }, ESTADOS[caso.status] ?? caso.status), h('h1', {}, expediente.company_name), h('p', {}, caso.objective), h('small', { class: 'fin-trazabilidad' }, `${necesidad.entity_id} · ${necesidad.model_version} · corte ${fecha(necesidad.source_month)}`)),
			h('div', { class: 'fin-score', 'aria-label': `Score ${f.numero(necesidad.score)}; antes ${f.numero(necesidad.previous_score)}` }, h('strong', {}, f.numero(necesidad.score)), h('span', { class: 'baja' }, `${f.signo(necesidad.score - necesidad.previous_score, 0)} puntos`)),
		),
		h('section', { class: 'fin-necesidad' },
			h('div', {}, h('span', {}, 'Necesidad prevista'), h('strong', {}, `${f.eurosCorto(necesidad.amount_low)}–${f.eurosCorto(necesidad.amount_high)}`), h('small', {}, `entre ${fecha(necesidad.needed_from)} y ${fecha(necesidad.needed_to)}`)),
			h('div', {}, h('span', {}, 'Caso propuesto'), h('strong', {}, f.eurosCorto(caso.amount)), h('small', {}, `${f.numero(caso.term_months)} meses · ${caso.product_types_json.map(nombreProducto).join(' o ')}`)),
			h('div', {}, h('span', {}, 'Confianza'), h('strong', {}, f.porcentaje(necesidad.confidence, 0)), h('small', {}, 'intervalo y horizonte revisables')),
			h('div', {}, h('span', {}, 'Señal'), h('strong', {}, trayectoria(necesidad.trajectory, necesidad.trajectory_nature)), h('small', {}, `detectada desde ${desde}`)),
		),
		h('section', { class: 'fin-factores' }, h('h2', {}, 'Por qué aparece ahora'), ...drivers.map(([label, value]) => h('div', {}, h('span', {}, primera(label)), h('strong', {}, value)))),
	);
	if (rol === 'company' && caso.status === 'in_review') raiz.append(preferenciasEmpresa(acciones.autorizar));
	if (rol === 'consultant' && caso.status === 'authorized') raiz.append(h('div', { class: 'fin-accion-principal' }, h('div', {}, h('strong', {}, 'Autorización recibida'), h('span', {}, 'El teaser seudonimizado está listo para proveedores compatibles.')), h('button', { type: 'button', class: 'fin-boton primario', onclick: acciones.publicar }, 'Abrir ronda de ofertas')));
	if (rol === 'company' && ['authorized', 'published', 'shortlisted'].includes(caso.status)) raiz.append(h('div', { class: 'fin-accion-secundaria' }, h('span', {}, 'Puedes retirar el acceso concedido en cualquier momento.'), h('button', { type: 'button', class: 'fin-boton secundario', onclick: acciones.revocar }, 'Revocar permisos')));
	return raiz;
}

function fecha(iso: string): string {
	return new Intl.DateTimeFormat('es-ES', { month: 'short', year: 'numeric' }).format(new Date(`${iso}T00:00:00`));
}

function nombreProducto(value: string): string {
	return ({ linea_credito: 'línea de crédito', factoring: 'factoring' } as Record<string, string>)[value] ?? value;
}

function primera(value: string): string {
	return value.charAt(0).toUpperCase() + value.slice(1);
}

function trayectoria(direction: string, nature: string | null): string {
	if (direction === 'deteriorating' && nature === 'structural') return 'Caída estructural';
	if (direction === 'deteriorating' && nature === 'shock_pending') return 'Bache bajo vigilancia';
	if (direction === 'improving') return 'Mejora sostenida';
	return 'Estable';
}
