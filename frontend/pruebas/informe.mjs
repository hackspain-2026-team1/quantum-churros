// Genera el PDF del informe de una ficha como lo haría el navegador al imprimir:
// bun pruebas/informe.mjs <url> <salida.pdf>
import puppeteer from 'puppeteer-core';
const [, , url, salida] = process.argv;
const b = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
const errores = [];
p.on('pageerror', (e) => errores.push(e.message));
await p.goto(url);
await new Promise((r) => setTimeout(r, Number(process.env.ESPERA ?? 3000)));
await p.evaluate(() => dispatchEvent(new Event('beforeprint')));
const hay = await p.evaluate(() => ({ informe: !!document.querySelector('.capa-informe .informe'), imagenes: document.querySelectorAll('.capa-informe .arena-impresa').length, secciones: document.querySelectorAll('.capa-informe .informe-seccion').length }));
await p.pdf({ path: salida, format: 'A4', printBackground: true, preferCSSPageSize: true });
await p.evaluate(() => dispatchEvent(new Event('afterprint')));
const quitado = await p.evaluate(() => !document.querySelector('.capa-informe'));
console.log(JSON.stringify({ ...hay, quitado, errores }));
await b.close();
