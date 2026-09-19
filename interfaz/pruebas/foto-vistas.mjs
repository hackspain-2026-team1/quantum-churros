// Captura la sección «La cartera» del monitor en cada forma y modo: bun pruebas/foto-vistas.mjs <carpeta> [params extra]
import puppeteer from 'puppeteer-core';
const [, , dir, extra = ''] = process.argv;
const b = await puppeteer.launch({ executablePath: process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true });
const p = await b.newPage();
await p.setViewport({ width: Number(process.env.ANCHO ?? 1440), height: 3000, deviceScaleFactor: 1 });
for (const forma of ['ranking', 'bandas', 'plano', 'tapiz', 'flujo', 'avisos', 'horizonte']) for (const modo of (process.env.MODOS ?? 'arena,tabla').split(',')) {
	await p.goto(`http://127.0.0.1:5317/?captura&mf=${forma}&mm=${modo}${extra}`);
	await p.waitForSelector('.mon-vista .mon-frase', { timeout: 30000 });
	await new Promise((r) => setTimeout(r, 1800));
	const el = await p.$('.mon-vista');
	await el.screenshot({ path: `${dir}/${forma}-${modo}.png` });
}
await b.close();
