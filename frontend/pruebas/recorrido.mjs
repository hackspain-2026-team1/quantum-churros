// Recorrido automático de Rumbo con Chrome (puppeteer-core), sobre los datos reales.
// Comprueba el recorrido entero (entrada → organización → empresa → cuatro secciones), que lo que
// sale en pantalla es lo que dicen los ficheros, las lentes de la cartera, la metodología, el móvil y
// las guardias: ninguna petición a terceros y ningún identificador escrito en el código.
// Uso: con el servidor arrancado (bun run dev), `bun run prueba`. Deja capturas en pruebas/capturas/.

import puppeteer from 'puppeteer-core';
import { mkdirSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const DIRECCION = process.env.XRAY_URL ?? 'http://127.0.0.1:5317/';
// Raíces de datos: en desarrollo /datos/ y /rumbo/; contra el servidor de producción, /data/v1/ y /data/rumbo/.
const DATOS = process.env.XRAY_DATOS ?? '/datos/';
const RUMBO = process.env.XRAY_RUMBO ?? '/rumbo/';
const DIR = fileURLToPath(new URL('./capturas/', import.meta.url));
const GRABADA = readFileSync(new URL('./jev/respuesta-grabada.json', import.meta.url), 'utf8');
const SRC = fileURLToPath(new URL('../src/', import.meta.url));
mkdirSync(DIR, { recursive: true });
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
let fallos = 0, total = 0;
const comprobar = (nombre, cond, detalle = '') => { total++; console.log(`${cond ? '✓' : '✗'} ${nombre}${detalle ? ` · ${detalle}` : ''}`); if (!cond) fallos++; };

// ─── Guardia estática: ningún identificador de empresa o grupo en el código de la aplicación ───
const ficheros = [];
const recorrer = (d) => { for (const f of readdirSync(d)) { const p = `${d}/${f}`; if (statSync(p).isDirectory()) recorrer(p); else if (/\.(ts|css|html)$/.test(f)) ficheros.push(p); } };
recorrer(SRC.replace(/\/$/, ''));
const conLiterales = ficheros.filter((p) => !p.endsWith('sintetico.ts') && /\b(COMP|GROUP)_\d{2,}/.test(readFileSync(p, 'utf8')));
comprobar('ningún identificador de empresa o grupo escrito en el código', conLiterales.length === 0, conLiterales.join(', '));

const navegador = await puppeteer.launch({
	executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
	headless: 'new',
	args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});

async function pagina(ruta, ancho = 1440, alto = 860, movil = false) {
	const p = await navegador.newPage();
	await p.setViewport({ width: ancho, height: alto, deviceScaleFactor: 2, isMobile: movil, hasTouch: movil });
	p.errores = []; p.fuera = [];
	p.on('console', (m) => { if (m.type() === 'error') p.errores.push(m.text()); });
	p.on('pageerror', (e) => p.errores.push(e.message));
	// El Worker de Jev es el único servicio externo, y en las pruebas responde una grabación.
	await p.setRequestInterception(true);
	p.on('request', (r) => {
		const u = new URL(r.url());
		if (u.hostname.endsWith('.workers.dev') && r.method() === 'OPTIONS') return r.respond({ status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Allow-Methods': 'POST, OPTIONS' } });
		if (u.hostname.endsWith('.workers.dev') && u.pathname === '/vista') { p.jev = (p.jev ?? 0) + 1; return r.respond({ status: 200, contentType: 'application/json', headers: { 'Access-Control-Allow-Origin': '*' }, body: GRABADA }); }
		if (!['127.0.0.1', 'localhost'].includes(u.hostname) && u.protocol.startsWith('http')) p.fuera.push(r.url());
		r.continue();
	});
	await p.evaluateOnNewDocument(() => localStorage.clear());
	await p.goto(`${DIRECCION}?captura${ruta}`, { waitUntil: 'networkidle0' });
	await esperar(900);
	return p;
}
const estado = (p) => p.evaluate(() => { const e = window.xray.S.e; return { vista: e.vista, sel: e.sel, emp: e.emp, sec: e.sec, lente: e.lente, q: e.q, previa: e.previa }; });
const frase = (p) => p.evaluate(() => document.querySelector('.frase-linea').textContent.replace(/\s+/g, ' ').trim());
const foto = (p, n) => p.screenshot({ path: `${DIR}${n}.png` });
const leer = (p, ruta) => p.evaluate(async (r) => (await fetch(r)).json(), ruta);
const hasta = async (p, cond, ms = 6000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (await p.evaluate(cond)) return true; await esperar(150); } return false; };

// ─── 1. La entrada ─────────────────────────────────────────
const p = await pagina('');
comprobar('arranca en la entrada', (await estado(p)).vista === 'entrada');
comprobar('los datos son los del motor', (await p.$eval('.nota-datos', (x) => x.textContent)).includes('datos reales'));
await hasta(p, () => document.querySelectorAll('.atencion li.tocable').length > 0);
comprobar('«las que piden atención hoy» sale de los datos', (await p.$$('.atencion li.tocable')).length > 0);
comprobar('la portada lleva la rosa de los vientos y no repite la marca en la cabecera', await p.evaluate(() => !!document.querySelector('.entrada-rosa[data-placa]') && getComputedStyle(document.querySelector('.barra .marca')).visibility === 'hidden'));
// ─── 1b. El monitor ───────────────────────────────────────
{
	const pf = await leer(p, `${DATOS}portfolio.json`);
	const tt = pf.months.length - 1;
	const criticas = pf.groups.filter((g) => g.band[tt] === 'critical').length;
	const linea = await p.$eval('.mon-estado', (x) => x.textContent);
	comprobar('el estado del mes sale de portfolio.json', linea.includes(`${criticas} en crítico`), `${criticas} en crítico`);
	const primera = await p.$eval('.mon-atencion li.tocable .at-texto', (x) => x.textContent);
	comprobar('piden atención empieza por las que entran en crítico', primera.startsWith('entra en crítico'), primera);
	const campana = await p.$eval('.campana', (x) => x.textContent);
	comprobar('la portada abre el plano y el tapiz a pantalla completa', (await p.$$eval('.mon-mapas .mapa-btn', (xs) => xs.map((x) => x.textContent))).join('|').includes('tapiz'));
	comprobar('la campana cuenta los avisos del mes', /\d+ avisos?/.test(campana), campana);
	// Las siete formas, en arena y en tabla.
	let formasOk = 0;
	for (const forma of ['ranking', 'bandas', 'plano', 'tapiz', 'flujo', 'avisos', 'horizonte']) {
		await p.click(`.mon-forma[data-forma="${forma}"]`); await esperar(250);
		const arena = await p.$('.mon-lienzo[data-placa], .mon-lienzo .mon-lienzo-arena[data-placa]');
		await p.click('.mon-modo button[data-valor="tabla"]'); await esperar(250);
		const tabla = await p.$('.mon-tabla');
		await p.click('.mon-modo button[data-valor="arena"]'); await esperar(150);
		if (arena && tabla) formasOk++;
	}
	comprobar('las siete formas se ven en arena y en tabla', formasOk === 7, `${formasOk} de 7`);
	await p.click('.mon-forma[data-forma="bandas"]'); await esperar(700);
	const antes = await p.evaluate(() => [...window.xray.arena.px.slice(0, 20000)]);
	await p.click('.mon-forma[data-forma="plano"]'); await esperar(900);
	const movidos = await p.evaluate((a) => { const b = window.xray.arena.px; let n = 0; for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 3) n++; return n; }, antes);
	comprobar('cambiar de forma mueve los granos de cada entidad', movidos > 5000, `${movidos} granos`);
	await p.click('.mon-unidad button[data-valor="empresas"]'); await esperar(500);
	const nEmp = await p.$eval('.mon-cuantas', (x) => x.textContent);
	comprobar('el monitor cambia a empresas', /empresas/.test(nEmp), nEmp);
	await p.click('.mon-unidad button[data-valor="organizaciones"]'); await esperar(300);
	// «Dile qué quieres ver»: palabras al instante y Jev (grabado) después.
	comprobar('«dile qué quieres ver» está a la vista, con ejemplos', await p.evaluate(() => { const c = document.querySelector('.mon-pedir-campo'); const r = c?.getBoundingClientRect(); return !!r && r.width > 200 && document.querySelectorAll('.mon-ejemplos .ejemplo').length >= 3; }));
	await p.type('.mon-pedir-campo', 'las organizaciones grandes que se tuercen, en tabla');
	await p.keyboard.press('Enter');
	await hasta(p, () => /Jev,/.test(document.querySelector('.mon-entendido')?.textContent ?? ''));
	const q = await p.evaluate(() => Object.fromEntries(new URLSearchParams(location.search)));
	comprobar('dile qué quieres ver: la frase se vuelve una vista', q.mz === 'tuerce' && q.mtam === 'Grande' && q.mm === 'tabla' && !!p.jev, JSON.stringify({ mz: q.mz, mtam: q.mtam, mm: q.mm }));
	await foto(p, '01b-monitor');
	await p.$eval('.mon-descripcion .mon-quitar', (b) => b.click()); await esperar(200);
	await p.evaluate(() => { history.replaceState(null, '', location.pathname + '?captura'); });
	await p.goto(`${DIRECCION}?captura`, { waitUntil: 'networkidle0' }); await esperar(900);
}
await foto(p, '01-entrada');
await p.type('.entrada-buscar', '237');
await esperar(200);
const entidades = await leer(p, `${RUMBO}entities.json`).catch(() => null);
const nombre237 = entidades?.groups?.GROUP_0237?.name ?? 'Grupo 237';
comprobar('escribir un número encuentra la organización', (await p.$eval('.entrada-resultados', (x) => x.textContent)).includes(nombre237));
await p.keyboard.press('Enter');
await hasta(p, () => document.querySelector('.hoja-ficha h1')?.textContent === 'Grupo 237');
let e = await estado(p);
comprobar('Enter abre la organización', e.vista === 'organizacion' && e.sel === 'GROUP_0237', `${e.vista} ${e.sel}`);
comprobar('una sola cabecera: la miga va junto a la marca', await p.evaluate(() => !!document.querySelector('.barra .miga .miga-paso.actual') && getComputedStyle(document.querySelector('.barra .marca')).visibility === 'visible'));

// ─── 2. La organización ────────────────────────────────────
const manifest = await leer(p, `${DATOS}manifest.json`);
const corte = manifest.months[manifest.months.length - 1];
const grupo = await leer(p, `${DATOS}groups/GROUP_0237.json`);
const mesG = grupo.months.find((m) => m.month === corte);
const numeroG = await p.$eval('.cab-numeral', (x) => x.getAttribute('aria-label'));
comprobar('el número del grupo es el del fichero', numeroG === `Score ${Math.round(mesG.shown / 10)}`, `${numeroG} · fichero ${mesG.shown}`);
const filas = await p.$$eval('.tabla-sutil.empresas tbody tr', (xs) => xs.length);
comprobar('la flota enseña todas sus empresas', filas === grupo.companies.length, `${filas} de ${grupo.companies.length}`);
await foto(p, '02-organizacion');
await p.keyboard.press('3');
await hasta(p, () => !!document.querySelector('.matriz'));
comprobar('la tecla 3 abre productos', (await estado(p)).sec === 'productos');
comprobar('la matriz empresas × productos tiene una fila por empresa', (await p.$$eval('.matriz tbody tr', (xs) => xs.length)) === grupo.companies.length);
await foto(p, '03-organizacion-productos');

// ─── 3. La empresa ─────────────────────────────────────────
await p.$eval('.matriz tbody tr .enlace-empresa', (b) => b.click());
await hasta(p, () => window.xray.S.e.vista === 'empresa' && !!document.querySelector('.hoja-ficha.company'));
e = await estado(p);
comprobar('desde la matriz se baja a la empresa', e.vista === 'empresa' && !!e.emp, e.emp ?? '');
const idE = e.emp;
const emp = await leer(p, `${DATOS}companies/${idE}.json`);
const prod = await leer(p, `${RUMBO}products/${idE}.json`);
const mesE = emp.months.find((m) => m.month === corte);
comprobar('la empresa se compara con las de su tamaño', (await p.$eval('.cab-explica', (x) => x.textContent)).includes('de su tamaño'));
comprobar('el número de la empresa es el del fichero', (await p.$eval('.cab-numeral', (x) => x.getAttribute('aria-label'))) === `Score ${Math.round(mesE.shown / 10)}`);
const tiene = await p.$$eval('.inv-item.estado-tiene', (xs) => xs.length);
comprobar('el inventario marca lo que tiene según products/', tiene === prod.held.length, `${tiene} en pantalla · ${prod.held.length} en el fichero`);
await foto(p, '04-empresa-productos');

await p.keyboard.press('2');
await hasta(p, () => !!document.querySelector('.recomendaciones'));
const recs = await p.$$eval('.recomendaciones .rec:not(.nada):not(.vacia)', (xs) => xs.length);
comprobar('las recomendaciones son las acciones del motor', recs === (mesE.actions ?? []).length, `${recs} · motor ${(mesE.actions ?? []).length}`);
if (recs) {
	await p.$eval('.recomendaciones .rec input[type=checkbox]', (x) => x.click());
	await esperar(400);
	comprobar('marcar una acción la lleva al horizonte', (await p.$eval('.frase-horizonte', (x) => x.textContent)).includes('Con esta acción'));
}
await foto(p, '05-empresa-acciones');

// El hilo lleva a la evidencia ya filtrada en su dato.
await p.keyboard.press('1');
await hasta(p, () => !!document.querySelector('.pt-fila.tocable'));
const pilarFila = await p.evaluate(() => { const f = document.querySelector('.pt-fila.tocable'); f.click(); return f.querySelector('.pt-nombre').firstChild.textContent; });
await hasta(p, () => !!document.querySelector('.evidencia select'));
const filtroPilar = await p.evaluate(() => { const s = document.querySelectorAll('.evidencia select')[1]; return s.options[s.selectedIndex].textContent; });
comprobar('un pilar lleva a su evidencia ya filtrada', filtroPilar === pilarFila, `${pilarFila} → ${filtroPilar}`);
// Triaje de avisos: se guarda y cambia de bandeja.
const hayAviso = await p.$('.bandeja .av-boton');
if (hayAviso) {
	const antes = await p.$$eval('.bandeja .aviso', (xs) => xs.length);
	await p.evaluate(() => [...document.querySelectorAll('.bandeja .av-boton')].find((b) => b.textContent === 'Descartar').click());
	await esperar(200);
	const despues = await p.$$eval('.bandeja .aviso', (xs) => xs.length);
	const guardado = await p.evaluate(() => Object.keys(JSON.parse(localStorage.getItem('rumbo.avisos.v1') ?? '{}')).length);
	comprobar('descartar un aviso lo saca de la bandeja y se guarda', despues === antes - 1 && guardado === 1, `${antes} → ${despues}`);
}
await p.keyboard.press('4');
await hasta(p, () => !!document.querySelector('.cascada-t'));
comprobar('la cascada cuadra al décimo', (await p.$eval('.cascada-t .total', (x) => x.textContent)).includes('cuadra al décimo'));
comprobar('las curvas son las de los parámetros verificados', (await p.$$('.fig-curva')).length >= 5);
await foto(p, '06-empresa-tecnico');

await p.keyboard.press('1');
await hasta(p, () => !!document.querySelector('.cifras-c'));
comprobar('el scoring enseña el previsto a seis meses', (await p.$eval('.cifras-c', (x) => x.textContent)).includes('previsto a seis meses'));
// Los tres escenarios a la vez; elegir otro reorganiza la arena.
if (await p.$('.esc-drift')) {
	comprobar('los escenarios alternativos se ven a la vez', (await p.$$('.grafico .g-etq.alternativa')).length === 2);
	const antes = await p.evaluate(() => [...window.xray.arena.px.slice(0, 40000)]);
	await p.click('.esc-drift');
	await esperar(900);
	const cambio = await p.evaluate((a) => { const b = window.xray.arena.px; let n = 0; for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 2) n++; return n; }, antes);
	const elegido = await p.$eval('.esc-drift', (x) => x.getAttribute('aria-checked'));
	comprobar('elegir un escenario reorganiza la arena', elegido === 'true' && cambio > 500, `${cambio} granos se mueven`);
	await p.click('.esc-base');
	await esperar(300);
}
// El informe para imprimir: las cuatro secciones, con la arena cocida en imágenes.
await p.evaluate(() => dispatchEvent(new Event('beforeprint')));
const inf = await p.evaluate(() => ({ secciones: document.querySelectorAll('.capa-informe .informe-seccion').length, arena: document.querySelectorAll('.capa-informe .arena-impresa').length }));
await p.evaluate(() => dispatchEvent(new Event('afterprint')));
comprobar('el informe imprime las cuatro secciones con su arena', inf.secciones === 4 && inf.arena >= 2 && !(await p.$('.capa-informe')), `${inf.secciones} secciones · ${inf.arena} placas`);
await foto(p, '07-empresa-scoring');
await p.keyboard.press('Escape');
await esperar(600);
comprobar('Esc sube a la organización', (await estado(p)).vista === 'organizacion');

