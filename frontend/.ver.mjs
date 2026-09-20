import puppeteer from 'puppeteer-core';
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const p = await b.newPage(); await p.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
p.on('pageerror', (e) => console.log('ERR', e.message.slice(0, 120)));
await p.goto('http://127.0.0.1:5474/?captura', { waitUntil: 'networkidle0' });
await esperar(3000);
console.log(await p.evaluate(() => {
  const c = document.querySelector('.mon-rosa'), r = document.querySelector('.entrada-rosa'), cab = document.querySelector('.mon-cabeza');
  const caja = (e) => e ? [Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)] : null;
  return { cabeza: caja(cab), marco: caja(c), rosa: caja(r), titulo: document.querySelector('.mon-titulo')?.getBoundingClientRect().top };
}));
await p.screenshot({ path: '/tmp/rosa-despues.png', clip: { x: 0, y: 0, width: 1440, height: 620 }, captureBeyondViewport: false });
await b.close();
