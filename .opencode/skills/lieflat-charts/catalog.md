# Lieflat Charts Chart Catalog · 63

> Every chart carries three labels: **data shape** (the primary key for selection), **context**, and **reader time**.
> **Main force and backup:** the main force is L1–L15 and F1–F13; draw from here by default. L16–L20, F14–F17, and G19–G22 are backup; use them only when the main force cannot honestly encode this data, and state the reason. The exception is these five — F15, F16, F17, L17, L20: no corresponding encoding exists in the main force, so when the data shape matches, use them directly (see `SKILL.md` section 0 clauses 3.1 / 3.2).
> **Selection priority follows the hard constraints in `SKILL.md`: by default, fully audit Lupi Editorial first, then Lupi Basics; only when neither group fits, or the user explicitly asks for Glance / dashboard / three-second read, do you enter Glance.**
> The "Sibling" column = same-topic, different-form pairs, used only to compare data contracts and recall candidates; it does not mean both must be generated, and it cannot change the priority above.
> Reference implementations are in `templates/`: Glance `templates/glance-gallery.html`, Lupi `templates/lupi-gallery.html`, foundational group `templates/basics-gallery.html`, maps `templates/maps-gallery.html`, big charts `templates/big-*.html`. Maps are recalled only when the user explicitly asks for a map or regional distribution. A gallery is a multi-card fold-out — to look up a chart's code, first find the card by the "in-card title" in the table below, then search `<script>` for the same-named `// ════` comment block. Real-data finished cases are in `examples/`.

## Glance system · 20 (thick strokes · pre-aggregated · read in 3 seconds)

| # | Name | In-card title | Data shape | Context | Reader time | Engine | Sibling |
|---|------|---------|---------|------|---------|------|------|
| G3 | Chunky Bars | Revenue by plan | Few-category ranking comparison (≤6) | Weekly dashboard | <10s | Chart.js* | L2 Dot Cascade; multi-select percentages → L15 Ballot Tally |
| G4 | Dot Waffle | Where sign-ups come from | 100% composition (shares) | General, the default pie replacement | <10s | Hand-written SVG | L14 Hundred Field |
| G5 | Pictorial Bar | Trees planted, year by year | Year-by-year counting (one symbol = a fixed quantity) | External story page | <10s | ECharts | — |
| G6 | Circular Graph (small) | Who works with whom | Network, ≤12 nodes | Quick illustration | <10s | ECharts (dark card) | Preview version of big chart B1; for many nodes use B1 |
| G7 | Tree LR | Everything the platform ships | Hierarchy (2–3 levels) | Product catalog / architecture page | ~30s | ECharts | — |
| G8 | Rainfall Dual Area | Campaigns rain down | Dual-series causality (input vs output) | Growth retrospective | ~30s | ECharts | — |
| G9 | Scatter Morph | One dataset, three views | Three dimensions of one entity set, carouseled | Short video / demo | animation | ECharts universalTransition | — |
| G10 | Diverging Bar | Where we gained, where we bled | Categorical values with positive and negative | Weekly dashboard | <10s | ECharts | — (Equalizer, Meridian Dots removed) |
| G11 | Force Graph (small) | Integrations, pulled into orbit | Center + satellite network, ≤15 nodes | Quick illustration, draggable | <10s | ECharts (dark card) | Preview version of big chart B2; static poster version L6 |
| G12 | Stagger Wave | Fifty markets, one wave | Many-category distribution (30–60 bars) | Short-video entrance | animation | ECharts | — |
| G13 | Big Slice (Custom Pie) | Big slice, deep engagement | Dual encoding: share (angle) × intensity (radius) | Product analysis | ~30s | ECharts custom | — |
| G14 | Single Axis | Support load, day by day | Weekday × hour × volume (punch-card data) | Support / ops weekly report | ~30s | ECharts | — (Punch Card removed; this is the only version) |
| G15 | Jitter Strip | Response times, spread out | Grouped distribution, per-record (several hundred points) | SRE / ticket analysis | ~30s | ECharts | — |
| G16 | Bar Race | Eight products race | Ranking evolving over time | Short video | animation | ECharts realtimeSort | — |
| G17 | Dynamic Stream | Concurrent users, streaming | Real-time scrolling series | Live stream / big screen | animation | ECharts | — |
| G18 | Draw-in + Counter | H1 revenue, drawn in one stroke | Cumulative growth (one line + one big number) | Short video / report opening | animation | ECharts | — (Release Rings removed) |
| G19 | Violin | How fast each plan gets an answer | Density contour of grouped continuous distribution + median | Dashboard / analysis report | <10s | SVG | F15 Tick Box; L19 Ridgeline |
| G20 | Matrix Heat (Glance) | Adoption runs hot on the new versions | Two discrete dimensions × value, ≤60 cells, number read directly in each cell | Dashboard / product analysis | <10s | SVG | L16 Matrix Heat (slow-read version) |
| G21 | Rank Strip | Flows climbs to the top | Multi-entity rank over discrete time; suits static print | Reporting / billing retrospective | <10s | SVG | G16 Bar Race (dynamic demo) |
| G22 | Aggregate Sankey | Channels pour into plans | Two-end aggregated flow, width = quantity, no per-path query required | Attribution / conversion analysis | ~30s | SVG | B3 Threads (per-path query) |