// ─── 4. Metodología ────────────────────────────────────────
await p.evaluate(() => window.xray.S.fijar({ vista: 'metodologia' }, true));
await hasta(p, () => document.querySelectorAll('.checks .check').length > 0);
const recibo = await leer(p, `${DATOS}receipt.json`);
comprobar('la metodología enseña todas las comprobaciones del recibo', (await p.$$eval('.checks .check', (xs) => xs.length)) === recibo.checks.length);
await foto(p, '08-metodologia');

// ─── 5. La cartera como mapa ───────────────────────────────
await p.evaluate(() => window.xray.S.fijar({ vista: 'plano', lente: 'score' }, true));
await esperar(700);
comprobar('el mapa arranca con la frase', (await frase(p)).startsWith(`Los ${manifest.counts.groups} grupos de la cartera`), await frase(p));
await p.click('.ficha-escala');
await esperar(250);
const opciones = await p.$$('.panel .opcion');
await opciones[1].hover();
await esperar(200);
e = await estado(p);
comprobar('pasar por una opción la previsualiza', e.previa && e.q.escala === 'trimestre');
await opciones[1].click();
await esperar(300);
await p.click('.ficha-quien');
await esperar(250);
const tuercen = await p.$$eval('.panel .opcion', (bs) => bs.findIndex((b) => b.textContent.startsWith('Se tuercen')));
await (await p.$$('.panel .opcion'))[tuercen].click();
await esperar(400);
comprobar('el tamiz y la escala: los que se tuercen, por trimestres', /que se tuercen.*por trimestres/.test(await frase(p)), await frase(p));
for (let i = 0; i < 6; i++) { await p.keyboard.down('Meta'); await p.keyboard.press('z'); await p.keyboard.up('Meta'); await esperar(150); }
e = await estado(p);
comprobar('⌘Z deshace sin salir de la aplicación', !e.q.filtros.length && e.q.escala === 'mes');
await p.evaluate(() => window.xray.S.fijar({ vista: 'plano', lente: 'horizonte' }, true));
await esperar(600);
comprobar('la lente de horizonte se explica', (await p.$eval('.lente-leyenda', (x) => x.textContent)).startsWith('Horizonte'));
await foto(p, '09-lente-horizonte');
await p.evaluate(() => window.xray.S.fijar({ lente: 'productos' }, true));
await esperar(600);
comprobar('la lente de productos se explica', (await p.$eval('.lente-leyenda', (x) => x.textContent)).startsWith('Productos'));
await foto(p, '10-lente-productos');
await p.keyboard.type('42');
await esperar(250);
await p.keyboard.press('Enter');
await hasta(p, () => window.xray.S.e.vista === 'organizacion');
e = await estado(p);
comprobar('escribir 42 en el mapa abre su organización', e.vista === 'organizacion' && e.sel === 'GROUP_0042', `${e.vista} ${e.sel}`);
comprobar('sin errores de consola en escritorio', p.errores.length === 0, p.errores.join(' | '));
comprobar('ninguna petición a terceros', p.fuera.length === 0, p.fuera.slice(0, 3).join(' '));

