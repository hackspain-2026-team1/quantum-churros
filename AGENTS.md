# Repository instructions

## Frontend stack

- Use SvelteKit 5 with TypeScript and Bun for all frontend work.
- Bun is the only JavaScript package manager and task runner in this repository. Use `bun install`, `bun add`, `bun run` and `bunx`; never introduce npm, pnpm, Yarn or their lockfiles.
- Commit `bun.lock` and keep dependency changes reproducible.

## Component-first UI with shadcn-svelte

- Build every frontend feature component-first from shadcn-svelte. Before writing UI markup or introducing another component library, check the existing local components and the shadcn-svelte registry for the required primitive or pattern.
- Initialize shadcn-svelte with `bunx shadcn-svelte@latest init -c frontend`. Add primitives with `bunx shadcn-svelte@latest add <component> -c frontend` so dependencies, aliases and source files remain consistent with `frontend/components.json`.
- Treat `frontend/components.json` as the source of truth for registry configuration and aliases. Registry primitives live under `frontend/src/lib/components/ui/`.
- Compose registry primitives into product and domain components under `frontend/src/lib/components/`. Routes should assemble components and load data; they should not duplicate reusable controls or large interface sections.
- A custom primitive is allowed only when neither the installed components nor the shadcn-svelte registry provides the required behavior. Build it with the same tokens, accessibility conventions and variant patterns as the local shadcn-svelte components.
- Extend shared primitives centrally when a behavior or style must propagate across the application. Do not fork a primitive per screen or reproduce it with page-local markup.
- Preserve keyboard interaction, focus states, semantic labels, loading states, empty states and error states when composing or adapting components.

## Dependency direction

- `frontend` may consume generated contracts but must not import Python code or research artifacts.
- `backend` may import `engine`; `engine` must not import `backend`.
- `research` may import `engine`; production code must never import `research`.

## Database lifecycle and dataset ingestion

- PostgreSQL is the shared application database. Use the container from `compose.yaml`; SQLite is only a lightweight fallback for isolated unit tests.
- Alembic owns schema changes only. Never place the challenge CSV contents or other bulk seed data inside an Alembic revision.
- `20260918_02_seed_baseline_dataset.py` is a frozen legacy demo seed already present in migration history. Do not regenerate it or use it as a pattern; all new dataset loads go through `xray-db ingest`.
- Start the stack with `make up`; the API applies pending Alembic migrations before serving requests.
- Validate the local dataset with `make db-seed-dry-run`, then load it with `make db-seed`. The ingestion command runs inside the API container, streams every CSV through PostgreSQL `COPY`, and records the content hash and row counts in `source.dataset_import`.
- Dataset ingestion is explicit and idempotent. Never trigger it from API startup, tests, or a migration. Re-running the same hash changes no rows; a different hash is stored alongside prior datasets.
- Never truncate source tables to refresh data. Add a new dataset version and select it by `dataset_hash` so experiments and score runs remain reproducible.

## Industry classification

- Company sector inference is documented in [`docs/INDUSTRY_CLASSIFICATION.md`](docs/INDUSTRY_CLASSIFICATION.md). Read it before changing rules, signals, thresholds, or `entityindustry` persistence.
- Classification logic lives in `engine/src/xray_engine/industry_classifier.py` (signals + `ClassifierStrategy`). The backend only persists results and serves the API.
- Run `uv run xray-db classify data/raw` after ingesting a new dataset. Use `--force` to re-run when `rules-v1` thresholds change. Never classify from API startup.
- Demo overrides in `backend/app/benchmarks/demo_overrides.py` are API-only; stored classifications remain signal-pure.
- Benchmark peer mapping is in [`docs/BENCHMARK_REFERENCE.mdx`](docs/BENCHMARK_REFERENCE.mdx).
