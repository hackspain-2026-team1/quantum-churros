# Repository instructions

## Frontend stack

- `frontend/` is the single Rumbo application. It uses plain TypeScript, Vite, Bun, direct DOM composition and WebGL2; do not introduce React, Svelte or another frontend framework unless the team explicitly changes this decision.
- Bun is the only JavaScript package manager and task runner in this repository. Use `bun install`, `bun add`, `bun run` and `bunx`; never introduce npm, pnpm, Yarn or their lockfiles.
- Commit `bun.lock` and keep dependency changes reproducible.

## Component-first UI

- Build frontend features from the existing primitives in `frontend/src/vistas/`; extend those shared primitives instead of duplicating page-local DOM structures.
- Use `frontend/src/vistas/dom.ts` for DOM construction and keep product sections in focused modules under `frontend/src/vistas/`.
- Keep financial contracts, loaders, derived values and formatting under `frontend/src/datos/`; visual modules consume that layer and must not reimplement its rules.
- Keep the WebGL2 renderer isolated under `frontend/src/arena/`; DOM views may coordinate scenes but must not duplicate rendering internals.
- Extend shared primitives centrally when a behavior or style must propagate across the application. Do not fork a primitive per screen or reproduce it with page-local markup.
- Preserve keyboard interaction, focus states, semantic labels, loading states, empty states and error states when composing or adapting components.

## UI number, currency and date formatting

- All number, currency, percentage and date rendering rules are documented in [`docs/UI_FORMATTING.mdx`](docs/UI_FORMATTING.mdx). Read it before rendering any numeric or monetary value, and follow it for every new component.
- Locale is Spanish (Spain): `es-ES`. Decimals use a comma, thousands use a dot (`1.234,56`).
- The euro symbol goes after the amount with a non-breaking space: `1.234,56 €`. Never write `€1.234,56`.
- Percentages are `NN,N %` with a non-breaking space; scores are integers without decimals.
- Never render a raw float in the UI (e.g. `-0.9976`, `60.68`). Format through the shared helpers in `frontend/src/datos/formato.ts`; never call `toLocaleString()` without an explicit `'es-ES'` locale.
- Do not duplicate `Intl` formatting per view. Extend `frontend/src/datos/formato.ts` centrally when a new format is needed.

## Rumbo data and deployment

- Read `frontend/README.md` and `frontend/DIARIO.md` before changing Rumbo.
- Rumbo ships as the root application in the `web` image. It reads the bundle from `/data/v1/` and its derived data (`params.json`, `entities.json`, `products/`, `horizons/`) from `/data/rumbo/`, mounted from `/opt/quantum-churros/rumbo`. Never put Rumbo files inside the engine bundle: that changes its `bundle_id` and breaks the bundle integrity check.
- Rumbo never falls back to invented data: a missing file is shown as missing. The synthetic portfolio exists only in development (`?datos=sinteticos`); `bun run build:despliegue` fails if it, any data file, a hard-coded entity id or a third-party request reaches the build.

## Pre-redesign UI catalog

- The frontend at commit `cad5b5a` is the **pre-redesign interface**. It is documented exhaustively in [`docs/ui-catalog-pre-redesign/`](docs/ui-catalog-pre-redesign/README.md): every screen, element, state, URL parameter, calculation and source file, with 113 real screenshots (desktop, tablet, mobile).
- Consult `docs/ui-catalog-pre-redesign/CATALOGO.md` before redesigning or replacing a screen, to know what the old one did and which behaviors, states and texts must be kept or deliberately dropped. Search it with `rg`; screenshots live in `capturas/`.
- The catalog is a frozen snapshot: do not update it to match new UI. Pages added after `cad5b5a` (such as `/wiki`) are not covered.

## Dependency direction

- `frontend` may consume generated contracts but must not import Python code or research artifacts.
- `backend` may import `engine`; `engine` must not import `backend`.
- `research` may import `engine`; production code must never import `research`.

## Database lifecycle and dataset ingestion

