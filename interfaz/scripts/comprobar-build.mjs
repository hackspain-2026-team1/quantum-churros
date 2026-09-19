// Comprobaciones del build de producción (dist/), sin navegador y sin datos: lo que corre en CI
// antes de meter Rumbo en la imagen web.
//   · no lleva datos dentro: ni el bundle ni lo generado por Rumbo (se montan en el servidor);
//   · no lleva la cartera sintética ni identificadores reales escritos a mano;
//   · no pide nada a terceros: solo el espacio de nombres SVG y el Worker de Jev (VITE_VISTA_URL, en .env);
//   · todos los recursos cuelgan de la base con la que se construyó.
// Uso: bun scripts/comprobar-build.mjs [base]   (por defecto, /rumbo/)

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const base = process.argv[2] ?? '/rumbo/';
const dist = fileURLToPath(new URL('../dist/', import.meta.url));
const fallos = [];
const falla = (m) => fallos.push(m);

function ficheros(dir) {
	return readdirSync(dir).flatMap((n) => {
		const p = join(dir, n);
		return statSync(p).isDirectory() ? ficheros(p) : [p];
	});
}

if (!existsSync(join(dist, 'index.html'))) {
	console.error('No hay dist/index.html: ejecuta antes el build.');
	process.exit(1);
}

for (const carpeta of ['datos', 'rumbo', 'data']) {
	if (existsSync(join(dist, carpeta))) falla(`dist/${carpeta} existe: los datos no pueden ir dentro de la imagen`);
}

const todos = ficheros(dist);
const codigo = todos.filter((f) => /\.(js|css|html)$/.test(f));
const PERMITIDAS = new Set(['http://www.w3.org/2000/svg', 'http://www.w3.org/1999/xlink']);
// El Worker propio de «dile qué quieres ver»: la única dirección externa admitida.
const envTexto = existsSync(new URL('../.env', import.meta.url)) ? readFileSync(new URL('../.env', import.meta.url), 'utf8') : '';
const worker = (process.env.VITE_VISTA_URL ?? envTexto.match(/^VITE_VISTA_URL=(.*)$/m)?.[1] ?? '').trim().replace(/\/$/, '');
if (worker) PERMITIDAS.add(worker);

for (const f of codigo) {
	const texto = readFileSync(f, 'utf8');
	const rel = f.slice(dist.length);
	for (const url of texto.match(/https?:\/\/[^\s"'`)<>]+/g) ?? []) {
		if (!PERMITIDAS.has(url)) falla(`${rel}: URL externa ${url}`);
	}
	for (const id of texto.match(/\b(?:COMP|GROUP)_\d{2,}\b/g) ?? []) falla(`${rel}: identificador escrito a mano ${id}`);
}
for (const f of todos) {
	if (/sintetic/i.test(f.slice(dist.length))) falla(`${f.slice(dist.length)}: la cartera sintética no puede ir en producción`);
}

const html = readFileSync(join(dist, 'index.html'), 'utf8');
for (const [, ruta] of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
	if (!/^(https?:|data:|#)/.test(ruta) && !ruta.startsWith(base)) falla(`index.html: ${ruta} no cuelga de ${base}`);
}

if (fallos.length) {
	console.error(`Build de Rumbo: ${fallos.length} problema(s)`);
	for (const m of fallos) console.error(`  · ${m}`);
	process.exit(1);
}
console.log(`Build de Rumbo correcto: ${todos.length} ficheros bajo ${base}, sin datos, sin terceros, sin cartera sintética.`);
