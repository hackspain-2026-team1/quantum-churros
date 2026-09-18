# Upstream provenance

This skill is a vendored, fully English-translated subset of an upstream project.

- **Source:** https://github.com/larashero3-dotcom/lieflat-charts
- **Commit:** `eace082a317b696c5570c25826a53a7fa113e984`
- **Mirror:** https://github.com/Rubenpombo/lieflat-charts (fork used to track upstream)
- **License:** PolyForm Noncommercial License 1.0.0 (see [`LICENSE`](LICENSE)). Chart.js, Apache ECharts, and the Inter typeface keep their own licenses (see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)). Use in this competition is noncommercial.

## Changes from upstream

- `SKILL.md`, `catalog.md`, `report-catalog.md`, `examples/README.md`, and `THIRD_PARTY_NOTICES.md` translated to English.
- All remaining Chinese in vendored files translated to English: page titles, intro text, card badges, and HTML/JS comments in the galleries and report templates; comments in `mono-tokens.js` and `color-presets.js`.
- `color-presets.js` lookup vocabulary anglicized: the `BY_WORDS` trigger-word keys and preset display names are now English ("blue", "warm", "black and white", …). Key names are unchanged.
- `templates/reports/index.html` adapted for this edition: English text, English-version links only, typographic placeholder tiles instead of the upstream thumbnails.
- The in-card `<h2>` titles and the `// ════ … ════` render-code separators in the galleries were already English upstream and are kept byte-identical so `catalog.md` lookups work end-to-end.
- The attribution request from the upstream signature notice is preserved in `SKILL.md`.
- One upstream example was translated in full: `examples/reports/r04-financial-report.html` (from `r04-financial-report.zh.html`; data values unchanged).

## Vendored

- Engine: `mono-tokens.js`, `color-presets.js`.
- Chart reference implementations: `templates/basics-gallery.html`, `templates/lupi-gallery.html`, `templates/glance-gallery.html`, `templates/maps-gallery.html`, `templates/big-*.html`.
- Report skeletons: all 12 English templates `templates/reports/report-01..12.en.html` plus the adapted `templates/reports/index.html`.
- Examples: `examples/lenny-2026-survey.html`, `examples/reports/r04-financial-report.html`.

## Not vendored

- `templates/color/` reskin samples (15 files) — recolor from `color-presets.js` instead; the galleries remain the structural source of truth.
- Chinese report templates (`templates/reports/report-NN.zh.html`).
- `docs/` (README hero images, gallery GIFs, report PNG previews — ~19 MB).
- `scripts/validate.mjs` / `scripts/smoke-new-charts.mjs` — upstream validators that assume the full repo tree (zh templates, docs assets, agents).
- `agents/openai.yaml` — moxt-platform agent config, not used by this skill.
- `README.md` / `README.en.md` — upstream marketing pages.