- PostgreSQL is the shared application database. Use the container from `compose.yaml`; SQLite is only a lightweight fallback for isolated unit tests.
- Alembic owns schema changes only. Never place the challenge CSV contents or other bulk seed data inside an Alembic revision.
- `20260918_02_seed_baseline_dataset.py` is a frozen legacy demo seed already present in migration history. Do not regenerate it or use it as a pattern; all new dataset loads go through `xray-db ingest`.
- Start the stack with `make up`; the API applies pending Alembic migrations before serving requests.
- Local PostgreSQL binds to host port `5433` by default. Set `POSTGRES_PORT` when that port belongs to another project; container-to-container commands such as `make db-sync` keep using the internal `postgres:5432` address.
- Validate the local dataset with `make db-seed-dry-run`, then load it with `make db-seed`. The ingestion command runs inside the API container, streams every CSV through PostgreSQL `COPY`, and records the content hash and row counts in `source.dataset_import`.
- Run `make db-sync` to start PostgreSQL and execute the complete reproducible data cycle: ingest the immutable source version, classify companies, calculate Parquet model artifacts, publish the relational score projection, and regenerate the JSON bundle consumed by the frontend.
- `make db-sync` also regenerates `rumbo/entities.json` from that exact bundle. Entity aliases are deterministic presentation data keyed by the immutable IDs; never edit the generated JSON, derive names from scores, or put aliases in an Alembic revision.
- Dataset ingestion is explicit and idempotent. Never trigger it from API startup, tests, or a migration. Re-running the same hash changes no rows; a different hash is stored alongside prior datasets.
- Never truncate source tables to refresh data. Add a new dataset version and select it by `dataset_hash` so experiments and score runs remain reproducible.

## Industry classification

- Company sector inference is documented in [`docs/INDUSTRY_CLASSIFICATION.md`](docs/INDUSTRY_CLASSIFICATION.md). Read it before changing rules, signals, thresholds, or `entityindustry` persistence.
- Classification logic lives in `engine/src/xray_engine/industry_classifier.py` (signals + `ClassifierStrategy`). The backend only persists results and serves the API.
- Run `uv run xray-db classify data/raw` after ingesting a new dataset. Use `--force` to re-run when `rules-v1` thresholds change. Never classify from API startup.
- Demo overrides in `backend/app/benchmarks/demo_overrides.py` are API-only; stored classifications remain signal-pure.
- Benchmark peer mapping is in [`docs/BENCHMARK_REFERENCE.mdx`](docs/BENCHMARK_REFERENCE.mdx).

## Continuous deployment

- Pull requests run the complete verification suite and build both production images through `.github/workflows/ci-deploy.yml`.
- Every verified commit on `main` publishes `api` and `web` images to GHCR using the full commit SHA, records their content digests, then deploys those exact digests to the `development` GitHub environment on `datons-dev`.
- The workflow reaches `datons-dev` through an ephemeral Tailscale node tagged `tag:github-ci`, authenticated with GitHub OIDC workload identity federation. Never add a persistent GitHub runner, restore a reusable Tailscale auth key, or broaden that tag beyond `datons-dev:22`.
- Server deployment state lives in `/opt/quantum-churros`. The `quantum-deploy` account may only invoke the root-owned `/usr/local/sbin/quantum-churros-deploy` command; never add it to the `docker` group or make deployment files writable by it.
- Deployment is image-based, not a mutable Git checkout. Do not run `git pull` on the server. The deployment command serializes releases, runs migrations through the API image, waits for container health checks, and restores the previous images when startup fails.
- Before any manual `docker compose` operation on `datons-dev`, confirm that no `main` deployment is running. Direct Compose commands bypass `/var/lock/quantum-churros-deploy.lock` and can race with CI while `.release.env` changes. Because production services use `pull_policy: always`, an administrative recreation without the ephemeral GHCR token must use the immutable image already present with `--pull never`.
- PostgreSQL data, model artifacts, and the exported frontend bundle persist independently from application images. The production bundle is mounted from `/opt/quantum-churros/bundle`; application deployments must never replace it or delete the `quantum-churros_postgres_data` volume.
