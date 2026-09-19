// Utilidades mínimas de DOM, sin framework.

type Hijo = Node | string | number | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(
	tag: K,
	attrs: Record<string, unknown> = {},
	...hijos: Hijo[]
): HTMLElementTagNameMap[K] {
	const el = document.createElement(tag);
	for (const [k, v] of Object.entries(attrs)) {
		if (v === undefined || v === null || v === false) continue;
		if (k === 'class') el.className = String(v);
		else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
		else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v as EventListener);
		else if (k === 'html') el.innerHTML = String(v);
		else el.setAttribute(k, v === true ? '' : String(v));
	}
	for (const c of hijos) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
	return el;
}

export function vaciar(el: Element) { while (el.firstChild) el.firstChild.remove(); }

/** Sparkline SVG: la cola de un número. Puntos nulos cortan la línea. */
export function cola(valores: (number | null)[], ancho = 96, alto = 22, color = '#050b2c', hasta = valores.length - 1): SVGSVGElement {
	const ns = 'http://www.w3.org/2000/svg';
	const svg = document.createElementNS(ns, 'svg');
	svg.setAttribute('width', String(ancho));
	svg.setAttribute('height', String(alto));
	svg.setAttribute('viewBox', `0 0 ${ancho} ${alto}`);
	svg.setAttribute('aria-hidden', 'true');
	const vs = valores.slice(0, hasta + 1);
	const nums = vs.filter((v): v is number => v !== null);
	if (nums.length < 2) return svg;
	const min = Math.min(...nums), max = Math.max(...nums);
	const rango = Math.max(60, max - min);
	const medio = (min + max) / 2;
	const x = (i: number) => (i / Math.max(1, valores.length - 1)) * (ancho - 4) + 2;
	const y = (v: number) => alto / 2 - ((v - medio) / rango) * (alto - 6);
	let d = '';
	let abierto = false;
	vs.forEach((v, i) => {
		if (v === null) { abierto = false; return; }
		d += `${abierto ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
		abierto = true;
	});
	const p = document.createElementNS(ns, 'path');
	p.setAttribute('d', d);
	p.setAttribute('fill', 'none');
	p.setAttribute('stroke', color);
	p.setAttribute('stroke-width', '1.4');
	p.setAttribute('stroke-linejoin', 'round');
	p.setAttribute('stroke-linecap', 'round');
	svg.append(p);
	const ult = vs.length - 1;
	if (vs[ult] !== null) {
		const c = document.createElementNS(ns, 'circle');
		c.setAttribute('cx', x(ult).toFixed(1));
		c.setAttribute('cy', y(vs[ult] as number).toFixed(1));
		c.setAttribute('r', '2.2');
		c.setAttribute('fill', color);
		svg.append(c);
	}
	return svg;
}

export const icono = {
	jugar: '<svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 1.8v8.4L10 6z" fill="currentColor"/></svg>',
	pausa: '<svg width="12" height="12" viewBox="0 0 12 12"><rect x="2.5" y="2" width="2.4" height="8" rx=".6" fill="currentColor"/><rect x="7.1" y="2" width="2.4" height="8" rx=".6" fill="currentColor"/></svg>',
	buscar: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="7" cy="7" r="4.8"/><path d="m10.6 10.6 3.4 3.4" stroke-linecap="round"/></svg>',
	volver: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10 3 5 8l5 5"/></svg>',
	marca: '<svg width="14" height="14" viewBox="0 0 14 14"><g fill="#fff"><circle cx="3" cy="3.5" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="11" cy="10.5" r="1.3"/><circle cx="11" cy="3.5" r="1.3"/><circle cx="3" cy="10.5" r="1.3"/></g></svg>',
};
