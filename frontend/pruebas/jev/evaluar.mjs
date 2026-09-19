// Evalúa «dile qué quieres ver» de punta a punta: escribe cada frase en la portada, espera a Jev y
// compara la vista que queda (sus parámetros en la URL) con la esperada, pieza a pieza.
// bun pruebas/jev/evaluar.mjs   (con el servidor de desarrollo arrancado)
import puppeteer from 'puppeteer-core';
import { readFileSync, writeFileSync } from 'node:fs';
const frases = JSON.parse(readFileSync(new URL('./frases.json', import.meta.url)));
const CLAVES = ['mf', 'mm', 'mu', 'mo', 'mb', 'mz', 'mmov', 'msec', 'mpais', 'mtam', 'mprod'];
const b = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 1000 });
const salida = [];
let piezasOk = 0, piezasTotal = 0, vistasOk = 0, sobra = 0, ms = 0, aceptables = 0;
for (const [frase, esperado] of frases) {
	await p.goto('http://127.0.0.1:5317/?captura');
	await p.waitForSelector('.entrada-buscar');
	await p.type('.entrada-buscar', frase);
	await p.keyboard.press('Enter');
	await p.waitForFunction(() => /Jev,|No sé qué vista|no responde/.test(document.querySelector('.mon-entendido')?.textContent ?? ''), { timeout: 30000 }).catch(() => {});
	const r = await p.evaluate(() => ({ q: location.search, texto: document.querySelector('.mon-entendido')?.textContent ?? '' }));
	const q = new URLSearchParams(r.q);
	// Lo que no está en la URL es el valor por defecto (forma ranking, orden por gravedad…).
	const obtenido = { mf: 'ranking', mo: 'gravedad', mu: 'organizaciones', ...Object.fromEntries(CLAVES.filter((k) => q.has(k)).map((k) => [k, q.get(k)])) };
	const POR_DEFECTO = { mf: 'ranking', mo: 'gravedad', mu: 'organizaciones' };
	const aciertos = Object.entries(esperado).filter(([k, v]) => obtenido[k] === v).length;
	const extra = Object.keys(obtenido).filter((k) => !(k in esperado) && k !== 'mm' && obtenido[k] !== POR_DEFECTO[k]);
	// Una forma o un orden de más no estrechan la vista: se cuentan aparte.
	const extraFiltros = extra.filter((k) => !['mf', 'mo'].includes(k));
	if (!extraFiltros.length) aceptables++;
	piezasOk += aciertos; piezasTotal += Object.keys(esperado).length; sobra += extra.length;
	const bien = aciertos === Object.keys(esperado).length && !extra.length;
	if (aciertos !== Object.keys(esperado).length && !extraFiltros.length) aceptables--;
	if (bien) vistasOk++;
	const t = Number(r.texto.match(/Jev, ([\d,]+) s/)?.[1]?.replace(',', '.') ?? 0); ms += t;
	salida.push({ frase, esperado, obtenido, bien, segundos: t, entendido: r.texto });
	console.log(`${bien ? '✓' : '✗'} ${frase} → ${JSON.stringify(obtenido)}${bien ? '' : `  (esperado ${JSON.stringify(esperado)})`}`);
}
await b.close();
const res = { fecha: new Date().toISOString(), frases: frases.length, vistas_correctas: vistasOk, vistas_sin_filtros_de_mas: aceptables, piezas_correctas: piezasOk, piezas_esperadas: piezasTotal, piezas_de_mas: sobra, segundos_medios: +(ms / frases.length).toFixed(2), detalle: salida };
writeFileSync(new URL('./resultados.json', import.meta.url), JSON.stringify(res, null, 1));
console.log(`\nVistas exactas: ${vistasOk} de ${frases.length} · con todas las piezas y sin filtros de más: ${aceptables} · piezas: ${piezasOk} de ${piezasTotal} · piezas de más: ${sobra} · ${res.segundos_medios} s de media`);
