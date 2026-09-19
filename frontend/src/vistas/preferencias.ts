import { h } from './dom';

export function preferenciasEmpresa(alAutorizar: (scope: Record<string, unknown>) => void): HTMLElement {
	const bancos = casilla('Consultar banco habitual', true);
	const mercado = casilla('Solicitar alternativas compatibles', true);
	const garantias = casilla('Excluir garantías personales', true);
	const identidad = casilla('Ocultar identidad hasta la preselección', true);
	const raiz = h('section', { class: 'fin-preferencias', 'aria-labelledby': 'fin-preferencias-titulo' },
		h('div', { class: 'fin-seccion-cab' }, h('div', {}, h('h2', { id: 'fin-preferencias-titulo' }, 'Control de la empresa'), h('p', {}, 'La ronda solo empieza con una autorización explícita y caduca automáticamente.'))),
		h('div', { class: 'fin-opciones' }, bancos.label, mercado.label, garantias.label, identidad.label),
		h('button', { type: 'button', class: 'fin-boton primario', onclick: () => alAutorizar({ channels: { habitual_bank: bancos.input.checked, market: mercado.input.checked }, restrictions: { personal_guarantees: !garantias.input.checked }, disclosure: { identity: identidad.input.checked ? 'shortlist_only' : 'round' } }) }, 'Autorizar la ronda'),
	);
	return raiz;
}

function casilla(texto: string, checked: boolean) {
	const input = h('input', { type: 'checkbox', checked }) as HTMLInputElement;
	return { input, label: h('label', { class: 'fin-casilla' }, input, h('span', {}, texto)) };
}
