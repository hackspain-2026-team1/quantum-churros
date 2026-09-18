# Lieflat Charts Report Template Catalog · 12

> The report template decides the whole page's narrative order, page grid, module density, and reading speed; charts inside the page must still follow the data contract of `catalog.md`. The scenarios in the table are recommended uses, not hard restrictions: the same layout can migrate to different content such as finance/economics, research, business, product, and personal records.
> This vendored edition ships the English versions only: `templates/reports/report-NN.en.html` (upstream also publishes `.zh.html` versions).
> The visualization index is at `templates/reports/index.html`; upstream keeps static previews in `docs/assets/reports/` (not vendored).

## Selection order

1. First filter by report type, audience, and reading task; do not filter by "which charts it contains" or the industry words in the template name.
2. Then filter by information density, page-grid width, reading speed, and whether offline operation is needed.
3. Compare at least 3 candidates; when fewer than 3 exist, compare all of them.
4. After locking a report template, keep its whole-page skeleton and do not stitch in blocks from other report templates.

## Template index

| # | Name | Common report types / migratable scenarios | Page grid | Density | Color system | Dependency |
|---|---|---|---:|---|---|---|
| R01 | Survey One-Pager | Research report, research brief, policy / market insight, white-paper opening, external data release | 1080 | 3 charts, medium | Porcelain | Online fonts |
| R02 | Annual Milestones | Annual retrospective, performance / earnings review, investor update, product or project milestones | 980 | 3 charts, medium | Palm | Online fonts |
| R03 | Year in Data | Annual data report, business / financial annual report, personal year log, annual trend poster | 1080 | 4 charts, higher | Wire | Online fonts |
| R04 | Monthly Ops | Monthly report, business data report, earnings, ops / financial retrospective, periodic monitoring | 1080 | 4 charts, higher | Porcelain | Online fonts |
| R05 | Impact Story | Project retrospective, product record, nonprofit / community case, impact narrative, personal growth log | 760 | 2 charts, low | Mono | Online fonts |
| R06 | Eight-Year Product Almanac | Long-cycle almanac, product / company history, multi-year financial or business trend, personal long-term data | 980 | 4 charts, high | Palm | Online fonts |
| R07 | Survey Collage Poster | Research report poster, user / market study, event / trade-show data, social-media material | 980 | 5 charts, very high | Palm | Online fonts |
| R08 | Population One-Pager | Cohort / user persona, policy / nonprofit brief, market segmentation, demographic and socioeconomic data | 880 | 2 charts, low | Wire | Online fonts |
| R09 | Data Story Dashboard | Dashboard, finance / business cockpit, business overview, competitor / market comparison, KPI snapshot | 1080 | 4 charts + KPI, high | Porcelain | Online fonts |
| R10 | Travel Notebook | Travel data log, sports data log, personal annual / life data, lightweight project journal | 980 | 4 charts + table, medium | Palm | Online fonts |
| R11 | Research Brief Card | Research brief, finance / economics bulletin, social-media card, report insert, key-metric snapshot | 600×1000 | 2 charts, fixed size | Mono | Chart.js + ECharts CDN |
| R12 | Weekly Glance | Weekly report, finance / business bulletin, ops monitoring, project progress, sports or travel weekly | 1080 | 4 charts, high | Palm | Chart.js + ECharts CDN |

## Report-type recall

- **Research report / research brief**: R01, R07, R08, R11.
- **Business data report / dashboard**: R04, R09, R12.
- **Earnings / finance-economics report**: R02, R03, R04, R09, R11, R12. A financialized example of R04 is in `examples/reports/r04-financial-report.html`.
- **Product record / project retrospective**: R02, R05, R06, R12.
- **Personal data log**: R03, R05, R06, R10, R12; sports, travel, and annual life data can all use these.
- **External poster / social-media share**: R03, R07, R11.
- **Template selection principle**: choose by content structure, information density, reading speed, and page grid; do not confine a template to a single industry just because its name says "travel", "ops", or "almanac".
- **Must run offline**: prefer R01–R10, and inline or remove online fonts; R11–R12 need their chart dependencies inlined additionally.
- **Fixed social-media format**: R11; when content does not fit, switch templates — do not shrink the font or crop information.

## Template contract

- A report template is a complete page, not a chart gallery. Copy the whole HTML of the corresponding language as the starting point.
- Keep the template's page-grid width, main grid, section order, principal whitespace, color system, and chart-slot relationships.
- You may replace copy, data, sources, legends, and modules that conflict with the real content; you may delete secondary modules that lack evidence.
- When a chart inside the page needs to be replaced, lock the chart type in `catalog.md` and reuse the real implementation of the corresponding gallery, replacing only that chart slot.
- Mixing two report templates is forbidden, and keeping demo data, demo sources, or demo conclusions is forbidden.