\* G1/G3 still use Chart.js; they may later migrate to ECharts to unify the rendering stack.

## Lupi system · 19 (hairlines · per-record · 30-second read)

| # | Name | In-card title | Data shape | Context | Reader time | Engine | Sibling |
|---|------|---------|---------|------|---------|------|------|
| L1 | Launch Fan | Twelve features, fanned out | Multiple entities, each with birth time + current scale | Annual report / story page | ~30s | SVG | — |
| L2 | Dot Cascade | What breaks, stacked and ranked | Ranking comparison, countable units (unit chart) | Annual report / story page | ~30s | SVG (dark card) | G3 Chunky Bars |
| L3 | Barcode Lollipop | Ninety days as a barcode | Daily series, one reading per day (90-day scale) | Annual report / story page (with text column) | ~30s | SVG (full-width) | — |
| L4 | Arc Matrix | Eight products land in twelve cities | Category × category + volume, small data (≤100 cells) | Lightweight matrix | ~30s | SVG | Lightweight version of L9 Almanac; use this one for thin data |
| L5 | Radial Convergence | 48 requests pull toward five themes | Many-to-one attribution, detail preserved (≤60 items) | Poster / cover | ~30s | SVG | L12 Colonnade (two options) |
| L6 | Cluster Field | The contributor field | Center + satellite network, poster version | Poster / cover (recognize shape, not read values) | ~30s | SVG (full-width) | B2 force-big (use B2 for interaction / querying) |
| L7 | Brand Spectrum | Where the brand sits | Bipolar scale (both ends are legitimate positions) + competitor comparison | Brand research report | ~30s | SVG | — (Equalizer removed; the only surviving scale chart) |
| L8 | Dotty Matrix | Four squads, stacked in space | Multiple groups × grid × volume, equidistant stacking | Cover / poster (strongly decorative) | ~30s | SVG | The flattened G14 is more readable; use G14 to read values |
| L9 | Bubble Almanac | Eight years of tickets, one almanac | Category × year + volume + status, long span (hand-drawn blob) | Annual report (with annotations / timeline) | >30s | SVG (full-width) | L4 Arc Matrix (lightweight version) |
| L10 | Radial Patchwork | A quarter of deploys, overlaid | Per-event overlay: time (angle) × scale (radius), opacity = density | Annual report / story page | >30s | SVG | — (Polar Line removed; this is the only 24h distribution chart) |
| L11 | Trend Lineage | Features rise, fall, come back | Event-sequence life history (launch / rework / dormancy / survival) | Product retrospective | >30s | SVG | — |
| L12 | Type Colonnade | Forty-four repos, ten owners | Many-to-one attribution + per-item list (≤50 items) | Governance / audit report | ~30s | SVG | L5 Convergence (two options) |
| L13 | Hourglass Stream | The funnel, poured | Stage-by-stage decreasing count (funnel) | Annual report / story page | ~30s | SVG | — |
| L14 | Hundred Field | A hundred of us, four minds | 100% composition (shares), ≤6 small-data categories | Annual report / story page | ~30s | SVG | G4 Dot Waffle |
| L15 | Ballot Tally | What they fear, tick by tick | Multi-select percentages (each item independent 0–100), ≤6 items | Annual report / story page | ~30s | SVG | G3 Chunky Bars |
| L16 | Matrix Heat | Which features get used together | Two discrete dimensions × value, ≤100 cells, keeps matrix structure and highlight cells | Annual report / product analysis | ~30s | SVG | G20 Matrix Heat (fast-read version) |
| L17 | Calendar Heat | A year of deploys, day by day | Full-year date × volume, 52 weeks × 7 days | Annual report / ops retrospective | ~30s | SVG (full-width) | F10 Dot Heat (weekday × hour) |
| L19 | Ridgeline | Five pipelines, five tempos | 3–8 groups, density-shape comparison of continuous distributions | Annual report / research report | >30s | SVG | G19 Violin (few groups, fast read) |
| L20 | Parallel Coordinates | Twelve products, four dimensions | One entity set across 3–6 continuous dimensions, one line per entity | Product portfolio / research report | >30s | SVG | G9 Scatter Morph (demo carousel) |

