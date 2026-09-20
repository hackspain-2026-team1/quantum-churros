// Requires a disposable API/database: this test creates real execution records.
import puppeteer from 'puppeteer-core';
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
const api = process.env.XRAY_EXECUTIONS_API;
if (!api) throw new Error('XRAY_EXECUTIONS_API debe apuntar a una API con base de pruebas aislada.');
const browser = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
await page.setViewport({width: 1440, height: 1000});
let fail = false;
await page.setRequestInterception(true);
page.on('request', async req => {
 const url = new URL(req.url());
 if (!url.pathname.startsWith('/api/v1/action-executions')) return req.continue();
 if (fail && req.method() === 'POST' && url.pathname.endsWith('action-executions')) return req.respond({status: 503, contentType: 'application/json', body: JSON.stringify({detail:'No se pudo guardar. Vuelve a intentarlo.'})});
 try {
  const res = await fetch(api + url.pathname + url.search, {method: req.method(), headers: {'Content-Type':'application/json'}, body: req.postData()});
  await req.respond({status: res.status, contentType: 'application/json', body: await res.text()});
 } catch { await req.abort(); }
});
const base = process.env.XRAY_URL ?? 'http://127.0.0.1:5317/';
try {
 await page.goto(base + '?v=empresa&cfo=GROUP_0142&g=GROUP_0142&emp=COMP_0289&sec=acciones');
 await page.waitForSelector('.rec-marca input');
 await page.waitForFunction(() => document.querySelector('.ejecuciones')?.textContent.includes('No hay acciones en curso'));
 assert(!await page.evaluate(() => /Mi plan para el banco|Informe en PDF|Descargar PDF/.test(document.body.innerText)));
 await page.click('.rec-marca input');
 fail = true;
 await page.click('.sec-acciones-cabecera .boton-propuesta');
 await page.waitForSelector('[role=dialog]');
 assert.equal(await page.$$eval('.propuesta-banco', els => els.length), 4);
 assert(!await page.$('.propuesta-col-doc'));
 await page.click('.confirmacion-acciones .boton-propuesta');
 await page.waitForFunction(() => document.querySelector('.confirmacion-acciones')?.textContent.includes('No se pudo guardar'));
 assert.equal(await page.$$eval('.ejecucion', els => els.length), 0);
 fail = false;
 await page.click('.confirmacion-acciones .boton-propuesta');
 await page.waitForSelector('.ejecucion');
 assert((await page.$eval('.ejecucion', el => el.textContent)).includes('A la espera del próximo cierre'));
 assert.equal(await page.$$eval('.ejecucion progress', els => els.length), 0);
 await page.reload();
 await page.waitForSelector('.ejecucion');
 await page.click('.ejecucion-abrir');
 await page.type('.ejecucion-dialogo textarea', 'Seguimiento verificado en una base de pruebas aislada.');
 await page.click('.ejecucion-controles button:last-child');
 await page.waitForFunction(() => document.querySelector('.ejecuciones-archivo .ejecucion') !== null);
 await page.reload();
 await page.waitForSelector('.ejecucion');
 assert.equal(await page.$$eval('.ejecuciones-archivo .ejecucion', els => els.length), 1);
 assert.equal(await page.$$eval('.ejecuciones-activas .ejecucion', els => els.length), 0);
 await page.click('.ejecuciones-archivo > summary');
 await page.click('.ejecucion-abrir');
 assert.equal(await page.$$eval('.ejecucion-historial li', els => els.length), 2);
 await page.click('.ejecucion-dialogo header button');
 assert.equal(await page.$$eval('.ejecucion progress', els => els.length), 0);
 if (process.env.XRAY_CAPTURAS) {
  mkdirSync(process.env.XRAY_CAPTURAS, {recursive: true});
  await page.$eval('.ejecuciones', el => el.scrollIntoView());
  await page.screenshot({path: process.env.XRAY_CAPTURAS + '/seguimiento-acciones.png'});
 }
 await page.setViewport({width: 390, height: 844});
 await page.$eval('.ejecuciones', el => el.scrollIntoView());
 assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
 if (process.env.XRAY_CAPTURAS) await page.screenshot({path: process.env.XRAY_CAPTURAS + '/seguimiento-movil.png'});
 await page.goto(base + '?v=empresa&cfo=GROUP_0250&g=GROUP_0250&emp=COMP_0263&sec=acciones');
 await page.waitForSelector('.rec.vacia');
 await page.waitForFunction(() => document.querySelector('.ejecuciones')?.textContent.includes('No hay acciones en curso'));
 await page.click('.sec-acciones-cabecera .boton-propuesta');
 await page.waitForSelector('[role=dialog]');
 assert.equal(await page.$eval('.confirmacion-acciones .boton-propuesta', el => el.disabled), true);
 await page.keyboard.press('Escape');
 await page.goto(base + '?v=empresa&cfo=GROUP_0035&g=GROUP_0035&emp=COMP_1134&sec=acciones');
 await page.waitForFunction(() => {const b=document.querySelector('.sec-acciones-cabecera .boton-propuesta');return b && !b.disabled;});
 await page.click('.sec-acciones-cabecera .boton-propuesta');
 await page.waitForSelector('.confirmacion-instrumento input');
 await page.click('.confirmacion-instrumento input');
 await page.click('.propuesta-ofertas .propuesta-oferta:nth-child(2) input');
 await page.click('.confirmacion-acciones .boton-propuesta');
 await page.waitForSelector('.ejecucion');
 assert((await page.$eval('.ejecucion',el=>el.textContent)).includes('Bancos elegidos'));
 await page.reload();
 await page.waitForSelector('.ejecucion');
 assert((await page.$eval('.ejecucion',el=>el.textContent)).includes('Bancos elegidos'));
 assert.deepEqual(errors, []);
 console.log('OK: error sin falsa confirmación, ejecución, persistencia tras recarga, finalización explícita, historial, ausencia de progreso inventado, móvil y empresa sin palancas.');
} finally { await browser.close(); }
