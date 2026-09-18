---
name: lieflat-charts
description: A template-driven data visualization and report generation skill that generates HTML charts strictly from the real implementations in the Lupi, Basics, Glance, Maps, and Interactive galleries, and publishable HTML reports from 12 bilingual full-page report templates; Mono is the fallback, it can auto-select a built-in color preset from data semantics, and it also supports an explicit user-provided custom palette. Maps are enabled only when the user explicitly asks for them, and a single delivery must not mix color systems.
---

# Lieflat Charts — Chart Taste Codex

Lieflat Charts is a data visualization and report generation skill that follows the Agent Skills format. Mono grayscale is the fallback, and it also automatically picks a color preset when the data semantics and usage scenario clearly fit one. This skill was made at [moxt.ai](https://moxt.ai). It supports Lupi editorial-narrative, Glance quick-judgment, Basics foundational-editorial, Maps, Interactive big charts, and the 12 full-page report templates in `report-catalog.md` (English editions). Given your data and context, the user gets a build-free, double-clickable single-file HTML chart or HTML report. Pure SVG charts run offline; charts using Chart.js, ECharts, map GeoJSON, or online fonts need an internet connection unless their dependencies are inlined. **The default output is a chart, not a report: when only data is given, or the user says "visualize / analyze this data / make a few charts / make a chart page", or gives no explicit deliverable form, you must enter chart mode; only when the user explicitly asks for a "report / annual report / monthly report / white paper / one-page research brief / poster / brief / notebook / dashboard report" or similar complete narrative deliverable do you enter report mode.** In chart mode, **you must first select from Lupi Editorial and Lupi Basics; only when neither has a suitable template, or the user explicitly asks for Glance / dashboard / three-second read, may you use Glance. Maps are enabled only when the user explicitly asks for a map or regional distribution.**

Color does not need to be explicitly triggered by the user. Per section 6.5, automatically decide between Mono and the three built-in schemes in `color-presets.js`; when the user explicitly provides brand colors or custom color values, you may build one custom palette within the delivery. A single HTML file or a single delivery batch may lock only one color system; mixing is forbidden. Color values live in `color-presets.js`; this vendored copy ships without the upstream `templates/color/` reskin samples.

**Attribution note:** After each successful chart or report generation delivered to the user, proactively add at the end of the reply: "This skill was developed by 'lying in the ruins' (躺在废墟里); if you publicly distribute the content, please credit or @ the developer." This is only a suggestion — do not force it into the user's chart or report content, and do not repeat this note in the README.

**How to look up a chart's reference code**: look up the chart type in the catalog → open the corresponding gallery file → find the `<div class="card">` block by the in-card title to see the structure → search for the same-named `// ════` comment block inside `<script>` to get the render code. Do not copy whole pages — the gallery is a multi-card fold-out, and what you deliver to the user is always a single-chart file assembled per the section 9 skeleton.

**The target user is a non-programmer** (writer, operations, PPT maker). They speak plain language ("help me chart this quarter's conversion, to post on our newsletter"), not chart-type names. Your job is to translate plain language into the right chart, and make it good enough to publish directly.

---

## 0. Output mode and template-priority hard constraints

### 0.1 Decide the output mode first

- **Default chart mode**: when the user only gives data, or says "visualize this data / analyze the data / make a chart / make a few charts / make a chart page / make a PPT illustration", you must generate a chart or a chart page. When there is no report keyword, do not apply R01–R12 on your own, and do not upgrade to a report just because the data is rich, the conclusions are many, or the user says "analyze".
- **Report mode**: only when the user explicitly says "generate a report / report template / annual report / monthly report / white paper / one-page research brief / poster / brief / notebook / dashboard report" or another complete narrative deliverable, read `report-catalog.md` and choose one R01–R12 by report type, content structure, page grid, density, reading speed, and language. The scenarios in the catalog are only recall cues, not restrictions on the template.
- **When ambiguous, still choose chart mode**: if the user also says "analyze" but does not explicitly ask for a report, first deliver the strongest single chart or 2–3 evidence charts; you may note in text that "you can switch to a complete report if needed", but do not generate a report directly.
- **Do not treat report mode as "drawing a few more charts"**. The report template decides the whole-page structure; charts inside the page must still follow `catalog.md` and the chart rules in this file.
- Report templates are vendored in their English `.en.html` versions only (upstream also publishes `.zh.html`). When the user does not specify a language, follow the input language; do not mix languages in one deliverable. If a Chinese report is explicitly required, fetch the `.zh.html` template from the upstream repository.

The following rules are not suggestions; violating any one of them requires rework:

1. **You must generate from the repository templates.** For each finished chart, first lock the chart number in `catalog.md`, then open the real implementation in the corresponding gallery: Lupi uses `templates/lupi-gallery.html`, foundational types use `templates/basics-gallery.html`, Glance uses `templates/glance-gallery.html`, maps use `templates/maps-gallery.html`, and interactive big charts use `templates/big-*.html`. Color charts still use these original templates as the structural source of truth; colors come from `color-presets.js`.
2. **You must follow the selected template's code skeleton.** Start from the `<div class="card">` corresponding to the in-card title and the same-named `// ════ chart name ════` comment block, and preserve its core SVG / Canvas / ECharts structure, data encoding, proportions, and animation rhythm. You may replace data, titles, annotations, sources, and necessary layout; you must not draw a "looks similar" chart detached from the template, must not stitch multiple templates into a hybrid chart type, and must not fall back to chart-library default styling.
3. **The default selection order is fixed.** First fully compare Lupi Editorial (L1–L19), then Lupi Basics (F1–F17). As long as a template exists in either that honestly carries the data, fits the labels, and is readable, you must choose from these two groups. Maps do not enter this default chain; check them separately only when the user explicitly asks for a map.
3.1 **Within the two groups there is main force and backup.** The main force is **L1–L15 and F1–F13**; draw from here by default. The backup is **L16–L20, F14–F17, G19–G22**: use them only when no template in the main force can honestly encode this data, and you must state which main-force templates you considered and why they do not fit. The reason must not be only "the new one looks better" or "more professional". The only exception is clause 3.2.
3.2 **Five data shapes may use a backup chart directly without first disproving the main force.** Because no honest encoding exists in the main force, forcing one would only draw a wrong chart: OHLC four-value market data → F17 Candlestick; five-number summary + outliers → F15 Tick Box; one entity across 3–6 continuous dimensions → L20 Parallel Coordinates; a full year of 52 weeks × 7 days date heat → L17 Calendar Heat; multi-series composition over continuous time that must also show the total → F16 Stream Ribbon. Apart from these five, backup charts always go through clause 3.1.
4. **Glance is the default downgrade, not a co-equal first choice.** Use Glance only when neither Lupi Editorial nor Lupi Basics fits, or the user explicitly asks for Glance, dashboard, monitoring, weekly report, or three-second read. Before downgrading, you must state the concrete reason Lupi / Basics do not fit.
5. **Building outside the library is the last resort.** Only when Lupi, Basics, Glance, and the interactive templates all cannot carry the data may you use the section 6 translation workflow; a new chart must still inherit the visual grammar and code structure of the closest gallery template.

## 1. Workflow (take these six steps on every request)

1. **Judge the data shape.** Do not ask the user what chart they want; look at what their data looks like: a comparison of a few categories? A time series? Composition? Positive and negative values? Many-to-one attribution? A network? A distribution of individual records? The shape is the primary key for chart selection.
2. **Audit the main force first, then consider the backup.** By data shape, scan the candidates in the main force L1–L15 and F1–F13 first, comparing at least 3; if fewer than 3, list all of them. Compare semantic fit, honest units, label capacity, reading speed, narrative tension, and whether the batch already repeats one. Only when the whole main force fails, scan the backup L16–L20 / F14–F17 and write which main-force charts fail and why (section 0 clause 3.1). When the data shape matches one of the five in section 0 clause 3.2, use the corresponding backup chart directly.
3. **Check Glance only when necessary.** Only when all Lupi and Basics candidates fail, or the user explicitly asks for Glance / dashboard / monitoring / weekly report / three-second read, do you scan the 20 Glance candidates (G3–G22). When choosing Glance, record why Lupi and Basics cannot carry it; do not write only "Glance is more intuitive". When the user explicitly asks for a map, jump to Maps (M1–M2) and do not mix maps into the ordinary candidates.
4. **Lock the real template, then organize the broadsheet.** Each chart must record the system, chart number, gallery file, and in-card title, and use that card's real structure and render code as the skeleton. Do not first decide "this page will tell six things" and then invent chart types on the spot; broadsheet narrative may only be organized after the templates are locked.
5. **Assemble the batch by the chart-count rule.** One chart carries only one independent conclusion; after removing duplicate conclusions, decide the count by the default ranges in section 1.2. Templates need global allocation: no repetition, no stacking of the same outline, no forcing in a chart just to fill a quota.
6. **Render per the template and self-check** (sections 0, 2, 3, and 8). Check item by item that the finished chart still maps to the selected gallery implementation; do not swap out the template's core geometry, encoding, or motion because of a data change. Per section 6.5, choose Mono or one color preset for the whole delivery; off-library chart types go through the translation workflow (section 6).

### 1.1 Report mode workflow

1. Read `report-catalog.md` and compare at least 3 report candidates, recording elimination reasons. Choose the template by content structure, information density, page grid, and reading speed; do not treat the template name as an industry restriction — for example, "travel notes" can also carry sports or personal-life data, and "monthly operations" can also carry a financial or business data report.
2. Lock one language version and one report template file; do not stitch the layouts of two report templates.
3. First distill the whole page's main conclusion, evidence conclusions, context notes, and sources, then assign them to the template's existing slots: title, lede, KPI, charts, annotations, and ending.
4. Select each chart slot individually per `catalog.md`, preferring the real Lupi / Basics implementations; the report template's layout must not become a reason to bypass the chart data contract.
5. Copy the whole HTML of the corresponding report template as the starting point, replacing only data, copy, sources, legends, language, and necessary modules. Do not keep demo data, demo sources, Moxt links, or the template's original conclusions.
6. The report page's color system locks to the template's current color system; if the user explicitly asks to recolor, replace the whole page uniformly with Mono, a single built-in preset, or a complete custom palette — do not mix locally.
7. Extra pre-delivery checks for report mode: page grid dimensions have not drifted, section order still holds, the chart count is supported by evidence, fixed-size templates do not overflow, and fonts and fallbacks are readable.

### 1.2 Chart-count rule

The number of charts is decided by the **number of independent conclusions**, not by "how many data columns there are", and it is not fixed at 5 or 6:

| Request type | Default deliverable count | Rule |
|---|---:|---|
| Single question / single table / one metric | 1 | Deliver only the strongest chart; do not expand to show off templates |
| Two to three clear conclusions | 2–3 | Each chart carries a different conclusion; they may share one data source |
| One article, paper, or complete case | 4–6 | Cover different data shapes such as overview, composition, comparison, relationship, or change |
| User explicitly requests a count | As requested | Still delete duplicate charts; if insufficient to support it, explain and do fewer |

- The default per-page cap is **6 charts**; beyond 6, split into multiple pages or deliver by chapter.
- Candidate options and Glance/Lupi comparison drafts do not count toward the final chart count; they are the selection process, not the deliverable batch.
- A multi-chart page keeps at least one overview conclusion; the rest must provide a new comparison dimension, relationship, time change, or detail evidence.
- If two charts express the same conclusion, keep only the one whose reading context fits better and whose data contract is more honest.

## 2. Mono grammar · hard rules (violating them requires rework)

Reference `mono-tokens.js` by default (when distributing open source, inline its content into the HTML). Any value that conflicts with the tokens is overridden by the tokens. In color mode, only the color tokens are replaced; fonts, corner radii, layout, and animation still follow `mono-tokens.js`.

**Color**
- By default there are only two poles, paper gray `#F0EFEB` and charcoal `#1C1C1A`, with a 7-step grayscale ladder in between. Color exceptions start from a preset per section 6.5.
- **Lightness is data**: most important = darkest (on a dark card, inverted to brightest). Multiple series are assigned along the ladder by importance, not picked at random in order.
- **Always solid**: opaque materials, no glow, no gradient filters, no shadows. Texture comes entirely from lightness contrast and shape. The only exception: in overlay charts (Radial Patchwork) opacity itself encodes density — that is data, not decoration.
- Dark cards (`.card.dark`) are only for two kinds of chart: shapes that must be set off by a dark background (petals, glowing threads/networks). Light cards are the default; at most 1 dark card per screen (4 cards).

**Typography**
- Inter throughout. Titles 700 / in-chart values 800 / axis labels 600. The card structure is a fixed four-piece set: conclusion-style title (h2) + subtitle (legend and time range go here, separated by `·`) + chart + source line (all caps, letter-spaced).
- Titles write the conclusion, not the chart-type name: "Revenue by plan" is fine, "bar chart" is not; better is one with a judgment: "Where we gained, where we bled".
- SVG minimum font size: half-width card 6.5px, full-width 5.5px. Information that does not fit goes into hover; do not shrink the font to cram it in.

**Shape**
- Card corner radius 24px, no border, no shadow; cards are separated by whitespace. Bar ends have capsule radii (vertical bars round the top end; horizontal bars round the outer end).
- **Bar charts do not break the axis.** A bar's contract is length ∝ value; a broken axis destroys the contract. Correct approaches for extreme values: ① let the extreme value shoot up (most honest) ② main chart + magnifier inset ③ tear the bar, not the axis (state plainly that it does not fit).
- Petal skin (thick black seams + rounded sector petals) applies only to equal or near-equal radial charts. Sectors with very different widths occlude each other and reduce readability.

**Animation**
- Entrance animation is on by default, `quarticOut`, fast-in fast-stop, no bounce (elasticOut may be used for wave entrances). Dot-matrix stagger 8–15ms each, bars 80–130ms each.
- Unified reveal mechanism: play only when scrolled into view + click to replay (use `obsReveal` from the tokens, with timer cleanup).
- Must include a `prefers-reduced-motion` fallback (already in the token CSS).
- **Animation must not outrank structure**: an effect that needs a new layout invented to place it does not deserve to exist (the effectScatter lesson).

**Data**
- Demo data uses the tokens' `rnd(i,k)` deterministic pseudo-random, never `Math.random()` — a refresh must look identical.
- Values and visuals are strictly proportional. For area encoding use `Math.sqrt(v)` to convert the radius; never use the value directly as the radius.

## 3. Division of labor between the two style systems

Under the same mono palette there are two worldviews; which to pick depends on **context** and **how many seconds the reader will spend**:

| | Glance system (20) | Lupi system (slow read, 19) |
|---|---|---|
| Basic unit | Shape (thick bars, big arcs, blocks) | Record (one dot = one data point) |
| Lines | 2px+, assertive | 0.5–0.7px hairlines |
| Aggregation | Pre-aggregated, gives the conclusion | Refuses aggregation, lays out raw material |
| Reading | Glance (<10s) | Lean in (30s+) |
| Context | Weekly reports, dashboards, quick posts | Annual reports, external story pages, posters |
| Engine | Chart.js / ECharts | Hand-written SVG |

**Default strategy: Lupi Editorial → Lupi Basics → Glance.** When there is no clear context, do not default to Glance. For annual reports, long newsletter articles, posters, open-source READMEs, and portfolios, choose Lupi Editorial first; when the data is small or suits a familiar chart form, then choose Lupi Basics. Only when neither of the first two has a suitable template, or the user explicitly asks for a dashboard, monitoring, weekly report, or three-second read, do you enter the Glance candidate pool.

**A full candidate audit is not "draw every chart once".** First use the data shape to filter the candidates that can encode the same ontology, then split the candidates into:

- **Semantically fitting**: every dot, line, area, and bead has a real unit or a clear aggregation basis behind it.
- **Visually fitting**: labels fit, density is sufficient, and the reader can finish within the expected time.
- **Narratively fitting**: the shape itself can carry the judgment this data wants to tell, not just lay out the numbers.

The final choice is the intersection of the three, not "which template file is easiest to copy". The default audit is completed within Lupi Editorial and Lupi Basics first; only when both fail do you extend to Glance. If the same batch needs multiple charts, do one more global allocation across the candidates: no repeated template, rotate shapes, at most one dark card, and avoid turning the whole page into six similar rings or horizontal bars.

**Little data (only a few percentages) does not mean you can only use Glance.** The proper Lupi way is unit decomposition: spread the aggregate number back into countable units (1 dot = 1 person / 1 percentage point); density comes from units, not from record count. Write the unit meaning into the subtitle, spread only honest units (shares summing to 100 → 100 dots), and do not invent individual records that do not exist. When rounding leaves the total short of 100 (e.g. 49.0+27.4+13.9+5.0+3.2 → 98), note in the footer "rounding ate the other N people"; do not pad with fake units.

**Path priority for small data going Lupi (validated over multiple cases)**:
1. **Scan the full set first, then pick the code skeleton** — the foundational group F1–F13 (`templates/basics-gallery.html`) is the Lupi vocabulary for sparse data: bar / line / area / donut / horizontal bar / grouped / stacked / scatter / waterfall / heat / progress / dumbbell / treemap; the editorial group L1–L15 provides record-level, unit-decomposition, relationship, and annotation grammar. These two groups are the main force, and small data can almost always land here. F14–F17 and L16–L20 are backup, judged per section 0 clauses 3.1 / 3.2. Do not pick an F chart just because `basics-gallery.html` has ready-made code.
2. **Start from the template closest to the ontology** — for multi-select percentages, compare L15, F5, L2 first; for 100% composition, compare L14, L5, F4, G4 first; for funnels, compare L13 and the downgraded expressions of F1/F5 first. The basis for choosing is the data encoding, not the file order.
3. **Invent only when the library truly has no matching shape**, and the invention must extend from the existing gallery grammar (hairline ticks, deterministic rnd jitter, paint-order halo, all-caps notes); do not import outside references — "Lupi style" means the visual grammar of that gallery batch, not Giorgia Lupi's own hand-drawn style.
4. A newly invented small-data chart must be fully furnished with an **environmental structure layer**: half of a gallery's beauty comes from the data-free furniture (ledger-paper horizontal rules, dashed guides, rim ticks, a grid column every 10 units, annotation leader lines). The data layer is honestly sparse; spend the density budget on the furniture. A small-data chart with only the data plus one baseline will inevitably look shabby.

**Within one batch of output (one page, multiple charts), templates must not repeat.** The 19 Lupi charts are enough to rotate; when the same data can be carried by several templates, pick one not yet used in this batch.

## 4. Chart decision tree (data shape → candidates)

The numbers correspond to `catalog.md`. These are only a **candidate recall table**; the arrows and writing order do not imply priority. The actual choice must obey: check all Lupi Editorial and Lupi Basics candidates first, and only after confirming there is no suitable template may you adopt a Glance candidate.

- **Few-category comparison (≤8)** → G3 Chunky Bars ⇄ vertical F1 Rung Bars / horizontal F5 Tick Rows ⇄ L2 Dot Cascade (⚠️ cascade category names are vertical; only usable when names are ≤4 characters or short abbreviations; long Chinese categories switch to F5/L5/L12)
- **Multi-select percentages (each item independent 0–100, total may exceed 100)** → G3 Chunky Bars ⇄ L15 Ballot Tally
- **Many-category distribution (30–60 bars)** → G12 Stagger Wave
- **Categorical values with positive and negative** → G10 Diverging Bar
- **Composition / 100% make-up** → G4 Dot Waffle ⇄ L14 Hundred Field ⇄ F4 Tick Donut (the default replacement for a pie chart); share × intensity dual encoding → G13 Big Slice; stacked by category → F7 Stacked Rungs
- **Two-timepoint comparison (before/after, then/now)** → category level (≤6 categories) → F12 Dumbbell Queue (horizontal, beads = real units) ⇄ F6 Paired Rungs (side-by-side ladders); when only 2–4 series need a trend line → Glance chunky slope (thick line, big number, conclusion in the title). Slope charts with too many crossings sharply reduce readability; do not add decorative structure just to make it Lupi.
- **Daily series (≤30 days, per-day reading)** → F2 Hairline Line ⇄ (90-day scale, wanting texture) L3 Barcode Lollipop; 30–60 days to see the shape → F3 Hairline Area
- **Cumulative growth** → G18 Draw-in + Counter
- **Dual-series causality (input vs output)** → G8 Rainfall
- **Real-time data** → G17 Dynamic Stream
- **Ranking over time** → for a dynamic demo use G16 Bar Race; for static see the "rank over discrete time" entry below
- **Weekday × hour × volume** → G14 Single Axis ⇄ F10 Dot Heat
- **Waterfall / increase-decrease decomposition (≤6 levels)** → F9 Rung Waterfall
- **Single-value progress (0–100%)** → F11 Tick Gauge ⇄ G18 Draw-in + Counter
- **Two-dimensional scatter (≤20 points)** → F8 Plumb Scatter; several hundred points distribution → G15 Jitter Strip
- **Single-variable binned frequency** → first check whether F1 Rung Bars can carry it directly (bins as categories); when bin semantics are truly needed use F14 Rung Histogram. Bin boundaries must have business meaning; do not cut bins arbitrarily for looks.
- **Grouped continuous distribution** → **five-number summary + outliers use F15 Tick Box directly** (no main-force encoding exists). When only density contours are needed, compare G15 Jitter Strip first; G19 Violin and L19 Ridgeline are backup, and you must state why Jitter / F15 are not enough.
- **Per-record distribution** → G15 Jitter Strip.
- **Category × category + volume (matrix)** → main force first: lightweight L4 Arc Matrix; cross-year with annotations L9 Bubble Almanac. Only when both cannot hold it (too many cells, bubbles squeezing each other, must read via lightness) use L16 Matrix Heat; for fast reading with a number printed in each cell use G20.
- **Full-year date × volume** → **a full year of 52 weeks × 7 days uses L17 Calendar Heat directly** (no main-force encoding; L3 only reaches the 90-day scale). A weekday × hour repeating cycle still uses F10 / G14.
- **Many-to-one attribution** → strong shape L5 Radial Convergence ⇄ with a name list L12 Type Colonnade
- **Funnel / stage-by-stage decrease** → L13 Hourglass Stream
- **Hierarchical structure** → G7 Tree LR
- **Hierarchy + share / weight (two levels, positive values)** → F13 Nested Treemap; to see only who belongs to whom without comparing size → G7 Tree LR
- **Multi-series composition over continuous time** → for static categorical composition use F7 Stacked Rungs first; **to see the total and composition together in a continuous time stream, use F16 Stream Ribbon directly** (no main-force encoding). A single-series total only uses F3 / G17.
- **One entity across 3–6 continuous dimensions** → **use L20 Parallel Coordinates directly** (no main-force encoding). More than 6 dimensions: filter or split first.
- **OHLC market data** → **use F17 Candlestick directly** (no main-force encoding). When there is only a min–max range and no open/close value, use G1.
- **Two-end aggregated flow** → first check whether L5 Radial Convergence / L12 Type Colonnade can carry the attribution relationship; only when the flow width truly must be seen use G22 Aggregate Sankey. To inspect every real path use B3 Threads.
- **Rank over discrete time (static)** → compare L11 Trend Lineage / L2 Dot Cascade first; only when per-period cell alignment is truly needed use G21 Rank Strip.
- **Event-sequence life history** → L11 Trend Lineage
- **Multiple entities' birth time + current state** → L1 Launch Fan
- **Per-event time-of-day distribution (within one day)** → L10 Radial Patchwork
- **Bipolar scale (both ends legitimate)** → L7 Brand Spectrum. Distinguish from single-pole scoring (radar): single-pole uses the native ECharts radar.
- **Network** → ≤15 nodes G6/G11 small charts; >15 or needing to query → B1 circular / B2 force-directed; multi-segment path flow → B3 Threads
- **Multiple groups × grid (wanting decorative feel)** → L8 Dotty Matrix; to read values → flatten with G14
- **One entity set, multiple dimensions carousel (demo)** → G9 Scatter Morph

### Map explicit-trigger rules

- Only when the user explicitly says "map", "regional distribution", "shade by country/state", or names choropleth, check Maps. A region field merely appearing in the data table must not auto-trigger.
- For US state-level numeric regions use M1 US Choropleth; for world country-level numeric regions use M2 World Choropleth. Map area is geographic area and does not represent value; the subtitle must state `shade = value`.
- M1/M2 depend on ECharts and online GeoJSON; state at delivery that an internet connection is needed, or inline legally sourced map data only when the user explicitly asks for offline.
- The China map is not to be copied and renamed from M1/M2. Only produce it after obtaining a complete data source and map-review information that meets current map-compliance requirements.

### F13 Nested Treemap hard rules

- Accepts only hierarchical data and non-negative weights; the parent value is the sum of the children, and contradictory parent/child totals are forbidden. Hand the area directly to the ECharts treemap layout; do not take the square root of the values.
- Show two levels by default (parent group + leaves). Enable drill-down only when there are more than two levels and the reader needs to query layer by layer; ordinary static delivery keeps `nodeClick:false` to avoid accidental view changes.
- Mono grayscale represents hierarchy only; do not randomly assign shades to each leaf; parent groups are distinguished by title bands, inter-group whitespace, and boundaries. The grouping must still be legible after removing color.
- porcelain uses single-hue lightness for ordered parent-group shares or hierarchy; palm uses hue correspondence for no more than 4 top-level categories; wire stays grayscale and allows only one clear protagonist to use `HERO`.
- When area already expresses value, color must not repeat the same value without explanation. The subtitle must state `area = ...`, and when color is used also state `color = ...`.
- When leaves exceed 30, labels are largely omitted, or the smallest rectangles are too small to form a stable hot zone, first merge the long tail into Other, split into multiple charts, or switch to G7 / L12 / the B-series relationship charts.
- The tooltip must at minimum show the full hierarchy path, the raw value, and the total share; if the in-card label does not fit, hide it — do not shrink below the minimum font size.

## 5. The three interaction questions (deciding static vs interactive)

Ask in order:

1. **Is there a real record behind this line/dot?** If not (pure texture decoration, such as the spokes of Cluster Field or the drips of Hourglass) → interaction is forbidden; adding hover to a contentless element is deception.
2. Has a record → **can it be read without clicking?** Fewer than 50 elements with both ends labeled (e.g. Colonnade) → static is enough; hover is a bonus.
3. **More than 50 elements or multi-segment paths** (e.g. Threads) → hover/pin is mandatory, otherwise it is just an atmosphere image. For implementation reference `templates/big-threads.html`: lay a 9px transparent twin line under the visible line as the hot zone; hovering a single line brightens the whole path, hovering a label pulls the whole bundle, clicking pins it.

## 6. Out-of-library chart types · translation workflow

When the chart the user wants is not among the 63 (or they send a reference image), **it is not impossible — you compose on the spot**. Four steps; step one may not be skipped:

1. **Answer the ontology first**: what does this chart type encode? Which data dimension does each visual channel (position / length / angle / area / lightness / density) map to? If you cannot answer, ask the user for the data structure. Copying the shape without the soul = wasted work (the pictorial bar once misbuilt "symbol counting" as "a tree growing taller" and had to be reworked).
2. **Find the nearest relative**: in the catalog, find the chart with the most similar data shape as a starting point, and inherit its layout skeleton and animation rhythm.
3. **Compose with tokens**: palette, fonts, corner radii, and animation parameters are all taken from `mono-tokens.js`; do not invent new colors or font sizes. The output must look "like one family at a glance" with the library charts. In color mode, colors change from a single preset in `color-presets.js`; the other tokens still follow `mono-tokens.js`.
4. **Pass the section 2 hard rules and the section 8 self-check**, the same standard as library charts.

Additional rule for translating a reference image: identify which school the reference belongs to (Glance or editorial); the editorial style's density, annotations, and hand-drawn feel (`blob`) are part of the ontology — do not over-converge it (the almanac had to be reworked for "not daring to crowd").

## 6.5 Color (auto-selected by scenario, single color system)

**Mono is the fallback, not the forced answer when color is not triggered.** Even when the user does not mention color, evaluate whether color fits based on data semantics, category count, reading scenario, and content temperament; when the fit is unclear, or color brings no real information value, go back to Mono.

The color first draft is chosen from one of three presets; the values are in `color-presets.js`. The presets are for quickly getting a stable, unified first version, not a locked palette. When the user asks "make that blue deeper", keep adjusting within the current color system; when the user explicitly gives brand colors, color values, or a complete palette, build a custom palette per the rules below. After adjusting, you must re-check contrast, visual hierarchy, and data semantics.

**The same HTML or the same delivery batch must first lock one global color system: Mono, porcelain, palm, wire, or one custom.** All charts share that choice. If one chart does not support the chosen system, do not recolor it alone; switch to a globally compatible system, or fall the whole set back to Mono.

**The structural source of truth is always the original gallery.** Look up render code in the galleries under the root of `templates/`; color values come from `color-presets.js`. First choose the structure per section 0, then decide whether to reskin.

### Whether to use color

Judge by the following priority:

1. **The user explicitly specifies.** When the user asks for a color, temperament, or preset, obey first, but still pass the capacity, contrast, and data-semantics checks.
2. **The agent auto-selects.** Even if the user does not mention color, as long as the data shape and scenario have a clear correspondence with a preset, you may use it automatically: an ordered single series suits porcelain; a few unordered categories suit palm; needing one controlled gaze anchor suits wire.
3. **When the relationship is unclear, use Mono.** Too many categories, high-density records, color with no stable meaning, or a batch that cannot share one preset → use Mono.

Color is not an upgraded version but a semantic tool the agent may proactively choose. At delivery, state in one sentence the chosen color system and the data meaning it carries.

### Custom palette (enabled only when the user explicitly asks)

The agent must not invent a fifth default aesthetic on its own. Build a custom palette only when the user gives explicit color values, brand colors, brand guidelines, or "use the colors of this reference image"; saying only "make it prettier" still picks from the three built-in presets.

1. **Determine the color logic first, then assign values.** Ordered data uses a single-hue lightness ramp; unordered categories use categorical colors; when focus is needed use neutral colors + one accent. Forbidden: grab five colors and then scatter them evenly over everything.
2. **Build complete roles, not scattered hex values.** A custom palette must at minimum define `BG`, `TXT`, `MUT`, `GRID`, `DATA`; define `HERO` when emphasis is needed, `RAMP` for ordered data, and `CAT` for categorical data. The deliverable inlines a `CUSTOM` object, and all charts take colors from roles.
3. **Interpret by input count.** 1 color generates a same-hue lightness ramp; 2 colors default to main data color + accent, not two equal categories; 3–6 colors enter `CAT` only when the data genuinely has corresponding categories. More than 6: first merge categories, switch to position/labels, or fall back to Mono.
4. **Derived light/dark is allowed; smuggling in new hues is not.** Light shades come from mixing the user's color with `BG`; dark shades from mixing the user's color with `TXT`; do not borrow porcelain, palm, or wire values to fill out custom.
5. **Contrast is a hard gate.** Body text and small labels are at least 4.5:1 against the background, large text at least 3:1; critical boundaries, data shapes, and interaction states are at least 3:1 against adjacent colors. When it fails, adjust lightness first; do not arbitrarily change the user's specified main hue.
6. **Color must not be the only cue.** Categories still carry labels, ordinals still keep position/length/area, and emphasis still has a title or annotation. For a color-vision-deficient user, the chart structure should still read after color is removed.
7. **Lock only this one custom per delivery.** Custom does not mix with any built-in preset; a multi-chart delivery shares the same `CUSTOM`. Unless the user explicitly asks to fix a brand color as a project-level preset, custom is only inlined in the current deliverable and is not written back to `color-presets.js`.

When the user later asks for "a bit deeper", "a warmer background", or replaces a color value, modify the corresponding role and re-check the whole set's contrast and semantic mapping; do not change only the named element.

### Which set to choose: data shape first, then temperament

| Data shape | Allowed | Reason |
|---|---|---|
| Ordered / single series (progress, heat, time series, single metric, ranking) | porcelain, wire | The contract that lightness is data still holds |
| Unordered categories ≤4 | palm | Hue corresponds to category |
| Unordered categories 5–6 | palm (barely) | Relies on lightness and saturation to help distinguish |
| Categories >6 | Mono grayscale | The color presets lack capacity |
| Needing restraint but one gaze anchor | wire | Grayscale carries the data, orange marks only the protagonist |

| The user will say | Preset | Temperament |
|---|---|---|
| blue, cold, academic, rational, serious, techy | porcelain | single-hue blue ramp |
| green, warm, natural, gentle, vintage, Morandi | palm | low-saturation green and yellow, amber accent |
| black and white, restrained, magazine-like, editorial | wire | black and gray plus a touch of fluorescent orange |

### Color hard rules

- **One color system per delivery.** A single chart, the same HTML, or the same sibling set may use only Mono, one preset from `color-presets.js`, or one user-requested custom. Mixing presets is forbidden, and custom borrowing built-in preset colors is forbidden.
- **Line width ×1.8, opacity floor .85.** Hairlines that read in grayscale easily disappear once tinted; `dot heat` is the exception.
- **Every chart has at least 3 color steps or positions.** Using only 1–2 colors falls back to grayscale.
- **Color must connect to a real dimension.** Ordinal ramps connect to values, segmented colors to months or segments, categorical colors to categories; the footnote states what the color encodes.
- **The accent color goes to only one protagonist.** A second protagonist cancels out the emphasis.
- **Dark-card data colors must be brighter than the card base.** Dark-background big charts use the preset's `DARK` block. `big-circular` / `big-force` / `big-threads` only have porcelain and palm; wire uses the original Mono big charts.
- **In palm, `DATA` and `HERO` must differ.** Amber and olive have close lightness; do not treat the two as equal category colors.

## 7. When to say no

Daring to refuse is more credible than accepting everything. Do not do the following cases; offer alternatives instead:

- **Broken-axis bar chart** → refuse; give the three honest options (shoot up / magnifier / tear the bar not the axis).
- **Glow / glassmorphism / 3D** → refuse; keep the existing visual grammar. Custom color values map per the custom rules; mixing color systems is refused.
- **Using multiple hues for a single series** → refuse. Offer porcelain, wire, or fall back to Mono.
- **More than 6 categories still wanting color** → refuse; fall back to Mono grayscale.
- **The user did not explicitly ask for a map** → do not auto-use M1/M2 just because the data has a region field; keep selecting by ordinary comparison, ranking, or composition.
- **Map scope beyond M1/M2** (China provincial, city points, trajectory maps, etc.) → do not apply wrong boundaries; confirm data source, projection, compliance, and interaction requirements before composing on the spot.
- **Adding interaction to purely decorative elements** (section 5 question 1) → refuse and explain.
- **Radar chart reconstruction** → do not reconstruct; use the native ECharts radar + Mono token reskinning (tested: in presentation scenarios, "a recognizable chart shape" has value).
- **The data is too little to support the chosen chart type** (e.g. 3 nodes for a force layout) → downgrade to a simpler chart and explain.

## 8. Pre-delivery self-check list

1. Are values and visuals proportional? (Did area use sqrt? Are the bars unbroken?)
2. Is the palette controlled? Does the whole HTML or the same delivery use only Mono, a single built-in preset, or a single custom? Any non-ladder color appearing in Mono = rework; another preset's color appearing in a built-in color mode = rework; does custom take colors only from `CUSTOM` roles and pass the contrast check?
3. Will labels overlap? (barcode lesson: adjacent peak labels need an enforced minimum gap)
4. Is the minimum font size within bounds? (half-width 6.5 / full-width 5.5)
5. Is the demo data deterministic via `rnd`? Does it look the same on two refreshes?
6. Does reveal work? (plays on scroll-in, click to replay, timers do not stack, reduced-motion fallback present)
7. Does `node --check` pass syntax? (Extract the `<script>` contents and check them.)
8. Is the four-piece card complete? Is the title a conclusion, not a chart-type name?
9. Does the subtitle make the legend clear? (The reader sees only this one line, not the code.)
10. Was a full candidate audit completed? Write down at least 3 candidates and elimination reasons, not just "which template was used".
11. If it is a multi-chart page, were the templates globally allocated? Are there repeated similar outlines, too many dark cards, or all charts turned into the same radial type?
12. Does each chart record the chart number, gallery file, and in-card title? Does the finished core structure really come from that template rather than being reinvented?
13. If Glance is used, is it stated why both Lupi Editorial and Lupi Basics do not fit? If not, rework back to Lupi / Basics.
14. Final question: placed back next to the corresponding card in the chosen gallery, is this chart the same template family, not just "kind of similar in style"?

## 9. Single-file template skeleton

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Mono — {chart name}</title>
<!-- When ECharts is needed: -->
<script src="https://cdn.jsdelivr.net/npm/echarts@6/dist/echarts.min.js"></script>
<!-- When Chart.js is needed (G1 / G3): -->
<!-- <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script> -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="{MONO.FONT.link}" rel="stylesheet">
<style>/* inline MONO.CARD_CSS */</style>
</head>
<body>
<div class="grid2">
  <div class="card"><!-- or card dark / card wide -->
    <h2>{conclusion-style title}</h2>
    <div class="sub">{description} · {legend} · {time range}</div>
    <!-- Chart container, choose one of three by engine: -->
    <div class="ch" id="ch"></div><!-- ECharts -->
    <!-- Hand-written SVG: <svg id="ch" viewBox="0 0 400 320"></svg> -->
    <!-- Chart.js (G1/G3): <div class="wrap"><canvas id="ch"></canvas></div>, with .wrap{position:relative;height:320px} -->
    <!-- ⚠️ Chart.js must attach to <canvas>; wrapping a <div class="ch"> triggers "can't acquire context" -->
    <div class="src">{chart type} · {series} · {data source}</div>
  </div>
</div>
<script>
// Inline the full mono-tokens.js
// ── Data (the user only needs to change this) ──
const DATA = [ /* ... */ ];
// ── Render ──
MONO.obsReveal('ch', el => { /* ... */ });
</script>
</body>
</html>
```

## 10. Report mode skeleton

```text
report-catalog.md                     # first choose R01–R12 by scenario
templates/reports/report-NN.en.html   # English full-page source (vendored)
templates/reports/index.html          # template index, openable locally
# upstream only (not vendored): .zh.html templates, PNG previews in docs/assets/reports/
```

A report delivery is still a single HTML file; the files in `templates/reports/` are copyable starting skeletons, not content samples to copy word for word. The demo data inside the templates only shows structure and must all be replaced when the final report is generated.
