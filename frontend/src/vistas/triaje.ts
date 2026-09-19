// Clasificación de avisos (traslado del triaje de la bandeja de Bruno): cada aviso del motor se
// puede marcar como visto o descartar, y restaurar. Se guarda solo en este navegador
// (localStorage) y se sincroniza entre pestañas; el bundle es de solo lectura.

import { claveDeMirada } from '../datos/redaccion';

export type Triaje = 'visto' | 'descartado';
const CLAVE = () => claveDeMirada('rumbo.avisos.v1');
const oyentes = new Set<() => void>();

function leer(): Record<string, Triaje> {
	try { return JSON.parse(localStorage.getItem(CLAVE()) ?? '{}'); } catch { return {}; }
}
let estado = leer();

addEventListener('storage', (e) => {
	if (e.key !== CLAVE()) return;
	estado = leer();
	for (const f of oyentes) f();
});

export const triaje = {
	/** Al cambiar de mirada se relee: cada una tiene su propio triaje. */
	releer() { estado = leer(); for (const f of oyentes) f(); },
	de: (id: string): Triaje | null => estado[id] ?? null,
	fijar(id: string, t: Triaje | null) {
		if (t) estado[id] = t; else delete estado[id];
		try { localStorage.setItem(CLAVE(), JSON.stringify(estado)); } catch { /* almacenamiento bloqueado: vale para la sesión */ }
		for (const f of oyentes) f();
	},
	oir(f: () => void) { oyentes.add(f); return () => oyentes.delete(f); },
};
