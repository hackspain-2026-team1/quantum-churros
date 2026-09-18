/* ═══════════════════════════════════════════════════════════════
   COLOR PRESETS — the single source of truth for the three built-in color presets
   Mono is the fallback; when data semantics and use case are a clear fit, one of
   these color starting points may be selected automatically. Never mix presets within one deliverable.
   Relation to mono-tokens.js: this file only overrides colors — fonts / radii /
   animation params / card structure always follow mono-tokens.js.
   If any built-in color gallery contains swatches that conflict with this file, this file wins.
   A user-supplied custom palette is only inlined into its matching deliverable, never
   written into this file, and must not borrow swatches from here to fill its gaps.
   Usage: hangs off window.PRESETS; spread one preset into your chart code;
   when distributing open source, inline the chosen preset into the single-file HTML.
   ═══════════════════════════════════════════════════════════════ */
(function (global) {
  'use strict';

  /* ── Two universal ink-boost rules for the color presets ──
     A 0.5px hairline is visible in greyscale but vanishes once it becomes a light color tint.
     Not optional — all three presets must comply. */
  const INK_BOOST = {
    strokeScale: 1.8,        // stroke width ×1.8
    opacityFloor: 0.85,      // opacity floor (dot heat exempt — its ink is already strong enough)
    exempt: ['dot heat'],
  };

  /* ═══════════════════════════════════════════════════════════
     PORCELAIN — single-hue blue ladder
     Color logic: lightness is data; fully inherits Mono's contract, just swapping grey for blue.
     Fits: ordinal data (progress / heatmaps / time series / single metric / rankings).
     Capacity: 4 lightness steps. Beyond 4 categories, switch to the Mono greyscale.
     ═══════════════════════════════════════════════════════════ */
  const PORCELAIN = {
    name: 'porcelain',
    cn: 'celadon blue',
    logic: 'ordinal',        // lightness = value, hue held constant
    BG: '#F7F2EB',
    TXT: '#081F5C',
    MUT: 'rgba(8,31,92,.60)',
    LAB: 'rgba(8,31,92,.72)',
    FAINT: 'rgba(8,31,92,.32)',
    FLOOR: 'rgba(8,31,92,.24)',
    QUIET: 'rgba(8,31,92,.15)',
    TRACK: 'rgba(8,31,92,.12)',
    GRID: 'rgba(8,31,92,.16)',
    DATA: '#334EAC',
    DATA2: '#7096D1',
    HERO: '#081F5C',
    HERODK: '#7096D1',
    FAINTDATA: '#BAD6EB',
    BEAD: '#7096D1',
    HALO: 'rgba(247,242,235,.92)',
    CAT4: ['#081F5C', '#334EAC', '#7096D1', '#BAD6EB'],
    CAT3: ['#334EAC', '#7096D1', '#BAD6EB'],
    HEAT: ['#334EAC', '#7096D1', '#BAD6EB'],
    SER:  ['#334EAC', '#081F5C', '#7096D1', '#BAD6EB', '#D0E3FF', 'rgba(51,78,172,.4)'],
    RAMP: ['#D0E3FF', '#BAD6EB', '#7096D1', '#334EAC', '#081F5C'],
    DRAMP4: ['#D0E3FF', '#BAD6EB', '#7096D1', 'rgba(247,242,235,.26)'],
    RAMPDK: ['rgba(247,242,235,.26)', 'rgba(247,242,235,.42)',
             'rgba(247,242,235,.60)', 'rgba(247,242,235,.84)', '#7096D1'],
    // ── For dark-background big charts (big-circular / big-force / big-threads) ──
    // Deep card bg; the 8-step single-hue ladder runs light→dark, encoding "distance from the core" (light = core)
    DARK: {
      CARDBG: '#081F5C',
      DK8: ['#EDEFF1','#D5DBE2','#BCC7D7','#9EB3CD','#809EC6','#6C93C7','#4D82C6','#3472C2'],
      HL: '#EDEFF1',           // hover highlight
      LABEL: '#9EB3CD', SUB: '#809EC6', SRCROW: '#3E5A8F', RULE: '#1B3159',
      LINK_SAME: '#32517B', LINK_CROSS: '#263E5E',
      LINK_HEAVY: '#3B6091', LINK_FAINT: '#213650',
    },
  };

  /* ═══════════════════════════════════════════════════════════
     PALM — low-saturation green-yellow + amber accent
     Color logic: hue = category (unordered); amber alone carries "this one is the point".
     Fits: a few mutually unordered categories side by side (source / team / product line / region).
     Capacity: 4 categories is clean, 6 is a stretch. Beyond 6, switch to porcelain or Mono.
     Note: amber (160) and olive (167) differ by only 7 in lightness, separated by a
           saturation gap of 56. Their semantics are opposite (amber jumps out, olive
           recedes), so in practice they never read as confused — but never use
           them as two equal categories.
     ═══════════════════════════════════════════════════════════ */
  const PALM = {
    name: 'palm',
    cn: 'palm green',
    logic: 'categorical',    // hue = category
    BG: '#F0EFEB',
    TXT: '#58402E',
    MUT: 'rgba(88,64,46,.60)',
    LAB: 'rgba(88,64,46,.72)',
    FAINT: 'rgba(88,64,46,.32)',
    FLOOR: 'rgba(88,64,46,.24)',
    QUIET: 'rgba(88,64,46,.15)',
    TRACK: 'rgba(88,64,46,.12)',
    GRID: 'rgba(88,64,46,.16)',
    DATA: '#43593B',         // deep green, L 79
    DATA2: '#58402E',        // dark coffee, L 69 (also the text color)
    HERO: '#D4A017',         // amber, L 160, S80 — pops against a field of S20 grey-greens
    HERODK: '#F2D17E',       // dark-card accent: deep green is unreadable on the coffee bg, switched to wheat
    FAINTDATA: '#ACAD79',
    BEAD: '#77835A',
    HALO: 'rgba(240,239,235,.92)',
    CAT4: ['#43593B', '#77835A', '#ACAD79', '#F2D17E'],   // 79/123/167/209
    CAT3: ['#43593B', '#929960', '#F2D17E'],              // 79/144/209
    CAT3L: ['#43593B', '#77835A', '#ACAD79'],
    HEAT: ['#43593B', '#929960', '#F2D17E'],
    SER:  ['#43593B', '#D4A017', '#77835A', '#F2D17E', '#ACAD79', '#58402E'],
    // Ordinal ramp: pure green→yellow in six steps, lightness 79→209, even spacing (22/22/21/23/42)
    RAMP6: ['#43593B', '#5A7049', '#77835A', '#929960', '#ACAD79', '#F2D17E'],
    RAMP: ['#F2D17E', '#ACAD79', '#929960', '#77835A', '#43593B'],
    SEG3: ['#43593B', '#77835A', '#ACAD79'],   // segments: dimensions that already exist inside the chart, like months
    ZONE3: ['#ACAD79', '#929960', '#43593B'],  // zones: darker as it gets closer to the target
    RAMPDK: ['rgba(240,239,235,.26)', 'rgba(240,239,235,.42)',
             'rgba(240,239,235,.60)', 'rgba(240,239,235,.84)', '#F2D17E'],
    DRAMP4: ['#F2D17E', '#ACAD79', 'rgba(240,239,235,.55)', 'rgba(240,239,235,.26)'],
    // ── For dark-background big charts ──
    // Card bg darkened with deep green (dark coffee at L 69 is too bright to hold it down), 8 steps wheat→deep green
    DARK: {
      CARDBG: '#28311F',
      DK8: ['#F0EFE9','#DDDBC9','#C8CAA8','#AFB885','#92A763','#7EA056','#658D49','#4F7D3E'],
      // Hover highlight uses wheat. Exception: big-threads highlights by changing opacity
      // (the line itself stays DK8[0]); that chart does not use HL.
      HL: '#F2D17E',
      LABEL: '#ACAD79', SUB: '#92A763', SRCROW: '#5A6B47', RULE: '#38452C',
      LINK_SAME: '#405333', LINK_CROSS: '#334329',
      LINK_HEAVY: '#4C6340', LINK_FAINT: '#2C3823',
    },
  };

  /* ═══════════════════════════════════════════════════════════
     WIRE — black greyscale + a touch of fluorescent orange
     Color logic: greyscale carries all the data (same as Mono); orange marks a
               single hero element (biggest bar / peak / NET / the "after" of a redesign).
     Fits: almost every situation. Use it when you want Mono's restraint but need one focal point.
     Capacity: 7 greyscale steps, same as Mono. Orange always goes to exactly one element —
           a second orange spot means there is no hero.
     ═══════════════════════════════════════════════════════════ */
  const WIRE = {
    name: 'wire',
    cn: 'editorial red',
    logic: 'mono+accent',    // greyscale = data, orange = the single hero
    BG: '#F0F0EE',
    TXT: '#1F1E1C',
    MUT: 'rgba(31,30,28,.60)',
    LAB: 'rgba(31,30,28,.72)',
    FAINT: 'rgba(31,30,28,.32)',
    FLOOR: 'rgba(31,30,28,.24)',
    QUIET: 'rgba(31,30,28,.15)',
    TRACK: 'rgba(31,30,28,.12)',
    GRID: 'rgba(31,30,28,.16)',
    DATA: '#22211F',
    DATA2: '#8F8E86',
    HERO: '#F5572F',         // fluorescent orange — one element per chart, no more
    HERODK: '#F5572F',
    FAINTDATA: '#C0BFB7',
    BEAD: '#8F8E86',
    HALO: 'rgba(255,255,255,.92)',
    CAT4: ['#F5572F', '#22211F', '#8F8E86', '#C0BFB7'],
    CAT3: ['#F5572F', '#22211F', '#8F8E86'],
    CAT3L: ['#F5572F', '#22211F', '#6E6D66'],
    HEAT: ['#F5572F', '#6E6D66', '#C0BFB7'],
    SER:  ['#22211F', '#8F8E86', '#C0BFB7', 'rgba(34,33,31,.52)', '#DBDAD3', 'rgba(34,33,31,.3)'],
    RAMP: ['#DBDAD3', '#C0BFB7', '#8F8E86', '#22211F', '#F5572F'],
    DRAMP4: ['#F5572F', '#C0BFB7', '#8F8E86', 'rgba(240,240,238,.26)'],
    RAMPDK: ['rgba(240,240,238,.26)', 'rgba(240,240,238,.42)',
             'rgba(240,240,238,.60)', 'rgba(240,240,238,.84)', '#F5572F'],
  };

  /* ── Plain-language mapping: users don't say preset names, they say "bluer" or "warmer" ── */
  const BY_WORDS = {
    'blue': 'porcelain', 'cool': 'porcelain', 'academic': 'porcelain',
    'rational': 'porcelain', 'serious': 'porcelain', 'tech': 'porcelain',
    'green': 'palm', 'warm': 'palm', 'natural': 'palm', 'gentle': 'palm',
    'vintage': 'palm', 'handmade': 'palm', 'morandi': 'palm',
    'black and white': 'wire', 'restrained': 'wire', 'magazine': 'wire', 'editorial': 'wire',
    'minimal': 'wire', 'no color but one highlight': 'wire',
  };

  global.PRESETS = { PORCELAIN, PALM, WIRE, INK_BOOST, BY_WORDS,
    list: ['porcelain', 'palm', 'wire'],
    get: n => ({ porcelain: PORCELAIN, palm: PALM, wire: WIRE })[String(n).toLowerCase()] || null };
})(typeof window !== 'undefined' ? window : globalThis);