> L14–L15 are the **small-data group**: when the data has only a few percentages, unit decomposition recovers Lupi density — 1 dot = 1 person / 1 percentage point; density comes from units, not record count. The unit meaning must be written into the subtitle (e.g. "one dot = one person in a hundred"), and only honest units are spread; do not invent individuals.

## Foundational group · 17 (F1–F17 · Lupi grammar × foundational chart silhouettes, made for sparse data)

From afar you recognize the foundational chart form (bar / line / donut…); up close every unit is countable. The Lupi first choice when the data has only a few categories or a few dozen days — look here first, and only go to out-of-library translation if nothing fits. Reference implementation `templates/basics-gallery.html`.

| # | Name | In-card title | Data shape | Context | Reader time | Engine | Sibling |
|---|------|---------|---------|------|---------|------|------|
| F1 | Rung Bars | Revenue by plan, rung by rung | Few-category comparison (≤8), countable units | Annual report / story page | ~30s | SVG | G3 Chunky Bars |
| F2 | Hairline Line | Thirty days of sign-ups | Daily series (≤30 days, per-day reading) | Annual report / story page | ~30s | SVG |
| F3 | Hairline Area | Concurrent users, filled with days | Daily series (30–60 days, to see the shape) | Annual report / story page | ~30s | SVG | L3 Barcode Lollipop |
| F4 | Tick Donut | Where the traffic comes from | 100% composition (≤6 segments) | Annual report / story page | ~30s | SVG | G4 Dot Waffle ⇄ L14 Hundred Field |
| F5 | Tick Rows | Six teams, shipped and counted | Horizontal ranking comparison, countable units (≤8 rows) | Annual report / story page | ~30s | SVG | L2 Dot Cascade |
| F6 | Paired Rungs | This year against last, plan by plan | Grouped comparison (2 series per category, e.g. then vs now) | Annual report / retrospective | ~30s | SVG | — |
| F7 | Stacked Rungs | Where each region's revenue sits | Stacked composition (≤4 categories × ≤3 segments) | Annual report / retrospective | ~30s | SVG | — |
| F8 | Plumb Scatter | Price against satisfaction | Two-dimensional scatter (≤20 points) | Product analysis | ~30s | SVG | G15 Jitter Strip (for distribution) |
| F9 | Rung Waterfall | From gross to net, step by step | Waterfall / increase-decrease decomposition (≤6 levels) | Finance / retrospective | ~30s | SVG | — |
| F10 | Dot Heat | When support gets loud | Weekday × hour × volume (small heatmap) | Support / ops | ~30s | SVG | G14 Single Axis |
| F11 | Tick Gauge | How far to the quarter's goal | Single-value progress (0–100%) | Report opening | <10s | SVG | G18 Draw-in + Counter |
| F12 | Dumbbell Queue | Onboarding, before and after | Category-level before/after comparison (≤6 categories, beads = real units) | Annual report / retrospective | ~30s | SVG | — (the Lupi slot for two-point trends, replacing the removed Slope Beads) |
| F13 | Nested Treemap | Where the work went | Two-level hierarchy + positive weights, rectangle area = value | Budget / product portfolio / space usage | ~30s | ECharts (SVG) | G7 Tree LR (when only viewing belonging, not share) |
| F14 | Rung Histogram | Most tickets resolve within six hours | Single-variable binned frequency, bins have business meaning and countable units | Support / ops analysis | ~30s | SVG | G19 Violin; F15 Tick Box |
| F15 | Tick Box | Reply times, boxed by plan | Grouped five-number summary + outliers; the raw distribution can be summarized | Support / experiment analysis | ~30s | SVG | G19 Violin; F14 Histogram |
| F16 | Stream Ribbon | Three products trade the same river | 2–5 series, composition over continuous time while also seeing the total | Product / traffic retrospective | ~30s | SVG (full-width) | F7 Stacked Rungs (static categories) |
| F17 | Candlestick | Six weeks of the token, candle by candle | OHLC four-value time series, hollow = up, filled = down | Market / price retrospective | ~30s | SVG |

