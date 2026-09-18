/* ═══════════════════════════════════════════════════════════════
   MONO TOKENS — the single source of truth for the style
   All mono charts (Chart.js / ECharts / hand-written SVG) share this one file.
   If colors, fonts, or animation params in any file conflict with this file, this file wins.
   Usage: <script src="mono-tokens.js"></script> — everything hangs off window.MONO;
   or inline this file's contents into a single-file HTML (recommended for open-source distribution).
   ═══════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  /* ── 1 · Palette ───────────────────────────────────────────
     Paper-grey ground + charcoal ink. No color. Lightness is data: most important = darkest. */
  const INK   = '#1C1C1A';   // ink: primary data, titles, emphasis
  const PAPER = '#F0EFEB';   // paper: page background = light-card background (no card borders; whitespace separates cards)
  const MUTED = '#8F8E88';   // secondary text, subtitles
  const FAINT = '#C6C5BF';   // source lines, auxiliary ticks
  const GRID  = '#DEDDD6';   // grid lines, hairlines

  // 7-step grey ladder: with multiple series, assign dark→light by importance
  const L   = ['#1C1C1A', '#4A4944', '#6A6963', '#8F8E88', '#B0AFA9', '#C6C5BF', '#D8D7D1'];
  // 5-step compact version (waffle and other few-series cases)
  const LAD = ['#1C1C1A', '#4A4944', '#8F8E88', '#B0AFA9', '#D8D7D1'];

  // Dedicated to dark cards: bg #1C1C1A, with "ink" inverted to paper on top
  const DARK = {
    bg: '#1C1C1A',
    ink: '#F0EFEB',          // primary data color on dark cards
    muted: '#8F8E88',
    faint: '#55554F',        // dark-card source line
    grid: '#2E2D29',         // dark-card grid / hairlines
    gridSoft: '#2A2925',
    ladder: ['#F0EFEB', '#DCDAD2', '#C9C7BD', '#B3B0A4', '#8F8E88', '#6A6963', '#4A4944'],
  };

  /* ── 2 · Fonts ───────────────────────────────────────────── */
  const FONT = {
    family: 'Inter',
    // Google Fonts link line (goes in <head>):
    link: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap',
    title:    { size: 16.5, weight: 700, spacing: '-.02em' },  // in-card h2
    titleBig: { size: 19,   weight: 700, spacing: '-.02em' },  // standalone big-chart h2
    sub:      { size: 11.5, weight: 400 },                     // subtitle (legend notes go here)
    src:      { size: 9.5,  weight: 500, spacing: '.08em' },   // source line, all caps
    value:    { weight: 800 },                                 // in-chart values always weight 800
    axis:     { size: 9.5,  weight: 600 },                     // axis labels
    // Minimum SVG font sizes: 6.5px in half-width cards, 5.5px in full-width / big charts; below the floor, move the label into a hover.
    minHalf: 6.5, minWide: 5.5,
  };

  /* ── 3 · Shape ───────────────────────────────────────────── */
  const SHAPE = {
    cardRadius: 24,          // card corner radius
    cardPad: '28px 28px 20px',
    barRadius: 99,           // pill-rounded bar ends (vertical bars round the top end only, horizontal bars the outer end only)
    tooltipRadius: 12,
  };

  /* ── 4 · Motion character ─────────────────────────────────
     Fast in, fast stop; quarticOut / cubicOut, no bounce (elasticOut reserved for wave entrances). */
  const MOTION = {
    enter: 900,              // standard entrance, ms
    enterSlow: 1200,         // large elements / network diagrams
    easing: 'quarticOut',
    staggerDot: 12,          // per-dot stagger delay, ms (8–15 range)
    staggerBar: 100,         // per-bar stagger delay, ms (80–130 range)
    // CSS animation classes (for hand-written SVG): pop = scale-in entrance / fade = fade-in / draw = line-draw
    css: `
  .pop{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.2,.7,.3,1.3) both}
  @keyframes pop{from{transform:scale(0)}to{transform:none}}
  .fade{animation:fade .9s ease both}
  @keyframes fade{from{opacity:0}}
  .draw{stroke-dasharray:1;stroke-dashoffset:1;animation:draw 1s cubic-bezier(.4,0,.2,1) both}
  @keyframes draw{to{stroke-dashoffset:0}}
  @media (prefers-reduced-motion:reduce){
    .pop,.fade{animation:none}
    .draw{animation:none;stroke-dasharray:none;stroke-dashoffset:0}
  }`,
  };

  /* ── 5 · Tooltip ──────────────────────────────────────────
     Light cards: ink background with paper text; dark cards the reverse. ECharts spreads these two objects directly. */
  const tipLight = { backgroundColor: INK, borderWidth: 0, padding: [10, 14],
    textStyle: { color: PAPER, fontFamily: 'Inter', fontSize: 12 } };
  const tipDark  = { backgroundColor: PAPER, borderWidth: 0, padding: [10, 14],
    textStyle: { color: INK, fontFamily: 'Inter', fontSize: 12 } };

  /* ── 6 · Deterministic pseudo-random ──────────────────────
     Always use this for demo data, never Math.random() — a refresh must look the same,
     or screenshots / screen recordings / regression comparisons all break. */
  const rnd = (i, k) => Math.abs(((i * 73856093) ^ (k * 19349663)) % 1000) / 1000;

  /* ── 7 · Geometry ────────────────────────────────────────── */
  const D2R = Math.PI / 180;
  const pol = (cx, cy, r, deg) => [cx + r * Math.cos(deg * D2R), cy + r * Math.sin(deg * D2R)];
  // Annular sector path (apply cornerRadius at the call site with an ECharts sector or a manual chamfer)
  const sect = (cx, cy, r0, r1, a0, a1) => {
    const big = a1 - a0 > 180 ? 1 : 0;
    const [xa, ya] = pol(cx, cy, r1, a0), [xb, yb] = pol(cx, cy, r1, a1);
    const [xc, yc] = pol(cx, cy, r0, a1), [xd, yd] = pol(cx, cy, r0, a0);
    return `M${xa} ${ya} A${r1} ${r1} 0 ${big} 1 ${xb} ${yb} L${xc} ${yc} A${r0} ${r0} 0 ${big} 0 ${xd} ${yd} Z`;
  };
  // Hand-drawn-looking circle (for editorial-style bubbles): circumference layered with two slow waves + noise; the seed sets the shape
  const blob = (x, y, r, seed) => {
    const n = Math.max(14, Math.round(r * 1.6)), pts = [];
    for (let t = 0; t < n; t++) {
      const a = t / n * Math.PI * 2;
      const w = 1 + .055 * Math.sin(a * 2 + seed * 7) + .04 * Math.sin(a * 3 + seed * 13)
              + (rnd(seed + t, 3) - .5) * .03;
      pts.push([x + Math.cos(a) * r * w, y + Math.sin(a) * r * w]);
    }
    let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
    for (let t = 0; t < n; t++) {
      const p = pts[t], q = pts[(t + 1) % n];
      d += ` Q${p[0].toFixed(1)} ${p[1].toFixed(1)} ${((p[0]+q[0])/2).toFixed(1)} ${((p[1]+q[1])/2).toFixed(1)}`;
    }
    return d + ' Z';
  };

  /* ── 8 · SVG helpers ─────────────────────────────────────── */
  const NS = 'http://www.w3.org/2000/svg';
  const el  = (p, t, a) => { const n = document.createElementNS(NS, t);
    for (const k in a) n.setAttribute(k, a[k]); p.appendChild(n); return n; };
  const txt = (p, a, s) => { const n = el(p, 'text', a); n.textContent = s; return n; };
  const tip = (n, s) => { const t = document.createElementNS(NS, 'title');
    t.textContent = s; n.appendChild(t); };

  /* ── 9 · Unified reveal: plays once scrolled into view, click to replay ──
     Registers timers (keep) and clears them before each replay to prevent animation stacking. */
  const timers = {};
  const keep = (id, t) => { (timers[id] = timers[id] || []).push(t); };
  const obsReveal = (id, fn) => {
    const n = document.getElementById(id);
    const go = () => {
      (timers[id] || []).forEach(clearInterval); timers[id] = [];
      if (n.tagName === 'svg' || n.tagName === 'SVG') n.innerHTML = '';
      fn(n);
    };
    const io = new IntersectionObserver(es => {
      if (es[0].isIntersecting) { go(); io.disconnect(); }
    }, { threshold: .3 });
    io.observe(n);
    n.style.cursor = 'pointer';
    n.addEventListener('click', go);
  };
  // ECharts version of reveal
  const eReveal = (id, opt) => obsReveal(id, elDom => {
    const g = echarts.getInstanceByDom(elDom) || echarts.init(elDom);
    g.clear(); g.setOption(opt);
  });

  /* ── 10 · Card skeleton (copy this structure for every new chart) ──
     <div class="card [dark] [wide]">
       <h2>Conclusion-style title</h2>
       <div class="sub">Subtitle · legend notes · time range</div>
       <div class="ch" id="xx"></div>  or  <svg id="xx" viewBox="0 0 400 320">
       <div class="src">Chart type · series names · data source (all caps)</div>
     </div>                                                        */
  const CARD_CSS = `
  :root{--bg:${PAPER};--dark:${DARK.bg};--ink:${INK};--muted:${MUTED};--faint:${FAINT};--grid:${GRID}}
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:var(--bg);font-family:'Inter',sans-serif;color:var(--ink);padding:40px;-webkit-font-smoothing:antialiased}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px;max-width:1400px;margin:0 auto}
  .card{background:var(--bg);border-radius:${SHAPE.cardRadius}px;padding:${SHAPE.cardPad}}
  .card.dark{background:var(--dark);color:${PAPER}}
  .card.dark .sub{color:${MUTED}}
  .card.dark .src{color:${DARK.faint}}
  .card.wide{grid-column:1/-1}
  h2{font-weight:${FONT.title.weight};font-size:${FONT.title.size}px;letter-spacing:${FONT.title.spacing};margin-bottom:3px}
  .sub{font-size:${FONT.sub.size}px;color:var(--muted);margin-bottom:14px}
  .src{font-size:${FONT.src.size}px;color:var(--faint);margin-top:10px;letter-spacing:${FONT.src.spacing};font-weight:${FONT.src.weight}}
  .ch{height:320px}
  svg text{font-family:'Inter',sans-serif}` + MOTION.css;

  global.MONO = { INK, PAPER, MUTED, FAINT, GRID, L, LAD, DARK,
    FONT, SHAPE, MOTION, tipLight, tipDark,
    rnd, pol, sect, blob, el, txt, tip, obsReveal, eReveal, keep, CARD_CSS };
})(typeof window !== 'undefined' ? window : globalThis);
