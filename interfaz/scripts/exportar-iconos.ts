// Exporta los grabados de los 7 productos (QUA-7) a public/productos/ y la hoja de prueba:
// cada producto a 96, 48, 24 y 16 px, en sus cuatro estados, en color y en gris.
// Uso: bun scripts/exportar-iconos.ts
import { writeFileSync, mkdirSync, readdirSync, unlinkSync } from 'node:fs';
import { FAMILIAS, PRODUCTOS } from '../src/datos/productos';
import { svgProducto, type EstadoIcono } from '../src/vistas/iconos';

const dir = new URL('../public/productos/', import.meta.url);
mkdirSync(dir, { recursive: true });
for (const f of readdirSync(dir)) if (f.endsWith('.svg')) unlinkSync(new URL(f, dir));
for (const p of PRODUCTOS) {
	writeFileSync(new URL(`${p.id}.svg`, dir), svgProducto(p.id, { tam: 96 }));
	writeFileSync(new URL(`${p.id}-24.svg`, dir), svgProducto(p.id, { tam: 24 }));
}
const ESTADOS: [EstadoIcono, string][] = [['tiene', 'Tiene'], ['encaja', 'Le encaja'], ['bloqueado', 'Bloqueado'], ['no_consta', 'No consta']];
const filas = (['proteccion', 'cobertura', 'inversion'] as const).map((f) => `
	<section><h2>${FAMILIAS[f].nombre} <small>${FAMILIAS[f].lema} · ${FAMILIAS[f].tono}</small></h2>
	${PRODUCTOS.filter((p) => p.familia === f).map((p) => `
	<div class="producto">
		<div class="nombre"><b>${p.nombre}</b>${p.nivel ? ` · nivel ${p.nivel}` : ''}<br><span>${p.metafora}</span></div>
		<div class="tams">${[96, 48, 24, 16].map((t) => `<figure>${svgProducto(p.id, { tam: t })}<figcaption>${t}</figcaption></figure>`).join('')}</div>
		<div class="gris tams">${[48, 24].map((t) => svgProducto(p.id, { tam: t })).join('')}</div>
		<div class="estados">${ESTADOS.map(([e, n]) => `<figure>${svgProducto(p.id, { tam: 48, estado: e })}<figcaption>${n}</figcaption></figure>`).join('')}</div>
	</div>`).join('')}</section>`).join('');
writeFileSync(new URL('muestras.html', dir), `<!doctype html><html lang="es"><meta charset="utf-8"><title>Rumbo · grabados de productos</title>
<style>body{font:14px/1.4 system-ui,sans-serif;color:#050b2c;margin:36px;background:#fff}h1{font:600 28px Georgia,serif;margin:0 0 6px}p.lead{color:#6e707c;margin:0 0 20px}
h2{font:600 20px Georgia,serif;margin:26px 0 8px}h2 small{font:400 13px system-ui;color:#6e707c;margin-left:8px}
.producto{display:grid;grid-template-columns:190px auto auto auto;gap:28px;align-items:center;padding:12px 0;border-top:1px solid #e8e8ed}
.nombre span{color:#6e707c;font-size:12.5px}.tams,.estados{display:flex;gap:14px;align-items:flex-end}figure{margin:0;text-align:center}figcaption{font-size:11px;color:#9a9cab}
.gris{filter:grayscale(1);padding-left:14px;border-left:1px solid #e8e8ed}
.estado-encaja .grano{animation:llega .9s cubic-bezier(.2,.8,.2,1) both}@keyframes llega{from{opacity:0;transform:translateY(-3px)}}</style>
<h1>Rumbo · los siete productos</h1><p class="lead">Grabados a mano: contorno de plumilla, sombra punteada en arena y filete de familia. De izquierda a derecha: tamaños ópticos, en gris y los cuatro estados.</p>${filas}</html>`);
console.log('Exportados', PRODUCTOS.length * 2, 'SVG y la hoja de prueba');