## Maps · 2 (recalled only when the user explicitly asks for a map)

A country, state/province, or region field appearing in the data **does not mean a map is used automatically**. Only when the user explicitly asks for "a map", "regional distribution", "shade by country/state", etc., do you select from `templates/maps-gallery.html`. Maps render via ECharts and online GeoJSON, and require an internet connection.

| # | Name | In-card title | Data shape | Context | Reader time | Engine | Limitation |
|---|------|---------|---------|------|---------|------|------|
| M1 | US Choropleth | Sign-ups across the states | US state-level regions + non-negative values, lightness = value | US market / ops report | ~30s | ECharts + GeoJSON | Only on explicit request; state area does not represent value |
| M2 | World Choropleth | Where the users are | World country-level regions + non-negative values, lightness = value | Global market / ops report | ~30s | ECharts + GeoJSON | Only on explicit request; not for points or paths |

## Standalone interactive big charts · 3 (one file per chart, full-page format)

| # | File | Data shape | Interaction | When to use |
|---|------|---------|------|-----------|
| B1 | `templates/big-circular.html` | Network, 60-node circular chord membrane | hover focuses adjacency, click replays | Relationship data with >15 nodes |
| B2 | `templates/big-force.html` | Network, 180-node force-directed galaxy | drag-and-spring-back, hover focuses | Large network to query node by node |
| B3 | `templates/big-threads.html` | Three-stage paths, 100+ silk threads | hover a single line / whole bundle, click to pin, status bar readout | Multi-stage flow to query path by path |

## Removed chart types (better replacements already exist)

Polar Line (24h distribution → L10), Punch Card (→ G14), Release Rings (style belongs to neither system), static Thread Triptych (→ B3), Profile Equalizer (→ G10), Slope Beads (crossing slopes are not readable enough; the slope chart still awaits redesign), Meridian Dots (positive/negative categories switched to G10). The last two come from an unused Lenny case draft and are not recommended for restoration as-is.
