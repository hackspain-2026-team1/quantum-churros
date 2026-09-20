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
 await page.waitForFunction(() => { const b = document.querySelector('.sec-acciones-cabecera .boton-propuesta'); return b && !b.disabled; });
 // Sin decisiones no hay sección de seguimiento ni notas explicativas: solo la lista.
 assert.equal(await page.$eval('.ejecuciones', el => el.hidden), true);
 assert(!await page.evaluate(() => /Mi plan para el banco|Informe en PDF|Descargar PDF/.test(document.body.innerText)));
 await page.click('.rec-marca input');
 fail = true;
 await page.click('.sec-acciones-cabecera .boton-propuesta');
 await page.waitForSelector('[role=dialog]');
 assert.equal(await page.$$eval('.propuesta-banco', els => els.length), 4);
 assert(!await page.$('.propuesta-col-doc'));
 await page.click('.confirmacion-acciones .boton-propuesta');
 await page.waitForFunction(() => document.querySelector('.confirmacion-acciones')?.textContent.includes('No se pudo guardar'));
 assert.equal(await page.$$eval('.rec[data-ejecucion]', els => els.length), 0);
 fail = false;
 await page.click('.confirmacion-acciones .boton-propuesta');
 // Lo ejecutado se sigue en su propia fila: sin casilla, fuera del horizonte, con su medida y sus mandos.
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 const fila = () => page.$eval('.rec[data-ejecucion]', el => ({ estado: el.dataset.estado, casilla: !el.querySelector('.rec-tick').hidden, elegida: el.classList.contains('elegida'), medida: el.querySelector('.seg-medida')?.innerText ?? '', barras: el.querySelectorAll('progress').length, pasos: [...el.querySelectorAll('.seg-pasos .seg-paso')].map(b => b.textContent) }));
 let f1 = await fila();
 assert.deepEqual([f1.estado, f1.casilla, f1.elegida, f1.barras], ['en_curso', false, false, 0]);
 assert.match(f1.medida, /Inicio[\s\S]*Próximo cierre[\s\S]*Objetivo/);
 assert.deepEqual(f1.pasos, ['Pausar', 'Finalizar', 'Notas']);
 assert.equal(await page.$eval('.sec-acciones-cabecera .boton-propuesta', el => el.textContent), 'Ejecutar acciones');
 // No se repite debajo: la sección solo existe para lo que no tiene fila.
 assert.equal(await page.$eval('.ejecuciones', el => el.hidden), true);
 await page.waitForFunction(() => !document.querySelector('.confirmacion-acciones'));
 assert.equal(await page.$$eval('dialog', els => els.length), 0);
 // La confirmación no vuelve a ofrecerla.
 await page.click('.sec-acciones-cabecera .boton-propuesta');
 await page.waitForSelector('[role=dialog]');
 assert.equal(await page.$$eval('.confirmacion-acciones .propuesta-accion', els => els.length), await page.$$eval('.rec[data-estado="disponible"]', els => els.length));
 await page.keyboard.press('Escape');
 await page.reload();
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 // Pausar y reanudar, a un clic y sin diálogo.
 await page.click('.rec[data-ejecucion] .seg-pasos .seg-paso:nth-child(1)');
 await page.waitForSelector('.rec[data-estado="pausada"]');
 assert.deepEqual((await fila()).pasos, ['Reanudar', 'Finalizar', 'Notas']);
 await page.click('.rec[data-ejecucion] .seg-pasos .seg-paso:nth-child(1)');
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 // Las notas se despliegan en la fila; una vacía no se puede guardar.
 await page.click('.rec[data-ejecucion] .rec-titulo');
 await page.waitForSelector('.rec-panel textarea');
 assert.equal(await page.$eval('.seg-escribir .seg-paso', el => el.disabled), true);
 await page.type('.rec-panel textarea', 'Seguimiento verificado en una base de pruebas aislada.');
 await page.click('.seg-escribir .seg-paso');
 await page.waitForFunction(() => document.querySelectorAll('.seg-historial li').length === 4);
 assert((await page.$eval('.seg-historial', el => el.innerText)).includes('Seguimiento verificado'));
 await page.click('.rec[data-ejecucion] .seg-pasos .seg-paso:nth-child(2)');
 await page.waitForSelector('.rec[data-estado="completada"]');
 await page.reload();
 await page.waitForSelector('.rec[data-estado="completada"]');
 assert.deepEqual((await fila()).pasos, ['Reabrir', 'Notas']);
 await page.click('.rec[data-ejecucion] .seg-pasos .seg-paso:nth-child(1)');
 await page.waitForSelector('.rec[data-estado="en_curso"]');
 await page.click('.rec[data-ejecucion] .seg-pasos .seg-paso:nth-child(2)');
 await page.waitForSelector('.rec[data-estado="completada"]');
 if (process.env.XRAY_CAPTURAS) {
  mkdirSync(process.env.XRAY_CAPTURAS, {recursive: true});
  await page.$eval('.sec-acciones', el => el.scrollIntoView());
  await page.screenshot({path: process.env.XRAY_CAPTURAS + '/seguimiento-acciones.png'});
 }
 await page.setViewport({width: 390, height: 844});
 await page.$eval('.sec-acciones', el => el.scrollIntoView());
 assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
 if (process.env.XRAY_CAPTURAS) await page.screenshot({path: process.env.XRAY_CAPTURAS + '/seguimiento-movil.png'});
 await page.goto(base + '?v=empresa&cfo=GROUP_0250&g=GROUP_0250&emp=COMP_0263&sec=acciones');
 await page.waitForSelector('.rec.vacia');
 await page.waitForFunction(() => { const b = document.querySelector('.sec-acciones-cabecera .boton-propuesta'); return b && !b.disabled; });
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
 assert((await page.$eval('.ejecucion',el=>el.textContent)).includes('Bancos'));
 await page.reload();
 await page.waitForSelector('.ejecucion');
 assert((await page.$eval('.ejecucion',el=>el.textContent)).includes('Bancos'));
 assert.deepEqual(errors, []);
 console.log('OK: error sin falsa confirmación, ejecución, seguimiento en la fila sin repetirlo debajo, pausa, reanudación, nota, reapertura, persistencia tras recarga, finalización explícita, historial, ausencia de progreso inventado, móvil y empresa sin palancas.');
} finally { await browser.close(); }
