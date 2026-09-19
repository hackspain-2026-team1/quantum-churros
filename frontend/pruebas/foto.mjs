// Captura de una página suelta (diseño de piezas): bun pruebas/foto.mjs <html|url> <png> [ancho] [alto]
import puppeteer from 'puppeteer-core';
const [, , dir, png, w = '1400', h = '900'] = process.argv;
const b = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const p = await b.newPage();
await p.setViewport({ width: +w, height: +h, deviceScaleFactor: 2 });
await p.goto(dir.startsWith('http') ? dir : `file://${dir}`);
await new Promise((r) => setTimeout(r, Number(process.env.ESPERA ?? 400)));
// PULSA='selector' pulsa un elemento antes de la captura (p. ej. un escenario).
if (process.env.PULSA) { await p.click(process.env.PULSA); await new Promise((r) => setTimeout(r, 900)); }
await p.screenshot({ path: png });
await b.close();
