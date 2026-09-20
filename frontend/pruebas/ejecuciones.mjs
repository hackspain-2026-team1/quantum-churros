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
 // Lo ejecutado deja de ser una casilla: la fila cuenta su estado, baja de la lista y sale del horizonte.
 const fila = () => page.$eval('.rec[data-accion]:not([data-estado="disponible"])', el => ({ estado: el.dataset.estado, casilla: !el.querySelector('.rec-tick').hidden, elegida: el.classList.contains('elegida'), texto: el.querySelector('.rec-estado').innerText }));
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 assert.deepEqual({ ...(await fila()), texto: undefined }, { estado: 'en_curso', casilla: false, elegida: false, texto: undefined });
 assert.match((await fila()).texto, /EN CURSO|En curso/);
 assert.equal(await page.$eval('.sec-acciones-cabecera .boton-propuesta', el => el.textContent), 'Ejecutar acciones');
 assert(await page.evaluate(() => { const l = [...document.querySelectorAll('.recomendaciones > li')]; return l.indexOf(document.querySelector('.rec-corte')) < l.indexOf(document.querySelector('.rec[data-estado="en_curso"]')); }));
 assert.equal(await page.evaluate(() => document.activeElement?.classList.contains('ejecucion')), true);
 // Pulsar la fila ya decidida lleva a su seguimiento; no la vuelve a marcar.
 await page.click('.rec[data-estado="en_curso"] .rec-titulo');
 assert.equal((await fila()).elegida, false);
 // La confirmación no vuelve a ofrecerla.
 await page.click('.sec-acciones-cabecera .boton-propuesta');
 await page.waitForSelector('[role=dialog]');
 const ofrecidas = await page.$$eval('.confirmacion-acciones .propuesta-accion', els => els.length);
 assert.equal(ofrecidas, await page.$$eval('.rec[data-estado="disponible"]', els => els.length));
 await page.keyboard.press('Escape');
 await page.reload();
 await page.waitForSelector('.ejecucion');
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 // Una actualización vacía no se puede guardar; pausar y reanudar se reflejan en la fila.
 await page.click('.ejecucion-abrir');
 assert.equal(await page.$eval('.ejecucion-controles .boton-propuesta', el => el.disabled), true);
 await page.click('.ejecucion-controles button:nth-child(2)');
 await page.waitForSelector('.rec[data-estado="pausada"]');
 assert.equal(await page.$$eval('.ejecuciones-activas .ejecucion.estado-pausada', els => els.length), 1);
 await page.click('.ejecucion-abrir');
 await page.click('.ejecucion-controles button:nth-child(2)');
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 await page.click('.ejecucion-abrir');
 await page.type('.ejecucion-dialogo textarea', 'Seguimiento verificado en una base de pruebas aislada.');
 await page.click('.ejecucion-controles button:last-child');
 await page.waitForFunction(() => document.querySelector('.ejecuciones-archivo .ejecucion') !== null);
 await page.waitForSelector('.rec[data-estado="completada"]');
 await page.reload();
 await page.waitForSelector('.ejecucion');
 assert.equal(await page.$$eval('.ejecuciones-archivo .ejecucion', els => els.length), 1);
 assert.equal(await page.$$eval('.ejecuciones-activas .ejecucion', els => els.length), 0);
 await page.click('.ejecuciones-archivo > summary');
 await page.click('.ejecucion-abrir');
 assert.equal(await page.$$eval('.ejecucion-historial li', els => els.length), 4);
 // Reabrir la devuelve al seguimiento activo y a la fila; se vuelve a finalizar para dejarla cerrada.
 await page.click('.ejecucion-controles button:last-child');
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 assert.equal(await page.$$eval('.ejecuciones-activas .ejecucion', els => els.length), 1);
 await page.click('.ejecucion-abrir');
 await page.click('.ejecucion-controles button:last-child');
 await page.waitForSelector('.rec[data-estado="completada"]');
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
 console.log('OK: error sin falsa confirmación, ejecución, estado en la fila, pausa, reanudación, reapertura, persistencia tras recarga, finalización explícita, historial, ausencia de progreso inventado, móvil y empresa sin palancas.');
} finally { await browser.close(); }
