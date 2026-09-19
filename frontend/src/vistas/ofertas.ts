import type { ExpedienteFinanciacion, OfertaFinanciacion, RolFinanciacion } from '../datos/financiacion';
import { f } from '../datos/formato';
import { h } from './dom';

export function vistaOfertas(expediente: ExpedienteFinanciacion, rol: RolFinanciacion, acciones: { preseleccionar(providerOrgId: string): void; aceptar(offerId: string): void }): HTMLElement {
	const ofertas = [...expediente.offers].sort((a, b) => coste(a.offer) - coste(b.offer));
	const raiz = h('section', { class: 'fin-ofertas', 'aria-labelledby': 'fin-ofertas-titulo' }, h('div', { class: 'fin-seccion-cab' }, h('div', {}, h('h2', { id: 'fin-ofertas-titulo' }, 'Ofertas comparables'), h('p', {}, ofertas.length ? 'Condiciones indicativas normalizadas sobre el mismo importe y plazo.' : 'La ronda está abierta. Las ofertas aparecerán aquí cuando un proveedor las presente.'))));
	if (!ofertas.length) {
		raiz.append(h('div', { class: 'fin-vacio' }, h('strong', {}, 'Aún no hay ofertas'), h('span', {}, 'Cambia a la vista de proveedor para presentar condiciones desde el catálogo demo.')));
		return raiz;
	}
	const tabla = h('div', { class: 'fin-tabla-ofertas', role: 'table', 'aria-label': 'Comparación de ofertas' });
	tabla.append(h('div', { class: 'fin-oferta-fila cabecera', role: 'row' }, h('span', {}, 'Proveedor'), h('span', {}, 'Importe'), h('span', {}, 'Tipo anual'), h('span', {}, 'Comisión'), h('span', {}, 'Garantía'), h('span', {}, 'Decisión')));
	for (const [index, item] of ofertas.entries()) {
		const oferta = item.offer;
		const decision = rol !== 'company' ? h('span', { class: 'fin-oferta-estado' }, etiquetaEstado(oferta.status)) : expediente.case.status === 'published' ? h('button', { type: 'button', class: 'fin-boton secundario', onclick: () => acciones.preseleccionar(oferta.provider_org_id) }, index === 0 ? 'Preseleccionar' : 'Elegir') : oferta.status === 'shortlisted' && expediente.case.status === 'shortlisted' ? h('button', { type: 'button', class: 'fin-boton primario', onclick: () => acciones.aceptar(oferta.id) }, 'Aceptar oferta') : h('span', { class: 'fin-oferta-estado' }, etiquetaEstado(oferta.status));
		tabla.append(h('div', { class: `fin-oferta-fila ${index === 0 ? 'recomendada' : ''}`, role: 'row' }, h('span', {}, h('strong', {}, item.provider_name), index === 0 ? h('small', {}, 'Mejor coste estimado') : null), h('span', {}, f.eurosCorto(oferta.amount)), h('span', {}, f.porcentaje(oferta.annual_rate, 1)), h('span', {}, f.porcentaje(oferta.opening_fee, 1)), h('span', {}, oferta.guarantee), h('span', {}, decision)));
	}
	raiz.append(tabla, h('p', { class: 'fin-nota' }, 'Oferta indicativa. La aprobación, el conocimiento del cliente (KYC) y la firma se realizan después de la preselección.'));
	return raiz;
}

function coste(oferta: OfertaFinanciacion): number {
	return oferta.annual_rate * (oferta.term_months / 12) + oferta.opening_fee;
}

function etiquetaEstado(status: string): string {
	return ({ submitted: 'Presentada', shortlisted: 'Preseleccionada', accepted: 'Aceptada', declined: 'No seleccionada' } as Record<string, string>)[status] ?? status;
}
