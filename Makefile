.DEFAULT_GOAL := help

COMPOSE := docker compose -f compose.yaml -f compose.dev.yaml
XRAY_DATA ?= data/raw
XRAY_BUNDLE ?= bundle
XRAY_OUT ?= artifacts
EVIDENCE_MONTHS ?= 24

.PHONY: dev
dev: ## Build and start the complete development stack
	$(COMPOSE) up --build --watch

.PHONY: up
up: ## Start the development stack in the background
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop services without deleting data
	$(COMPOSE) down

.PHONY: logs
logs: ## Follow service logs
	$(COMPOSE) logs -f $(service)

.PHONY: status
status: ## Show service and health status
	$(COMPOSE) ps

.PHONY: mailpit-notify
mailpit-notify: ## Reset Mailpit and capture demo emails from the latest fired close
	$(COMPOSE) run --rm notifier

.PHONY: test
test: test-engine test-backend test-frontend ## Run every test suite

.PHONY: test-engine
test-engine: ## Run scoring engine tests
	uv run --package xray-engine pytest engine/tests

.PHONY: test-backend
test-backend: ## Run API tests
	uv run --package quantum-churros-api pytest backend/tests

.PHONY: test-frontend
test-frontend: ## Type-check and build the production frontend
	cd frontend && bun run check && bun run test

.PHONY: test-engine-data
test-engine-data: ## Run the engine tests that need the real dataset (XRAY_DATA=<folder>)
	XRAY_DATA=$(XRAY_DATA) uv run --package xray-engine pytest engine/tests -m dataset

.PHONY: fit-reference
fit-reference: ## Measure and freeze params/reference_v1.json from XRAY_DATA
	uv run --package xray-engine xray-score fit-reference $(XRAY_DATA) --out params/reference_v1.json

.PHONY: predict
predict: ## Score every group and company of XRAY_DATA (any folder with the 8 CSVs) into XRAY_OUT
	uv run --package xray-engine xray-score predict $(XRAY_DATA) --out $(XRAY_OUT)

.PHONY: score
score: predict ## Alias of predict

.PHONY: validate
validate: ## Run the label-free validation suite and write XRAY_OUT/validation.json
	uv run --package xray-engine xray-score validate $(XRAY_DATA) --out $(XRAY_OUT)/validation.json

# ---------------------------------------------------------------------------
# Fase A — evaluación del motor (docs/engine/EVALUATION.md)
# ---------------------------------------------------------------------------

.PHONY: eval-reconcile-tests
eval-reconcile-tests: ## 1a. Tests conciliación (io, cleaning, invoice as-of) sin Docker
	uv run --package xray-engine pytest engine/tests/test_io.py engine/tests/test_cleaning.py engine/tests/test_invoices_as_of.py -q -m "not dataset"

.PHONY: eval-reconcile-docker
eval-reconcile-docker: up db-seed-dry-run db-seed eval-reconcile-tests ## 1b. Ingesta PostgreSQL + tests conciliación

.PHONY: eval-validate
eval-validate: validate ## 2–3. Validación completa → validation.json (P2,P4,R6,scoring,KPIs)

.PHONY: eval-snapshot
eval-snapshot: kpi-snapshot ## Append fila a docs/engine/KPI_HISTORY.md

.PHONY: eval-report
eval-report: ## Imprime resumen legible desde validation.json
	@uv run --package xray-engine python scripts/print_eval_report.py $(XRAY_OUT)/validation.json

.PHONY: eval-injection
eval-injection: ## Tutorial del estudio de inyección con resultados y puntos de mejora
	@uv run --package xray-engine python scripts/print_injection_report.py $(XRAY_OUT)/validation.json

.PHONY: eval-phase-a
eval-phase-a: eval-reconcile-tests eval-validate eval-snapshot eval-report ## Fase A local (CSV): conciliación→validación→KPIs→informe

.PHONY: eval-phase-a-docker
eval-phase-a-docker: eval-reconcile-docker eval-validate eval-snapshot eval-report ## Fase A con db-seed (Docker)

.PHONY: kpi-snapshot
kpi-snapshot: ## Append KPI row from validation.json to docs/engine/KPI_HISTORY.md
	uv run --package xray-engine xray-score kpi-snapshot --validation $(XRAY_OUT)/validation.json

.PHONY: daily-reconcile
daily-reconcile: eval-reconcile-docker ## Alias: ingesta + tests conciliación

.PHONY: daily-core
daily-core: eval-phase-a ## Alias: Fase A local completa

.PHONY: daily-core-docker
daily-core-docker: eval-phase-a-docker ## Alias: Fase A con PostgreSQL

.PHONY: export
export: ## Score XRAY_DATA and write the static JSON bundle to XRAY_BUNDLE (EVIDENCE_MONTHS of evidence per entity)
	uv run --package xray-engine xray-score predict $(XRAY_DATA) --out $(XRAY_OUT) --export-dir $(XRAY_BUNDLE) --evidence-months $(EVIDENCE_MONTHS)

.PHONY: db-migrate
db-migrate: ## Apply pending Alembic migrations
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api alembic -c backend/alembic.ini upgrade head

.PHONY: db-seed-dry-run
db-seed-dry-run: ## Validate source files and print their immutable dataset hash
	uv run --package quantum-churros-api xray-db ingest data/raw --dry-run

.PHONY: db-seed
db-seed: ## Idempotently ingest the challenge dataset into PostgreSQL
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api xray-db ingest /data/raw

.PHONY: db-publish
db-publish: ## Load the engine run in XRAY_OUT (panel, scores, alerts) into the xray schema, one attribute per column
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api xray-db publish $(XRAY_OUT)

.PHONY: db-classify
db-classify: ## Classify companies into industry archetypes for the mounted dataset
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api xray-db classify /data/raw

.PHONY: db-sync
db-sync: ## Start PostgreSQL and synchronize source data, scores, database projections, and the frontend bundle
	$(COMPOSE) up --build -d --wait postgres api
	$(COMPOSE) exec api uv run --locked --package quantum-churros-api xray-db sync /data/raw --out-dir /app/artifacts --bundle-dir /app/bundle --evidence-months $(EVIDENCE_MONTHS)

.PHONY: data-extract
data-extract: ## Extract the local challenge archive into the ignored data directory
	unzip -j -n "$(archive)" 'output/*' -d data/raw

NO_MOCKS_PATTERN := COMP_0680|Velasco|4,1 meses|74\.5|[Cc]at[Bb]oost|SHAP

.PHONY: no-mocks
no-mocks: ## Fail when demo literals or retired model copy remain in shipped code
	@if rg -n '$(NO_MOCKS_PATTERN)' frontend/src backend/app; then \
		echo 'no-mocks: demo literals found in shipped code (listed above)'; exit 1; \
	else \
		echo 'no-mocks: clean'; \
	fi

.PHONY: help
help: ## Show available targets
	@rg '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST)