// ─── 6. Móvil ──────────────────────────────────────────────
const m = await pagina('&v=empresa&g=GROUP_0237&emp=COMP_0023', 390, 844, true);
await hasta(m, () => !!document.querySelector('.hoja-ficha.company'));
comprobar('en el móvil la empresa cabe en el ancho', await m.evaluate(() => document.querySelector('.pagina').scrollWidth <= innerWidth + 1));
await foto(m, '11-movil-empresa');
const mm = await pagina('&v=plano', 390, 844, true);
await mm.tap('.ficha-quien');
await esperar(350);
comprobar('en el móvil el panel es una hoja', await mm.$eval('.panel', (x) => x.classList.contains('hoja') && x.classList.contains('ver')));
await mm.type('.panel-buscar', 'factor');
await esperar(500);
const primera = await mm.$eval('.panel .opcion .opcion-texto', (x) => x.textContent);
comprobar('en el móvil se escribe en el buscador del panel', primera.includes('factoring'), primera);
comprobar('sin errores de consola en el móvil', m.errores.length === 0 && mm.errores.length === 0, [...m.errores, ...mm.errores].join(' | '));

await navegador.close();
console.log(fallos ? `\n${fallos} de ${total} comprobaciones fallidas` : `\nTodo correcto: ${total} de ${total}`);
process.exit(fallos ? 1 : 0);
