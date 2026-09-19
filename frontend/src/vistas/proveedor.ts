import type { ExpedienteFinanciacion, IdentidadFinanciacion, OportunidadProveedor } from '../datos/financiacion';
import { f } from '../datos/formato';
import { vistaCaso } from './casos';
import { h } from './dom';

export function vistaProveedor(expedientes: ExpedienteFinanciacion[], oportunidades: OportunidadProveedor[], proveedores: { key: string; label: string; identity: IdentidadFinanciacion }[], proveedorActivo: string, alProveedor: (key: string) => void, alOfertar: (identity: IdentidadFinanciacion, opportunityId: string, values: { amount: number; annual_rate: number; term_months: number; opening_fee: number; guarantee: string }) => void): HTMLElement {
	const raiz = h('div', { class: 'fin-proveedor' },
		h('div', { class: 'fin-seccion-cab' }, h('div', {}, h('h1', {}, 'Oportunidades compatibles'), h('p', {}, 'El proveedor ve primero un teaser seudonimizado. La identidad y el detalle operativo siguen ocultos.')), h('div', { class: 'fin-selector-proveedor', role: 'tablist', 'aria-label': 'Proveedor demo' }, ...proveedores.map((provider) => h('button', { type: 'button', role: 'tab', 'aria-selected': String(provider.key === proveedorActivo), onclick: () => alProveedor(provider.key) }, provider.label)))),
	);
	for (const expediente of expedientes) {
		raiz.append(h('section', { class: 'fin-revelado' }, h('div', { class: 'fin-seccion-cab' }, h('div', {}, h('h2', {}, 'Expediente revelado'), h('p', {}, 'La empresa te ha preseleccionado. Ya puedes revisar su identidad y el detalle autorizado.'))), vistaCaso(expediente, 'provider', { autorizar: () => undefined, publicar: () => undefined, revocar: () => undefined })));
	}
	if (!oportunidades.length) {
		if (!expedientes.length) raiz.append(h('div', { class: 'fin-vacio' }, h('strong', {}, 'No hay oportunidades visibles'), h('span', {}, 'La empresa todavía no ha autorizado y publicado ninguna ronda compatible.')));
		return raiz;
	}
	const identity = proveedores.find((item) => item.key === proveedorActivo)!.identity;
	for (const item of oportunidades) {
		const teaser = item.teaser;
		const amountRange = teaser.amount_range as number[];
		const profile = (teaser.profile ?? {}) as Record<string, string>;
		const formulario = h('form', { class: 'fin-form-oferta' }) as HTMLFormElement;
		const importe = campoNumero('Importe', amountRange?.[1] ?? 100000, 1000);
		const tipo = campoNumero('Tipo anual (%)', item.own_offer ? item.own_offer.annual_rate * 100 : proveedorActivo === 'provider' ? 5.4 : 5.9, 0.1);
		const plazo = campoNumero('Plazo (meses)', item.own_offer?.term_months ?? 12, 1);
		const comision = campoNumero('Comisión (%)', item.own_offer ? item.own_offer.opening_fee * 100 : 0.5, 0.1);
		const garantia = h('select', { 'aria-label': 'Garantía' }, h('option', { value: 'Sin garantía personal' }, 'Sin garantía personal'), h('option', { value: 'Cesión de cobros' }, 'Cesión de cobros')) as HTMLSelectElement;
		formulario.append(importe.label, tipo.label, plazo.label, comision.label, h('label', {}, h('span', {}, 'Garantía'), garantia), h('button', { type: 'submit', class: 'fin-boton primario' }, item.own_offer ? 'Actualizar oferta' : 'Presentar oferta'));
		formulario.addEventListener('submit', (event) => {
			event.preventDefault();
			alOfertar(identity, item.opportunity.id, { amount: importe.input.valueAsNumber, annual_rate: tipo.input.valueAsNumber / 100, term_months: plazo.input.valueAsNumber, opening_fee: comision.input.valueAsNumber / 100, guarantee: garantia.value });
		});
		raiz.append(h('article', { class: 'fin-oportunidad' },
			h('header', {}, h('div', {}, h('span', {}, item.opportunity.public_code), h('h2', {}, `${profile.industry ?? 'Empresa'} · ${profile.country ?? '—'}`), h('small', {}, profile.size ?? '')), h('span', { class: 'fin-estado published' }, item.own_offer ? 'Oferta presentada' : 'Abierta')),
			h('div', { class: 'fin-teaser' }, dato('Score', String(teaser.score_band ?? '—'), String(teaser.trajectory ?? '')), dato('Necesidad', amountRange ? `${f.eurosCorto(amountRange[0])}–${f.eurosCorto(amountRange[1])}` : '—', 'en 3–5 meses'), dato('Confianza', f.porcentaje(Number(teaser.confidence ?? 0), 0), 'señal explicada')),
			h('p', { class: 'fin-oculto' }, 'Oculto hasta preselección: razón social, cuentas, movimientos, contrapartes y documentos.'),
			formulario,
		));
	}
	return raiz;
}

function dato(label: string, value: string, detail: string): HTMLElement {
	return h('div', {}, h('span', {}, label), h('strong', {}, value), h('small', {}, detail));
}

function campoNumero(label: string, value: number, step: number) {
	const input = h('input', { type: 'number', value: String(value), step: String(step), min: '0', required: true }) as HTMLInputElement;
	return { input, label: h('label', {}, h('span', {}, label), input) };
}
