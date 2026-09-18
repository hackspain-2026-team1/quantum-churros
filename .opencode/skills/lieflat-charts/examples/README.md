# Examples · Finished cases with real data

The galleries in `templates/` are "example sentences" (demo data, multi-card fold-out); this is "finished prose" — take the public data of a real article and walk the whole skill process from judging the data shape to outputting charts. If you are unsure what the deliverable should look like, start here.

> **Vendored subset note:** this copy includes the two example HTML files but not the upstream PNG previews (`docs/assets/`) or the full color/report variants. See the upstream repository for those.

## r04-financial-report.html

This is a financial-scenario example of the R04 "Monthly Ops" template: it keeps the original page grid and four chart slots, and changes the content to a monthly business/financial report, including revenue, gross profit, operating cash flow, gross margin, months of cash runway, daily revenue, collection timing, revenue composition, and business-line gross-profit contribution. The data is fictional demo data, used to show how the same template adapts to a financial / economic report. This file was translated into English from the upstream Chinese demo (`r04-financial-report.zh.html`); currency amounts keep their original values.

Preview image (not vendored): `docs/assets/examples/r04-financial-report.zh.png` in the upstream repo.

## lenny-2026-survey.html

Data source: Lenny's Newsletter, "How tech workers are feeling in 2026" (2026-07-07, annual tech-worker survey). One article → 8 charts, all English, 8 non-repeating templates:

This is an early showcase kept from before the chart-count rule was settled, using 8 charts to cover more templates. When the current skill handles a similar article, it defaults to filtering down to 4–6 charts and splitting into pages when there are more than 6.

| # | Template | Data |
|---|------|------|
| 1 | Type Colonnade (L12) | AI identity 49/27/14/5/3 |
| 2 | Ballot Tally (L15) | The contradiction trio: enjoy work 79 · significant burnout 56 · optimistic 49 |
| 3 | Hundred Faces (semantic units · full-width) | Layoff worry 28/31/21/12/8, mouth curvature = degree of worry |
| 4 | Tick Rows (F5) | The four fears 51/46/41/22 |
| 5 | Hourglass Stream (L13) | Contradiction narrowing 100 → 77 → 51 |
| 6 | Brand Spectrum (L7) | Layered NPS −49/−23/−5 |
| 7 | Radial Convergence (L5) | Industry in one phrase: chaos 30 / fast 17 / bubble 12 / excitement 11 / other 30 |
| 8 | Ballot Rings (dial tick · full-width) | AI productivity 82 → 49 |

This file also demonstrates a few easily forgotten rules:

- **Acknowledge rounding**: AI identity rounds to only 98; the footer says "rounding ate the other two" — do not pad with fake lines.
- **Do not invent data you do not have**: the Brand Spectrum template originally had competitor comparison points; Lenny had no such data, so they were removed.
- **Turn off random leakage for exact shares**: the Radial Convergence template's rnd leakage logic (roughly 8% routed to the wrong hub to create an organic feel) had to be switched off for survey data.
- **No repeated templates within one batch of multiple charts**: 8 charts, 8 templates.
- **cascade vertical category names only suit short labels** — this case once used Dot Cascade for the fear data and was judged "can't read it" twice; switching to horizontal Tick Rows fixed it: keeping labels horizontal is always the safer choice.
- **The reduced-motion fallback must not be missing** (when verifying with headless screenshots you can use `--force-prefers-reduced-motion` to bypass animation timing).
